"""Stage 3.1 / 3.1b report: per-configuration success tables (Wilson 95 %), the registered selections (selection_31.json, selection_31b.json) and a completeness check.
usage: evaluate_s31.py --dir31 DIR --dir31b DIR --out FILE.md"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_s1 import wilson  # noqa: E402


def rows(d, pat):
    out = []
    for f in sorted(glob.glob(os.path.join(d, pat))):
        out += [json.loads(x) for x in open(f) if x.strip()]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir31", required=True)
    ap.add_argument("--dir31b", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    L = ["# Stage 3.1 report (DRAFT; tuning-only, ideal device / untiled nominal p3n240; not confirmatory)", ""]
    r1 = rows(a.dir31, "s31.*.jsonl")
    g = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0]))
    for r in r1:
        e = g[(r["arm"], r["cid"])][r["cell"]]
        e[0] += r["success"]; e[1] += 1; e[2] += r["best_E"]
    L += [f"3.1: {len(r1)} run rows, {len(g)} (arm, configuration) groups.", "", "| arm | configuration | p3n480 | p4n480 | p3n960 | mean of cells |", "|---|---|---|---|---|---|"]
    for (arm, cid), cells in sorted(g.items(), key=lambda kv: (kv[0][0], -sum(v[0] / v[1] for v in kv[1].values()))):
        vals = {c: cells[c][0] / cells[c][1] if c in cells else float("nan") for c in ("p3n480", "p4n480", "p3n960")}
        mean = sum(vals.values()) / 3
        def f(c):
            if c not in cells:
                return "-"
            lo, hi = wilson(int(cells[c][0]), cells[c][1])
            return f"{vals[c]:.2f} [{lo:.2f}, {hi:.2f}] n={cells[c][1]}"
        L.append(f"| {arm} | {cid} | {f('p3n480')} | {f('p4n480')} | {f('p3n960')} | {mean:.2f} |")
    for name, p in (("SEL.31 (global rule: mean of cell success, ties mean best_E, ours non-regression -0.10)", os.path.join(a.dir31, "selection_31.json")),
                    ("SEL.31b (T-1 stack parameters: success >= 0.87 at all three cliff points; cheapest passing)", os.path.join(a.dir31b, "selection_31b.json"))):
        L += ["", f"## {name}"]
        if os.path.exists(p):
            d = json.load(open(p))
            keep = {k: v for k, v in d.items() if k not in ("ranking",)}
            L += ["```", json.dumps({k: (v if k != "table" else {n: s for n, s in list(v.items())[:40]}) for k, v in keep.items()}, indent=1)[:6000], "```"]
        else:
            L.append("selection file missing")
    r2 = rows(a.dir31b, "s31b.*.jsonl")
    L += ["", f"3.1b: {len(r2)} run rows."]
    Path(a.out).write_text("\n".join(L) + "\n")
    print(f"report: {len(r1)} + {len(r2)} rows")
    return 0 if r1 and r2 else 1


if __name__ == "__main__":
    sys.exit(main())
