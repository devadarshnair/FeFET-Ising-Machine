"""Explicit parameterised analog area / energy / time model of one CiM tile (timing study v2, item C5).

Digital blocks are MEASURED (Nangate45 Yosys + OpenROAD, timing study v1 / T2). The analog parts have no PDK here and are CITED or SPICE-derived stand-ins;
this module makes every one of them an explicit parameter with a low / nominal / high value (the cost-table bands) so that no analog number is
a hidden constant:

  a_array_cell        um2 per crossbar cell          lit: Zhou NC 2025 2FeFET cell 0.15 um2 (upper value for 1FeFET1R); band 0.1x - 2x
  a_adc_col           um2 per column ADC             built-up SAR estimate (ENERGY_RECONCILE.md); band 0.3x - 3x
  e_array_cell_read   fJ per cell read               char_v1 SPICE (1FeFET1R, 20 ns read); band 0.5x - 2x
  e_adc_conv_bit      fJ per SAR conversion bit      char_v1 SPICE comparator + analytic C-DAC; band 0.5x - 2x
  e_adc_bias_step     fJ per ungated step            comparator bias held between conversions (I10 gates it); band 0.2x - 5x
  t_array_settle_ns   ns per performed CiM read      char_v1 read window 20 ns (t_cim_verify_read row); band 0.5x - 2x. Priced as
                                                     ceil(t_settle / t_clk) clock cycles, so a faster clock does not make it free
Functions: parameters(), tile_area(), step_energy(), settle_cycles(), sensitivity_corners() (the scale / settle arguments for
reprice_v2.py: one-at-a-time low / high and all-low / all-high corners).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "golden"))
from cost_model import Arch, table_by_name  # noqa: E402

ENERGY_KEYS = ("e_array_cell_read", "e_adc_conv_bit", "e_adc_bias_step")
AREA_KEYS = ("a_array_cell", "a_adc_col")
SETTLE_ROW = "t_cim_verify_read"            # us per verify read in the table: 0.02 us = 20 ns read window


def parameters(table: str = "measured_v2") -> dict[str, dict[str, float]]:
    t = table_by_name(table)
    p = {k: {"lo": t[k]["value"] * t[k]["band_lo_x"], "nom": t[k]["value"], "hi": t[k]["value"] * t[k]["band_hi_x"]}
         for k in ENERGY_KEYS + AREA_KEYS}
    r = t[SETTLE_ROW]
    p["t_array_settle_ns"] = {c: r["value"] * 1e3 * f for c, f in (("lo", r["band_lo_x"]), ("nom", 1.0), ("hi", r["band_hi_x"]))}
    return p


def settle_cycles(t_settle_ns: float, t_clk_ns: float) -> int:
    return max(1, math.ceil(t_settle_ns / t_clk_ns - 1e-9))


def tile_area(arch: Arch, corner: str = "nom", table: str = "measured_v2") -> dict[str, float]:
    """Analog area of one tile in um2 (digital area comes from the cost model)."""
    p, cols = parameters(table), 2 * arch.w_bits * arch.n
    return {"array": arch.n * cols * p["a_array_cell"][corner], "adc": cols * arch.row_tiles * p["a_adc_col"][corner]}


def step_energy(c: dict, steps: int, corner: str = "nom", table: str = "measured_v2") -> dict[str, float]:
    """Analog energy in fJ from summed counters c (CiM reads, ADC conversion bits, ungated steps)."""
    p = parameters(table)
    return {"array": c["array_cell_reads"] * p["e_array_cell_read"][corner], "adc": c["adc_conv_bits"] * p["e_adc_conv_bit"][corner],
            "adc_bias": (steps - c["gated_cycles"]) * p["e_adc_bias_step"][corner]}


def sensitivity_corners(table: str = "measured_v2") -> dict[str, dict]:
    """Named corners as reprice_v2 arguments: {name: {"scale": {row: factor}, "settle_ns": ns | None}}. Area rows scale the area
    (a_*), energy rows the energy; one at a time (low / high) and all-low / all-high (every analog parameter at its band edge)."""
    t, p = table_by_name(table), parameters(table)
    base = {k: p[k]["nom"] for k in p}
    out: dict[str, dict] = {"nominal": {"scale": {}, "settle_ns": None}}
    for k in ENERGY_KEYS + AREA_KEYS:
        for c in ("lo", "hi"):
            out[f"{k}_{c}"] = {"scale": {k: p[k][c] / base[k]}, "settle_ns": None}
    for c in ("lo", "hi"):
        out[f"t_array_settle_{c}"] = {"scale": {}, "settle_ns": p["t_array_settle_ns"][c]}
        out[f"all_{c}"] = {"scale": {k: p[k][c] / base[k] for k in ENERGY_KEYS + AREA_KEYS}, "settle_ns": p["t_array_settle_ns"][c]}
    return out


if __name__ == "__main__":
    for k, v in parameters().items():
        print(f"{k:20s} lo {v['lo']:10.4g}  nom {v['nom']:10.4g}  hi {v['hi']:10.4g}")
    for n in (256, 512, 1024):
        arch = Arch(n=n, w_bits=2, arm="kc2", i11=True)
        print(n, {c: round(sum(tile_area(arch, c).values())) for c in ("lo", "nom", "hi")}, "analog um2 (lo / nom / hi)")
