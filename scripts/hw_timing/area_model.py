"""timing study v1 explicit area model of one tile: measured digital (Nangate45 P&R-based a_nand2) + CITED analog (FeFET crossbar cells and
column ADCs), every analog parameter with a low / nominal / high range taken from its cost-table band.

Analog numbers are not measured here (no FeFET PDK, no ADC layout): a_array_cell = Zhou NC 2025 2FeFET cell as an upper value,
a_adc_col = built-up SAR estimate (ENERGY_RECONCILE.md). Corners combine all-low / nominal / all-high.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "golden"))
from cost_model import Arch, CostModel, table_by_name  # noqa: E402

ANALOG_KEYS = ("a_array_cell", "a_adc_col")


def analog_params(table: str = "measured_v1") -> dict[str, dict[str, float]]:
    t = table_by_name(table)
    return {k: {"lo": t[k]["value"] * t[k]["band_lo_x"], "nom": t[k]["value"], "hi": t[k]["value"] * t[k]["band_hi_x"]}
            for k in ANALOG_KEYS}


def tile_area(arch: Arch, table: str = "measured_v1", a_array_cell: float | None = None, a_adc_col: float | None = None) -> dict:
    """Area in um2 per block for one tile; analog parameters can be overridden (parameter sweep), digital uses the table."""
    cm = CostModel(table=table_by_name(table))
    a = cm.area(arch)
    cols = 2 * arch.w_bits * arch.n
    if a_array_cell is not None:
        a["array"] = arch.n * cols * a_array_cell
        a["tcam"] = arch.tcam_rows * arch.n * 2 * a_array_cell
    if a_adc_col is not None:
        a["adc"] = cols * arch.row_tiles * a_adc_col
    return a


def tile_area_range(arch: Arch, table: str = "measured_v1") -> dict[str, float]:
    """Total tile area (um2) at the all-low / nominal / all-high analog corners; digital fixed at the table value."""
    p = analog_params(table)
    return {c: sum(tile_area(arch, table, p["a_array_cell"][c], p["a_adc_col"][c]).values()) for c in ("lo", "nom", "hi")}


if __name__ == "__main__":
    for n in (256, 1024):
        arch = Arch(n=n, w_bits=2, arm="kc2", i11=True)
        a = tile_area(arch)
        print(n, {k: round(v) for k, v in a.items()}, {k: round(v) for k, v in tile_area_range(arch).items()})
