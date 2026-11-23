"""Round 2 architecture tweaks T-1..T-6 (R2_PROBLEMS_AGREED "Architecture hypotheses"), priced from the logged counters of a run.

Every tweak keeps the win mechanism: the field stays EXACT (LSB 1 per tile, A8), so on the ideal device the trajectory is unchanged and the
re-pricing of the stored counters is exact up to the stated per-operation estimates. Flags live on the cost model (cost.arch_t, set by
cost_flags.apply with t1..t6); default empty = the measured_v2 machine as built.

  t1  incremental field update (desc sim_refresh = R adds one full column-ADC refresh read per R steps): after an accepted flip of spin k (and per kicked spin) the lanes add column k of P, read once with
      1-bit sense per cell; no per-step whole-array read and no SAR. Cycles per update = settle + sense = 2.
      Hardware: n x FIELD_BITS field registers per lane (priced as shadow-bit flops); the ADC area is KEPT (conservative, a sense-amp
      array would be smaller); 1-bit sense energy = the ADC curve at 1 bit (estimate, not SPICE-measured).
  t2  sparse storage: only the 1-cells are stored (plus a ceil(log2 n)-bit row index per stored cell, priced as array cells; estimate).
      Array read energy scales with the stored fraction; leaky level-0 cells disappear (variation_v2.OURS_SPARSE simulates that).
  t3  small tiles: tile_rows (default 64) row tiles, each LSB-1 ADC at the tile full scale (desc["adc_bits_tile_rows"]), exact digital
      sum; re-uses pricing.tiled_counts / tile_rebits at that tile height.
  t4  skip the read when the state did not change (previous step rejected, no kick): steps - flips - restarts reads removed.
  t5  overlap the read (settle + SAR, or the t1 update) with the select tree: per read, min(read cycles, sel_lat - 1) cycles hidden.
      Estimate: needs a pipelined controller (RTL not built).
  t6  clock-gate lanes whose field did not change: per cycle, lane idle energy x active fraction + one clock gate per lane (measured
      tt_e_idle_icg_fj). Applied to EVERY machine with lanes (ours, B1, B3) under the same rule (fairness).
Not measured: t1 sense energy and field-register area class, t2 index storage, t5 controller; t3 / t4 / t6 use measured rows only.
"""
from __future__ import annotations

import csv
import functools
import math
from pathlib import Path

FLAGS = ("t1", "t1f", "t2", "t3", "t4", "t5", "t6", "m3", "m4", "t6s")
# m4 = measured_v4 (Round 4): SRAMs from OpenRAM (FreePDK45, ngspice): B3's coupler memory (read energy AND leakage, which earlier pricing
#      omitted) and ours' per-cell correction table, both as banks of 32-bit words with the bit-line length of the machine (fit in
#      docs/hw/energy_table_measured_v4_r4.csv); requires m3 for ours. Sub-switches cost.m4_b3_leak (default True),
#      cost.m4_sram_cells, cost.m4_sram_read (sram_bank).
# t6s = per-machine lane-gating split (replaces t6): ours gates whole lanes (synthesised row-change enable); B3 gates only its field
#      register (its accept datapath compares a fresh RNG word every step, so that part keeps its clock).
# m3 = measured_v3 pricing of the t1f digital blocks (Round 3): synthesised lane / remap / correction-table / screening control
# (docs/hw/energy_table_measured_v3_r3.csv); analog terms (1-bit sense, verify / re-erase) stay estimates scaled by t1_est_scale.
# t1f = t1 FULL STACK (internal review s15.3.1): t1 plus every cost the exact-incremental design needs, each a cost attribute (sensitivity):
T1F_DEFAULTS = {
    "t1_refresh": 100,          # full column-ADC refresh read every R steps (0 = none)
    "t1_spare_frac": 0.02,      # spare rows provisioned per tile (screening remap targets), fraction of the array
    "t1_screen_frac": 0.01,     # fraction of level-0 cells retired to spares (S3.0-B: scr5 retires about 1 %)
    "t1_lcor_k": 4,             # sparse correction entries per column (index + flag): cells forced to 0 in the 1-bit sense
    "t1_runs_per_program": 1,   # one-time screening/programming energy amortised over this many runs per instance (1 = all on every run)
    "t1_est_scale": 1.0,        # x2 / x0.5 sensitivity on the unmeasured T-1 estimates (sense energy, field registers, lcor, remap)
    "t1_lcor_impl": "sram",     # m3: correction table as SRAM (literature bit cell) or "flop" (synthesised per-column table)
}
M3_CSV = Path(__file__).resolve().parents[2] / "docs" / "hw" / "energy_table_measured_v3_r3.csv"
M4_CSV = Path(__file__).resolve().parents[2] / "docs" / "hw" / "energy_table_measured_v4_r4.csv"
SRAM_BANK_W = 32


@functools.lru_cache(maxsize=1)
def m4_rows() -> dict:
    with open(M4_CSV, newline="") as f:
        return {r["key"]: float(r["value"]) for r in csv.DictReader(f) if r["key"].startswith("r4_") and not r["key"].startswith("r4_pt_")}


SRAM_CELLS = {"lstp": "r4_cacti_lstp_leak_bit_nw", "hp": "r4_cacti_hp_leak_bit_nw", "openram": "r4_leak_bit_openram_nw"}
# The DECLARED measured_v4 primary (review item s20): the hybrid most favourable to B3 among the measured / cross-checked options:
# OpenRAM 32 x 64 bank read (49.5 fJ/bit) and CACTI itrs-lstp leakage (2.9 pW/bit). Sensitivities: m4_sram_read in
# {cacti_hp, cacti_lstp (32-bit words, 512 rows), cacti_wide_lstp, cacti_wide_hp (B3's 7680-bit row), array_lb (array-only lower
# bound for B3's coupler read)}, m4_sram_cells in {hp, openram, none}.
M4_PRIMARY = {"m4_sram_read": "openram", "m4_sram_cells": "lstp"}
# The bank AREA of measured_v4 is NOT usable against B3: a 32 x 64 OpenRAM macro is periphery-dominated (about 4.5 um2/bit vs a 0.35
# um2 bit cell), inflating a 3.7 Mbit memory about 5-9x. Energy / leakage only; areas keep the literature a_sram_bit rows.
M4_AREA_USABLE = False


def sram_bank(bits_per_access: float, total_bits: float, cost=None) -> dict:
    """measured_v4 SRAM: the memory is built from OpenRAM 32 x 64 banks (FreePDK45, measured; no bit-line extrapolation). An access of
    `bits_per_access` bits reads ceil(bits / 32) banks. Leakage per bit by cell type, cost.m4_sram_cells (same for every machine):
    'lstp' (CACTI itrs-lstp, default: a low-leakage cell is the design choice for a large, mostly idle memory), 'hp' (CACTI itrs-hp),
    'openram' (FreePDK45 nominal-Vt measured), 'none'. Read energy cost.m4_sram_read: 'openram' (default) or 'cacti_hp' / 'cacti_lstp'
    (CACTI per-bit read at 512 rows, cross-check)."""
    p = m4_rows()
    words = SRAM_BANK_W
    acc = math.ceil(bits_per_access / words)
    rd = getattr(cost, "m4_sram_read", "openram")
    e = acc * p["r4_bank_e_read_fj"] if rd == "openram" else bits_per_access * p[f"r4_{rd}_e_bit_n512_fj"]
    cells = getattr(cost, "m4_sram_cells", "lstp")
    leak = 0.0 if cells == "none" else total_bits * p[SRAM_CELLS[cells]]
    area = math.ceil(total_bits / p["r4_bank_bits"]) * p["r4_bank_area_um2"]
    return {"e_fj": e, "leak_nw": leak, "area_um2": area, "accesses": acc, "area_usable_vs_b3": M4_AREA_USABLE}


@functools.lru_cache(maxsize=1)
def m3_rows() -> dict:
    with open(M3_CSV, newline="") as f:
        return {r["key"]: float(r["value"]) for r in csv.DictReader(f)}


def m3(key: str, n: int | None = None) -> float:
    rows = m3_rows()
    if n is not None:
        key = key.format(n=512 if n <= 512 else 1024)
    return rows[key]
FIELD_BITS = 16
T3_ROWS = 64


def flags_of(cost) -> frozenset:
    return getattr(cost, "arch_t", frozenset())


def _read_cycles(c: dict, desc: dict) -> float:
    """Settle + mean SAR bits per performed read (B1 raw counters carry no conversions yet: its own ADC width)."""
    conv = c.get("adc_conversions", 0)
    if conv:
        return 1.0 + c["adc_conv_bits"] / conv
    return 1.0 + float(desc.get("adc_bits_fs") or desc.get("adc_bits", 0))


def transform(desc: dict, c: dict, steps: int, flips: int, cost) -> dict:
    """Counters of the tweaked machine (raw, before tiling / adjust_counters)."""
    fl = flags_of(cost)
    if not fl:
        return c
    c = dict(c)
    kind = desc["kind"]
    if kind not in ("ours", "b1", "b1bs"):
        return c
    reads = c.get("array_reads", 0)
    if reads <= 0:
        return c
    n = desc["n_pad"]
    w = desc.get("w_bits", 1)
    per_read_cyc = _read_cycles(c, desc)
    restarts = c.get("restarts", 0)
    if kind == "ours" and ("t1" in fl or "t1f" in fl):
        L = int(desc.get("kick_L", 10))
        updates = flips + restarts * L + 1
        cols = 2 * w * n
        R = int(desc.get("sim_refresh", 0) or 0)            # periodic full refresh through the column ADC (one full read per R steps)
        if hasattr(cost, "t1_refresh"):                     # R4 fix (R3-A6): an explicit cost attribute overrides the simulated period
            R = int(cost.t1_refresh)                        # (pricing-only sensitivity: the trajectory was simulated at the desc period)
        elif "t1f" in fl and not R:
            R = int(t1f(cost, "t1_refresh"))
        fr = steps // R if R else 0
        per = {k: c.get(k, 0) / reads for k in ("array_cell_reads", "adc_conversions", "adc_conv_bits")}
        c["adds"] = c["adds"] - reads * 2 * w * n + (0 if "m3" in fl else updates * 2 * w * n)   # m3: lane adds priced as measured lane updates
        c["cycles"] = c["cycles"] - reads * per_read_cyc + updates * 2
        c.update(array_reads=updates, field_reads=updates, array_cell_reads=updates * cols, adc_conversions=updates * cols,
                 adc_conv_bits=updates * cols, adc_lowbit_conv=updates * cols, adc_lowbit_bits=updates * cols)   # 1-bit senses: own width class
        c["t1_updates"] = updates
        if fr:
            c["array_reads"] += fr
            c["field_reads"] += fr
            c["array_cell_reads"] += fr * per["array_cell_reads"]
            c["adc_conversions"] += fr * per["adc_conversions"]
            c["adc_conv_bits"] += fr * per["adc_conv_bits"]
            c["adds"] += fr * 2 * w * n
            c["cycles"] += fr * per_read_cyc
            c["t1_refreshes"] = fr
        per_read_cyc, reads = 2.0, updates
    elif "t4" in fl and not ("t1" in fl or "t1f" in fl):
        saved = min(max(0, steps - flips - restarts), reads - 1)
        keep = (reads - saved) / reads
        for k in ("array_reads", "field_reads", "array_cell_reads", "adc_conversions", "adc_conv_bits", "adc_lowbit_conv", "adc_lowbit_bits"):
            if k in c:
                c[k] = c[k] * keep
        c["adds"] -= saved * 2 * w * n
        c["cycles"] -= saved * per_read_cyc
        reads -= saved
    if kind == "ours" and "t2" in fl:
        c["array_cell_reads"] *= float(desc.get("ones_frac", 1.0))
    if "t5" in fl and hasattr(cost, "sel_lat_at"):
        hide = min(per_read_cyc, cost.sel_lat_at(cost.pad(desc), kind) - 1)
        c["cycles"] -= reads * max(hide, 0)
    return c


def t1f(cost, key: str) -> float:
    return getattr(cost, key, T1F_DEFAULTS[key])


def t1f_blocks(desc: dict, c: dict, cost, area: dict, blocks: dict) -> None:
    """t1f extra energy blocks / area (ours). Per run: one-time screening + spare programming (amortised), lcor checks per update,
    1-bit sense energy scale; area: field registers (in Arch.field_regs, with leakage), spare rows, remap table, lcor table."""
    if desc.get("kind") != "ours" or "t1f" not in flags_of(cost):
        return
    v = cost.v
    n, w = desc["n_pad"], desc.get("w_bits", 1)
    est = t1f(cost, "t1_est_scale")
    cells = 2 * w * n * n
    zeros = cells * (1.0 - float(desc.get("ones_frac", 0.0)))
    runs = max(1.0, t1f(cost, "t1_runs_per_program"))
    scr = t1f(cost, "t1_screen_frac") * zeros
    once = zeros * v("e_cim_verify_read") + scr * (v("e_cim_write_l0") + v("e_cim_verify_read"))
    blocks["t1_screen_once"] = once / runs
    k = t1f(cost, "t1_lcor_k")
    upd = c.get("t1_updates", 0)
    cols = 2 * w * n
    blocks["t1_lcor"] = est * upd * cols * k * (8 / 16) * v("e_add") * 0.25     # per update: k index compares (8 b) per column, activity 0.25
    if est != 1.0 and "adc" in blocks:                                              # 1-bit sense energy is an estimate: scale its share
        sense = upd * cols
        tot = c.get("adc_conversions", 0) or 1
        blocks["adc"] += (est - 1.0) * blocks["adc"] * sense / tot
    if "m3" in flags_of(cost):
        _m3_blocks(desc, c, cost, area, blocks, zeros, scr, runs, k, upd, cols, n, est)
        return
    spare = t1f(cost, "t1_spare_frac")
    if "array" in area:
        area["array"] *= 1.0 + spare
    remap_bits = spare * n * math.ceil(math.log2(max(n, 2))) * 2 * w           # one remap entry per spare row per plane/polarity
    lcor_bits = cols * k * (math.ceil(math.log2(max(n, 2))) + 1)
    area["t1_tables"] = est * (remap_bits + lcor_bits) * v("g_shadow_per_bit") * v("a_nand2")
    blocks["leakage"] = blocks.get("leakage", 0.0) + cost.leak_fj(est * (remap_bits + lcor_bits) * v("g_shadow_per_bit"),
                                                                  c["cycles"] * v("t_clk"))


def _m3_blocks(desc, c, cost, area, blocks, zeros, scr, runs, k, upd, cols, n, est) -> None:
    """measured_v3: every digital T-1 block from synthesis + gate-level event energy; analog terms keep the estimate x est."""
    v = cost.v
    time_ns = c["cycles"] * v("t_clk")
    steps = max(1, int(c.get("field_reads", 0)) or 1)
    deg = float(desc.get("deg_frac", 1.0)) * n
    gated = bool({"t6", "t6s"} & flags_of(cost))
    cycles = c["cycles"]
    # T-1 lanes: update energy for changed lanes only; idle clock of the field registers (gated / ungated); leakage; area
    e_upd = m3("r3_e_lane_update_fj") if gated else m3("r3_e_lane_update_ungated_fj")
    idle = m3("r3_e_idle_lane_t1_gated_fj") if gated else m3("r3_e_idle_lane_t1_ungated_fj")
    blocks["t1_lane"] = upd * deg * e_upd + cycles * n * idle
    blocks["leakage"] = blocks.get("leakage", 0.0) + n * m3("r3_p_leak_lane_t1_nw") * time_ns * 1e-3
    area["t1_lanes"] = n * m3("r3_a_lane_t1")
    # spare-row remap: one lookup per row read (updates + refresh rows); entries scale the measured table
    spares = max(1.0, t1f(cost, "t1_spare_frac") * n)
    S = (512 if n <= 512 else 1024) // 32
    lookups = upd + c.get("t1_refreshes", 0) * n
    blocks["t1_remap"] = lookups * m3("r3_e_remap_lookup_n{n}_fj", n) * spares / S
    blocks["leakage"] += spares * m3("r3_p_leak_remap_entry_n{n}_nw", n) * time_ns * 1e-3
    area["t1_remap"] = spares * m3("r3_a_remap_entry_n{n}", n)
    if "array" in area:
        area["array"] *= 1.0 + t1f(cost, "t1_spare_frac")
    # one-time screening: digital sequencer (measured) + analog verify / re-erase (estimate x est), amortised per run
    analog_once = zeros * v("e_cim_verify_read") + scr * (v("e_cim_write_l0") + v("e_cim_verify_read"))
    blocks["t1_screen_once"] = (zeros * m3("r3_e_screen_cell_n{n}_fj", n) + est * analog_once) / runs
    # correction table: SRAM (literature bit cell, per-row organisation: read the entries of the flipped row) or synthesised flops
    if k:
        bits_e = math.ceil(math.log2(max(n, 2))) + 1
        if "m4" in flags_of(cost) and t1f(cost, "t1_lcor_impl") == "sram":   # OpenRAM bank model, per-row organisation (n words deep)
            row_bits = k * cols / n * bits_e
            sb = sram_bank(row_bits, row_bits * n, cost)
            blocks["t1_lcor"] = upd * sb["e_fj"]
            blocks["leakage"] += sb["leak_nw"] * time_ns * 1e-3
            area["t1_lcor"] = sb["area_um2"] if M4_AREA_USABLE else row_bits * n * v("a_sram_bit")   # same literature bit-cell area as B3
        elif t1f(cost, "t1_lcor_impl") == "flop":
            kk = 4 if k <= 4 else 16
            blocks["t1_lcor"] = (k / kk) * upd * cols * m3(f"r3_e_lcor{kk}_lookup_n{{n}}_fj", n)
            blocks["leakage"] += (k / kk) * cols * m3(f"r3_p_leak_lcor{kk}_col_n{{n}}_nw", n) * time_ns * 1e-3
            area["t1_lcor"] = (k / kk) * cols * m3(f"r3_a_lcor{kk}_col_n{{n}}", n)
        else:
            bits = cols * k * bits_e
            blocks["t1_lcor"] = upd * (k * cols / n) * bits_e * v("e_sram_read_bit")
            blocks["leakage"] += bits * m3("r3_p_leak_sram_bit_nw") * time_ns * 1e-3
            area["t1_lcor"] = bits * v("a_sram_bit")
    else:
        blocks["t1_lcor"] = 0.0
    # analog 1-bit sense keeps its estimate, scaled
    if est != 1.0 and "adc" in blocks:
        tot = c.get("adc_conversions", 0) or 1
        blocks["adc"] += (est - 1.0) * blocks["adc"] * (upd * cols) / tot
    del steps


def tile_rows(desc: dict, cost, default: int) -> int:
    return T3_ROWS if (desc.get("kind") == "ours" and "t3" in flags_of(cost)) else default


def area_extra(desc: dict, cost, area: dict) -> None:
    """Area changes of t1 / t2 (ours)."""
    fl = flags_of(cost)
    if desc.get("kind") != "ours" or not fl:
        return
    v = cost.v
    n = desc["n_pad"]
    if "t1" in fl and "t1f" not in fl:      # t1 alone: area only (t1f puts the field registers into Arch.field_regs: area AND leakage)
        area["digital"] = area.get("digital", 0.0) + n * FIELD_BITS * v("g_shadow_per_bit") * v("a_nand2")
    if "t2" in fl and "array" in area:
        idx = max(1, math.ceil(math.log2(n)))
        area["array"] *= float(desc.get("ones_frac", 1.0)) * (1 + idx)


def lane_active_frac(desc: dict, steps: int, flips: float, restarts: float) -> float:
    """Mean fraction of lanes whose field changes in a cycle (t6): changed fields per step / lanes, at most 1."""
    deg = float(desc.get("deg_frac", 1.0))
    L = int(desc.get("kick_L", 0) or 0)
    upd = (flips + restarts * L) / max(steps, 1)
    return min(1.0, upd * deg + 1.0 / max(desc.get("n_pad", 1), 1))


def b3_m4(desc: dict, c: dict, cost, blocks: dict, area: dict, time_ns: float) -> None:
    """measured_v4 for B3: coupler SRAM read energy and leakage from the OpenRAM bank model (banks n words deep, one coupler row =
    n_act x coupler_bits bits per accepted flip); replaces the literature e_sram_read_bit; scale via cost.scale e_sram_read_bit."""
    if "m4" not in flags_of(cost) or desc.get("kind") != "b3":
        return
    import fujitsu_da as b3
    cb = b3.B3Cfg().coupler_bits
    n = int(desc["n_act"])
    sb = sram_bank(n * cb, n * n * cb + n * b3.B3Cfg().bias_bits, cost)     # same cell type as ours' table
    flips_reads = c.get("sram_bit_reads", 0) / max(n * cb, 1)
    s_e = cost.scale.get("e_sram_read_bit", 1.0)
    blocks["sram"] = flips_reads * sb["e_fj"] * s_e
    if getattr(cost, "m4_b3_leak", True):
        blocks["leakage"] = blocks.get("leakage", 0.0) + sb["leak_nw"] * time_ns * 1e-3
    if M4_AREA_USABLE:                              # never true for measured_v4: B3 keeps the literature bit-cell area
        area["sram"] = sb["area_um2"]


def t6s_lane_idle(kind: str, act: float, cost) -> float:
    """Per-lane idle energy per cycle under the per-machine gating split (t6s)."""
    lane, icg = cost._row("tt_e_idle_lane_fj"), cost._row("tt_e_idle_icg_fj")
    if kind != "b3":
        return act * lane + icg
    fr = m3("r3_e_idle_lane_t1_ungated_fj")                  # a 16-bit field register's clock (synthesised); the rest stays clocked
    return (lane - fr) + act * fr + icg
