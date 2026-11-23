"""Offline re-pricing of the Stage 3 (H6) records under a named cost table (no new runs): the frozen evaluate_h6 report with
its CostModel (and B3's table) pointed at table_by_name(<table>). Same records, same statistics, only the price table changes.

  reprice_stage3.py --raw sim/out/hw/stage3 --table measured_v1 --out docs/hw/results/timing_v1/h6_report_measured_v1.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for sub in ("testing", "golden", "baselines"):
    sys.path.insert(0, str(HERE.parent / sub))
import evaluate_h6 as e6  # noqa: E402
import fujitsu_da  # noqa: E402
from cost_model import CostModel, table_by_name, table_hash  # noqa: E402


def use_table(name: str, scale: dict | None = None) -> str:
    t = table_by_name(name)
    e6.CostModel = lambda: CostModel(table=t, scale=scale)
    fujitsu_da.b3_table = lambda: t
    return table_hash(t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--table", default="measured_v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", nargs="*", default=[], help="sensitivity factors key=x (CostModel scale), e.g. t_clk=0.1")
    ap.add_argument("--boot", type=int, default=e6.ev.N_BOOT)
    a = ap.parse_args()
    scale = {k: float(x) for k, x in (kv.split("=") for kv in a.scale)}
    h = use_table(a.table, scale)
    rep = e6.evaluate(a.raw, a.boot)
    rep["cost_table"], rep["cost_table_sha256"], rep["scale"] = a.table, h, scale
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text(f"cost table: {a.table} (sha256 {h[:16]}), scale {scale or 'none'}\n\n" + e6.markdown(rep))
    out.write_text(json.dumps(rep, indent=1, default=float))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
