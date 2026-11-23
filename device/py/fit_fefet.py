"""Fit the FeFET-level parameters of sets B and C with the offline reduced FeFET model
(fefet_ref.FeFETReduced) and write them to device/params/set<B|C>.json.

Set B: only the channel vth0 is fitted, so that the mean of the two thresholds after
       +-4.5 V / 10 us (2 s wait) equals the mean of T5 (-0.01 and 0.73 V). The film kinetics
       stay as fitted to the capacitor data (fit_setB.py); the FeFET table T4 is a check.
Set C: tau_inf, alpha, median E_a, sigma_ln and P_S are least-squares fitted (three start points)
       to the Ni 2019 targets:
       MW(+-4 V, 10 us) = 1.03 V and the iso-MW points of SI Fig. 1 (MW = 1.0 V and 0.2 V lines),
       with eps_r = 30, beta = 1, V_imp = 0 held fixed (no data for them);
       A third term is target C6 of docs/lit/device_models.md §4.3 (no switching at |V_G| <= 1-1.5 V
       for 1e5 s): the high-V_th state held at +1.1 V (the search-line level) for 1e5 s.
       vth0 is then set so the mean threshold is (0.65 + 1.68)/2.
All thresholds are read with the same gate ramps as the SPICE decks, so read disturb is included.
Needs the MOS tables in sim/out/mos/ made from the CURRENT library: run scripts/gen_fefet_lib.py, then
device/tb/mos_table.cir, then this script. The vth0 shift is relative to the table.

Run: scripts/run_guarded.sh <python> device/py/fit_fefet.py --set C [--write]
"""
import argparse
import time

import numpy as np
from scipy.optimize import least_squares

import fefet_ref as fr

RTOL_FIT = 1e-4
WAIT = 2.0

# Ni 2019 SI Fig. 1 iso-MW points (gate amplitude V, pulse width s, MW V), docs/lit/device_models.md §4.1
ISO_MW = [(4.00, 1e-7, 1.0), (3.86, 5e-7, 1.0), (3.77, 1e-6, 1.0), (3.66, 1e-5, 1.0), (3.30, 1e-4, 1.0),
          (3.38, 5e-8, 0.2), (2.82, 1e-6, 0.2), (2.60, 1e-5, 0.2), (2.50, 1e-3, 0.2), (2.18, 1e-2, 0.2)]
C_VTH_LOW, C_VTH_HIGH = 0.65, 1.68
B_VTH_LOW, B_VTH_HIGH = -0.01, 0.73


def i_crit(p):
    f = p["fefet"]
    if p["name"] == "B":
        return 1e-7 * f["W_m"] / 1e-6          # 1e-7 A per um of width
    return 1e-7 * f["W_m"] / f["L_m"]          # 1e-7 A * W/L


READ = {"b": (-1.2, 1.8), "c": (-0.2, 2.4)}   # gate ramps of the SPICE reads (device/tb/make_fefet_mw.py)
C6_V, C6_T = 1.1, 1e5                        # C6: search-level gate voltage held for 1e5 s


class Model:
    def __init__(self, p, card, dv):
        self.p, self.mos, self.ic, self.read = p, fr.MosTable(card, dv), i_crit(p), READ[card]

    def make(self):
        m = fr.FeFETReduced(self.p, self.mos, self.ic)
        m.run = _loose(m.run)
        return m

    def vth_pair(self, amp, width):
        return fr.mw_protocol(self.make, amp, width, WAIT, read=self.read)

    def c6_shift(self):
        """High-V_th state (after +-4 V / 10 us) held at +C6_V for C6_T s: V_th change (V)."""
        m = self.make()
        m.pulse(+4.0, 1e-5)
        m.wait(WAIT)
        m.pulse(-4.0, 1e-5)
        m.wait(WAIT)
        v0 = m.read_ramp(*self.read)
        m.run([0, 5e-9, C6_T, C6_T + 5e-9], [0, C6_V, C6_V, 0])
        m.wait(WAIT)
        return m.read_ramp(*self.read) - v0


def _loose(run):
    def wrapped(seg_t, seg_v, rtol=RTOL_FIT, **kw):
        return run(seg_t, seg_v, rtol=max(rtol, RTOL_FIT), **kw)
    return wrapped


def fit_dv(p, card, amp, width, target_mean):
    """Shift vth0 until the mean threshold hits target_mean (secant method). The slope is not 1:
    with the neutral start (node m at 0 V when P = 0) a vth0 change also moves the start charge."""
    def mean_err(dv):
        lo, hi = Model(p, card, dv).vth_pair(amp, width)
        return 0.5 * (lo + hi) - target_mean, lo, hi

    d0 = 0.0
    e0, lo, hi = mean_err(d0)
    d1 = -e0
    e1, lo, hi = mean_err(d1)
    for _ in range(8):
        if abs(e1) < 1e-3 or e1 == e0:
            break
        d0, e0, d1 = d1, e1, d1 - e1 * (d1 - d0) / (e1 - e0)
        e1, lo, hi = mean_err(d1)
    return d1, lo, hi


def unpack_c(theta, base):
    p = dict(base)
    p["dist"] = dict(base["dist"])
    p["tau_inf_s"] = 10 ** theta[0]
    p["alpha"] = theta[1]
    p["dist"]["median_MV_per_cm"] = theta[2]
    p["dist"]["sigma_ln"] = theta[3]
    p["P_S_C_per_m2"] = theta[4] / 100
    return p


def residuals_c(theta, base, dv):
    p = unpack_c(theta, base)
    m = Model(p, "c", dv)
    res = []
    for amp, width, mw in ISO_MW:
        lo, hi = m.vth_pair(amp, width)
        res.append((hi - lo) - mw)
    lo, hi = m.vth_pair(4.0, 1e-5)
    res.append(5.0 * ((hi - lo) - (C_VTH_HIGH - C_VTH_LOW)))   # main target (the TCAM states), weight 5
    res.append(2.0 * m.c6_shift())                             # C6: a 50 mV shift costs like 0.1 V of MW
    return np.array(res)


def run_c(write):
    base = fr.load_set("C")
    dv = 0.0   # relative to the vth0 the MOS table was made with
    t0 = time.time()
    starts = [[-8.83, 3.16, 3.02, 0.10, 2.0], [-10.0, 4.0, 3.5, 0.15, 1.5]]
    r = None
    for theta0 in starts:
        ri = least_squares(residuals_c, theta0, args=(base, dv), diff_step=1e-2,
                           x_scale=[1, 0.5, 0.5, 0.1, 5], max_nfev=40,
                           bounds=([-14, 1.0, 1.0, 0.05, 0.5], [-6, 8.0, 12.0, 1.0, 40.0]))
        print(f"  start {theta0}: cost {ri.cost:.4f} at {np.round(ri.x, 3)}", flush=True)
        if r is None or ri.cost < r.cost:
            r = ri
    p = unpack_c(r.x, base)
    target_mean = 0.5 * (C_VTH_LOW + C_VTH_HIGH)
    dv, lo, hi = fit_dv(p, "c", 4.0, 1e-5, target_mean)
    res = residuals_c(r.x, base, dv)
    print(f"set C fit ({time.time()-t0:.0f} s): tau_inf {p['tau_inf_s']:.3e} s, "
          f"alpha {p['alpha']:.3f}, E_a median {p['dist']['median_MV_per_cm']:.3f} MV/cm, "
          f"sigma_ln {p['dist']['sigma_ln']:.3f}, P_S {p['P_S_C_per_m2']*100:.2f} uC/cm^2, "
          f"vth0 shift {dv:+.3f} V")
    print(f"  +-4 V / 10 us: Vth low {lo:.3f}, high {hi:.3f}, MW {hi-lo:.3f} V")
    for (amp, width, mw), e in zip(ISO_MW, res[:-2]):
        print(f"  iso-MW {mw:.1f} V at {amp:.2f} V / {width:.0e} s: model MW {mw+e:.3f}")
    print(f"  C6: high-V_th shift after {C6_T:.0e} s at +{C6_V} V: {res[-1]/2*1000:+.1f} mV")
    if write:
        out = fr.load_set("C")
        out["tau_inf_s"] = float(f"{p['tau_inf_s']:.5g}")
        out["alpha"] = round(float(p["alpha"]), 4)
        out["dist"]["median_MV_per_cm"] = round(float(p["dist"]["median_MV_per_cm"]), 4)
        out["dist"]["sigma_ln"] = round(float(p["dist"]["sigma_ln"]), 4)
        out["P_S_C_per_m2"] = round(float(p["P_S_C_per_m2"]), 5)
        out["fefet"]["card"]["vth0"] = round(out["fefet"]["card"]["vth0"] + float(dv), 4)
        out["what"] = ("28 nm-class TCAM FeFET: 8 nm doped HfO2 on 1 nm SiO2 (Ni et al. Nat. Electron. 2019 SI; "
                       "Yin 2024). Kinetics and vth0 fitted to the Ni 2019 targets by device/py/fit_fefet.py.")
        fr.save_set(out)
        print("wrote device/params/setC.json")


def run_b(write):
    p = fr.load_set("B")
    dv, lo, hi = fit_dv(p, "b", 4.5, 1e-5, 0.5 * (B_VTH_LOW + B_VTH_HIGH))
    print(f"set B: vth0 shift {dv:+.3f} V -> Vth low {lo:.3f}, high {hi:.3f}, MW {hi-lo:.3f} V at +-4.5 V / 10 us")
    if write:
        p["fefet"]["card"]["vth0"] = round(p["fefet"]["card"]["vth0"] + float(dv), 4)
        fr.save_set(p)
        print("wrote device/params/setB.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["B", "C"], required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    (run_b if args.set == "B" else run_c)(args.write)


if __name__ == "__main__":
    main()
