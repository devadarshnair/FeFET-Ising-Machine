"""Stage 3.1b: T-1 stack parameter tuning (the Stage 3 plan section 4b; the engineering notes section 13 pricing flag t1f). Simulation side of the choice: which screening threshold, correction-table
size and refresh period keep the incrementally-read exact field within 0.05 of the ideal level at the cliff points. Same instances / seeds as 3.0-B1 (p3 keys 2101-2112 x 3 seeds, p3n240,
nominal, base ours_new c 0 K 0.25n, sim_incremental). 12 configurations: screening threshold {3, 5, 8} nA x lcor table size {0 (screening only), 4} x refresh R {50, 200}.
Points: (C2C share, k) = (0, 1), (0.03, 1), (0.25, 2). Ideal level for these keys: 0.92 (36 runs).
Selection (declared before the runs): configurations with success >= 0.87 at ALL three points; among them the cheapest by priced cost (table 0 = screening only < table 4; larger R;
larger threshold = fewer retired cells), then grid order. **Table 0 (screening only) is a selectable configuration under this same rule** (pricing t1f at table 0:
ours/B3_sel 0.66 [0.43, 0.95], robust to refresh, retire fraction and x2 estimates 0.69); table 4 (0.76) is reported as the conservative sensitivity (`cheapest_passing_with_table4`).
usage: s3_1b_jobs.py plan OUT.tsv | select DIR OUT.json"""
import glob
import json
import os
import sys
from collections import defaultdict

PY = "$PY -I scripts/testing/run_s1.py"
OUT = "sim/out/hw/s31b"
K3 = [str(2101 + i) for i in range(12)]
BASE = {"kick_c": 0, "knob": 0.25, "sim_incremental": True}
POINTS = ((0.0, 1), (0.03, 1), (0.25, 2))
CFGS = [(thr, lc, R) for thr in (3, 5, 8) for lc in (0, 4) for R in (50, 200)]


def name(c):
    return f"scr{c[0]}_lcor{c[1]}_R{c[2]}"


def mit(c):
    return "wv+diff+cal" + f"+scr{c[0]}" + (f"+lcor{c[1]}" if c[1] else "")


def jobs():
    out = []
    for c in CFGS:
        for sh, k in POINTS:
            jid = f"s31b.{name(c)}.s{sh}k{k}"
            cfg = ",".join(f"{a}={str(b).lower() if isinstance(b, bool) else b}" for a, b in {**BASE, "sim_refresh": c[2]}.items())
            out.append((jid, f"{PY} run --id {jid} --stage s31b --arm t1stack --cid {name(c)} --label ours_kc2_i11 --family p3n240 --cell p3n240 --cond nominal --mit {mit(c)} --shares {sh} "
                             f"--keys {','.join(K3)} --seeds 3 --k {k} --tile 0 --cfg {cfg} --out {OUT}/{jid}.jsonl"))
    return out


def select(d, outp):
    g = defaultdict(dict)
    for f in glob.glob(os.path.join(d, "s31b.*.jsonl")):
        rows = [json.loads(x) for x in open(f) if x.strip()]
        if rows:
            g[rows[0]["cid"]][(rows[0]["share"], rows[0]["k"])] = sum(r["best_E"] <= 0 for r in rows) / len(rows)
    ok = []
    for i, c in enumerate(CFGS):
        s = g.get(name(c), {})
        if len(s) == len(POINTS) and min(s.values()) >= 0.87:
            ok.append((c[1], -c[2], -c[0], i, name(c)))
    ok.sort()
    res = {"table": {n: {f"{a}/{b:g}": v for (a, b), v in s.items()} for n, s in g.items()}, "passing": [o[4] for o in ok], "cheapest_passing": ok[0][4] if ok else None,
           "cheapest_passing_with_table4": next((o[4] for o in ok if o[0] == 4), None)}
    json.dump(res, open(outp, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("passing", "cheapest_passing", "cheapest_passing_with_table4")}))


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        js = jobs()
        open(sys.argv[2], "w").write("\n".join(f"{i}\t{c}" for i, c in js) + "\n")
        print(len(js), "jobs")
    else:
        select(sys.argv[2], sys.argv[3])
