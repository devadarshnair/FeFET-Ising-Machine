"""P4_v2 section 7 (checklist A7): each baseline's own clock, and the offline Stage 4 re-pricing under it.

  baseline_clock.py rows     parse sim/out/hw/baselines_v2/clock/{lane_ours,lane_b3} (baseline_clock.sh) and write
                             docs/hw/energy_table_baseline_clock.csv
  baseline_clock.py reprice  Stage 4 (H7) report re-priced with OwnClockCost -> docs/hw/results/baselines_v2/h7_own_clock.json

Clock rule ("own"):
  ours  unchanged (MeasuredCost: max(select tree at padded N, lane, RNG)).
  B3    Aramon Alg. 2 keeps the N-wide uniform select of one accepted flip, so: max(select tree at padded N, B3 lane at the DA
        widths, RNG). The B3 lane is our lane RTL synthesised + placed/routed at JW 16 / BW 26 / HW 32 / EW 26 (same flow).
  B1    Yin: one proposal per iteration, no parallel trial and no select tree: max(lane, RNG); the digital sum of the row tiles
        is a pipelined adder tree charged as ceil(log2 row_tiles) extra cycles per read (the rule ours already pays for its
        tiles in pricing.price). The B1 lane is our lane at our widths (Yin's 3-bit cells give a narrower field: upper bound).
The scaling of a synthesised path to the P&R path uses the P&R numbers of the same run (both lanes placed and routed).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts" / "golden"))
sys.path.insert(0, str(REPO / "scripts" / "testing"))
sys.path.insert(0, str(REPO / "scripts" / "hw_timing"))
sys.path.insert(0, str(REPO))
from cost_model import MeasuredCost, load_table  # noqa: E402

CLOCK_DIR = REPO / "sim/out/hw/baselines_v2/clock"
ROWS = REPO / "docs/hw/energy_table_baseline_clock.csv"
OUT = REPO / "docs/hw/results/baselines_v2"
TILE = 32


def lane_paths() -> dict[str, float]:
    import timing_v1_report as tt
    out = {}
    for tag in ("lane_ours", "lane_b3"):
        b = tt.block(CLOCK_DIR / tag)
        out[tag] = tt.path_ns(b)
        out[tag + "_synth"] = b.get("arrival_ns")
        out[tag + "_pnr"] = b.get("pnr_arrival_ns")
        out[tag + "_area_um2"] = b.get("pnr_design_area_um2") or b.get("cell_area_um2")
    return out


def write_rows() -> dict:
    p = lane_paths()
    src = ("BASELINES_V2 scripts/baselines/baseline_clock.sh (timing study v1 flow functions of rtl/pnr/run_timing_v1.sh from the committed "
           "tree; Yosys 0.69 + ABC, OpenSTA 3.1, OpenROAD 2.0 post-global-route; Nangate45 typical 1.1 V 25 C)")
    rows = [("tt_t_lane_path_b3", p["lane_b3"], f"{src}: tt_lane_i11 at DA widths JW 16 / BW 26 / HW 32 / EW 26"),
            ("tt_t_lane_path_ours_rerun", p["lane_ours"], f"{src}: tt_lane_i11 at our widths (reference re-run, same flow)"),
            ("tt_a_lane_b3", p["lane_b3_area_um2"], f"{src}: B3 lane P&R design area um2")]
    with open(ROWS, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "block", "kind", "unit", "value", "band_lo_x", "band_hi_x", "source", "placeholder"])
        for k, v, s in rows:
            w.writerow([k, "time" if k.startswith("tt_t") else "digital", "time" if k.startswith("tt_t") else "area",
                        "ns per cycle" if k.startswith("tt_t") else "um2", round(float(v), 4), 0.8, 1.5, s, 0])
    return p


class OwnClockCost(MeasuredCost):
    """MeasuredCost with each baseline's own clock (module docstring)."""

    def __init__(self, table: dict | None = None, rows: Path = ROWS):
        super().__init__(table=table, baseline_clock="same_tree")
        r = load_table(rows)
        self.b3_lane = r["tt_t_lane_path_b3"]["value"]
        self._kind = None
        self._row_tiles = 1

    def t_clk_at(self, n: int, kind: str) -> float:
        b = self.blocks
        rng = b["tt_t_rng_path"]["value"]
        lane = b["tt_t_lane_path"]["value"]
        if kind == "b3":
            return max(super().t_clk_at(n, "ours"), self.b3_lane, rng)
        if kind in ("b1", "b1bs"):
            return max(lane, rng)
        return super().t_clk_at(n, kind)

    def at(self, desc: dict) -> "OwnClockCost":
        c = super().at(desc)
        c._kind = desc["kind"]
        c._row_tiles = math.ceil(int(desc["n_act"]) / TILE) if desc["kind"] in ("b1", "b1bs") else 1
        return c

    def time_ns(self, c: dict) -> float:
        t = super().time_ns(c)
        if self._kind in ("b1", "b1bs") and self._row_tiles > 1:
            t += math.ceil(math.log2(self._row_tiles)) * c.get("array_reads", 0) * self.v("t_clk")
        return t


def reprice(raw: Path, B: int) -> dict:
    import evaluate_h7 as e7
    own = e7._view(raw, OwnClockCost(), B)
    prim = e7._view(raw, MeasuredCost(), B)
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {"rule": __doc__.split("Clock rule")[1].strip(), "own_clock": own, "primary_same_tree": prim,
           "scale_verdict_own": own["scale"], "scale_verdict_primary": prim["scale"]}
    (OUT / "h7_own_clock.json").write_text(json.dumps(doc, indent=1, default=float))
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("rows", "reprice"))
    ap.add_argument("--raw", default=str(REPO / "sim/out/hw/stage4"))
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args(argv)
    if a.cmd == "rows":
        print(json.dumps(write_rows(), indent=1))
        return 0
    d = reprice(Path(a.raw), a.boot)
    print(json.dumps({"own": d["scale_verdict_own"], "primary": d["scale_verdict_primary"]}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
