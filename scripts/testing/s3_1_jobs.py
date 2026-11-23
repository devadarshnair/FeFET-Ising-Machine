"""Stage 3.1 tuning job list (the Stage 3 plan section 4): ONE global rule for every arm's escape options. Each arm evaluates exactly 12 distinct configurations on ALL
three tuning cells (p3n480 8x3, p4n480 8x3, p3n960 6x2; tag 10; ideal device) and ONE configuration per arm is selected for every cell:
score = mean of the three cell-level success rates (equal cell weights), ties by mean best_E over all runs, then grid order; non-regression: the selected ours
configuration must keep p3n480 success >= base - 0.10 (base = Stage 2 ours_new: R7 off, plain). Reference rows (not selectable): ours_new base, B3_h8 (registered).
ours escape options: R7 adaptive-L m in {0 (off), 2, 3, 4} x {plain, burst B, esc A} at K = 0.25n, L = 10. B3's escape option is its native temperature schedule (the DA offset is
disabled in Aramon's final configuration, the B3 v2 hook): T_start x {1, 1.5, 2.5} x T_final multiplier {1/32, 1/16, 1/8, 1/4} (12).
usage: s3_1_jobs.py plan OUT.tsv | select DIR OUT.json"""
import glob
import json
import os
import sys
from collections import defaultdict

PY = "$PY -I scripts/testing/run_s1.py"
OUT = "sim/out/hw/s31"
CELLS = {"p3n480": ([str(2101 + i) for i in range(8)], 3), "p4n480": ([str(2201 + i) for i in range(8)], 3), "p3n960": ([str(2101 + i) for i in range(6)], 2)}
BASE = {"kick_c": 0, "knob": 0.25}
ESC = {"plain": {}, "burstB": {"burst_K": 0.1, "burst_len": 0.1, "burst_up": 3}, "escA": {"esc_step": 1, "esc_max": 2}}
OURS = {f"m{m}_{e}": {**BASE, **({"adaptive_m": m} if m else {}), **ESC[e]} for m in (0, 2, 3, 4) for e in ("plain", "burstB", "escA")}
B3 = {f"th{h:g}_tl{l:g}": {"pct_hi": 90, "pct_lo": 5, "knob": 1.0, "t_hi_mult": h, "t_lo_mult": l} for h in (1.0, 1.5, 2.5) for l in (0.03125, 0.0625, 0.125, 0.25)}
REFS = {"ours_ref_base": ("ours", "ours_kc2_i11", BASE), "B3_ref_h8": ("B3", "B3_v2", {"pct_hi": 90, "pct_lo": 5, "knob": 0.5})}


def cfgs(d):
    return ",".join(f"{k}={v}" if not isinstance(v, bool) else f"{k}={str(v).lower()}" for k, v in d.items())


def jobs():
    out = []
    allc = [("ours", "ours_kc2_i11", n, c, False) for n, c in OURS.items()] + [("B3", "B3_v2", n, c, False) for n, c in B3.items()] + \
           [(a, lab, n, c, True) for n, (a, lab, c) in REFS.items()]
    for arm, label, name, cfg, ref in allc:
        for cell, (keys, seeds) in CELLS.items():
            jid = f"s31.{arm}.{name}.{cell}"
            out.append((jid, f"{PY} run --id {jid} --stage s31 --arm {arm} --cid {name} --label {label} --family {cell} --cell {cell} --cond ideal --mit none --shares 0 --keys {','.join(keys)} "
                             f"--seeds {seeds} --k 1 --tile 0 --cfg {cfgs(cfg)} --out {OUT}/{jid}.jsonl"))
    return out


def select(d, outp):
    rows = []
    for f in glob.glob(os.path.join(d, "s31.*.jsonl")):
        rows += [json.loads(x) for x in open(f) if x.strip()]
    g = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0]))
    for r in rows:
        e = g[(r["arm"], r["cid"])][r["cell"]]
        e[0] += r["success"]; e[1] += 1; e[2] += r["best_E"]
    res = {}
    for arm in ("ours", "B3"):
        cand = []
        for (a, cid), cells in g.items():
            if a != arm or cid in REFS or set(cells) != set(CELLS):
                continue
            score = sum(cells[c][0] / cells[c][1] for c in CELLS) / len(CELLS)
            mean_e = sum(cells[c][2] for c in CELLS) / sum(cells[c][1] for c in CELLS)
            cand.append((-score, mean_e, list(OURS if arm == "ours" else B3).index(cid), cid, {c: cells[c][0] / cells[c][1] for c in CELLS}))
        cand.sort()
        base = g.get(("ours", "ours_ref_base"), {}).get("p3n480")
        ok = [c for c in cand if arm != "ours" or base is None or c[4]["p3n480"] >= base[0] / base[1] - 0.10]
        res[arm] = {"selected": ok[0][3] if ok else None, "score": -ok[0][0] if ok else None, "cells": ok[0][4] if ok else None,
                    "ranking": [(c[3], round(-c[0], 3), {k: round(v, 2) for k, v in c[4].items()}) for c in cand],
                    "non_regression_applied": arm == "ours", "cfg": (OURS if arm == "ours" else B3).get(ok[0][3]) if ok else None}
    res["refs"] = {f"{a}:{c}": {k: [v[0], v[1]] for k, v in cells.items()} for (a, c), cells in g.items() if c in REFS}
    json.dump(res, open(outp, "w"), indent=1)
    print(json.dumps({a: (res[a]["selected"], res[a]["score"]) for a in ("ours", "B3")}))


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        js = jobs()
        open(sys.argv[2], "w").write("\n".join(f"{i}\t{c}" for i, c in js) + "\n")
        print(len(js), "jobs")
    else:
        select(sys.argv[2], sys.argv[3])
