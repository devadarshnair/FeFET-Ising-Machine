"""Shared evaluator code for H2/H3/H5: record loading, targets, per-run arrays, TTS99/ETS99, paired two-level bootstrap and the
registered win/tie/loss rules. Pure functions of the raw records; no scored data is read until an evaluator is pointed at it.

Definitions fixed here (H2 section 5-6):
  success(run, t)  best-so-far energy at step t reaches the target. Max-Cut: cut >= 0.99 x best-known; MaxSAT: best objective found
                   in the reference set R (ref jobs); colouring: exact optimum by enumeration; QKP: profit >= 0.99 x exact optimum.
  p(t)             fraction of pooled runs that succeeded by t;  R99 = ln(0.01)/ln(1-p) (1 if p = 1, inf if p = 0)
  TTS99 / ETS99    min over t of  t x R99(p(t))  /  cumE(t) x R99(p(t)); t = pooled mean machine time, cumE = pooled mean cumulative
                   energy at the 400-point step grid (counters interpolated linearly between the 40 snapshots, then priced).
  gap              (E - E_ref) / max(1, |E_ref|), E_ref = -best-known (Max-Cut) / R best / exact optimum.
  bootstrap        10 000 resamples: instances with replacement, then seeds within each drawn instance (same indices for every arm,
                   so every contrast is paired); pooled TTS/ETS per resample.
  Holm             across the registered contrasts of a family, on the bootstrap p-value of "ratio < 1"; "CI excludes no change" is
                   Holm-adjusted p < 0.05 (the unadjusted 95 % percentile CI is reported next to it).
  win (energy)     ETS99 ratio <= 0.95 and Holm p < 0.05, at equal-or-better success (success diff >= -0.01, point and CI lower bound)
  equivalent       success diff CI inside +-0.01 AND ETS99 ratio CI inside [0.95, 1.05]
"""
from __future__ import annotations

import glob
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan as pl  # noqa: E402
import pricing as pr  # noqa: E402

WIN_RATIO, EQ_LO, EQ_HI, EQ_SUCC = 0.95, 0.95, 1.05, 0.01
N_BOOT = 10_000
ALPHA = 0.05
SEED_BOOT = 20261116


# --------------------------------------------------------------------------------------------------------------- loading
def load_records(raw: str | Path, study: str, phase: str | None = None) -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(Path(raw) / study / "*.json"))):
        d = json.loads(Path(f).read_text())
        for r in d.get("records", []):
            if phase is None or r["spec"]["phase"] == phase:
                out.append(r)
    return out


def best_known_cut(inst: str) -> int:
    import machines as ma
    return ma.bks_cut(inst)


def targets(family: str, instances: list[str], ref_records: list[dict] | None = None) -> dict[str, dict]:
    """{instance: {"E_ref": ..., "E_target": ...}} in minimisation-energy units."""
    out = {}
    for i in instances:
        if family == "maxcut":
            bks = best_known_cut(i)
            out[i] = {"E_ref": -float(bks), "E_target": -pl.MAXCUT_TARGET_FRAC * bks}
        elif family == "maxsat":
            es = [r["best_E"] for r in (ref_records or []) if r["spec"]["instance"] == i and r["spec"]["family"] == "maxsat"]
            if not es:
                raise ValueError(f"no reference-set runs for MaxSAT instance {i}")
            out[i] = {"E_ref": min(es), "E_target": min(es)}
        elif family == "colouring":
            import machines as ma
            e = float(ma.colouring_optimum(i))
            out[i] = {"E_ref": e, "E_target": e}
        else:
            raise ValueError(family)
    return out


def gap_of(E: np.ndarray, E_ref: float) -> np.ndarray:
    return (E - E_ref) / max(1.0, abs(E_ref))


# --------------------------------------------------------------------------------------------------------- per-run arrays
@dataclass
class RunArrays:
    curve: np.ndarray      # (K,) best-so-far energy at the fine step grid
    t_steps: np.ndarray    # (K,)
    ecum: np.ndarray       # (K,) cumulative energy fJ
    tcum: np.ndarray       # (K,) cumulative machine time ns
    best_E: float
    a_total: float
    e_total: float
    t_total: float
    restarts: int
    prog: dict
    blocks: dict


def variant_key(variant: str) -> str:
    """'c' (as simulated) or 'c_ns' (what the same trajectory costs without I10)."""
    return "c_ns" if variant in ("off", "i7") else "c"


def run_arrays(rec: dict, cost, noskip: bool = False, rebits: int = 0) -> RunArrays:
    """Cumulative energy / time on the fine grid, priced from the counter snapshots with `cost` (any scaled CostModel).
    noskip=True prices the I10-free counters of an I10-simulated run (H2 'off' / 'i7' variants). rebits = B1 ADC-bit delta (H3)."""
    desc = rec["desc"]
    snaps = rec["snaps"]
    key = "c_ns" if noskip and snaps[0]["c_ns"] is not None else "c"
    ts, es, tn = [0], [0.0], [0.0]
    for s in snaps:
        c, d = (s[key], desc) if not rebits else pr.b1_rebits(s[key], desc, rebits)
        p = pr.price(d, c, s["t"], s["flips"], cost)
        ts.append(s["t"])
        es.append(p["e_total"])
        tn.append(p["time_ns"])
    fine = np.asarray(rec["curve_t"], float)
    cf, df = (snaps[-1][key], desc) if not rebits else pr.b1_rebits(snaps[-1][key], desc, rebits)
    final = pr.price(df, cf, snaps[-1]["t"], snaps[-1]["flips"], cost)
    return RunArrays(np.asarray(rec["curve"], float), fine, np.interp(fine, ts, es), np.interp(fine, ts, tn), rec["best_E"],
                     final["a_total"], final["e_total"], final["time_ns"], rec["restarts"], rec["prog"], final["blocks"])


# ------------------------------------------------------------------------------------------------------------ arm tensors
@dataclass
class ArmData:
    """Runs of one arm arranged (instance, seed): success(I,S,K), ecum(I,S,K), tcum(I,S,K), final success (I,S), gap (I,S)."""
    name: str
    instances: list[str]
    succ: np.ndarray
    ecum: np.ndarray
    tcum: np.ndarray
    ok_final: np.ndarray
    gap_end: np.ndarray
    curve_gap: np.ndarray      # (I,S,K) normalised gap along the grid
    area: float
    restarts: np.ndarray       # (I,S)
    e_final: np.ndarray        # (I,S)


def arm_data(name: str, recs: list[dict], tg: dict, cost, noskip=False, rebits=0, instances: list[str] | None = None) -> ArmData:
    inst = instances or sorted({r["spec"]["instance"] for r in recs}, key=lambda s: (len(s), s))
    by = {(r["spec"]["instance"], r["spec"]["r"]): r for r in recs}
    seeds = sorted({r["spec"]["r"] for r in recs})
    K = len(recs[0]["curve"])
    S, I = len(seeds), len(inst)
    succ = np.zeros((I, S, K), bool)
    ecum, tcum, gap = np.zeros((I, S, K)), np.zeros((I, S, K)), np.zeros((I, S, K))
    ok, restarts, ef = np.zeros((I, S), bool), np.zeros((I, S)), np.zeros((I, S))
    area = 0.0
    for a, i in enumerate(inst):
        for b, s in enumerate(seeds):
            ra = run_arrays(by[(i, s)], cost, noskip, rebits)
            succ[a, b] = ra.curve <= tg[i]["E_target"] + 1e-9
            gap[a, b] = gap_of(ra.curve, tg[i]["E_ref"])
            ecum[a, b], tcum[a, b] = ra.ecum, ra.tcum
            ok[a, b] = succ[a, b, -1]
            restarts[a, b], ef[a, b], area = ra.restarts, ra.e_total, ra.a_total
    return ArmData(name, inst, succ, ecum, tcum, ok, gap[:, :, -1], gap, area, restarts, ef)


def gap_at_energy(a: ArmData, budget: np.ndarray) -> float:
    """Mean normalised gap when each run has spent `budget[instance]` fJ (first grid point at or above it, else the end of the run)."""
    I, S, K = a.ecum.shape
    k = np.minimum((a.ecum < budget[:, None, None]).sum(axis=2), K - 1)
    return float(np.take_along_axis(a.curve_gap, k[:, :, None], axis=2).mean())


# ---------------------------------------------------------------------------------------------------------- metrics
def r99(p: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(0.01) / np.log1p(-np.minimum(p, 1.0 - 1e-300))
    out = np.where(p >= 1.0, 1.0, np.maximum(out, 1.0))    # R99 floored at one run (frozen, pre-Stage 2 review MINOR 2)
    return np.where(p <= 0.0, np.inf, out)


def tts_ets(p: np.ndarray, t: np.ndarray, e: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rows = resamples; p, t, e shape (B, K). Returns (TTS99, ETS99) per row (inf if never succeeded)."""
    r = r99(p)
    with np.errstate(invalid="ignore"):
        return np.min(np.where(np.isinf(r), np.inf, t * r), axis=1), np.min(np.where(np.isinf(r), np.inf, e * r), axis=1)


def resample_indices(n_inst: int, n_seed: int, B: int, rng: np.random.Generator):
    ii = rng.integers(0, n_inst, (B, n_inst))
    ss = rng.integers(0, n_seed, (B, n_inst, n_seed))
    return ii, ss


def pooled(a: ArmData, ii: np.ndarray, ss: np.ndarray) -> dict:
    """Pooled per-resample metrics of arm a for resample (ii, ss); ii == None means the observed sample."""
    if ii is None:
        I, S, _ = a.succ.shape
        ii = np.arange(I)[None]
        ss = np.broadcast_to(np.arange(S), (1, I, S))
    ix = ii[:, :, None]
    p = a.succ[ix, ss].mean(axis=(1, 2))
    t = a.tcum[ix, ss].mean(axis=(1, 2))
    e = a.ecum[ix, ss].mean(axis=(1, 2))
    tts, ets = tts_ets(p, t, e)
    return {"success": a.ok_final[ix, ss].mean(axis=(1, 2)), "tts": tts, "ets": ets, "gap": a.gap_end[ix, ss].mean(axis=(1, 2)),
            "e_final": a.e_final[ix, ss].mean(axis=(1, 2)), "restarts": a.restarts[ix, ss].mean(axis=(1, 2))}


def boot_stats(arms: dict[str, ArmData], B: int = N_BOOT, seed: int = SEED_BOOT, chunk: int = 250) -> dict[str, dict]:
    """{arm: {metric: (B,) array}} on shared resamples, plus "obs" (observed point values) under key '__obs__'."""
    names = list(arms)
    ref = arms[names[0]]
    I, S = ref.succ.shape[:2]
    rng = np.random.default_rng(seed)
    out = {n: {} for n in names}
    for lo in range(0, B, chunk):
        ii, ss = resample_indices(I, S, min(chunk, B - lo), rng)
        for n in names:
            m = pooled(arms[n], ii, ss)
            for k, v in m.items():
                out[n].setdefault(k, []).append(v)
    out = {n: {k: np.concatenate(v) for k, v in d.items()} for n, d in out.items()}
    out["__obs__"] = {n: {k: float(v[0]) for k, v in pooled(arms[n], None, None).items()} for n in names}
    return out


def ci(x: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return (float("nan"), float("nan"))
    return float(np.quantile(x, (1 - level) / 2)), float(np.quantile(x, 1 - (1 - level) / 2))


def holm(pvals: dict[str, float], alpha: float = ALPHA) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone)."""
    order = sorted(pvals, key=pvals.get)
    m, run, out = len(order), 0.0, {}
    for k, name in enumerate(order):
        run = max(run, min(1.0, (m - k) * pvals[name]))
        out[name] = run
    return out


def ratio_samples(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / den
    r[np.isinf(num) & np.isinf(den)] = np.nan
    return r


def contrast(bs: dict, arm: str, comp: str) -> dict:
    """Paired contrast arm vs comp from boot_stats output: ETS99/TTS99 ratios, success difference, gap difference."""
    a, c, o = bs[arm], bs[comp], bs["__obs__"]
    ets = ratio_samples(a["ets"], c["ets"])
    tts = ratio_samples(a["tts"], c["tts"])
    ds = a["success"] - c["success"]
    dg = a["gap"] - c["gap"]
    n = np.isfinite(ets).sum()
    p_lt1 = (np.sum(~(ets < 1.0) & np.isfinite(ets)) + 1) / (n + 1) if n else 1.0
    return {"ets_ratio": _div(o[arm]["ets"], o[comp]["ets"]), "ets_ci": ci(ets), "tts_ratio": _div(o[arm]["tts"], o[comp]["tts"]),
            "tts_ci": ci(tts), "d_success": o[arm]["success"] - o[comp]["success"], "d_success_ci": ci(ds),
            "d_gap": o[arm]["gap"] - o[comp]["gap"], "d_gap_ci": ci(dg), "p_ets_lt1": float(p_lt1), "n_valid": int(n)}


def _div(a: float, b: float) -> float:
    if math.isinf(a) and math.isinf(b):
        return float("nan")
    return float("inf") if b == 0 else a / b


ZERO_COMPARATOR_NOT_EVALUABLE = False   # EVAL-1 (default off: frozen evaluators unchanged): a comparator with no success has ETS = inf,
                                        # so ratio 0 is not an energy win; True labels it "not evaluable" (H8 convention, success win)


def energy_verdict(c: dict, holm_p: float) -> str:
    """win / tie / loss / inconclusive on energy-to-solution (H2 section 6)."""
    r = c["ets_ratio"]
    if not math.isfinite(r) or (ZERO_COMPARATOR_NOT_EVALUABLE and r == 0.0):
        return "not evaluable"
    succ_ok = c["d_success"] >= -EQ_SUCC and c["d_success_ci"][0] >= -EQ_SUCC
    if r <= WIN_RATIO and holm_p < ALPHA and c["ets_ci"][1] < 1.0 and succ_ok:
        return "win"
    if c["d_success_ci"][0] >= -EQ_SUCC and c["d_success_ci"][1] <= EQ_SUCC and c["ets_ci"][0] >= EQ_LO and c["ets_ci"][1] <= EQ_HI:
        return "tie"
    if r >= 1.0 and c["ets_ci"][0] > 1.0:
        return "loss"
    return "inconclusive"


def area_verdict(ratio: float) -> str:
    return "win" if ratio <= WIN_RATIO else "loss" if ratio >= EQ_HI else "tie"


def quality_verdict(c: dict) -> str:
    lo, hi = c["d_success_ci"]
    if lo >= EQ_SUCC:
        return "win"
    if hi <= -EQ_SUCC:
        return "loss"
    if lo >= -EQ_SUCC and hi <= EQ_SUCC:
        return "tie"
    return "inconclusive"
