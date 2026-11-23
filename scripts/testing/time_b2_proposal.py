"""Stage 0 timing of B2 (QKP, one run) in seconds per proposal, from the slope between two proposal counts so the set-up cost cancels.

Measures the plain runner and the H5-wrapped runner ("nominal" point). The numbers replace the placeholders plan.B2_US_PER_PROPOSAL and
plan.B2_PERT_US_PER_PROPOSAL when the Stage 2 jobs are re-budgeted. Timing only: no objective is read. Run alone on an idle box.
Run: OPENBLAS_NUM_THREADS=1 python -I scripts/testing/time_b2_proposal.py [--out sim/out/hw/time_chunk/b2_proposal.json] [--low 20000 --high 100000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import machines as ma  # noqa: E402
import plan as pl  # noqa: E402
import run_cell as rc  # noqa: E402


def wall(proposals: int, point: str) -> float:
    inst = pl.TUNE_SET["qkp"][0]
    argv = ["--id", f"time_b2_{proposals}", "--study", "h2", "--phase", "tune", "--arm", "b2.b2", "--family", "qkp",
            "--runs", f"{rc.find_config('b2.b2', pl.grid('b2')[0].cid)['cid']}/{inst}/0-0", "--proposals", str(proposals)]
    if point:
        argv += ["--point", point]
    spec = rc.build_specs(rc.make_parser().parse_args(argv), None, None)[0]
    t0 = time.time()
    ma.execute(spec, ma.CostModel())
    return time.time() - t0


def slope_us(low: int, high: int, point: str) -> dict:
    t_lo, t_hi = wall(low, point), wall(high, point)
    us = 1e6 * (t_hi - t_lo) / (high - low)
    return {"us_per_proposal": round(us, 3), "setup_s": round(t_lo - us * 1e-6 * low, 3), "wall_low_s": round(t_lo, 2), "wall_high_s": round(t_hi, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=rc.REPO / "sim/out/hw/time_chunk/b2_proposal.json")
    ap.add_argument("--low", type=int, default=20_000)
    ap.add_argument("--high", type=int, default=100_000)
    a = ap.parse_args()
    wall(2000, "")                                                   # warm-up (JIT)
    res = {"low": a.low, "high": a.high, "plain": slope_us(a.low, a.high, ""), "h5_nominal": slope_us(a.low, a.high, "nominal"),
           "planned_us": {"plain": pl.B2_US_PER_PROPOSAL, "h5": pl.B2_PERT_US_PER_PROPOSAL}}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, indent=1))
    tmp.rename(a.out)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
