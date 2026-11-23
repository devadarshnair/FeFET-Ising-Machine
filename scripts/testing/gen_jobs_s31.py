"""Stage 3.1 + 3.1b cloud job enumeration (the Stage 3 plan section 4): 78 tuning jobs (s3_1_jobs.py), 36 T-1 stack parameter jobs (s3_1b_jobs.py), selection steps SEL.31 / SEL.31b that run on the box,
and a report row. Dependencies (column 7): SEL.31 <- every 3.1 job; SEL.31b <- every 3.1b job; report_s31 <- everything. No gate row: all jobs are ideal-device (3.1) or untiled nominal p3n240 (3.1b).
Usage: python -I scripts/testing/gen_jobs_s31.py --tsv jobs_s31.tsv [--smoke-tsv F] [--plan F]"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import s3_1_jobs as j1  # noqa: E402
import s3_1b_jobs as j1b  # noqa: E402

PY = "$PY -I scripts/testing"
MARGIN = 1.3
# measured cloud s/run (Stage 1/2) with a +10 % allowance for the escape hooks (3.0: burst / adaptive-L runs were 5-15 % slower)
SPR = {("ours", "p3n480"): 13.0, ("ours", "p4n480"): 15.5, ("ours", "p3n960"): 95.0, ("B3", "p3n480"): 6.7, ("B3", "p4n480"): 7.7, ("B3", "p3n960"): 32.0, ("t1", "p3n240"): 5.6}
RSS = {"p3n960": 1.0}


def rows():
    out = []
    for jid, cmd in j1.jobs():
        arm = jid.split(".")[1]
        cell = jid.rsplit(".", 1)[1]
        keys, seeds = j1.CELLS[cell]
        est = SPR[("ours" if arm.startswith("ours") else "B3", cell)] * len(keys) * seeds * MARGIN
        out.append({"id": jid, "est_s": est, "rss": RSS.get(cell, 0.6), "deps": "", "cmd": cmd, "group": "31"})
    for jid, cmd in j1b.jobs():
        out.append({"id": jid, "est_s": SPR[("t1", "p3n240")] * 12 * 3 * MARGIN, "rss": 1.0, "deps": "", "cmd": cmd, "group": "31b"})
    ids31 = [r["id"] for r in out if r["group"] == "31"]
    ids31b = [r["id"] for r in out if r["group"] == "31b"]
    out.append({"id": "SEL.31", "est_s": 60, "rss": 1.0, "deps": ",".join(ids31), "group": "sel",
                "cmd": f"{PY}/s3_1_jobs.py select {j1.OUT} {j1.OUT}/selection_31.json"})
    out.append({"id": "SEL.31b", "est_s": 60, "rss": 1.0, "deps": ",".join(ids31b), "group": "sel",
                "cmd": f"{PY}/s3_1b_jobs.py select {j1b.OUT} {j1b.OUT}/selection_31b.json"})
    out.append({"id": "report_s31", "est_s": 90, "rss": 2.0, "deps": "*", "group": "rep",
                "cmd": f"{PY}/evaluate_s31.py --dir31 {j1.OUT} --dir31b {j1b.OUT} --out {j1.OUT}/s31_report.md"})
    return out


def smoke(r: dict) -> dict:
    """Tiny-budget copy: 1 instance, 1 seed, 1 sweep, outputs under *_smoke; selection / report read the smoke dirs."""
    c = re.sub(r"sim/out/hw/s31b(?!_)", "sim/out/hw/s31b_smoke", r["cmd"])
    c = re.sub(r"sim/out/hw/s31(?![b_])", "sim/out/hw/s31_smoke", c)
    if r["group"] in ("31", "31b"):
        c = re.sub(r"--keys (\S+)", lambda m: "--keys " + m.group(1).split(",")[0], c)
        c = re.sub(r"--seeds \d+", "--seeds 1", c) + " --sweeps 1"
    return dict(r, cmd=c)


def tsv(rs, is_smoke):
    out = []
    for r in rs:
        r = smoke(r) if is_smoke else r
        est = 0.5 if is_smoke else max(0.2, r["est_s"] / 60)
        tmo = 10.0 if is_smoke else min(60.0, max(10.0, est * 2.5 + 5))
        rss = (1.5 if r["rss"] < 2 else 2.0) if is_smoke else r["rss"]
        out.append("\t".join([r["id"], "par", f"{rss:.1f}", f"{est:.1f}", f"{tmo:.0f}", r["cmd"], r["deps"]]))
    return out


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--smoke-tsv")
    ap.add_argument("--plan")
    a = ap.parse_args()
    rs = rows()
    hdr = "# id\tmode\trss_gb\test_min\ttimeout_min\tcommand\tdeps\n# Stage 3.1 + 3.1b tuning (tuning-only, ideal device / untiled nominal p3n240). Selection steps run on the box.\n"
    if a.tsv:
        open(a.tsv, "w").write(hdr + "\n".join(tsv(rs, False)) + "\n")
    if a.smoke_tsv:
        open(a.smoke_tsv, "w").write(hdr + "\n".join(tsv(rs, True)) + "\n")
    if a.plan:
        open(a.plan, "w").write("job_id\tgroup\test_min\trss_gb\n" + "\n".join(f"{r['id']}\t{r['group']}\t{r['est_s'] / 60:.1f}\t{r['rss']}" for r in rs) + "\n")
    cpu = sum(r["est_s"] for r in rs) / 3600
    ms = makespan(rs, 16, 53.0)
    print(f"# jobs {len(rs)}; est CPU-h {cpu:.1f} (margin {MARGIN}); simulated makespan on 16 slots {ms:.0f} min; longest job {max(r['est_s'] for r in rs) / 60:.0f} min", file=sys.stderr)


if __name__ == "__main__":
    main()
