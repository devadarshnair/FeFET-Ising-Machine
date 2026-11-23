"""Stage 3.0-B summary: success (Wilson 95 %) and mean best_E per job from sim/out/hw/s30/*.jsonl. usage: analyse_s30.py DIR"""
import glob, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from run_s1 import wilson  # noqa: E402
d = sys.argv[1]
rows = defaultdict(list)
for f in sorted(glob.glob(os.path.join(d, "s30.*.jsonl"))):
    for x in open(f):
        if x.strip():
            r = json.loads(x); rows[os.path.basename(f)[:-6]].append(r)
print("| job | cell | share/k | n | success | Wilson 95 % | mean best_E |\n|---|---|---|---|---|---|---|")
for k, rs in rows.items():
    s = sum(r["best_E"] <= 0 for r in rs) if rs[0]["family"] != "maxcut" else float("nan")
    n = len(rs)
    lo, hi = wilson(int(s), n) if s == s else (float("nan"),) * 2
    print(f"| {k} | {rs[0]['cell']} | {rs[0]['share']}/{rs[0]['k']:g} | {n} | {s / n if s == s else float('nan'):.2f} | [{lo:.2f}, {hi:.2f}] | {sum(r['best_E'] for r in rs) / n:.2f} |")
