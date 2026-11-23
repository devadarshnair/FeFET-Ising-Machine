"""P6.02 testing-phase compute budget (planning arithmetic only; runs nothing, reads no result).

Re-budgeted 16 Nov 2026 IST from the Stage 1 cloud timing chunks (32 vCPU IN1, scripts/testing/time_chunk.py, 800-spin Max-Cut G1:
ours 184 us/step at N = 1024 padded, B1 2115 at 800 spins, B3 47, B2 41; plan.CLOUD_TIME_CHUNK_US, re-mapped to the registered schedule by plan.LOCAL_RUNNER_US) and from the exact Stage 2 job
list (scripts/testing/gen_jobs_stage2.py), so the budget, the TSV and the runner cannot drift apart.

Timing basis (see plan.py): the cloud chunks were taken at the smoke temperatures, where ours skips most reads (I10), so 184 us/step is
not the cost of the registered percentile-rule schedules (a flip is accepted almost every step). The per-step costs used here are the
runner's own local timings under the registered schedule (per machine and family, ours padded to 1024/512/64 lanes, B1 per 32x32 tile
read, B3 per spin; H5 with the field wrapper), mapped to the cloud by the local/cloud ratio of the same time_chunk machines (x0.709).
The field read uses exact incremental column sums (scripts/testing/fastcim.py, bit-identical to cim_field; without it ours costs
~3.6 ms/step at 1024 lanes and B1 4.3 ms). The two scenarios are central and x1.5 (untimed per-family scaling, slower cloud cores).

Usage: python -I scripts/budget_p602.py          prints the markdown tables used in docs/hw/results/P6.02_budget.md
"""
from __future__ import annotations

import heapq
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "testing"))
import gen_jobs_stage2 as gj  # noqa: E402
import plan as pl  # noqa: E402

RATE_RS_PER_VCPU_H = 2.01
VCPU = 32
SETUP_H = 0.17                 # ~10 min set-up on a fresh instance (LAUNCH.md)
BARRIER_MIN = 2.0              # select_tuned / freeze_h2 evaluator run alone


def makespan_h(secs: list[float], workers: int = VCPU) -> float:
    """Greedy longest-first list scheduling on `workers` slots (what xargs -P over an LPT-ordered list does, up to dispatch order)."""
    heap = [0.0] * workers
    for s in sorted(secs, reverse=True):
        heapq.heappush(heap, heapq.heappop(heap) + s)
    return max(heap) / 3600


def phases(jobs):
    ph, cur = [], []
    for j in jobs:
        if j.mode == "all":
            ph.append(cur)
            cur = []
        else:
            cur.append(j)
    ph.append(cur)
    return ph


def table(scale: float = 1.0) -> dict:
    jobs = gj.all_jobs()
    ph = phases(jobs)
    names = ("ref + H2 tuning", "H2 test", "H5 + H3")
    rows = []
    wall = 0.0
    for n, js in zip(names, ph):
        secs = [j.secs * scale for j in js]
        ms = makespan_h(secs)
        wall += ms + BARRIER_MIN / 60
        rows.append((n, len(js), sum(j.n_runs for j in js), sum(secs) / 3600, ms))
    by = {}
    for j in jobs:
        if j.mode == "all":
            continue
        k = {"ref": "reference set R (MaxSAT)", "tune": "H2 tuning", "test": "H2 test", "h5": "H5", "h3": "H3"}[j.phase]
        a = by.setdefault(k, [0, 0, 0.0])
        a[0] += 1
        a[1] += j.n_runs
        a[2] += j.secs * scale / 3600
    total_cpu = sum(v[2] for v in by.values())
    return {"phases": rows, "sweeps": by, "cpu_h": total_cpu, "wall_h": wall + SETUP_H, "scale": scale}


def main() -> None:
    for scale, label in ((1.0, "central"), (1.5, "high (per-step cost x1.5: untimed N, power-off arms, H5 wrapper)")):
        t = table(scale)
        print(f"\n### scenario {label}")
        print("| sweep | jobs | runs | CPU-h | Rs at 2.01/vCPU-h (busy) |\n|---|---|---|---|---|")
        for k, (nj, nr, h) in t["sweeps"].items():
            print(f"| {k} | {nj} | {nr} | {h:.1f} | {h * RATE_RS_PER_VCPU_H:.0f} |")
        print(f"| **total** | {sum(v[0] for v in t['sweeps'].values())} | {sum(v[1] for v in t['sweeps'].values())} | **{t['cpu_h']:.1f}** "
              f"| **{t['cpu_h'] * RATE_RS_PER_VCPU_H:.0f}** |")
        print("\n| phase (barrier-separated) | jobs | runs | CPU-h | makespan h on 32 vCPU |\n|---|---|---|---|---|")
        for n, nj, nr, h, ms in t["phases"]:
            print(f"| {n} | {nj} | {nr} | {h:.1f} | {ms:.2f} |")
        billed = t["wall_h"] * VCPU * RATE_RS_PER_VCPU_H
        print(f"\nwall on 32 vCPU (phases + barriers + set-up): {t['wall_h']:.1f} h; billed {t['wall_h'] * VCPU:.0f} vCPU-h = Rs {billed:.0f}")
    j = [j for j in gj.all_jobs() if j.mode == "par"]
    print(f"\nlongest planned job {max(x.secs for x in j) / 60:.1f} min; jobs over 30 min: {sum(x.secs > 1800 for x in j)}")
    print("us/step used:", {m: {f: round(pl.us_per_step(m, f), 1) for f in pl.FAMILIES} for m in ("ours", "b1", "b3")})


if __name__ == "__main__":
    main()
