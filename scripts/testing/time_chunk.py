"""Timing chunk for the P6.02 re-budget: wall seconds per step of one machine on the 800-spin Max-Cut G1 (N = 1024 padded for ours).

Timing only: the objective is discarded and never written. Output sim/out/hw/time_chunk/<machine>.json (atomic).
Run: OPENBLAS_NUM_THREADS=1 python -I scripts/testing/time_chunk.py --machine ours|b1|b2|b3 [--steps 20000] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import smoke_all as sa  # noqa: E402

from scripts.problems import load as ld  # noqa: E402


def timed(machine: str, steps: int):
    mq, cost = ld.load_maxcut("G1"), sa.CostModel()
    run = {"ours": lambda: sa.run_ours(mq, "maxcut", "kc2", True, True, steps, cost),
           "b1": lambda: sa.run_b1(mq, "maxcut", True, steps, cost),
           "b2": lambda: sa.run_b2(mq, "maxcut", True, steps, cost),
           "b3": lambda: sa.run_b3(mq, "maxcut", steps, cost)}[machine]
    t0 = time.time()
    row = run()
    return row, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", required=True, choices=("ours", "b1", "b2", "b3"))
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--out", type=Path, default=REPO / "sim/out/hw/time_chunk")
    a = ap.parse_args()
    row, wall = timed(a.machine, a.steps)
    res = dict(machine=a.machine, instance="G1", spins=row["spins"], steps=a.steps, wall_s=round(wall, 2),
               us_per_step=round(1e6 * wall / a.steps, 2), tiles=row["tiles"])
    a.out.mkdir(parents=True, exist_ok=True)
    tmp = a.out / f".{a.machine}.tmp"
    tmp.write_text(json.dumps(res, indent=1))
    tmp.rename(a.out / f"{a.machine}.json")
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
