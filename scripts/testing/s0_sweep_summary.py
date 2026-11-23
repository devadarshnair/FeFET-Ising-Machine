"""Stage 0.2 summary: success (best_E == 0) per C2C share with Wilson 95 % CIs from s0_sweep.py JSONL files. usage: s0_sweep_summary.py FILE..."""
import json
import math
import sys
from collections import defaultdict


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


for f in sys.argv[1:]:
    rows = [json.loads(x) for x in open(f)]
    by = defaultdict(list)
    for r in rows:
        by[r["share"]].append(r["best_E"] <= 0)
    print(f"\n{f}  ({rows[0]['label']} {rows[0]['family']} {rows[0]['cond']})")
    print("| share | success | n | Wilson 95 % |\n|---|---|---|---|")
    for s in sorted(by):
        k, n = sum(by[s]), len(by[s])
        lo, hi = wilson(k, n)
        print(f"| {s:g} | {k / n:.2f} | {n} | [{lo:.2f}, {hi:.2f}] |")
