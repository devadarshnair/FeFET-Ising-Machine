"""Does the integer golden model rank the D5c rules in the same direction as the reference software study's float model (qkp_nb.py)?

Not a bit-exact check: the two models use different RNGs, a LUT acceptance and integer rounding (SPEC 10).
Cell n = 200, m = 16; arms and their configs are the ones D5c selected (results/confirm/selection.json):
  HX = exact hinge (penalty), HQ8 / HQ16 = TCAM thermometer hinge at Q = 8 / 16, FI = exact filter.
Test instances 5000-5004, seeds 100-101 (the first D5c test units), full budget 100000 steps.
Criterion, fixed before running: for each contrast (HQ8 - HX, HQ16 - HX, FI - HQ8, in gap points, positive = first
arm worse) the mean paired difference has the same sign in both models. Also reported: the D5c full-test values.

Run: NUMBA_CACHE_DIR=sim/out/numba_cache GUARD_S=3000 scripts/run_guarded.sh <python> -I -B \
     scripts/golden/d5c_rank_check.py
Reads the reference software study code and results (read only). Writes sim/out/d5c_rank/result.json and prints a markdown table.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
D5C = Path("$PROJECT/sw_ref/experiments/d5c_qhinge")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(D5C))

import numpy as np  # noqa: E402

import instances as gi  # noqa: E402
import qhinge as H  # noqa: E402  (the reference software study harness: config names -> engine parameters)
import qkp_nb as qk  # noqa: E402  (the reference software study float model)
import tim_golden as tg  # noqa: E402

N_ITEMS, M_CONS = 200, 16
INSTS = (5000, 5001, 5002, 5003, 5004)
SEEDS = (100, 101)
ARMS = ("HX", "HQ8", "HQ16", "FI")
CONTRASTS = (("HQ8", "HX"), ("HQ16", "HX"), ("FI", "HQ8"))
D5C_FULL = {("HQ8", "HX"): "D2_HQ8_minus_HX", ("HQ16", "HX"): "D2b_HQ16_minus_HX", ("FI", "HQ8"): "Dd_FI_minus_HQ8"}


def selected_configs() -> dict:
    sel = json.loads((D5C / "results/confirm/selection.json").read_text())
    return {arm: sel[f"{N_ITEMS}x{M_CONS}"]["selected"][arm] for arm in ARMS}


def d5c_full_contrasts() -> dict:
    out = {}
    for line in (D5C / "results/confirm/summary.csv").read_text().splitlines():
        parts = line.split(",")
        for key, name in D5C_FULL.items():
            if parts[0] == f"{N_ITEMS}x{M_CONS}" and parts[1] == name:
                out[key] = float(parts[2])
    return out


def run_float(raw: dict, params: dict, seed: int) -> float:
    p = dict(params)
    rule = p.pop("rule")
    return qk.run(raw, rule, budget=H.budget(N_ITEMS), seed=seed, **p)["best_f"]


def run_int(raw_int: dict, params: dict, seed: int) -> float:
    p = dict(params)
    rule = p.pop("rule")
    q = int(p.get("Q", 8))
    kind = {"penalty": "penalty", "qhinge": "hw", "filter": "filter"}[rule]
    gsh = int(round(math.log2(q))) if kind == "hw" else 3
    inst = gi.d5c_to_tim(raw_int, rule=kind, T0=p["T0"], T_min=p["T_min"], budget=H.budget(N_ITEMS), seed=seed,
                         lam=p.get("lam", 0.0), dE_off=p["dE_off"], Q=q, gsh=gsh)
    return float(tg.Machine(inst).run(keep_trace=False).best_f)


def main() -> int:
    cfgs = selected_configs()
    params = {arm: H.engine_params(cfg, N_ITEMS) for arm, cfg in cfgs.items()}
    best = {"float": {}, "int": {}}
    t0 = time.time()
    for inst in INSTS:
        raw_f = qk.make_instance(N_ITEMS, M_CONS, inst)
        raw_i = gi.d5c_make_instance(N_ITEMS, M_CONS, inst)
        for seed in SEEDS:
            for arm in ARMS:
                best["float"][(inst, seed, arm)] = run_float(raw_f, params[arm], seed)
                best["int"][(inst, seed, arm)] = run_int(raw_i, params[arm], seed)
            print(f"inst {inst} seed {seed} done ({time.time() - t0:.0f} s)", flush=True)
    bk = {inst: max(v for (i, _, _), v in list(best["float"].items()) + list(best["int"].items()) if i == inst)
          for inst in INSTS}

    def gap(model, inst, seed, arm):
        return 100.0 * (bk[inst] - best[model][(inst, seed, arm)]) / bk[inst]

    mean_gap = {model: {arm: float(np.mean([gap(model, i, s, arm) for i in INSTS for s in SEEDS])) for arm in ARMS}
                for model in best}
    full = d5c_full_contrasts()
    rows, agree_all = [], True
    for a, b in CONTRASTS:
        diffs = {model: [gap(model, i, s, a) - gap(model, i, s, b) for i in INSTS for s in SEEDS] for model in best}
        mf, mi = float(np.mean(diffs["float"])), float(np.mean(diffs["int"]))
        agree = np.sign(mf) == np.sign(mi)
        agree_all &= bool(agree)
        rows.append(dict(contrast=f"{a} - {b}", float=mf, int=mi, d5c_full=full.get((a, b)), agree=bool(agree),
                         float_pos=int(sum(d > 0 for d in diffs["float"])),
                         int_pos=int(sum(d > 0 for d in diffs["int"]))))
    result = dict(cell=f"{N_ITEMS}x{M_CONS}", insts=INSTS, seeds=SEEDS, configs=cfgs, mean_gap=mean_gap,
                  contrasts=rows, all_agree=agree_all, seconds=round(time.time() - t0))
    out = REPO / "sim/out/d5c_rank"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=1, default=str))

    npair = len(INSTS) * len(SEEDS)
    print(f"\nMean gap (points, lower is better), {npair} runs per arm:")
    print("| model | " + " | ".join(ARMS) + " |")
    print("|---|" + "---|" * len(ARMS))
    for model in ("float", "int"):
        print(f"| {model} | " + " | ".join(f"{mean_gap[model][a]:.3f}" for a in ARMS) + " |")
    print(f"\n| contrast | float (qkp_nb) | integer (golden) | D5c full test | same sign | first arm worse in "
          f"(float / int) of {npair} |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['contrast']} | {r['float']:+.3f} | {r['int']:+.3f} | {r['d5c_full']:+.3f} | "
              f"{'yes' if r['agree'] else 'NO'} | {r['float_pos']} / {r['int_pos']} |")
    print(f"\nall contrasts agree in direction: {agree_all}  ({result['seconds']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
