"""Stage 1 analysis tables (reads the JSONL of a Stage 1 return; no selection logic beyond run_s1.py select). usage: analyse_s1.py DIR"""
import glob, json, math, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from run_s1 import wilson, newcombe  # noqa: E402

d = sys.argv[1]
rows = [json.loads(x) for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))) for x in open(f) if x.strip()]
def tab(sel, keyf, title):
    g = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        if sel(r):
            e = g[keyf(r)]; e[0] += r["success"]; e[1] += 1; e[2] += r["best_E"]
    print(f"\n### {title}\n| key | success | n | Wilson 95 % | mean best_E |\n|---|---|---|---|---|")
    for k in sorted(g, key=lambda k: (-g[k][0] / g[k][1], str(k))):
        s, n, e = g[k]; lo, hi = wilson(s, n)
        print(f"| {k} | {s / n:.2f} | {n} | [{lo:.2f}, {hi:.2f}] | {e / n:.2f} |")
    return g
for st, cell, arm, title in (("1a", "p3n480", "ours", "1a ours p3n480 (round 1)"), ("1a", "gk", "ours", "1a ours gk"), ("1a", "p3n960", "ours", "1a ours p3n960 (round 2)")):
    tab(lambda r: r["stage"] == st and r["cell"] == cell and r["arm"] == arm, lambda r: r["cid"], title)
for arm in ("B3", "kc2c", "none_B1"):
    tab(lambda r: r["stage"] == "1a" and r["cell"] == "p3n960" and r["arm"] == arm, lambda r: r["cid"] + "|" + json.dumps(r["cfg_over"], sort_keys=True), f"1a {arm} p3n960 round 2")
for cell in ("p3n480", "gk", "p3n960"):
    tab(lambda r: r["stage"] == "1b" and r["cell"] == cell, lambda r: r["cid"], f"1b {cell}")
tab(lambda r: r["stage"] == "1d", lambda r: r["cid"], "1d gk")
tab(lambda r: r["stage"] == "1c.k", lambda r: (r["cid"], r["k"], r["share"]), "1c.k")
tab(lambda r: r["stage"] == "1c", lambda r: (r["cell"], r["cid"], r["share"], r["mit"]), "1c")
tab(lambda r: r["stage"] == "1e", lambda r: (r["cell"], r["arm"], r["cid"]), "1e")
for f in sorted(glob.glob(os.path.join(d, "1c.fmc.*.json"))):
    x = json.load(open(f)); print(os.path.basename(f), {k: round(x[k], 3) for k in ("mean", "sd", "frac_nonzero", "frac_neg", "frac_pos")})
