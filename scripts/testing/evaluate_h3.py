"""H3 evaluator: the sensitivity grid on the H2 headline contrast (prereg/hw/H3_sensitivity.md sections 2-4). NOT run on real data
at the time of writing.

The grid has 3600 cells = read energy (5) x array-RC/ADC energy (4) x ADC bits (5) x sigma (4) x RNG (3) x clock (3). Only
ADC bits x sigma (20) change trajectories (the H3 runs); the other 180 cost combinations per trajectory configuration are re-priced
from the logged counters. Energy is linear in the individual table-row scales, so each snapshot is priced once per row (finite
difference) and every cell is a dot product: all cells share the bootstrap resamples (instances, then seeds), paired across arms.

Interpretations that the draft leaves open (flagged for the author, [AUTHOR] in the prereg):
  * the table has ONE array row (e_array_cell_read: cell read incl. line capacitance), so the "array/search-line capacitance and ADC
    energy" axis scales e_array_cell_read, e_adc_conv_bit and e_adc_bias_step together; the read-energy axis scales e_array_cell_read;
  * B3 (digital) reuses its H2 runs (first 5 instances, seeds 0-4); it is scaled on RNG, clock and, with the capacitance axis, the SRAM
    read energy (default yes); it has no ADC or sigma axis. B1 ADC-bit changes are cost-only (its 32-row tile ADC is exact from 6 bits);
  * a cell "wins" against a baseline iff ETS99 ratio <= 0.95 with the 95 % bootstrap CI upper bound < 1 and quality not worse than the
    equivalence margin (success diff CI lower bound >= -0.01); advance needs the win fraction >= 0.80 against EVERY simulated baseline
    (B1-tuned and B3) in BOTH Max-Cut and MaxSAT, and a break-even factor >= 2 for every term. B2 (QKP) is not evaluable: ours is not run
    on QKP by default.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evalcommon as ev  # noqa: E402
import plan as pl  # noqa: E402
import pricing as pr  # noqa: E402
from cost_model import CostModel  # noqa: E402

KEYS = ("e_array_cell_read", "e_adc_conv_bit", "e_adc_bias_step", "e_rng_draw", "t_clk", "e_sram_read_bit")
BASE = CostModel()
PROBES = [CostModel(scale={k: 2.0}) for k in KEYS]
WIN_FRACTION, BREAK_EVEN = 0.80, 2.0


def comps_at(desc: dict, c: dict, t: int, flips: int) -> tuple[np.ndarray, float]:
    """(7,) energy components [rest, one per KEYS row] in fJ and the time in ns, for cumulative counters c."""
    p0 = pr.price(desc, c, t, flips, BASE)
    v = np.zeros(len(KEYS) + 1)
    for j, pm in enumerate(PROBES):
        v[j + 1] = pr.price(desc, c, t, flips, pm)["e_total"] - p0["e_total"]
    v[0] = p0["e_total"] - v[1:].sum()
    return v, p0["time_ns"]


def cell_weights(read: float, arc: float, rng: float, clock: float) -> np.ndarray:
    """Multipliers on [rest, e_array_cell_read, e_adc_conv_bit, e_adc_bias_step, e_rng_draw, t_clk, e_sram_read_bit] for a cost cell."""
    return np.array([1.0, read * arc, arc, arc, rng, clock, arc])


class Arm:
    def __init__(self, recs: list[dict], tg: dict, rebits: int = 0, noskip: bool = False, first_inst: list[str] | None = None,
                 max_seed: int | None = None):
        if first_inst is not None:
            recs = [r for r in recs if r["spec"]["instance"] in first_inst]
        if max_seed is not None:
            recs = [r for r in recs if r["spec"]["r"] < max_seed]
        self.instances = first_inst or sorted({r["spec"]["instance"] for r in recs})
        seeds = sorted({r["spec"]["r"] for r in recs})
        by = {(r["spec"]["instance"], r["spec"]["r"]): r for r in recs}
        I, S, K = len(self.instances), len(seeds), len(recs[0]["snaps"])
        self.succ = np.zeros((I, S, K), bool)
        self.comp = np.zeros((I, S, K, len(KEYS) + 1))
        self.time = np.zeros((I, S, K))
        self.ok = np.zeros((I, S), bool)
        key = "c_ns" if noskip and recs[0]["snaps"][0]["c_ns"] is not None else "c"
        for a, i in enumerate(self.instances):
            for b, s in enumerate(seeds):
                r = by[(i, s)]
                for k, sn in enumerate(r["snaps"]):
                    c, d = (sn[key], r["desc"]) if not rebits else pr.b1_rebits(sn[key], r["desc"], rebits)
                    self.comp[a, b, k], self.time[a, b, k] = comps_at(d, c, sn["t"], sn["flips"])
                    self.succ[a, b, k] = sn["best_E"] <= tg[i]["E_target"] + 1e-9
                self.ok[a, b] = self.succ[a, b, -1]
        self.area = pr.price(r["desc"], r["snaps"][-1]["c"], r["snaps"][-1]["t"], r["snaps"][-1]["flips"], BASE)["a_total"]


def pooled_cells(arm: Arm, ii, ss) -> dict:
    ix = ii[:, :, None]
    p = arm.succ[ix, ss].mean(axis=(1, 2))                      # (B, K)
    return {"p": p, "r99": ev.r99(p), "comp": arm.comp[ix, ss].mean(axis=(1, 2)), "time": arm.time[ix, ss].mean(axis=(1, 2)),
            "success": arm.ok[ix, ss].mean(axis=(1, 2))}


def ets_of(pc: dict, w: np.ndarray) -> np.ndarray:
    e = pc["comp"] @ w                                           # (B, K)
    with np.errstate(invalid="ignore"):
        return np.min(np.where(np.isinf(pc["r99"]), np.inf, e * pc["r99"]), axis=1)


def tts_of(pc: dict, clock: float = 1.0) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.min(np.where(np.isinf(pc["r99"]), np.inf, pc["time"] * clock * pc["r99"]), axis=1)


def cell_verdict(ets_a: np.ndarray, ets_b: np.ndarray, dsucc: np.ndarray) -> dict:
    """Row 0 of every array is the observed sample, rows 1.. the bootstrap resamples."""
    lo, hi = ev.ci(ev.ratio_samples(ets_a[1:], ets_b[1:]))
    r_obs = ev._div(float(ets_a[0]), float(ets_b[0]))
    ds_lo = ev.ci(dsucc[1:])[0]
    win = bool(math.isfinite(r_obs) and r_obs <= ev.WIN_RATIO and hi < 1.0 and ds_lo >= -ev.EQ_SUCC)
    return {"ratio": r_obs, "ci": (lo, hi), "win": win}


def evaluate_family(raw, frozen: dict, fam: str, h2_b3: list[dict], tg: dict, B: int) -> dict:
    recs = ev.load_records(raw, "h3")
    recs = [r for r in recs if r["spec"]["family"] == fam]
    first = pl.TEST_SET[fam][:pl.H3_INSTANCES]
    I, S = len(first), pl.H3_SEEDS
    rng = np.random.default_rng(ev.SEED_BOOT)
    ii, ss = ev.resample_indices(I, S, B, rng)
    oi, os_ = observed_resample(I, S)
    ii, ss = np.concatenate([oi, ii]), np.concatenate([os_, ss])
    ours_arm, b1_arm = frozen[fam]["ours_best"]["arm"], frozen[fam]["b1_tuned"]["arm"]

    def sel(arm, d, s):
        return [r for r in recs if r["spec"]["arm"] == arm and r["spec"]["adc_delta"] == d and r["spec"]["sigma_mult"] == s]
    b3 = Arm(h2_b3, tg, first_inst=first, max_seed=S)
    pc_b3 = pooled_cells(b3, ii, ss)
    cells, out_traj = [], []
    for sg in pl.H3_SIGMA:
        b1_r = sel(b1_arm, 0, sg)
        b1_by_delta = {d: pooled_cells(Arm(b1_r, tg, rebits=d), ii, ss) for d in pl.H3_ADC_DELTA}
        for dl in pl.H3_ADC_DELTA:
            pc_o = pooled_cells(Arm(sel(ours_arm, dl, sg), tg), ii, ss)
            pc_1 = b1_by_delta[dl]
            for rd, arc, rn, ck in itertools.product(pl.H3_READ_E, pl.H3_ARRAY_ADC, pl.H3_RNG, pl.H3_CLOCK):
                w = cell_weights(rd, arc, rn, ck)
                eo, e1, e3 = ets_of(pc_o, w), ets_of(pc_1, w), ets_of(pc_b3, w)
                cells.append({"read": rd, "arc": arc, "adc_delta": dl, "sigma": sg, "rng": rn, "clock": ck,
                              "vs_b1": cell_verdict(eo, e1, pc_o["success"] - pc_1["success"]), "b1_cost_only_approx": bool(dl != 0 and sg > 0),
                              "vs_b3": cell_verdict(eo, e3, pc_o["success"] - pc_b3["success"])})
            out_traj.append({"adc_delta": dl, "sigma": sg, "tts_ratio_vs_b1_clock1": float(ev._div(float(tts_of(pc_o)[0]), float(tts_of(pc_1)[0])))})
    return {"cells": cells, "traj": out_traj}


def observed_resample(I: int, S: int):
    """(ii, ss) of the observed sample, prepended as row 0 of every cell so point ratios are the observed ones."""
    return np.arange(I)[None], np.broadcast_to(np.arange(S), (1, I, S))


def win_fractions(cells: list[dict]) -> dict:
    n = len(cells)
    return {b: sum(c[b]["win"] for c in cells) / n for b in ("vs_b1", "vs_b3")}


def break_even(cells: list[dict], base_key: str = "vs_b1") -> dict:
    """Smallest tested factor on one term (others nominal) at which the observed ETS99 ratio reaches 1; inf if never within the tested grid.
    Continuous terms are read off the tested values; ADC bits count as 2^|delta|; reported for every term, favouring either side.
    A win that is already gone at factor 2 reports 2.0, which is not a pass: H3 requires the win to survive a factor of 2
    (see survives_factor_2), so the pass test is strictly `> BREAK_EVEN`."""
    def ratio(**kw):
        for c in cells:
            if all(math.isclose(c[k], v) for k, v in kw.items()):
                return c[base_key]["ratio"]
        return float("nan")
    nominal = dict(read=1.0, arc=1.0, adc_delta=0, sigma=1.0, rng=1.0, clock=1.0)
    out = {}
    for term, vals in (("read", pl.H3_READ_E), ("arc", pl.H3_ARRAY_ADC), ("rng", pl.H3_RNG), ("clock", pl.H3_CLOCK),
                       ("sigma", pl.H3_SIGMA), ("adc_delta", pl.H3_ADC_DELTA)):
        lost = []
        for v in vals:
            if v == nominal[term]:
                continue
            r = ratio(**(nominal | {term: v}))
            if not math.isfinite(r) or r >= 1.0:
                lost.append(2.0 ** abs(v) if term == "adc_delta" else max(v, 1.0 / v))
        out[term] = min(lost) if lost else math.inf
    return out


def survives_factor_2(break_even_factor: float) -> bool:
    """The win must hold at factor 2 (ratio < 1 there): the smallest losing factor has to exceed 2."""
    return break_even_factor > BREAK_EVEN


def evaluate(raw, B: int = ev.N_BOOT) -> dict:
    frozen = json.loads((Path(raw) / "frozen.json").read_text())
    if not frozen.get("gate_pass"):
        return {"run": False, "statement": "H3 is not run: H2 produced no win"}
    ref = ev.load_records(raw, "ref")
    h2 = ev.load_records(raw, "h2", "test")
    res, fam_ok = {}, {}
    for fam in ("maxcut", "maxsat"):
        tg = ev.targets(fam, pl.TEST_SET[fam], ref)
        h2_b3 = [r for r in h2 if r["spec"]["arm"] == "b3.b3" and r["spec"]["family"] == fam]
        res[fam] = evaluate_family(raw, frozen, fam, h2_b3, tg, B)
        fr, be = win_fractions(res[fam]["cells"]), break_even(res[fam]["cells"])
        exact = win_fractions([c for c in res[fam]["cells"] if not c["b1_cost_only_approx"]])
        res[fam]["win_fraction"], res[fam]["win_fraction_exact_b1_cells"], res[fam]["break_even"] = fr, exact, be
        fam_ok[fam] = (all(v >= WIN_FRACTION for v in fr.values()) and exact["vs_b1"] >= WIN_FRACTION   # frozen MINOR 9
                       and all(survives_factor_2(v) for v in be.values()))
    adv = all(fam_ok.values())
    return {"run": True, "families": res, "advance": adv, "per_family_pass": fam_ok,
            "statement": ("H3 advance: the H2 win survives the credible range" if adv else
                          "H3 fail: the H2 result does not survive the credible range"),
            "dominance_order": ["adc energy (arc)", "read energy", "sigma", "adc bits", "rng", "clock"],
            "n_cells_per_family": pl.H3_CELLS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=ev.N_BOOT)
    a = ap.parse_args()
    res = evaluate(a.raw, a.boot)
    Path(a.out).write_text(json.dumps(res, default=float))
    print(res["statement"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
