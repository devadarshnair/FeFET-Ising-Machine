"""Stage 2 job enumeration (DRAFT prereg prereg/hw/S2_confirmatory_DRAFT.md; 480-only scope, energy primary): jobs_s2.tsv (executable), jobs_s2_smoke.tsv, plan table, cost.
Dependencies as Stage 1 (column 7: ids / prefix* / *). Row 1 is the R13 identity gate (tiled-256 nominal vs ideal, fresh tag-11 spec at p3n480); every nominal tiled job waits for it.
Usage: python -I scripts/testing/gen_jobs_s2.py --tsv jobs_s2.tsv [--smoke-tsv F] [--plan F] [--summary]
"""
from __future__ import annotations

import argparse
import json
import sys

PY = "$PY -I scripts/testing/run_s1.py"
EVAL = "$PY -I scripts/testing/evaluate_s2.py"
OUT, SMOKE_OUT = "sim/out/hw/s2", "sim/out/hw/s2_smoke"
TAG = 11
MARGIN, CHUNK_S = 1.3, 600
GATE_ID = "0.5.r13_480"
N_MAIN, SEEDS_MAIN = 64, 3          # p3n480 / p4n480 (ETS power: instances over seeds, internal review item 11.2.1)
N_NOREG, SEEDS_NOREG = 16, 3        # p3n240 / p4n240 report-only
KEYS = {"p3": [str(2301 + i) for i in range(64)], "p4": [str(2401 + i) for i in range(64)]}
# measured single-core s/run (Stage 1, 16 vCPU cloud instance). B1 bit-sliced n480 is extrapolated (p3n240: 12.7 s vs B1 6.5 s).
S = {("ours", "p3n480", "nom"): 34.4, ("ours", "p3n480", "id"): 9.8, ("B3", "p3n480", "id"): 6.7, ("B1", "p3n480", "nom"): 50.0, ("B1bs", "p3n480", "nom"): 100.0,
     ("ours", "p3n240", "nom"): 4.6, ("ours", "p3n240", "id"): 2.5, ("B3", "p3n240", "id"): 1.5, ("B1", "p3n240", "nom"): 6.5}
RSS = {("ours", "nom", "480"): 3.0, ("ours", "id", "480"): 0.6, ("B3", "id", "480"): 0.6, ("B1", "nom", "480"): 1.5, ("B1bs", "nom", "480"): 1.5,
       ("ours", "nom", "240"): 1.0, ("ours", "id", "240"): 0.5, ("B3", "id", "240"): 0.5, ("B1", "nom", "240"): 1.0}
CFG = {   # Stage 1b selections (unchanged by the edge probe); p4 uses the transferred p3 configuration for every arm
    "ours_new": {"kick_c": 0, "knob": 0.25},
    "ours_h8": {"kick_c": 0, "knob": 2},
    "B3_sel": {"pct_hi": 90, "pct_lo": 5, "knob": 1.0, "t_hi_mult": 1.5, "t_lo_mult": 0.0625},
    "B3_h8": {"pct_hi": 90, "pct_lo": 5, "knob": 0.5},
    "B1_sel": {"pct_hi": 90, "pct_lo": 5, "knob": 0.5, "t_hi_mult": 2.0, "t_lo_mult": 0.5},
    "B1_bs": {"pct_hi": 90, "pct_lo": 5, "knob": 0.5, "t_hi_mult": 2.0, "t_lo_mult": 0.5},
    "ours_ets": {"kick_c": 0.04, "knob": 0.125},
    "B3_ets": {"pct_hi": 90, "pct_lo": 5, "knob": 1.0, "t_hi_mult": 1.5, "t_lo_mult": 0.015625},
}
LABEL = {"ours_new": "ours_kc2_i11", "ours_h8": "ours_kc2_i11", "ours_ets": "ours_kc2_i11", "B3_sel": "B3_v2", "B3_h8": "B3_v2", "B3_ets": "B3_v2", "B1_sel": "B1_best", "B1_bs": "B1_best"}
CLASS = {"ours_new": "ours", "ours_h8": "ours", "ours_ets": "ours", "B3_sel": "B3", "B3_h8": "B3", "B3_ets": "B3", "B1_sel": "B1", "B1_bs": "B1bs"}


def plan():
    """(arm, cell, cond) cells: cond in ideal | nominal."""
    cells = []
    for pf, n in (("p3", "n480"), ("p4", "n480")):
        c = f"{pf}{n}"
        for a in ("ours_new", "ours_h8"):
            cells += [(a, c, "ideal"), (a, c, "nominal")]
        cells += [("B3_sel", c, "ideal"), ("B3_h8", c, "ideal"), ("B1_sel", c, "nominal")]
    cells += [("B1_bs", "p3n480", "nominal"), ("ours_ets", "p3n480", "nominal"), ("B3_ets", "p3n480", "ideal")]      # B1_bs and the ETS-selected sensitivity: p3n480 only
    for pf in ("p3", "p4"):
        c = f"{pf}n240"
        for a in ("ours_new", "ours_h8"):
            cells += [(a, c, "ideal"), (a, c, "nominal")]
        cells += [("B3_sel", c, "ideal"), ("B3_h8", c, "ideal"), ("B1_sel", c, "nominal")]
    return cells


def spr(arm: str, cell: str, cond: str) -> float:
    base = cell.replace("p4", "p3")
    x = 1.15 if cell.startswith("p4") else 1.0
    cl = CLASS[arm]
    key = (cl if cl != "B1bs" else "B1bs", base, "nom" if cond == "nominal" else "id")
    if key not in S:                         # B3 nominal = ideal (digital)
        key = (cl, base, "id")
    return S[key] * x


def rss_of(arm: str, cell: str, cond: str) -> float:
    sz = "480" if "480" in cell else "240"
    cl = CLASS[arm]
    return RSS.get((cl, "nom" if cond == "nominal" else "id", sz), RSS[("B3", "id", sz)] if cl == "B3" else 1.0)


def rows():
    out = [{"id": GATE_ID, "kind": "gate", "est_s": 2 * (S[("ours", "p3n480", "id")] + 1.5 * S[("ours", "p3n480", "nom")]) * MARGIN, "rss": 4.0, "deps": "", "keys": ["2301"], "arm": "", "cell": "p3n480", "cond": "nominal", "seeds": 2}]
    for arm, cell, cond in plan():
        pf = cell[:2]
        n = N_MAIN if "480" in cell else N_NOREG
        seeds = SEEDS_MAIN if "480" in cell else SEEDS_NOREG
        keys = KEYS[pf][:n]
        per = spr(arm, cell, cond) * seeds * MARGIN
        k = max(1, int(CHUNK_S // per))
        chunks = [keys[i:i + k] for i in range(0, len(keys), k)]
        tile = 256 if (CLASS[arm] == "ours" and cond == "nominal" and "480" in cell) else 0
        for i, ks in enumerate(chunks):
            jid = f"s2.{arm}.{cell}.{cond}" + (f".p{i:02d}" if len(chunks) > 1 else "")
            out.append({"id": jid, "kind": "run", "arm": arm, "cell": cell, "cond": cond, "keys": ks, "seeds": seeds, "tile": tile,
                        "est_s": spr(arm, cell, cond) * len(ks) * seeds * MARGIN, "rss": rss_of(arm, cell, cond), "deps": GATE_ID if tile else ""})
    out.append({"id": "report_s2", "kind": "report", "est_s": 180, "rss": 3.0, "deps": "*", "keys": [], "arm": "", "cell": "", "cond": "", "seeds": 0})
    return out


def mit_of(arm: str, cond: str) -> str:
    if cond == "ideal" or CLASS[arm] == "B3":
        return "none"
    return {"ours": "wv+diff+cal", "B1": "wv+cal", "B1bs": "wv+diff+cal+bin"}[CLASS[arm]]


def cmd(r: dict, out: str, smoke: bool) -> str:
    if r["kind"] == "gate":
        return f"{PY} gate --id {r['id']} --out {out}/{r['id']}.json --family p3n480 --key 2301 --tag {TAG}" + (" --smoke" if smoke else "")
    if r["kind"] == "report":
        return f"{EVAL} --records {out}/records --out {out}/s2_report.md" + (" --smoke" if smoke else "")
    cf = ",".join(f"{k}={json.dumps(v)}" for k, v in CFG[r["arm"]].items())
    fam = r["cell"]
    share = 0.5 if r["cond"] == "nominal" else 0
    keys = ",".join(r["keys"][:1] if smoke else r["keys"])
    return (f"{PY} run --id {r['id']} --stage s2 --arm {r['arm']} --cid {r['arm']} --label {LABEL[r['arm']]} --family {fam} --cell {r['cell']} --cond {r['cond']} "
            f"--mit {mit_of(r['arm'], r['cond'])} --shares {share} --keys {keys} --seeds {1 if smoke else r['seeds']} --k 1 --tile {r['tile']} --cfg {cf} --tag {TAG} "
            f"--out {out}/{r['id']}.jsonl --records {out}/records" + (" --sweeps 1" if smoke else ""))


def tsv(rs: list[dict], smoke: bool) -> list[str]:
    out = []
    for r in rs:
        est = max(0.2, r["est_s"] / 60)
        tmo = min(60.0, max(10.0, est * 2.5 + 5))
        rss = r["rss"]
        if smoke:
            est, tmo = 0.5, 10.0
            rss = min(rss, 4.0) if rss >= 3 else 1.5
        out.append("\t".join([r["id"], "par", f"{rss:.1f}", f"{est:.1f}", f"{tmo:.0f}", cmd(r, SMOKE_OUT if smoke else OUT, smoke), r["deps"]]))
    return out


def smoke_rows(rs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rs:
        if r["kind"] != "run":
            out.append(r)
            continue
        sig = (r["arm"], r["cell"], r["cond"], r["tile"])
        if sig in seen:
            continue
        seen.add(sig)
        out.append(dict(r, keys=r["keys"][:1], seeds=1))
    ids = {r["id"] for r in out}
    res = []
    for r in out:
        d = ",".join(x for x in r["deps"].split(",") if x and (x in ids or x == "*"))
        res.append(dict(r, deps=d))
    return res


def makespan(rs: list[dict], slots: int, mem_gb: float) -> float:
    import heapq
    done, pend, running, t = set(), list(rs), [], 0.0
    ids = [r["id"] for r in rs]
    def ready(r):
        for d in filter(None, r["deps"].split(",")):
            if d == "*":
                if any(x not in done for x in ids if x != r["id"]):
                    return False
            elif d not in done:
                return False
        return True
    while pend or running:
        used = sum(x[2] for x in running)
        for r in list(pend):
            if len(running) < slots and used + r["rss"] <= mem_gb and ready(r):
                heapq.heappush(running, (t + max(0.2, r["est_s"] / 60), r["id"], r["rss"]))
                used += r["rss"]
                pend.remove(r)
        if not running:
            break
        t, rid, _ = heapq.heappop(running)
        done.add(rid)
    return t


def cost(rs: list[dict]) -> dict:
    cpu_h = sum(r["est_s"] for r in rs) / 3600
    out = {"cpu_h": round(cpu_h, 1)}
    for v, rate, mem in ((16, 32.14, 53.0), (32, 64.28, 108.0)):
        ms = makespan(rs, v, mem)
        out[v] = {"makespan_min": round(ms), "expected_rs": round((0.3 + 0.15 + ms / 60 + 0.1) * rate)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--smoke-tsv")
    ap.add_argument("--plan")
    a = ap.parse_args()
    rs = rows()
    hdr = "# id\tmode\trss_gb\test_min\ttimeout_min\tcommand\tdeps\n# Stage 2 (DRAFT, 480-only, energy primary). Dependencies as Stage 1.\n"
    if a.tsv:
        open(a.tsv, "w").write(hdr + "\n".join(tsv(rs, False)) + "\n")
    if a.smoke_tsv:
        open(a.smoke_tsv, "w").write(hdr + "\n".join(tsv(smoke_rows(rs), True)) + "\n")
    if a.plan:
        open(a.plan, "w").write("job_id\tkind\tarm\tcell\tcond\tinstances\tseeds\test_job_min\trss_gb\tdeps\n" + "\n".join(
            f"{r['id']}\t{r['kind']}\t{r.get('arm','')}\t{r.get('cell','')}\t{r.get('cond','')}\t{len(r['keys'])}\t{r['seeds']}\t{r['est_s'] / 60:.1f}\t{r['rss']}\t{r['deps']}" for r in rs) + "\n")
    c = cost(rs)
    print(f"# jobs {len(rs)}; est CPU-h {c['cpu_h']} (incl. margin {MARGIN}); simulated makespan 16 vCPU {c[16]['makespan_min']} min -> Rs {c[16]['expected_rs']}; "
          f"32 vCPU {c[32]['makespan_min']} min -> Rs {c[32]['expected_rs']} (set-up 0.3 h + gate 0.15 h + makespan + collect 0.1 h); longest job {max(r['est_s'] for r in rs) / 60:.0f} min", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
