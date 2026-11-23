"""Stage 3.2 job enumeration (DRAFT prereg prereg/hw/S3_confirmatory_DRAFT.md; scope B enlarged): jobs_s32.tsv (executable), jobs_s32_smoke.tsv, plan table, cost.
Configurations are the Stage 3.1 / 3.1b selections (STAGE3_1_RESULTS.md): ours_stack = I11 + Kc2 (c 0, K 0.25n, L 10) + RNG-free escalating offset esc A (esc_step 1, esc_max 2), nominal condition
simulated with the incremental field (sim_incremental, refresh 200) and leaky-zero screening at 8 nA (screening only, correction table 0); B3_sel = T_start x2.5, T_final x0.0625 (knob 1);
B3_h8 = H8-registered. Row 1 is the R13 identity gate (fresh tag-12 spec at p3n960); tiled nominal jobs at >= 960 lanes depend on it.
Usage: python -I scripts/testing/gen_jobs_s32.py --tsv jobs_s32.tsv [--smoke-tsv F] [--plan F]"""
from __future__ import annotations

import argparse
import json
import sys

PY = "$PY -I scripts/testing/run_s1.py"
EVAL = "$PY -I scripts/testing/evaluate_s3.py"
OUT, SMOKE_OUT = "sim/out/hw/s32", "sim/out/hw/s32_smoke"
TAG = 12
MARGIN, CHUNK_S = 1.3, 600
GATE_ID = "0.5.r13_960"
SIZES = {"p3n480": (64, 3), "p4n480": (64, 3), "p3n960": (64, 2), "maxcut": (20, 5)}
KEYS = {"p3n480": [str(3301 + i) for i in range(64)], "p4n480": [str(3401 + i) for i in range(64)], "p3n960": [str(3301 + i) for i in range(64)],
        "maxcut": [f"R{6001 + i}" for i in range(20)]}
CFG = {
    "ours_stack": {"kick_c": 0, "knob": 0.25, "esc_step": 1, "esc_max": 2, "sim_incremental": True, "sim_refresh": 200},
    "ours_new": {"kick_c": 0, "knob": 0.25},
    "B3_sel": {"pct_hi": 90, "pct_lo": 5, "knob": 1.0, "t_hi_mult": 2.5, "t_lo_mult": 0.0625},
    "B3_h8": {"pct_hi": 90, "pct_lo": 5, "knob": 0.5},
    "B1_sel": {"pct_hi": 90, "pct_lo": 5, "knob": 0.5, "t_hi_mult": 2.0, "t_lo_mult": 0.5},
}
LABEL = {"ours_stack": "ours_kc2_i11", "ours_new": "ours_kc2_i11", "B3_sel": "B3_v2", "B3_h8": "B3_v2", "B1_sel": "B1_best"}
MIT = {"ours_stack": "wv+diff+cal+scr8", "ours_new": "wv+diff+cal", "B1_sel": "wv+cal"}
# measured cloud s/run (Stages 1-2); ours_stack +10 % for the escape hook; 960 / Max-Cut nominal tiled are estimates (gate job and the S1 smoke: 122 s at 1 sweep for gk)
SPR = {("ours_stack", "p3n480"): 38.0, ("ours_stack", "p4n480"): 44.0, ("ours_stack", "p3n960"): 320.0, ("ours_stack", "maxcut"): 100.0,
       ("ours_new", "p3n480"): 34.4, ("ours_new", "p4n480"): 39.6,
       ("B3_sel", "p3n480"): 6.7, ("B3_sel", "p4n480"): 7.7, ("B3_sel", "p3n960"): 32.0, ("B3_sel", "maxcut"): 9.2,
       ("B3_h8", "p3n480"): 6.7, ("B3_h8", "p4n480"): 7.7, ("B3_h8", "p3n960"): 32.0, ("B3_h8", "maxcut"): 9.2,
       ("B1_sel", "p3n480"): 50.0, ("B1_sel", "p4n480"): 57.5}
RSS = {("ours_stack", "p3n960"): 6.5, ("ours_stack", "maxcut"): 6.5, ("ours_stack", "p3n480"): 3.0, ("ours_stack", "p4n480"): 3.0, ("ours_new", "p3n480"): 3.0, ("ours_new", "p4n480"): 3.0,
       ("B1_sel", "p3n480"): 1.5, ("B1_sel", "p4n480"): 1.5}


def plan():
    # report-only arms (ours_new bridge, B1_sel) run on p3n480 only (cost trim to keep the worst case <= Rs 150 on 16 vCPU)
    cells = [("ours_stack", c) for c in SIZES] + [("ours_new", "p3n480")]
    cells += [(b, c) for b in ("B3_sel", "B3_h8") for c in SIZES] + [("B1_sel", "p3n480")]
    return cells


def cond_of(arm):
    return "ideal" if arm.startswith("B3") else "nominal"


def rows():
    out = [{"id": GATE_ID, "kind": "gate", "est_s": 2 * (86 + 1.5 * 320) * MARGIN, "rss": 7.0, "deps": "", "keys": ["3301"], "arm": "", "cell": "p3n960", "seeds": 2, "tile": 0}]
    for arm, cell in plan():
        n, seeds = SIZES[cell]
        keys = KEYS[cell][:n]
        per = SPR[(arm, cell)] * seeds * MARGIN
        k = max(1, int(CHUNK_S // per))
        tile = 256 if arm.startswith("ours") else 0
        gated = bool(tile) and cell in ("p3n960", "maxcut")
        for i, ks in enumerate(chunks(keys, k)):
            nch = -(-len(keys) // k)
            out.append({"id": f"s32.{arm}.{cell}" + (f".p{i:02d}" if nch > 1 else ""), "kind": "run", "arm": arm, "cell": cell, "keys": ks, "seeds": seeds, "tile": tile,
                        "est_s": SPR[(arm, cell)] * len(ks) * seeds * MARGIN, "rss": RSS.get((arm, cell), 0.8 if cell == "maxcut" or "960" in cell else 0.6), "deps": GATE_ID if gated else ""})
    out.append({"id": "report_s32", "kind": "report", "est_s": 600, "rss": 4.0, "deps": "*", "keys": [], "arm": "", "cell": "", "seeds": 0})
    return out


def chunks(xs, k):
    return [xs[i:i + k] for i in range(0, len(xs), k)]


def cmd(r, out, smoke):
    if r["kind"] == "gate":
        return f"{PY} gate --id {r['id']} --out {out}/{r['id']}.json --family {'p3n480' if smoke else 'p3n960'} --key 3301 --tag {TAG}" + (" --smoke" if smoke else "")
    if r["kind"] == "report":
        return f"{EVAL} --records {out}/records --out {out}/s32_report.md" + (" --smoke" if smoke else "")
    cf = ",".join(f"{k}={json.dumps(v) if not isinstance(v, bool) else str(v).lower()}" for k, v in CFG[r["arm"]].items())
    cond = cond_of(r["arm"])
    fam = "maxcut" if r["cell"] == "maxcut" else r["cell"]
    keys = ",".join(r["keys"][:1] if smoke else r["keys"])
    return (f"{PY} run --id {r['id']} --stage s32 --arm {r['arm']} --cid {r['arm']} --label {LABEL[r['arm']]} --family {fam} --cell {r['cell']} --cond {cond} "
            f"--mit {MIT.get(r['arm'], 'none') if cond == 'nominal' else 'none'} --shares {0.5 if cond == 'nominal' else 0} --keys {keys} --seeds {1 if smoke else r['seeds']} --k 1 "
            f"--tile {r['tile']} --cfg {cf} --tag {TAG} --out {out}/{r['id']}.jsonl --records {out}/records" + (" --sweeps 1" if smoke else ""))


def tsv(rs, smoke):
    out = []
    for r in rs:
        est = max(0.2, r["est_s"] / 60)
        tmo = min(60.0, max(10.0, est * 2.5 + 5))
        rss = r["rss"]
        if smoke:
            est, tmo = 0.5, 10.0
            rss = min(rss, 5.7) if rss >= 3 else 1.5
        out.append("\t".join([r["id"], "par", f"{rss:.1f}", f"{est:.1f}", f"{tmo:.0f}", cmd(r, SMOKE_OUT if smoke else OUT, smoke), r["deps"]]))
    return out


def smoke_rows(rs):
    seen, out = set(), []
    for r in rs:
        if r["kind"] != "run":
            out.append(r)
            continue
        sig = (r["arm"], r["cell"], r["tile"])
        if sig in seen:
            continue
        seen.add(sig)
        out.append(dict(r, keys=r["keys"][:1], seeds=1))
    ids = {r["id"] for r in out}
    return [dict(r, deps=",".join(x for x in r["deps"].split(",") if x and (x in ids or x == "*"))) for r in out]


def makespan(rs, slots, mem_gb):
    import heapq
    done, pend, run, t = set(), list(rs), [], 0.0
    ids = [r["id"] for r in rs]

    def ready(r):
        for d in filter(None, r["deps"].split(",")):
            if d == "*":
                if any(x not in done for x in ids if x != r["id"]):
                    return False
            elif d not in done:
                return False
        return True
    while pend or run:
        used = sum(x[2] for x in run)
        for r in list(pend):
            if len(run) < slots and used + r["rss"] <= mem_gb and ready(r):
                heapq.heappush(run, (t + max(0.2, r["est_s"] / 60), r["id"], r["rss"]))
                pend.remove(r)
        if not run:
            break
        t, rid, _ = heapq.heappop(run)
        done.add(rid)
    return t


def cost(rs):
    out = {"cpu_h": round(sum(r["est_s"] for r in rs) / 3600, 1)}
    for v, rate, mem in ((16, 32.14, 53.0), (32, 64.28, 108.0)):
        ms = makespan(rs, v, mem)
        out[v] = {"makespan_min": round(ms), "expected_rs": round((0.3 + 0.15 + ms / 60 + 0.1) * rate)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--smoke-tsv")
    ap.add_argument("--plan")
    a = ap.parse_args()
    rs = rows()
    hdr = "# id\tmode\trss_gb\test_min\ttimeout_min\tcommand\tdeps\n# Stage 3.2 (DRAFT, scope B enlarged, energy + success primary). Dependencies as Stage 1/2.\n"
    if a.tsv:
        open(a.tsv, "w").write(hdr + "\n".join(tsv(rs, False)) + "\n")
    if a.smoke_tsv:
        open(a.smoke_tsv, "w").write(hdr + "\n".join(tsv(smoke_rows(rs), True)) + "\n")
    if a.plan:
        open(a.plan, "w").write("job_id\tkind\tarm\tcell\tinstances\tseeds\test_job_min\trss_gb\tdeps\n" + "\n".join(
            f"{r['id']}\t{r['kind']}\t{r.get('arm', '')}\t{r.get('cell', '')}\t{len(r['keys'])}\t{r['seeds']}\t{r['est_s'] / 60:.1f}\t{r['rss']}\t{r['deps']}" for r in rs) + "\n")
    c = cost(rs)
    print(f"# jobs {len(rs)}; est CPU-h {c['cpu_h']} (margin {MARGIN}); makespan 16 vCPU {c[16]['makespan_min']} min -> Rs {c[16]['expected_rs']}; 32 vCPU {c[32]['makespan_min']} min -> Rs {c[32]['expected_rs']}; "
          f"longest job {max(r['est_s'] for r in rs) / 60:.0f} min", file=sys.stderr)


if __name__ == "__main__":
    main()
