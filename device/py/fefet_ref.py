"""Offline reference of the this project v0 FeFET equations (multi-domain kinetic Preisach, NLS rate).

These are the same equations as device/veriloga/fefet_preisach.va and the generated
device/ngspice/fefet_preisach.lib (see docs/device/MODEL_EQUIVALENCE.md). They are used for:
  * analytic references in the test checkers (device/tb/), and
  * fitting parameter sets B and C (device/py/fit_setB.py, fit_setC.py).
The SPICE runs are the tests; this file is a design and cross-check tool.

Units are SI: volts, metres, seconds, C/m^2. Fields in V/m (1 MV/cm = 1e8 V/m).
"""
import json
from pathlib import Path

import numpy as np
from scipy import special, stats
from scipy.integrate import solve_ivp

EPS0 = 8.8541878128e-12
EXP_CAP = 200.0          # cap on (E_a/|E|)^alpha, as in the SPICE model
V_FLOOR = 1e-3           # |V_FE + V_imp| below this is treated as this (rate is ~exp(-200) there)
LOG_FLOOR = 1e-300

REPO = Path(__file__).resolve().parents[2]
PARAM_DIR = REPO / "device" / "params"


def load_set(name):
    """Load parameter set 'A', 'B' or 'C' from device/params/set<name>.json."""
    with open(PARAM_DIR / f"set{name}.json") as f:
        return json.load(f)


def save_set(p):
    with open(PARAM_DIR / f"set{p['name']}.json", "w") as f:
        json.dump(p, f, indent=2)
        f.write("\n")


def activation_quantile(p, u):
    """Activation field E_a (V/m) at cumulative probability u of the set's distribution."""
    d = p["dist"]
    u = np.asarray(u, dtype=float)
    if d["type"] == "gb2":
        z = special.betaincinv(d["p"], d["q"], u)
        return d["b_MV_per_cm"] * 1e8 * (z / (1.0 - z)) ** (1.0 / d["a"])
    if d["type"] == "lognormal":
        return d["median_MV_per_cm"] * 1e8 * np.exp(d["sigma_ln"] * stats.norm.ppf(u))
    raise ValueError(f"unknown distribution {d['type']}")


def activation_fields(p, n=None):
    """Domain activation fields at equal-probability mid-quantiles u_i = (i - 0.5)/N."""
    n = p["N"] if n is None else n
    u = (np.arange(n) + 0.5) / n
    return activation_quantile(p, u)


def rate(v_fe, va, p):
    """NLS switching rate 1/tau (1/s). v_fe = V(g) - V(m) (V); va = E_a * t_FE (V)."""
    v_eff = np.maximum(np.abs(v_fe + p["V_imp_V"]), V_FLOOR)
    expo = np.minimum((va / v_eff) ** p["alpha"], EXP_CAP)
    return np.exp(-expo) / p["tau_inf_s"]


def dxdt(v_fe, x, va, p):
    """Domain-state ODE right-hand side (recipe R3a/R3b in one expression)."""
    v = v_fe + p["V_imp_V"]
    sg = np.sign(v)
    beta = p["beta"]
    r = rate(v_fe, va, p)
    if beta == 1.0:
        return r * (sg - x)
    one_m = 1.0 - sg * x
    hist = np.maximum(-np.log(np.maximum(0.5 * one_m, LOG_FLOOR)), 0.0) + p["h0"]
    return sg * beta * r * one_m * hist ** ((beta - 1.0) / beta)


def switched_fraction_weibull(v_fe, t, va, p):
    """Analytic NLS (P3 eq. 2): fraction switched after time t at constant voltage, from the
    opposite saturated state. No seed."""
    r = rate(v_fe, va, p)
    return 1.0 - np.exp(-(r * t) ** p["beta"])


def switched_fraction_seeded(v_fe, t, va, p):
    """Exact solution of the seeded ODE (R3b with h0): u = (r t + h0^(1/beta))^beta - h0."""
    r = rate(v_fe, va, p)
    b = p["beta"]
    u = (r * t + p["h0"] ** (1.0 / b)) ** b - p["h0"]
    return 1.0 - np.exp(-u)


def p_ensemble_const(v_fe, t, p, n=None):
    """Normalised polarization P/P_S of the N-domain ensemble after time t at constant v_fe,
    starting from -P_S (all domains at -1). Analytic per domain."""
    va = activation_fields(p, n) * p["t_fe_m"]
    s = switched_fraction_seeded(v_fe, np.asarray(t)[..., None], va, p)
    return -1.0 + 2.0 * s.mean(axis=-1)


def p_eq5_continuous(v_fe, t, p, n_grid=20000):
    """P3 eq. (5): continuous integral over the activation-field distribution (mid-point rule
    in probability space with n_grid points). Returns P/P_S."""
    u = (np.arange(n_grid) + 0.5) / n_grid
    va = activation_quantile(p, u) * p["t_fe_m"]
    s = switched_fraction_weibull(v_fe, np.asarray(t)[..., None], va, p)
    return -1.0 + 2.0 * s.mean(axis=-1)


def simulate_fecap(p, wave_t, wave_v, x0=-1.0, t_out=None, n=None, max_step=None):
    """Integrate the N-domain FE capacitor (MFM) under a piecewise-linear voltage waveform.
    Returns (t, V, P/P_S, x[N, len(t)])."""
    va = activation_fields(p, n) * p["t_fe_m"]
    nd = len(va)
    wave_t = np.asarray(wave_t, float)
    wave_v = np.asarray(wave_v, float)

    def rhs(t, x):
        v = np.interp(t, wave_t, wave_v)
        return dxdt(v, x, va, p)

    x = np.full(nd, x0, float) if np.isscalar(x0) else np.asarray(x0, float)
    t_out = np.asarray(t_out if t_out is not None else [], float)
    ts, xs = [], []
    for k in range(len(wave_t) - 1):
        t0, t1 = wave_t[k], wave_t[k + 1]
        if t1 <= t0:
            continue
        inside = t_out[(t_out > t0) & (t_out <= t1)]
        te = np.unique(np.append(inside, t1))
        sol = solve_ivp(rhs, (t0, t1), x, method="Radau", t_eval=te, rtol=1e-7, atol=1e-9,
                        max_step=max_step if max_step else np.inf)
        keep = np.isin(sol.t, inside)
        ts.append(sol.t[keep])
        xs.append(sol.y[:, keep])
        x = sol.y[:, -1]
    t_all = np.concatenate(ts)
    x_all = np.concatenate(xs, axis=1)
    return t_all, np.interp(t_all, wave_t, wave_v), x_all.mean(axis=0), x_all


class MosTable:
    """Gate charge and drain current of the FeFET's internal MOSFET, tabulated by ngspice
    (device/tb/mos_table.cir -> sim/out/mos/mos_dc.txt and mos_q.txt), V_S = V_B = 0:
    gate charge (integral of the gate terminal current; BSIM4's qg output misses the fringing and
    overlap charge) at V_D = 0 (write and wait) and at V_D = 50 mV (read); drain current at 50 mV.
    card = 'b' or 'c'. A shift 'dv' (= change of vth0) moves the curves along the voltage axis."""

    ID_COL = {"b": 1, "c": 2}
    Q_COLS = {"b": (2, 3), "c": (4, 5)}

    def __init__(self, card, dv=0.0, folder=None):
        folder = folder or REPO / "sim" / "out" / "mos"
        dc = np.loadtxt(folder / "mos_dc.txt", skiprows=1)
        qt = np.loadtxt(folder / "mos_q.txt", skiprows=1)
        q0, qr = self.Q_COLS[card]
        self.vg, self.id = dc[:, 0], dc[:, self.ID_COL[card]]
        self.qg = np.interp(self.vg, qt[:, 1], qt[:, q0])
        self.qg_read = np.interp(self.vg, qt[:, 1], qt[:, qr])
        self.dv = dv

    def q(self, vm):
        return np.interp(vm - self.dv, self.vg, self.qg)

    def q_read(self, vm):
        return np.interp(vm - self.dv, self.vg, self.qg_read)

    def vm_at_current(self, i_crit):
        """Internal gate voltage where I_D crosses i_crit (log interpolation)."""
        li = np.log(np.maximum(self.id, 1e-30))
        k = np.argmax(li >= np.log(i_crit))
        f = (np.log(i_crit) - li[k - 1]) / (li[k] - li[k - 1])
        return self.vg[k - 1] + f * (self.vg[k] - self.vg[k - 1]) + self.dv


class FeFETReduced:
    """Quasi-static reduction of the FeFET (FE in series with the MOS gate through node m).

    Charge on the floating node m is conserved: Q_mos(V_m) - C_lin (V_g - V_m) - A P = K,
    with K fixed by the start state (all nodes at 0 V, all domains at x0 = 0, as in the SPICE
    testbenches). The domain states follow dxdt() with V_FE = V_g - V_m.
    """

    def __init__(self, p, mos, i_crit, x0=0.0):
        f = p["fefet"]
        self.p = p
        self.mos = mos
        self.area = f["W_m"] * f["L_m"] * f["r_A"]
        self.c_lin = self.area * EPS0 * p["eps_r"] / p["t_fe_m"]
        self.va = activation_fields(p) * p["t_fe_m"]
        self.i_crit = i_crit
        self.x = np.full(len(self.va), x0, float)
        self.k = self.mos.q(0.0) - self.area * p["P_S_C_per_m2"] * x0
        vm = np.linspace(-8, 8, 4001)
        self._vm = vm
        self._g = self.mos.q(vm) + self.c_lin * vm
        self._g_read = self.mos.q_read(vm) + self.c_lin * vm   # drain at 50 mV during reads

    def vm(self, vg, x, read=False):
        target = self.k + self.c_lin * vg + self.area * self.p["P_S_C_per_m2"] * np.mean(x)
        return np.interp(target, self._g_read if read else self._g, self._vm)

    def _jac_beta1(self, vg, x, read=False):
        """Analytic Jacobian of the domain ODE for beta = 1 (speeds up fitting)."""
        p = self.p
        vm = self.vm(vg, x, read)
        v = vg - vm + p["V_imp_V"]
        av = max(abs(v), V_FLOOR)
        r = rate(vg - vm, self.va, p)
        expo = (self.va / av) ** p["alpha"]
        # d r / d v_fe = r * alpha * expo / |v| * sign(v)   (zero where the exponent is capped)
        dr = np.where(expo < EXP_CAP, r * p["alpha"] * expo / av * np.sign(v), 0.0)
        g = self._g_read if read else self._g
        dgdv = np.interp(vm, self._vm, np.gradient(g, self._vm))
        dvfe_dx = -(self.area * p["P_S_C_per_m2"] / len(x)) / dgdv
        jac = np.outer(dr * (np.sign(v) - x), np.full(len(x), dvfe_dx))
        jac[np.diag_indices_from(jac)] -= r
        return jac

    def run(self, seg_t, seg_v, rtol=1e-6, read=False, events=None):
        """Advance the state through a piecewise-linear gate waveform (absolute times).
        read=True: drain at 50 mV (read charge table). Returns the event times, if any."""
        p = self.p

        def rhs(t, x):
            vg = np.interp(t, seg_t, seg_v)
            return dxdt(vg - self.vm(vg, x, read), x, self.va, p)

        jac = None
        if p["beta"] == 1.0:
            def jac(t, x):
                return self._jac_beta1(np.interp(t, seg_t, seg_v), x, read)

        hits = []
        for k in range(len(seg_t) - 1):
            t0, t1 = seg_t[k], seg_t[k + 1]
            if t1 <= t0:
                continue
            sol = solve_ivp(rhs, (t0, t1), self.x, method="Radau", rtol=rtol, atol=1e-9, jac=jac,
                            events=events)
            self.x = sol.y[:, -1]
            if events is not None:
                hits += list(sol.t_events[0])
        return hits

    def read_ramp(self, lo, hi, ramp=26e-6, rtol=1e-6):
        """Threshold from a gate ramp, as in the SPICE decks: 0 -> lo in 1 us, lo -> hi in
        'ramp', back to 0 in 1 us, drain at 50 mV. Domains may switch during the ramp."""
        vm_star = self.mos.vm_at_current(self.i_crit)
        seg_t, seg_v = [0, 1e-6, 1e-6 + ramp, 2e-6 + ramp], [0, lo, hi, 0]

        def crossing(t, x):
            return self.vm(np.interp(t, seg_t, seg_v), x, True) - vm_star
        crossing.direction = 1
        hits = self.run(seg_t, seg_v, rtol=rtol, read=True, events=crossing)
        hits = [h for h in hits if 1e-6 <= h <= 1e-6 + ramp]
        return float(np.interp(hits[0], seg_t, seg_v)) if hits else float("nan")

    def vth(self):
        """Gate-referred threshold (constant-current criterion) for the present state."""
        vm_star = self.mos.vm_at_current(self.i_crit)
        q_needed = self.mos.q_read(vm_star) - self.k - self.area * self.p["P_S_C_per_m2"] * np.mean(self.x)
        return vm_star + q_needed / self.c_lin

    def pulse(self, amp, width, t_edge=5e-9):
        """One trapezoid gate pulse from 0 V (edges t_edge), local time."""
        self.run([0, t_edge, t_edge + width, 2 * t_edge + width], [0, amp, amp, 0])

    def wait(self, t):
        self.run([0, t], [0, 0])


def mw_protocol(model_factory, amp, width, wait=2.0, read=None, model_out=None):
    """P1-style memory-window protocol from the neutral start: +V (conditioning), wait,
    -V, wait, read (high Vth), +V, wait, read (low Vth). Returns (vth_low, vth_high).
    read=(lo, hi): read with a gate ramp as in the SPICE decks (else the quasi-static vth())."""
    m = model_factory()

    def measure():
        return m.read_ramp(*read) if read else m.vth()
    m.pulse(+amp, width)
    m.wait(wait)
    m.pulse(-amp, width)
    m.wait(wait)
    vth_high = measure()
    if model_out is not None:
        model_out["high"] = m.x.copy()
    m.pulse(+amp, width)
    m.wait(wait)
    vth_low = measure()
    if model_out is not None:
        model_out["low"] = m.x.copy()
    return vth_low, vth_high
