import json, glob, collections, math
from pathlib import Path
D = Path(__file__).parent
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)
print("file,share,n,success,wilson95")
for f in sorted(D.glob("*.jsonl")):
    g = collections.defaultdict(list)
    for r in map(json.loads, f.read_text().splitlines()): g[r["share"]].append(r["best_E"] == 0)
    for s, v in sorted(g.items()):
        lo, hi = wilson(sum(v), len(v)); print(f.stem, s, len(v), f"{sum(v)/len(v):.2f}", f"[{lo:.2f}, {hi:.2f}]", sep=",")
