"""Stage 1b energy first look (internal review item 9.3.4): ETS99 (H8 evaluator machinery: evalcommon.arm_data / boot_stats, MeasuredCostV2 with the corrected
cost flags B-1..B-3) from the saved full records of the re-tune. Ideal device, p3n480 tuning instances 2101-2108 x seeds 0-2 (24 runs per config).
usage: s1b_ets.py RECORDS_DIR SELECTION.json OUT.md [B]   (selection.json from run_s1.py select --stage 1a on the same JSONL directory)"""
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import numpy as np  # noqa: E402
import cost_flags as cf  # noqa: E402
import evalcommon as ev  # noqa: E402
from cost_model import MeasuredCostV2  # noqa: E402

rec_dir, sel_path, out, B = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 2000
cost = cf.apply(MeasuredCostV2(), cf.parse("all"))
sel = json.load(open(sel_path))["arms"]
groups = {}
for f in sorted(glob.glob(f"{rec_dir}/*.json")):
    d = json.load(open(f))
    groups[(d["arm"], d["cid"])] = [cf.prepare(r, cost) for r in d["records"]]
insts = sorted({r["spec"]["instance"] for rs in groups.values() for r in rs})
tg = {i: {"E_ref": 0.0, "E_target": 0.0} for i in insts}   # planted colouring: optimum energy 0 by construction (H8 rule)
data = {k: ev.arm_data(f"{k[0]}:{k[1]}", rs, tg, cost) for k, rs in groups.items()}
names = {f"{k[0]}:{k[1]}": k for k in data}
bs = ev.boot_stats({n: data[k] for n, k in names.items()}, B=B)
obs = bs["__obs__"]


def blocks(k):
    tot, br = {}, 0
    for r in groups[k]:
        for b, v in r["price"]["blocks"].items():
            tot[b] = tot.get(b, 0.0) + v
        br += r["restarts"]
    s = sum(tot.values())
    return tot, s, br / len(groups[k])


L = ["# Stage 1b ETS first look (ideal device, p3n480 tuning instances 2101-2108 x 3 seeds; corrected pricing B-1..B-3; fixed H8 evaluator machinery)", "",
     "ETS99 in fJ, pooled over the (instance, seed) rectangle with the H8 paired bootstrap (B = %d). Not confirmatory: tuning instances, 24 runs per configuration, ideal device (no mitigation energy)." % B, "",
     "| arm | cid | success | ETS99 (fJ) | e_final/run (fJ) | restarts/run | restart block share | rng block share |", "|---|---|---|---|---|---|---|---|"]
for k in sorted(data, key=lambda k: (k[0], obs[f"{k[0]}:{k[1]}"]["ets"])):
    n = f"{k[0]}:{k[1]}"
    tot, s, br = blocks(k)
    o = obs[n]
    L.append(f"| {k[0]} | {k[1]} | {o['success']:.2f} | {o['ets']:.3g} | {o['e_final']:.3g} | {br:.0f} | {tot.get('restart', 0) / s:.4f} | {tot.get('rng', 0) / s:.4f} |")
sel_cid = {a: sel[a]["col"][0]["cid"] for a in ("ours", "B3", "kc2c", "none_B1")}
L += ["", "## Contrasts of the selected configurations (ratio < 1 favours the first)", "", "| contrast | ETS ratio [95 % CI] | d success [95 % CI] |", "|---|---|---|"]
def row(a, b, lab):
    na, nb = f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}"
    c = ev.contrast(bs, na, nb)
    L.append(f"| {lab} | {c['ets_ratio']:.3g} [{c['ets_ci'][0]:.3g}, {c['ets_ci'][1]:.3g}] | {c['d_success']:+.2f} [{c['d_success_ci'][0]:+.2f}, {c['d_success_ci'][1]:+.2f}] |")
oursel, b3sel = ("ours", sel_cid["ours"]), ("B3", sel_cid["B3"])
if ("ours", "ours_ref_H8") in data:
    row(oursel, ("ours", "ours_ref_H8"), f"ours selected ({oursel[1]}) vs ours H8 reference (L=10, K=2n): the energy cost / gain of the retune")
row(oursel, b3sel, f"ours selected vs B3 selected ({b3sel[1]})")
if ("B3", "B3_ref_H8") in data:
    row(oursel, ("B3", "B3_ref_H8"), "ours selected vs B3 H8 reference")
    row(b3sel, ("B3", "B3_ref_H8"), "B3 selected vs B3 H8 reference (retune effect on B3)")
row(oursel, ("kc2c", sel_cid["kc2c"]), f"ours selected vs ours_kc2c selected ({sel_cid['kc2c']})")
row(oursel, ("none_B1", sel_cid["none_B1"]), f"ours selected vs ours_none selected ({sel_cid['none_B1']}; priced as ours hardware)")
Path(out).write_text("\n".join(L) + "\n")
print("\n".join(L))

# ---- ETS-selected variant (symmetric rule: lowest observed ETS99 among the arm's 16 configurations; selection and scoring on the same runs: optimistic for every arm alike)
best = {}
for k in data:
    n = f"{k[0]}:{k[1]}"
    if k[1].endswith("_ref_H8"):
        continue
    e = obs[n]["ets"]
    if k[0] not in best or e < best[k[0]][0]:
        best[k[0]] = (e, k)
M = ["", "## ETS-selected variant (lowest ETS99 per arm among its configurations; same-data selection bias for every arm)", "", "| arm | config | success | ETS99 (fJ) |", "|---|---|---|---|"]
for a, (e, k) in sorted(best.items()):
    M.append(f"| {a} | {k[1]} | {obs[f'{k[0]}:{k[1]}']['success']:.2f} | {e:.3g} |")
M += ["", "| contrast | ETS ratio [95 % CI] | d success [95 % CI] |", "|---|---|---|"]
def row2(a, b, lab):
    c = ev.contrast(bs, f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}")
    M.append(f"| {lab} | {c['ets_ratio']:.3g} [{c['ets_ci'][0]:.3g}, {c['ets_ci'][1]:.3g}] | {c['d_success']:+.2f} [{c['d_success_ci'][0]:+.2f}, {c['d_success_ci'][1]:+.2f}] |")
if "ours" in best and "B3" in best:
    row2(best["ours"][1], best["B3"][1], "ours (ETS-selected) vs B3 (ETS-selected)")
    if ("B3", "B3_ref_H8") in data:
        row2(best["ours"][1], ("B3", "B3_ref_H8"), "ours (ETS-selected) vs B3 H8 reference")
Path(out).write_text("\n".join(L + M) + "\n")
print("\n".join(M))
