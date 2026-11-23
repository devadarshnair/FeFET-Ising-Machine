"""Simulation core of the testing-phase runner: build one machine (ours / B1 / B1 bit-sliced / B3 / B2) for one Spec, drive it
step by step and return a raw per-run record (best-so-far curve, cumulative counter snapshots, priced totals).

Sign convention (checked by tests/hw/test_testing_runner.py): the golden machine MAXIMISES f = d.x + x.P.x/2, the mapped QUBO
(scripts/problems/load.py) is a MINIMISATION form (Max-Cut f = -cut). The machines are therefore fed (-d, -P) and the energy of
a machine state is E = -best_f + offset (exact original-unit energy is recomputed when the integers had to be scaled to fit).
Baseline modules are imported unchanged.
"""
from __future__ import annotations

import dataclasses
import functools
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan as pl  # noqa: E402
import pricing as pr  # noqa: E402
from fastcim import FastCimField  # noqa: E402

REPO = pr.REPO
import fujitsu_da as b3  # noqa: E402
import hycim as hc  # noqa: E402
import hycim_b2 as hb2  # noqa: E402
import instances as gi  # noqa: E402
import yin_mesa as b1  # noqa: E402
from cim_field import CimCfg, max_column_sum, max_tile_column_sum  # noqa: E402
from cost_model import CostModel  # noqa: E402
from counters import CycleCfg  # noqa: E402
from power import PowerCfg  # noqa: E402
from restart import RestartCfg, RestartUnit  # noqa: E402
from tim_golden import Machine  # noqa: E402
from tweaks import TweakCfg  # noqa: E402

from scripts.problems import load as ld  # noqa: E402
from scripts.problems import maxcut as mcut  # noqa: E402
from scripts.problems import spin_table as st  # noqa: E402

GRID_POINTS = 400            # best-so-far curve points per run; snapshots every GRID_POINTS // N_CHECKPOINTS points
T_SAMPLES = 32               # percentile rule samples (calib_b1.temperatures)
SEED_TAG = 20261115


# ---------------------------------------------------------------------------------------------------------- instances
@functools.lru_cache(maxsize=None)
def mapped(family: str, key: str) -> ld.MappedQubo:
    if family == "maxcut":
        import mc_fresh
        if mc_fresh.is_fresh(key):                         # MC-1: fresh G-set-like graphs R<seed>
            return mc_fresh.mapped(key)
        return ld.load_maxcut(key)
    if family == "maxsat":
        return ld.from_problem("maxsat", st.random_ksat(60, round(4.26 * 60), 3, seed=int(key)), 60)
    if family == "colouring":
        return ld.from_problem("colouring", st.random_colouring(12, 0.3, 3, seed=int(key)), 12)
    if family in ("col3p", "col4p"):                       # H6 planted colouring (optimum 0 by construction)
        import h6_instances as h6i
        cp = h6i.problem(family, key)
        return ld.from_problem("colouring", cp, cp.n)
    if family in ("vmc120", "vmc240"):                    # VARIATION_V2 smoke: small Max-Cut, G(n, 4n) unit weights
        return ld.from_problem("maxcut", mcut.random_graph(int(family[3:]), 4 * int(family[3:]), 7000 + int(key)), int(family[3:]))
    import h8_instances as h8i
    if family in h8i.FAMILIES_COLOURING:                   # H8 full study: ladder 120..2040 spins, generated DIMACS-style graphs
        cp = h8i.problem(family, key)
        return ld.from_problem("colouring", cp, cp.n)
    import h7_instances as h7i
    if family in h7i.PLANTED or family == "dimacs":        # H7 planted families at 240/480/960 spins, DIMACS-construction graphs
        cp = h7i.problem(family, key)
        return ld.from_problem("colouring", cp, cp.n)
    raise ValueError(family)


@functools.lru_cache(maxsize=None)
def quantised(family: str, key: str, machine: str):
    return ld.quantise(mapped(family, key), ld.QUANT[machine])


def bks_cut(key: str) -> int | None:
    import mc_fresh
    if mc_fresh.is_fresh(key):                             # MC-1: best-found reference (no BKS for a fresh graph)
        return mc_fresh.reference(key)
    return mcut.best_known(key)


def colouring_optimum(key: str) -> int:
    """Exact optimum of the colouring energy over all 3^12 valid colourings (enumeration, H2 section 5); energy of a valid
    colouring = its number of monochromatic edges (the one-hot penalty is 0)."""
    sp = st.random_colouring(12, 0.3, 3, seed=int(key))
    n, k = sp.n, sp.k
    grids = np.indices((k,) * n, dtype=np.int8).reshape(n, -1)
    conf = np.zeros(grids.shape[1], np.int32)
    for u, v in sp.edges:
        conf += grids[u] == grids[v]
    return int(conf.min())


def seed_of(spec: pl.Spec) -> int:
    return gi.mix_seed(pl.BASE_SEED, pl.FAMILY_ID[spec.family], spec.inst_index, spec.r, spec.tag)


def temperatures(d: np.ndarray, P: np.ndarray, tag: int, hi: int, lo: int) -> tuple[float, float]:
    """Aramon App. A / P4.02 rule: T_start = hi-th, T_end = lo-th percentile of nonzero single-flip |dE| over random states."""
    rng = np.random.default_rng([SEED_TAG, 99, tag])
    dE = []
    for _ in range(T_SAMPLES):
        x = rng.integers(0, 2, len(d))
        dE.append(np.abs(d + P @ x))
    dE = np.concatenate(dE)
    dE = dE[dE > 0]
    return float(np.percentile(dE, hi)), float(np.percentile(dE, lo))


@functools.lru_cache(maxsize=None)
def _temps_cached(family: str, key: str, machine: str, hi: int, lo: int):
    qz = quantised(family, key, machine)
    return temperatures(qz.d, qz.P, sum(map(ord, family + key)), hi, lo)


# ---------------------------------------------------------------------------------------------------------- perturbation
class PerturbedCim:
    """Wraps the machine's CiM field with the H5 effects, identically for ours and B1 (same logical draw, machine-specific
    amplitude from its own coupling bits): static per-entry weight error (device sigma, level-0 spread, write band), static
    per-lane ADC offset (mismatch), uniform read-gain (drift, temperature, supply). Dynamic read noise is the machine's own
    sigma knob. Also records the energy error implied by each readout (eta = x.(h_used - h_exact)/2) for the false-stall count."""

    def __init__(self, inner, machine, pert: pl.Perturb, seed_parts: tuple, n_act: int, w_bits: int, sign_magnitude: bool = False):
        self.inner, self.m, self.n_act = inner, machine, n_act
        self.last_eta = 0.0
        P = np.asarray(machine.inst.P)[:n_act, :n_act]
        planes = np.arange(w_bits)
        s0 = (pl.LEVEL0_SIGMA_UNVERIFIED if pert.l0_measured else pl.LEVEL0_SIGMA_VERIFIED) * pert.dev
        s1 = math.sqrt((pert.dev * pl.LEVEL7_REL_SIGMA) ** 2 + (pert.write * pl.WRITE_BAND / math.sqrt(3.0)) ** 2)
        if pert.ideal:
            s0 = s1 = 0.0
        var = np.zeros(P.shape)
        for p in planes:
            bp = (np.maximum(P, 0) >> p) & 1
            bn = (np.maximum(-P, 0) >> p) & 1
            if sign_magnitude:       # T7: one cell per magnitude bit (the other polarity has none), sign applied digitally
                var += 4.0 ** p * np.where(bp + bn == 1, s1 ** 2, s0 ** 2)
            else:                    # differential pair: both polarity arrays hold a cell per bit, the unused one at level 0
                var += 4.0 ** p * (np.where(bp == 1, s1 ** 2, s0 ** 2) + np.where(bn == 1, s1 ** 2, s0 ** 2))
        rng = np.random.default_rng([*seed_parts, 55])
        eps = rng.standard_normal(P.shape)
        self.dP = eps * np.sqrt(var)
        lane_off = rng.standard_normal(n_act) * pert.mismatch * (0 if pert.ideal else 1) * pl.MISMATCH_OFFSET_LSB \
            * math.sqrt((1.0 if sign_magnitude else 2.0) * float((4.0 ** planes).sum()))
        self.lane_off = lane_off
        self.gain = pert.supply * (1.0 - pert.drift_v_dec * pl.DRIFT_DECADES / pl.MW_V) * (1.0 + pl.TEMPCO_GAIN * (pert.temp_c - 25.0))
        self.xprev = np.zeros(n_act, np.int64)
        self.dh = np.zeros(n_act)

    def __getattr__(self, name):                 # delegate cfg, adc_bits, set_bits, pos, neg, ...
        return getattr(self.inner, name)

    def field(self, x):
        h = self.inner.field(x)
        d = self.inner.d
        xa = x[:self.n_act]
        for k in np.flatnonzero(xa != self.xprev):
            self.dh += self.dP[:, k] * (1 if xa[k] else -1)
        self.xprev = xa.copy()
        lsb = getattr(self.inner, "lsb", 1)
        out = h.copy()
        out[:self.n_act] = d[:self.n_act] + np.rint(self.gain * (h[:self.n_act] - d[:self.n_act]) + self.dh + self.lane_off * lsb).astype(np.int64)
        e = out - self.m.h
        self.last_eta = float(x @ e) / 2.0
        return out


class NoisyRestartUnit(RestartUnit):
    """Stall counter on the MEASURED energy (true f + the readout error of this step) for MESA / Kc2, with the false-stall and
    false-reset tracking of H5 section 4. The golden restart.py logic is reproduced unchanged except that "improved" is judged on
    the measured energy and MESA reloads the state it measured as best; at zero readout error it is the golden arm.
    false reset = the counter was reset by a measured improvement the true energy did not show in that step;
    false stall = the counter reached its limit although the true best (MESA: best-so-far, Kc2: epoch best) improved since
    the last counter reset."""

    def __init__(self, cfg, machine):
        super().__init__(cfg, machine)
        self.best_meas = machine.best_f
        self.best_x_meas = machine.best_x.copy()
        self.epoch_meas = machine.f
        self.true_ref = machine.best_f if cfg.arm == "mesa" else machine.f      # running true best (MESA) / epoch best (Kc2)
        self.win_true = self.true_ref
        self.stats = {"stalls": 0, "false_stalls": 0, "resets": 0, "false_resets": 0}

    def after_step(self, m) -> bool:
        mesa = self.cfg.arm == "mesa"
        eta = getattr(m.cim, "last_eta", 0.0)
        fm = m.f + eta
        true_now = m.best_f if mesa else m.f
        true_imp = true_now > self.true_ref
        self.true_ref = max(self.true_ref, true_now)
        if mesa:
            improved = fm > self.best_meas
            if improved:
                self.best_meas, self.best_x_meas = fm, m.x.copy()
        else:
            improved = m.is_feasible() and fm > self.epoch_meas
            if improved:
                self.epoch_meas = fm
        if improved:
            self.stats["resets"] += 1
            self.stats["false_resets"] += not true_imp
            self.win_true = self.true_ref
        self.stall = 0 if improved else self.stall + 1
        self._maybe_burst()
        if self.stall < self.K:
            return False
        self.stats["stalls"] += 1
        self.stats["false_stalls"] += self.true_ref > self.win_true
        self.last_cycles = self.restart_cycles(m)
        if mesa:
            m.load_state(self.best_x_meas)
        else:
            self._kick(m)
            self.epoch_meas = m.f + eta if m.is_feasible() else -(1 << 62)
            self.true_ref = m.f
        if mesa or self.cfg.kc2_reset_sched:
            m.temp = m.inst.t0
            m.eoff = 0
        self.win_true = self.true_ref
        self.stall = 0
        self.events.append(m.t)
        self.event_cycles.append(self.last_cycles)
        return True

    def restart_cycles(self, m) -> int:
        """As the golden unit, except MESA reloads the state it MEASURED as best, so the differing spins are counted against it."""
        if self.cfg.arm == "mesa":
            return 4 * int((m.x != self.best_x_meas).sum()) + 3
        return super().restart_cycles(m)


# ---------------------------------------------------------------------------------------------------------- build
@dataclasses.dataclass
class Built:
    m: Machine
    desc: dict
    qz: object
    mq: ld.MappedQubo
    prog: dict
    nominal_bits: int
    power_mode: str
    pert_wrap: object = None
    t_floor: int = 0            # epoch schedule (H6, P4.02a): temperature register floor


def scaled_temps(temps: tuple[float, float], cfg: dict) -> tuple[float, float]:
    """Stage 1 re-tune knobs (internal review item 9.3.2): |dE| is integer-valued on colouring, so nearby percentiles give the same
    (T_start, T_end) and pct_lo / pct_hi steps are often inert. t_hi_mult / t_lo_mult (default 1 = off) scale the percentile
    temperatures continuously, for every annealing arm (ours, B1, B3) under one rule."""
    hi, lo = temps
    return hi * float(cfg.get("t_hi_mult", 1.0)), lo * float(cfg.get("t_lo_mult", 1.0))


def effective_params(spec) -> dict:
    """The parameters a config actually changes (for the distinct-config check): temperatures after scaling, schedule fraction,
    the B3 final temperature, kick size, stall window, Kc2c T_final."""
    arm = pl.Arm.parse(spec.arm)
    cfg = spec.cfg
    machine = "b1" if arm.machine == "b1bs" else arm.machine
    mq = mapped(spec.family, spec.instance)
    t_hi, t_lo = scaled_temps(_temps_cached(spec.family, spec.instance, machine, cfg["pct_hi"], cfg["pct_lo"]), cfg)
    out = {"t_hi": round(t_hi, 9), "t_lo": round(t_lo, 9)}
    if arm.restart == "none":
        out["sched_frac"] = cfg["knob"]
    if arm.machine == "b3" and arm.restart == "b3v2":
        out = {"t_hi": round(t_hi, 9), "t_final": round(b3.b3v2_t_final(t_hi, t_lo, cfg["knob"]), 9)}
    if arm.restart in ("kc2", "mesa"):
        r = _restart_for(arm.restart, cfg, mq.spins)
        out.update(K=r.K, L=r.L if arm.restart == "kc2" else None, tfinal=cfg.get("tfinal", 1.0))
        if arm.tweak == "i11":                    # I11 is greedy: temperatures and T_final never enter the trajectory
            out = {"K": r.K, "L": r.L}
    return out


def kick_size(cfg: dict, n_act: int) -> int | None:
    """R4: cfg kick_L (fixed) or kick_c (L = max(10, ceil(kick_c * n_act))), capped at n_act - 1; None = RestartCfg default (10)."""
    if cfg.get("kick_c"):
        L = max(10, math.ceil(float(cfg["kick_c"]) * n_act))
    elif cfg.get("kick_L"):
        L = int(cfg["kick_L"])
    else:
        return None
    return min(L, max(1, n_act - 1))


TWEAK_KEYS = ("i11_temp", "i11_tol", "hyb_f", "lahc_len", "cc", "bo_K", "bo_T", "esc_step", "esc_max", "colour_par")      # R10 / R12 cfg overrides of the I11 tweak (default off)


def _restart_for(arm: str, cfg: dict, n_act: int):
    if arm in ("mesa", "kc2", "mesa2"):
        if arm == "mesa2":                         # BASELINES_V2 hook: MESA v2 unit is attached in build (yin_mesa.MesaV2Unit)
            return RestartCfg(arm="mesa", K=max(1, int(round(cfg["knob"] * n_act))))
        kw = {}
        if arm == "kc2":
            L = kick_size(cfg, n_act)
            if L is not None:
                kw["L"] = L
            kw.update(tabu=float(cfg.get("tabu", 0.0)), target=bool(cfg.get("kick_target", False)),
                      adaptive_m=int(cfg.get("adaptive_m", 0)), conflict=bool(cfg.get("kick_conflict", False)))
            if cfg.get("burst_K"):                 # barrier burst; burst_K / burst_len in units of n_act (fractions), burst_up absolute
                kw.update(burst_K=max(1, int(round(float(cfg["burst_K"]) * n_act))), burst_len=max(1, int(round(float(cfg.get("burst_len", 0.05)) * n_act))),
                          burst_up=int(cfg.get("burst_up", 3)))
        return RestartCfg(arm=arm, K=max(1, int(round(cfg["knob"] * n_act))), **kw)
    if arm == "b3v2":                              # BASELINES_V2 hook: offset off (Aramon final setting)
        return RestartCfg(arm="none")
    return RestartCfg(arm="da_offset" if arm == "b3" else arm)


def _instance(spec: pl.Spec, qz, machine: str, steps: int, seed: int, restart: str, cfg: dict, t_lo_hi):
    t_hi, t_lo = t_lo_hi
    if cfg.get("tfinal", 1.0) != 1.0:              # BASELINES_V2 fairness hook: colder schedule end T_end^2 / T_start (= B3 v2 knob)
        assert cfg["tfinal"] == 0.5 and restart not in ("none", "b3v2")
        t_lo = t_lo * t_lo / t_hi
    frac = cfg["knob"] if restart == "none" else 1.0
    d, P, lane = ld._pad_pow2(-qz.d, -qz.P)
    if restart == "da_offset" and machine in ("ours", "b1"):
        deoff = max(1, int(round(t_lo / cfg["knob"])))
    elif machine == "b3" and restart == "b3":
        deoff = max(1, int(round(t_lo / 4))) if cfg["knob"] >= 1.0 else 0
    else:
        deoff = 0
    inst = gi.qubo_instance(d, P, seed=seed, steps=max(2, int(steps * frac)), t_start=t_hi, t_end=t_lo, deoff=deoff)
    n = len(d)
    if qz.d.shape[0] != n:
        inst = dataclasses.replace(inst, lane_en=lane)
    return inst, deoff


FAST_CIM = True        # exact incremental column sums (fastcim.py); False = the parent's full products (tests compare both)


def i7v2_bits(fs: int, adc_delta: int = 0) -> tuple[int, int]:
    """(b_hi, b_lo) of I7v2: b_hi = bitlen(fs) is exact; b_lo = b_hi - 1 gives LSB 2 unless the rounded half scale does not fit
    (fs = 2^b - 2 or 2^b - 1 would give LSB 4); then b_lo = b_hi, so the low-bits error never exceeds one cell (H6 amendment 1)."""
    b_hi = fs.bit_length() + adc_delta
    b_lo = max(1, b_hi - 1)
    return b_hi, (b_hi if ((fs + 1) >> 1) > (1 << b_lo) - 1 else b_lo)


def build(spec: pl.Spec, cost: CostModel, steps: int, mit=None) -> Built:
    """mit: variation_v2.Mitigation (None or model v1 = the unchanged H5 PerturbedCim)."""
    arm = pl.Arm.parse(spec.arm)
    cfg = spec.cfg
    mq = mapped(spec.family, spec.instance)
    seed = seed_of(spec)
    machine = "b1" if arm.machine == "b1bs" else arm.machine
    qz = quantised(spec.family, spec.instance, machine)
    temps = scaled_temps(_temps_cached(spec.family, spec.instance, machine, cfg["pct_hi"], cfg["pct_lo"]), cfg)
    n_act = mq.spins
    inst, deoff = _instance(spec, qz, machine, steps, seed, arm.restart, cfg, temps)
    t_floor = 0
    if cfg.get("epoch_sweeps"):          # H6 MESA harness fix = calib_b1 amendment P4.02a: T0 -> T_end within each epoch, then held
        t_floor = max(1, int(round(inst.t0 * (inst.alpha / gi.TWO32) ** (inst.steps - 1))))
        inst = dataclasses.replace(inst, alpha=gi.alpha_reg(inst.t0, t_floor, int(cfg["epoch_sweeps"]) * n_act))
    n_pad = inst.n
    sig_mult = spec.sigma_mult
    pert = pl.Perturb(**spec.pert) if spec.pert else None
    if pert is not None:
        sig_mult = pert.read * (0 if pert.ideal else 1)
    desc = {"kind": arm.machine, "restart": arm.restart, "n_pad": n_pad, "n_act": n_act, "tweak": arm.tweak,
            "offset_rate": deoff, "scale": qz.scale}
    Pq = np.asarray(qz.P)
    desc["deg_frac"] = float(np.count_nonzero(Pq, axis=1).mean()) / n_pad    # T-6: lanes whose field one flip changes / lanes
    rcfg = _restart_for(arm.restart, cfg, n_act)
    if rcfg.arm in ("kc2", "mesa"):                # R4: the kick / stall settings every record must carry (pricing reads kick_L)
        desc["K"] = rcfg.K
    if rcfg.arm == "kc2":
        desc["kick_L"] = min(rcfg.L, max(n_act - 1, 0))
        if rcfg.tabu:
            desc["tabu"] = rcfg.tabu
        if rcfg.target:
            desc["kick_target"] = True
        for k_, v_ in (("adaptive_m", rcfg.adaptive_m), ("kick_conflict", rcfg.conflict), ("burst_K", rcfg.burst_K),
                       ("burst_len", rcfg.burst_len), ("burst_up", rcfg.burst_up)):
            if v_:
                desc[k_] = v_
    for k in TWEAK_KEYS:
        if cfg.get(k) and arm.tweak == "i11":
            desc[k] = cfg[k]
    if cfg.get("round_even"):
        desc["round_even"] = True
    for k_ in ("sim_incremental", "sim_sparse", "sim_refresh"):    # T-1 / T-2 simulator modes and the T-1 refresh period (priced by arch_t)
        if cfg.get(k_) and arm.machine == "ours":
            desc[k_] = cfg[k_]
    prog = {}
    wrap = None
    power_mode = arm.power
    if arm.machine == "ours":
        wb = max(1, int(np.abs(inst.P).max()).bit_length())
        fs_col = max_column_sum(inst.P, wb)
        v2 = arm.power.startswith("i7v2")
        fsm = arm.power == "fs"
        if v2:                                 # I7v2: ADC full scale = max column sum, exact at b_hi, LSB 2 at b_lo
            b_hi, b_lo = i7v2_bits(fs_col, spec.adc_delta)
        elif fsm:                              # H7 default: full scale = max column sum, simulated (clipping under noise is real)
            b_hi = b_lo = fs_col.bit_length() + spec.adc_delta
        else:
            b_hi = max(4, n_pad.bit_length()) + spec.adc_delta
            b_lo = min(b_hi, max(3, b_hi - 4))
        pw = None
        if arm.power not in ("off", "fs"):
            pw = PowerCfg(i7=arm.power in ("i7", "i7i10", "i7v2", "i7v2i10"), i10=arm.power in ("i10", "i7i10", "i7v2i10"),
                          b_hi=b_hi, b_lo=b_lo, K_p=pl.K_P, K_g=pl.K_G)
        tw = None
        if arm.tweak == "i11":
            tw = TweakCfg(i11=True, **{k: type(getattr(TweakCfg, k))(cfg[k]) for k in TWEAK_KEYS if cfg.get(k)})
        elif arm.tweak.startswith("i5"):
            tw = TweakCfg(i5=True, hold=1 if "h1" in arm.tweak else 4, group=1 if "g1" in arm.tweak else 4)
        sigma = pl.sigma_nominal(n_pad) * sig_mult
        m = Machine(inst, rcfg, cim=CimCfg(adc_bits=b_hi, w_bits=wb, sigma=sigma, seed=seed & 0xFFFFFFFF, fs=fs_col if (v2 or fsm) else 0,
                                          round_even=bool(cfg.get("round_even", False))), power=pw,
                    counters=CycleCfg(), tweaks=tw)
        cells = m.cim.pos.size + m.cim.neg.size
        zeros = int(cells - m.cim.pos.sum() - m.cim.neg.sum())
        if arm.tweak == "sm":                  # T7: half the cells (one per magnitude bit); array/ADC energy rows are NOT re-priced
            cells //= 2
            zeros = int(cells - (m.cim.pos.sum() + m.cim.neg.sum()))
        desc["ones_frac"] = (cells - zeros) / max(cells, 1)                     # T-2: stored fraction under sparse storage
        prog = cost.program_cost(cells, zeros, spec.verify_l0, "bin")
        if FAST_CIM:
            FastCimField.adopt(m.cim)
        desc.update(w_bits=wb, adc_bits=b_hi, fs_col=fs_col, adc_bits_fs=fs_col.bit_length())
        if fsm:                                # B-3: per-tile full scale (exact LSB-1 tile ADC), used only by cost.tile_bits
            desc["adc_bits_tile"] = max_tile_column_sum(inst.P, wb, pr.TILE_ROWS).bit_length() + spec.adc_delta
            desc["adc_bits_tile_rows"] = {str(r): max_tile_column_sum(inst.P, wb, r).bit_length() + spec.adc_delta for r in (64, 128)}  # T-3
        nominal_bits = b_hi
    elif arm.machine in ("b1", "b1bs"):
        sigma = pl.sigma_nominal(b1.TILE) * sig_mult
        bcfg = b1.B1Cfg(count_max=rcfg.K if arm.restart in ("mesa", "kc2", "mesa2") else None, sigma=sigma, seed=seed & 0xFFFFFFFF,
                        adc_bits=8)
        if arm.restart == "mesa2":                 # BASELINES_V2 hook: MESA v2 (epoch cooling, hold, kick), priced as MESA
            m = b1.b1_mesa2_machine(inst, bcfg, temps[1])
            desc["restart"] = "mesa"
            desc["mesa_variant"] = "v2"
        else:
            m = b1.b1_machine(inst, bcfg)
        if arm.restart not in ("mesa", "mesa2"):
            m.restart = RestartUnit(rcfg, m)
            m.deoff = deoff if arm.restart == "da_offset" else 0
        cnt = b1.tile_counts(n_act, bcfg)
        if arm.power == "fs":                  # H7: simulate the fs ADC in every tile (noise above full scale clips); the
            for tf in m.cim.tiles:             # counters keep adc_bits 8, pricing.price re-bits them to the native fs bits
                tf.cfg = dataclasses.replace(tf.cfg, fs=b1_tile_fs(tf))
                tf.set_bits(tf.cfg.fs.bit_length())
        if FAST_CIM:
            for tf in m.cim.tiles:
                FastCimField.adopt(tf)
        if arm.machine == "b1":
            import smoke_all as sa
            prog = sa.native_levels_program(cost, np.asarray(qz.P), cnt["blocks"], b1.TILE, spec.verify_l0)
        else:
            cells = cnt["tiles"] * b1.TILE * b1.TILE
            nonzero = int(sum(tf.pos.sum() + tf.neg.sum() for tf in m.cim.tiles))
            prog = cost.program_cost(cells, cells - nonzero, spec.verify_l0, "bin")
        desc.update(w_bits=3, adc_bits=8)
        if arm.power == "fs":                  # H7 one cost rule: ADC bits = bitlen(max column sum); priced by pricing.price
            desc.update(adc_fs=True, adc_bits_fs=pr.b1_native_fs_bits(np.asarray(qz.P), b1.TILE))
            if arm.machine == "b1bs":          # VARIATION_V2 fix: bit-sliced columns hold 0/1 cells -> fs = max bit-plane tile sum
                desc.update(adc_bits_fs=max(b1_tile_fs(tf) for tf in m.cim.tiles).bit_length())
        wb, nominal_bits = 3, 8
    elif arm.machine == "b3" and arm.restart == "b3v2":     # BASELINES_V2 hook: Aramon lin-beta, T_final knob, offset off
        m = b3.b3_machine(inst, b3.b3v2_cfg(temps[0], temps[1], cfg["knob"]))
        desc["t_final"] = b3.b3v2_t_final(temps[0], temps[1], cfg["knob"])
        wb, nominal_bits = 0, 0
    elif arm.machine == "b3":
        m = b3.b3_machine(inst, b3.B3Cfg(offset_rate=deoff))
        wb, nominal_bits = 0, 0
    else:
        raise ValueError(arm.machine)
    if pert is not None and m.cim is not None and not (spec.pert and spec.pert.get("corner")):
        parts = (pl.BASE_SEED, pl.FAMILY_ID[spec.family], spec.inst_index, spec.r) + ((spec.tag,) if spec.tag else ())
        if mit is not None and mit.model == "v2":     # VARIATION_V2 physical model + mitigations (variation_v2.py)
            import variation_v2 as v2
            wrap = v2.PerturbedCimV2(m.cim, m, pert, parts, n_act, wb, mit, arm.machine,
                                     incremental=bool(cfg.get("sim_incremental")), sparse=bool(cfg.get("sim_sparse")),
                                     refresh=int(cfg.get("sim_refresh", 0)))
            if arm.machine == "ours" and wrap.cf.tile != n_act:
                desc["sim_tile_rows"] = wrap.cf.tile
        else:
            wrap = PerturbedCim(m.cim, m, pert, parts, n_act, wb,
                                sign_magnitude=arm.tweak == "sm")
        wrap.m = m
        m.cim = wrap
        if arm.restart in ("mesa", "kc2"):
            m.restart = NoisyRestartUnit(rcfg, m)
    if t_floor:
        desc["epoch_sweeps"] = cfg["epoch_sweeps"]
    return Built(m, desc, qz, mq, prog, nominal_bits, power_mode, wrap, t_floor)


def b1_tile_fs(tf) -> int:
    """Largest bit-plane column sum of one B1 row tile (cells in a lane x plane x polarity column over the tile's rows), >= 1."""
    return max(1, int(tf.pos.sum(axis=2).max(initial=0)), int(tf.neg.sum(axis=2).max(initial=0)))


# ---------------------------------------------------------------------------------------------------------- drive
def _energy(b: Built, m: Machine) -> float:
    if b.qz.scale == 1.0:
        return float(-m.best_f + b.mq.offset)
    return float(b.mq.energy(m.best_x[:b.mq.spins]))


def drive(spec: pl.Spec, cost: CostModel, mit=None) -> dict:
    steps = int(round(spec.sweeps * mapped(spec.family, spec.instance).spins))
    b = build(spec, cost, steps, mit)
    m, desc = b.m, b.desc
    arm = pl.Arm.parse(spec.arm)
    grid = sorted({max(1, round(steps * (i + 1) / pl.N_CHECKPOINTS * (1.0))) for i in range(pl.N_CHECKPOINTS)})
    fine = sorted({max(1, round(steps * (i + 1) / GRID_POINTS)) for i in range(GRID_POINTS)} | set(grid))
    snap_at, fine_at = set(grid), set(fine)
    curve, snaps = [], []
    acc: dict[str, float] = {}
    track_skips = arm.machine == "ours" and m.power is not None and m.power.cfg.i10
    bits_trace = m.power.bits_trace if m.power is not None else None
    wb = desc.get("w_bits", 0)
    t0 = time.time()
    last_best = m.best_f
    best_t = 0
    for t in range(1, steps + 1):
        m.step()
        if b.t_floor and m.temp < b.t_floor:
            m.temp = b.t_floor
        rec = m.counters.steps.pop()
        if track_skips and rec["skipped_reads"]:
            bits = bits_trace[t - 1] if m.power.cfg.i7 else b.nominal_bits
            for k, v in pr.unskip_delta(rec, bits, desc["n_pad"], wb, b.nominal_bits).items():
                acc[k] = acc.get(k, 0) + v
        if m.best_f != last_best:
            last_best, best_t = m.best_f, t
        if t in fine_at:
            curve.append(_energy(b, m))
        if t in snap_at:
            c = {k: int(v) for k, v in m.counters.total.items()}
            c_ns = {k: c[k] + int(acc.get(k, 0)) for k in c} if track_skips else None
            snaps.append({"t": t, "c": c, "c_ns": c_ns, "flips": int(m.flips), "best_E": curve[-1]})
    wall = time.time() - t0
    c = {k: int(v) for k, v in m.counters.total.items()}
    c_ns = {k: c[k] + int(acc.get(k, 0)) for k in c} if track_skips else None
    final_E = _energy(b, m)
    out = {"desc": desc, "steps": steps, "mapped_sha256": b.mq.sha256()[:16], "seed": seed_of(spec), "curve": curve,
           "curve_t": fine, "snaps": snaps, "best_E": final_E, "best_t": best_t, "flips": int(m.flips), "wall_s": round(wall, 2),
           "restarts": c["restarts"], "array_writes": c["array_writes"], "skipped_reads": c["skipped_reads"],
           "prog": b.prog, "power_mode": b.power_mode}
    p = pr.price(desc, c, steps, int(m.flips), cost)
    out["price"] = {"e_total": p["e_total"], "blocks": p["blocks"], "time_ns": p["time_ns"], "a_total": p["a_total"],
                    "area": p["area"], "tiles": p["tiles"]}
    if c_ns is not None:
        pn = pr.price(desc, c_ns, steps, int(m.flips), cost)
        out["price_noskip"] = {"e_total": pn["e_total"], "blocks": pn["blocks"], "time_ns": pn["time_ns"]}
    if isinstance(m.restart, NoisyRestartUnit):
        out["false_stall"] = dict(m.restart.stats)
    if mit is not None:                      # VARIATION_V2: mitigation label, final counters, V2 programming cost
        import variation_v2 as v2
        out["mit"] = mit.label
        out["counters"] = c
        if hasattr(b.pert_wrap, "prog_stats"):
            out["prog_v2"] = v2.program_cost(b.pert_wrap.prog_stats, mit.wv)
            cfw = getattr(b.pert_wrap, "cf", None)
            if cfw is not None:
                out["spares"], out["zero_cells"] = int(cfw.spares), int(cfw.zero_cells)
    return out


# ---------------------------------------------------------------------------------------------------------- B2 (QKP)
B2_UNIT = 1000           # integer scale of the perturbed effective weights handed to the unchanged hycim kernel


def b2_effective_filter(inst: hc.Inst, pert: pl.Perturb, rng) -> tuple[np.ndarray, float]:
    """Static (device, write-band, level-0) error of the HyCiM filter cells, drawn once per run with the same sigmas as PerturbedCim:
    per-cell current error in unit currents (level>0: dev x level-7 relative sigma and write band, level 0: dev x level-0 sigma),
    summed into effective integer-weight columns wI_j and the effective replica threshold Cref. Filter accepts iff x.wI < Cref
    (ideal cells: x.w <= C). Returns (wI, Cref) in weight units."""
    f = hb2.Filter.build(inst)
    iu = f.cell[1]["i_target_nA"]
    s0 = (pl.LEVEL0_SIGMA_UNVERIFIED if pert.l0_measured else pl.LEVEL0_SIGMA_VERIFIED) * pert.dev
    s1 = math.sqrt((pert.dev * pl.LEVEL7_REL_SIGMA) ** 2 + (pert.write * pl.WRITE_BAND / math.sqrt(3.0)) ** 2)
    if pert.ideal:
        s0 = s1 = 0.0

    def draw(levels):
        err = np.where(levels == 0, s0, s1 * np.maximum(levels, 1)) * rng.standard_normal(levels.shape)   # unit currents
        return levels + err
    wI = draw(f.weight_levels).sum(axis=0)
    cref = draw(f.replica_levels).sum() + 0.5
    return wI, float(cref)


def run_b2_perturbed(inst: hc.Inst, T, x0, y0, seed, pswap, pert: pl.Perturb, rng_pert) -> dict:
    """The unchanged hycim filter kernel stepped one proposal at a time with the perturbed filter (effective integer weights and
    capacity, plus a per-decision read-noise draw on the replica threshold). True feasibility (exact weights) of every visited state
    is tracked outside the kernel, so the reported best profit is the best TRULY feasible profit; false accepts are counted."""
    wI, cref = b2_effective_filter(inst, pert, rng_pert)
    w_eff = np.rint(wI * B2_UNIT).astype(inst.w.dtype)
    read_sigma = 0.0 if pert.ideal else pert.read * pl.LEVEL7_REL_SIGMA * math.sqrt(2.0 * inst.C) * B2_UNIT
    L = T.shape[0]
    rng = np.random.default_rng(seed)
    rng_i = rng.integers(0, inst.n, size=L).astype(np.int64)
    rng_u = rng.random(L)
    rng_j = rng.integers(0, inst.n, size=L).astype(np.int64)
    rng_m = rng.random(L)
    noise = read_sigma * rng_pert.standard_normal(L)
    x, y = x0.copy(), y0.copy()
    off = inst.off
    best = float(inst.profit(x)) if int(inst.w @ x) <= inst.C else -1.0
    rej, bad_steps, prev = 0, 0, x.tobytes()
    for t in range(L):
        c_eff = int(math.floor(cref * B2_UNIT + noise[t] - 1e-9))
        _, r, _, _ = hc._run(hc.A_FILTER, inst.p, off, w_eff, c_eff, T[t:t + 1], x, y, rng_u[t:t + 1], rng_i[t:t + 1], rng_j[t:t + 1],
                             rng_m[t:t + 1], float(pswap), hc.ALPHA, hc.BETA)
        rej += int(r)
        key = x.tobytes()
        if key == prev:
            continue
        prev = key
        if int(inst.w @ x) <= inst.C:
            best = max(best, float(inst.profit(x)))
        elif int(w_eff @ x) <= c_eff:
            bad_steps += 1
    return {"best": best, "rej": rej, "false_accept_states": bad_steps}


def drive_b2(spec: pl.Spec, cost: CostModel) -> dict:
    cfgd = spec.cfg
    inst = hc.load(spec.instance)
    idx = hc.INSTANCES.index(spec.instance)
    sch = pl.B2_SCHEDULES.index(cfgd["sched"])
    L = spec.proposals
    t0 = time.time()
    T = hc.temps(cfgd["sched"], hc.t0_for(inst, "filter", cfgd["sched"], hc.seed_of(idx, 0, sch, 99)), L)
    x0, y0 = hc.initial_state(inst, "filter", hc.seed_of(idx, 0, 0, spec.r))
    seed = hc.seed_of(idx, 0, sch, spec.r, L)
    pswap = hc.PSWAP_V3 if cfgd["pswap"] else 0.0
    extra = {}
    if spec.pert:
        pt = pl.Perturb(**spec.pert)
        res = run_b2_perturbed(inst, T, x0, y0, seed, pswap, pt, np.random.default_rng([pl.BASE_SEED, 4, idx, spec.r, 77]))
        best, rej = res["best"], res["rej"]
        extra = {"false_accept_states": res["false_accept_states"], "pert_point": pt.pid}
    else:
        best, rej, final, _ = hc.run_one(inst, "filter", T, x0, y0, seed, pswap)
    x_typ = hc.feasible_random(inst, np.random.default_rng(hc.seed_of(406, 9)))
    pb = pr.price_b2(spec.instance, L, [int(v) for v in x_typ], spec.verify_l0, cost)
    return {"desc": {"kind": "b2", "restart": "b2", "n_pad": inst.n, "n_act": inst.n, "x_typ": [int(v) for v in x_typ]},
            "steps": L, "best_profit": float(best), "rejected": int(rej), "wall_s": round(time.time() - t0, 2),
            "price": {k: pb[k] for k in ("e_total", "blocks", "time_ns", "a_total", "area", "tiles")},
            "prog": pb["prog"], "restarts": 0, "array_writes": 0, **extra}


# ---------------------------------------------------------------------------------------------------------- software (H7)
def drive_sw(spec: pl.Spec) -> dict:
    """H7 software references on the same colouring instance: sw.dsatur (deterministic), sw.tabucol (spec.cfg['iters_per_vertex'] x n
    iterations), sw.sa (dwave-samplers SA on the same mapped QUBO, spec.sweeps sweeps). Quality only: no hardware price."""
    import sw_colouring as sw
    import h7_instances as h7i
    import h8_instances as h8i
    mq = mapped(spec.family, spec.instance)
    algo = spec.arm.split(".")[1]
    seed = seed_of(spec)
    t0 = time.time()
    if spec.family == "maxcut":                     # H8: the only software reference on G-set is SA on the same QUBO (energy = -cut)
        assert algo == "sa", algo
        r = sw.sa_qubo(mq.d, mq.P, mq.offset, int(spec.sweeps), seed)
        return {"desc": {"kind": "sw", "algo": algo, "n_act": mq.spins}, "restarts": 0, "array_writes": 0, "best_E": float(r["energy"]),
                "steps": int(spec.sweeps) * mq.spins, "wall_s": round(time.time() - t0, 3)}
    cp = h8i.problem(spec.family, spec.instance) if spec.family in h8i.FAMILIES_COLOURING else h7i.problem(spec.family, spec.instance)
    out: dict = {"desc": {"kind": "sw", "algo": algo, "n_act": mq.spins}, "restarts": 0, "array_writes": 0}
    if algo == "dsatur":
        col = sw.dsatur(cp.n, cp.edges)
        used = int(col.max()) + 1
        best = sw.conflicts(cp.edges, sw.fold_to_k(cp.n, cp.edges, col, cp.k))
        out.update(best_E=float(best), colours_used=used, steps=cp.n)
    elif algo == "tabucol":
        iters = int(spec.cfg["iters_per_vertex"] * cp.n)
        r = sw.tabucol(cp.n, cp.edges, cp.k, iters, seed)
        out.update(best_E=float(r["best_conflicts"]), steps=r["iters"], best_t=r["best_iter"], iters_budget=iters)
    elif algo == "sa":
        r = sw.sa_qubo(mq.d, mq.P, mq.offset, int(spec.sweeps), seed)
        assert abs(r["energy"] - mq.energy(r["x"])) < 1e-6, "SA energy does not match the mapped QUBO"
        out.update(best_E=float(r["energy"]), steps=int(spec.sweeps) * mq.spins, feasible=bool(cp.decode(r["x"])["feasible"]))
    else:
        raise ValueError(algo)
    out["wall_s"] = round(time.time() - t0, 3)
    return out


def execute(spec: pl.Spec, cost: CostModel | None = None, mit=None) -> dict:
    cost = cost or CostModel()
    if spec.arm.startswith("sw."):
        rec = drive_sw(spec)
    else:
        rec = drive_b2(spec, cost) if spec.arm.startswith("b2") else drive(spec, cost, mit)
    rec["spec"] = dataclasses.asdict(spec)
    return rec
