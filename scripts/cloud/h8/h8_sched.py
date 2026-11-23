#!/usr/bin/env python3
"""H8 job scheduler (memory-aware, resumable). Usage: h8_sched.py --tsv jobs.tsv --run RUNDIR --wt WORKTREE --py PYTHON [--slots N] [--mem-frac 0.85 | --mem-gb G] [--plan]
[--deadline-min M] [--hard-min H]

Rows of the TSV: id, mode, rss_gb, est_min, timeout_min, command, smoke_command. mode par = launched in file order whenever a slot AND the declared
rss fit (sum of declared rss of running jobs <= mem_frac x MemTotal); mode all = barrier: starts only when every earlier row has a done marker,
runs alone. Done marker RUNDIR/done/<id> (rc 0), failure marker RUNDIR/failed/<id>. No new job after the deadline; at the hard limit running jobs
are killed (billing cap). A job that cannot fit even on an empty machine is refused loudly, never silently skipped.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def mem_total_gb() -> float:
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemTotal"):
            return int(ln.split()[1]) / 1048576.0
    return 8.0


def admission_budget(mem_gb: float, mem_frac: float) -> float:
    """Declared-RSS admission budget: the profile budget (or frac of MemTotal), never more than MemTotal - 4 GiB (a '64 GB' box reports ~61-62 GiB)."""
    total = mem_total_gb()
    return min(mem_gb or total * mem_frac, total - 4.0)


def simulate(rows: list[dict], slots: int, budget_gb: float) -> dict:
    """Event simulation of the scheduler's policy (file order, first fit under slots and declared-RSS budget, barrier after everything) with the
    estimated minutes of each row: returns makespan (min), peak concurrency / RSS. Used for --plan and for the launch guard of go_h8.sh."""
    import heapq
    t, running, peak_n, peak_gb, pend = 0.0, [], 0, 0.0, [r for r in rows if r["mode"] == "par"]
    while pend or running:
        used = sum(g for _, _, g in running)
        for r in list(pend):
            if len(running) < slots and used + r["rss"] <= budget_gb:
                heapq.heappush(running, (t + r["est"], r["id"], r["rss"]))
                used += r["rss"]
                pend.remove(r)
        peak_n, peak_gb = max(peak_n, len(running)), max(peak_gb, used)
        if not running:
            break
        t, _, _ = heapq.heappop(running)
    bar = sum(r["est"] for r in rows if r["mode"] == "all")
    return {"makespan_min": round(t + bar, 1), "jobs_min": round(t, 1), "peak_concurrent": peak_n, "peak_rss_gb": round(peak_gb, 1)}


def read_rows(tsv: str) -> list[dict]:
    rows = []
    for ln in open(tsv):
        if not ln.strip() or ln.startswith("#"):
            continue
        f = ln.rstrip("\n").split("\t")
        rows.append({"id": f[0], "mode": f[1], "rss": float(f[2]), "est": float(f[3]), "tmo": float(f[4]), "cmd": f[5]})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--wt", required=True)
    ap.add_argument("--py", required=True)
    ap.add_argument("--slots", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--mem-frac", type=float, default=0.85)
    ap.add_argument("--mem-gb", type=float, default=0.0, help="absolute admission budget in GB (profile 16: 60 of 64 GB); overrides --mem-frac")
    ap.add_argument("--plan", action="store_true", help="only simulate the schedule from the estimated minutes; exit 1 if it exceeds --deadline-min")
    ap.add_argument("--deadline-min", type=float, default=1e9)
    ap.add_argument("--hard-min", type=float, default=1e9)
    a = ap.parse_args()
    run = Path(a.run)
    for d in ("done", "failed", "logs"):
        (run / d).mkdir(parents=True, exist_ok=True)
    rows = read_rows(a.tsv)
    budget = admission_budget(a.mem_gb, a.mem_frac)
    if a.plan:
        too = [r["id"] for r in rows if r["rss"] > budget]
        if too:
            print(f"PLAN REFUSED: {len(too)} job(s) declare more RSS than the budget {budget:.0f} GB (first {too[:3]})")
            return 2
        sim = simulate(rows, a.slots, budget)
        ok = sim["makespan_min"] <= a.deadline_min
        print(f"PLAN slots={a.slots} budget={budget:.0f} GB: makespan {sim['makespan_min']} min (deadline {a.deadline_min}), peak {sim['peak_concurrent']} jobs / {sim['peak_rss_gb']} GB -> {'FITS' if ok else 'EXCEEDS'}")
        return 0 if ok else 1
    too_big = [r["id"] for r in rows if r["rss"] > budget]
    if too_big:
        print(f"REFUSED: {len(too_big)} job(s) declare more RSS than the memory budget {budget:.0f} GB (first: {too_big[:3]})", flush=True)
        return 2
    t_start = float((run / "sched.start").read_text()) if (run / "sched.start").exists() else time.time()
    (run / "sched.start").write_text(str(t_start))
    log = open(run / "queue.log", "a")

    def L(m: str) -> None:
        s = time.strftime("[%F %T UTC] ", time.gmtime()) + m
        print(s, flush=True)
        log.write(s + "\n")
        log.flush()
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", NUMBA_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1",
               NUMBA_CACHE_DIR=str(Path(a.wt) / "sim/out/numba_cache"), PY=a.py)
    done = lambda i: (run / "done" / i).exists()  # noqa: E731
    pending = [r for r in rows if not done(r["id"])]
    L(f"start: {len(rows)} rows, {len(pending)} pending, {a.slots} slots, memory budget {budget:.0f} GB")
    running: dict = {}
    killed = False
    while pending or running:
        el = (time.time() - t_start) / 60
        for jid, (p, t0, r) in list(running.items()):
            rc = p.poll()
            if rc is None:
                continue
            del running[jid]
            L(f"end {jid} rc={rc} {int(time.time() - t0)}s")
            if rc == 0:
                (run / "done" / jid).write_text(time.strftime("%F %T UTC", time.gmtime()) + "\n")
                (run / "failed" / jid).unlink(missing_ok=True)
            else:
                (run / "failed" / jid).write_text(f"rc={rc}\n")
        if el > a.hard_min and running and not killed:
            L(f"HARD LIMIT {a.hard_min} min: killing {len(running)} running job(s)")
            for p, _, _ in running.values():
                subprocess.run(["pkill", "-TERM", "-P", str(p.pid)])
                p.terminate()
            killed = True
        used = sum(r["rss"] for _, _, r in running.values())
        for r in list(pending):
            if r["mode"] == "all":
                if running:
                    break                                   # a barrier waits for everything launched before it
                earlier = [x["id"] for x in rows[:rows.index(r)]]
                miss = [i for i in earlier if not done(i)]
                if miss:
                    L(f"BARRIER {r['id']} not run: {len(miss)} earlier job(s) without a done marker (first: {miss[:5]}); stopping")
                    pending.clear()
                    break
            elif len(running) >= a.slots or used + r["rss"] > budget or el > a.deadline_min or killed:
                continue
            pending.remove(r)
            (run / "failed" / r["id"]).unlink(missing_ok=True)
            cmd = r["cmd"].replace("$PY", a.py)
            L(f"start {r['id']} rss={r['rss']} tmo={r['tmo']:.0f}m")
            p = subprocess.Popen(["timeout", "-k", "30", f"{r['tmo']:.0f}m", "nice", "-n", "10", "bash", "-c", cmd], cwd=a.wt, env=env,
                                 stdout=open(run / "logs" / (r["id"] + ".log"), "w"), stderr=subprocess.STDOUT)
            running[r["id"]] = (p, time.time(), r)
            used += r["rss"]
            if r["mode"] == "all":
                break
        if el > a.deadline_min and not running:
            L(f"DEADLINE {a.deadline_min} min: {len(pending)} row(s) not started")
            break
        time.sleep(2)
    n_done = sum(done(r["id"]) for r in rows)
    fails = sorted(x.name for x in (run / "failed").iterdir())
    L(f"finished: {n_done}/{len(rows)} done, failed {len(fails)}: {fails[:8]}")
    (run / ("H8_DONE" if n_done == len(rows) else "H8_INCOMPLETE")).write_text(f"{n_done}/{len(rows)}\n")
    return 0 if n_done == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
