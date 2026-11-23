"""B1 faithful to Yin et al. 2024 ("B1_yin"), as a priced harness machine. The earlier harness B1 (shared parallel-trial core +
golden MESA arms) is kept unchanged and is called "B1_ours_mesa" in BASELINES_V2 for continuity.

Algorithm (Yin, Nat. Commun. 15:2419, Results "MESA"; docs/hw/lit/yin2024_supp.md):
  * one proposal per iteration: flip m distinct uniformly drawn bits, m uniform in {1, 2, 3} ("a few bits");
  * the proposal's energy comes from ONE CiM read of the whole tiled array (x^T Q y in a single read cycle, SI Sec. 3);
    Metropolis acceptance on the exact dE (the read is exact at sigma = 0, P4.01 test_tiled_field_exact_at_sigma0);
  * no parallel trial, no select tree;
  * arm "sa": conventional SA, geometric T0 -> T_end over a fraction f of the run (f = 1 or 0.5, the same schedule knob and
    the same continued cooling as ours' "none" arm), single epoch;
  * arm "mesa": MESA v2 rules (yin_mesa.py): epochs start at the best state so far, T := T0, geometric cooling to T_end over
    E sweeps then held; the trap counter (no new epoch-best) runs only after cooling; at Count_max the epoch ends.
Kernel: numba, exact integer dE; per-iteration statistics are accumulated at the record checkpoints so that the golden
counter fields (counters.FIELDS) can be rebuilt exactly and priced by the unchanged pricing.price (kind "b1", native cells).

Counter model per iteration (SPEC_v0 cycle rule without the select stage): cycles = 3 + cim_array_lat + adc bits; one array
read; adds = 2 (dE compare) + shift/tile adds (added by b1_native_counts); rng draws = 1 (m) + m (indices) + 1 (accept);
lut reads 1; reg writes = step 1 + T 1 (+ m x + 1 f + 1 E per accepted proposal; + n + 3 per epoch reload; + 1 per best update).
"""
from __future__ import annotations

import dataclasses
import math
import sys
from pathlib import Path

import numba as nb
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE, REPO / "scripts" / "golden", REPO / "scripts" / "testing", REPO):
    sys.path.insert(0, str(p))

import yin_mesa as b1  # noqa: E402
from counters import FIELDS, CycleCfg  # noqa: E402

KICK_MAX = 3
EPOCH_SWEEPS = b1.MESA2_EPOCH_SWEEPS
ARMS = ("sa", "mesa")
# per-checkpoint statistics columns
S_ITERS, S_ACC, S_ACCBITS, S_EPOCHS, S_BESTUPD, S_DRAWBITS = range(6)


@nb.njit(cache=True)
def _seed(seed):
    np.random.seed(seed)


@nb.njit(cache=True)
def _run(d, P, total, T0, Tend, cool_iters, epoch_iters, count_max, mode, checkpoints, kick_max):
    """Returns best_f, best_x, stats (len(checkpoints), 6), best_f at each checkpoint. checkpoints: sorted 1-based iterations."""
    n = d.shape[0]
    x = np.zeros(n, np.int64)
    h = d.copy()
    f = 0
    best_f = 0
    best_x = x.copy()
    idx = np.empty(kick_max, np.int64)
    ratio = Tend / T0
    e = 0
    trap = 0
    epoch_best = 0
    acc = 0
    accbits = 0
    drawbits = 0
    epochs = 0
    bestupd = 0
    K = checkpoints.shape[0]
    stats = np.zeros((K, 6), np.int64)
    bcurve = np.zeros(K, np.int64)
    c = 0
    for t in range(total):
        if mode == 0:
            T = T0 * ratio ** (t / max(cool_iters - 1, 1))
        else:
            T = T0 * ratio ** (min(e, epoch_iters - 1) / max(epoch_iters - 1, 1))
        m = 1 + np.random.randint(kick_max)
        drawbits += m
        k = 0
        while k < m:
            j = np.random.randint(n)
            dup = False
            for a in range(k):
                if idx[a] == j:
                    dup = True
            if not dup:
                idx[k] = j
                k += 1
        df = 0
        for a in range(m):
            i = idx[a]
            si = 1 if x[i] == 0 else -1
            df += si * h[i]
            for b in range(a):
                q = idx[b]
                sq = 1 if x[q] == 0 else -1
                df += si * sq * P[i, q]
        if df >= 0 or np.random.random() < np.exp(df / T):
            for a in range(m):
                i = idx[a]
                s = 1 if x[i] == 0 else -1
                x[i] ^= 1
                for q in range(n):
                    h[q] += s * P[q, i]
            f += df
            acc += 1
            accbits += m
            if f > best_f:
                best_f = f
                best_x[:] = x
                bestupd += 1
        if mode == 1:
            e += 1
            if f > epoch_best:
                epoch_best = f
                trap = 0
            elif e >= epoch_iters:
                trap += 1
            if trap >= count_max:
                x[:] = best_x
                h[:] = d
                for i in range(n):
                    if x[i] == 1:
                        for q in range(n):
                            h[q] += P[q, i]
                f = best_f
                epoch_best = f
                e = 0
                trap = 0
                epochs += 1
        while c < K and checkpoints[c] == t + 1:
            stats[c, 0] = t + 1
            stats[c, 1] = acc
            stats[c, 2] = accbits
            stats[c, 3] = epochs
            stats[c, 4] = bestupd
            stats[c, 5] = drawbits
            bcurve[c] = best_f
            c += 1
    return best_f, best_x, stats, bcurve


@dataclasses.dataclass(frozen=True)
class NativeCfg:
    arm: str                       # "sa" | "mesa"
    t0: float
    t_end: float
    sched_frac: float = 1.0        # sa only
    count_max: int = 0             # mesa only (0 -> 2n)
    epoch_sweeps: int = EPOCH_SWEEPS


def run(d, P, sweeps: float, cfg: NativeCfg, seed: int, checkpoints: np.ndarray):
    n = len(d)
    total = int(round(sweeps * n))
    assert cfg.arm in ARMS and checkpoints[-1] == total and np.all(np.diff(checkpoints) > 0)
    _seed(int(seed) & 0x7FFFFFFF)
    cool = max(2, int(round(total * cfg.sched_frac)))
    return _run(np.asarray(d, np.int64), np.asarray(P, np.int64), total, float(cfg.t0), float(cfg.t_end), cool,
                int(cfg.epoch_sweeps * n), int(cfg.count_max or 2 * n), 0 if cfg.arm == "sa" else 1,
                np.asarray(checkpoints, np.int64), KICK_MAX)


def counters_from(stats_row, n: int, adc_bits: int, cyc: CycleCfg = CycleCfg()) -> dict[str, int]:
    """Golden counter fields after `iters` iterations (module docstring). Tile/shift adds and cell reads are expanded by
    yin_mesa.b1_native_counts from array_reads, exactly as for the harness B1."""
    it, acc, accbits, epochs, bestupd, drawbits = (int(v) for v in stats_row)
    c = dict.fromkeys(FIELDS, 0)
    c["field_reads"] = c["array_reads"] = it
    c["array_cell_reads"] = c["adc_conversions"] = c["adc_conv_bits"] = 0      # filled by b1_native_counts (tiles)
    c["adds"] = 2 * it
    c["rng_draws"] = 2 * it + drawbits
    c["lut_reads"] = it
    c["reg_writes"] = 2 * it + accbits + 2 * acc + epochs * (n + 3) + bestupd
    c["restarts"] = epochs
    c["best_updates"] = bestupd
    c["cycles"] = it * (3 + cyc.cim_array_lat + adc_bits)
    return c


def execute(spec) -> dict:
    """Harness record (machines.drive format) for arm keys 'b1y.sa' / 'b1y.mesa' (cfg: pct_hi, pct_lo, knob)."""
    import machines as M
    import plan as pl
    import pricing as pr
    import smoke_all as sa
    from cost_model import CostModel
    arm = spec.arm.split(".")[1]
    cfg = spec.cfg
    mq = M.mapped(spec.family, spec.instance)
    qz = M.quantised(spec.family, spec.instance, "b1")
    d, P = -np.asarray(qz.d, np.int64), -np.asarray(qz.P, np.int64)
    n = len(d)
    t_hi, t_lo = M._temps_cached(spec.family, spec.instance, "b1", cfg["pct_hi"], cfg["pct_lo"])
    steps = int(round(spec.sweeps * mq.spins))
    grid = sorted({max(1, round(steps * (i + 1) / pl.N_CHECKPOINTS)) for i in range(pl.N_CHECKPOINTS)})
    fine = sorted({max(1, round(steps * (i + 1) / M.GRID_POINTS)) for i in range(M.GRID_POINTS)} | set(grid))
    ncfg = NativeCfg(arm, t_hi, t_lo, sched_frac=cfg["knob"] if arm == "sa" else 1.0,
                     count_max=max(1, int(round(cfg["knob"] * n))) if arm == "mesa" else 0,
                     epoch_sweeps=int(cfg.get("epoch_sweeps", EPOCH_SWEEPS)))
    seed = M.seed_of(spec)
    best_f, best_x, stats, bcurve = run(d, P, spec.sweeps * mq.spins / n, ncfg, seed, np.asarray(fine))
    scale1 = qz.scale == 1.0
    energy = (lambda bf: float(-bf + mq.offset)) if scale1 else None
    curve = [energy(b) for b in bcurve] if scale1 else [float("nan")] * len(fine)
    final_E = float(mq.energy(best_x[:mq.spins]))
    if not scale1:
        curve[-1] = final_E
    blocks = b1.tile_counts(n)["blocks"]
    adc_fs = pr.b1_native_fs_bits(np.asarray(qz.P), b1.TILE)
    desc = {"kind": "b1", "restart": "mesa" if arm == "mesa" else "none", "n_pad": n, "n_act": n, "tweak": "",
            "offset_rate": 0, "scale": qz.scale, "w_bits": 3, "adc_bits": 8, "adc_fs": True, "adc_bits_fs": adc_fs,
            "native": "yin", "move": "m in {1,2,3} bits, single trial"}
    pos = {t: k for k, t in enumerate(fine)}
    snaps = []
    for t in grid:
        k = pos[t]
        snaps.append({"t": t, "c": counters_from(stats[k], n, 8), "c_ns": None, "flips": int(stats[k, S_ACCBITS]),
                      "best_E": curve[k]})
    cost = CostModel()
    c_end = snaps[-1]["c"]
    p = pr.price(desc, c_end, steps, int(stats[-1, S_ACCBITS]), cost)
    prog = sa.native_levels_program(cost, np.asarray(qz.P), blocks, b1.TILE, spec.verify_l0)
    return {"desc": desc, "steps": steps, "mapped_sha256": mq.sha256()[:16], "seed": seed, "curve": curve, "curve_t": fine,
            "snaps": snaps, "best_E": final_E, "best_t": int(fine[int(np.argmax(np.asarray(bcurve) >= best_f))]),
            "flips": int(stats[-1, S_ACCBITS]), "wall_s": 0.0, "restarts": int(stats[-1, S_EPOCHS]), "array_writes": 0,
            "skipped_reads": 0, "prog": prog, "power_mode": "fs",
            "price": {"e_total": p["e_total"], "blocks": p["blocks"], "time_ns": p["time_ns"], "a_total": p["a_total"],
                      "area": p["area"], "tiles": p["tiles"]},
            "spec": dataclasses.asdict(spec)}


def grid(arm: str) -> list[dict]:
    """P4_v2 s.5 equal rule: 4 shared percentile pairs x 2 knob values (sa: schedule fraction {1, 0.5}; mesa: Count_max {n, 2n})."""
    import plan as pl
    knobs = pl.SCHED_FRAC if arm == "sa" else pl.STALL_K_MULT
    return [dict(cid=f"b1y{arm}_p{hi}_{lo}_k{k:g}", pct_hi=hi, pct_lo=lo, knob=float(k), sched="", pswap=0)
            for hi, lo in pl.PCT_PAIRS for k in knobs]
