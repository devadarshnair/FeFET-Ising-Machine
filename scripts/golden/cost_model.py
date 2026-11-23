"""Cost/energy/area model G0 (P2.07): P2.06 op counts x a labelled energy table -> energy, time, area per block.

Table-driven: every number lives in docs/hw/energy_table_v1_p309.csv (+ b3_extra) with a source, a band (lo/hi multipliers) and a
placeholder flag, so char_v1 (P1.12) and Yosys (P3.09) values replace rows without code changes.
Leakage (ONE rule for all four machines): p_leak_nand2_nw (liberty, per NAND2-eq) x the machine's own synthesised NAND2-eq
count (gate_eq, the same counts as the area) x time. It scales with machine and N. I10 can remove only what it gates: the
digital logic stays powered (no power gating is modelled), so I10 shortens time (skipped reads drop their cycles) and the
ADC bias term is charged on ungated steps only. TCAM is dropped: its two rows are unused and energy() asserts they are never charged.
Explicit lines: I10-skipped reads cost nothing in the array/ADC (they are counted, priced at 0, and their cycles are
absent); I7 low-bit conversions are priced at their reduced bits via adc_conv_bits (I7v2 / a full scale set from the max
column sum, H6: same rows, fewer bits per conversion; the 16-bit full-scale register and reference trim are not priced,
no new row); restart-arm logic (stall counter,
MESA best-state shadow register, DA offset adder) is its own block. I3 ramp updates and I5 Vth noise samples are
priced from rows in energy_table_tweaks_i11_i3_i5.csv (RTL-synthesised gate counts, lib-derived energies); I11 saves the lane RNG
draws and LUT reads in the counters and the lane RNGs in the area, and pays the RTL greedy gating per lane. `scale` = H3 sensitivity hook: {key: factor}.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs" / "hw"
# P4.08 (P4_CHECK M1): ONE canonical table for every machine (ours, B1, B2, B3) = the P3.09/P3.11 back-filled table
# (hw/p3-rtl 573cbb7) plus the literature SRAM rows (used by B3 only). Rows with placeholder=1 are labelled as such.
# energy_table_v1.csv (pre-P3.09 placeholders) is kept for history only and is not loaded by default.
TABLE = DOCS / "energy_table_v1_p309.csv"
TABLE_EXTRA = DOCS / "energy_table_b3_extra.csv"
TABLE_TWEAKS = DOCS / "energy_table_tweaks_i11_i3_i5.csv"     # I3 / I5 rows: RTL synth counts (hw/p3-rtl 65b0a71), energies from gscl45nm liberty
FJ_PER_NW_NS = 1e-3                              # 1 nW x 1 ns = 1e-18 J = 1e-3 fJ
ADC_CURVE = Path(__file__).resolve().parents[2] / "circuit" / "adc" / "adc_energy.csv"


def adc_curve_points(path: Path = ADC_CURVE) -> dict[int, float]:
    """SPICE E_ADC(b) in fJ per conversion, b = 3..8 (comparator + C-DAC; SAR logic excluded, as for e_adc_conv_bit)."""
    with open(path, newline="") as f:
        return {int(r["bits"]): float(r["e_adc_fJ"]) for r in csv.DictReader(f)}


def adc_conv_fj(bits: float, e8_fj: float, pts: dict[int, float]) -> float:
    """Energy of one conversion at `bits` on the SPICE curve, scaled so E(8) = e8_fj (= 8 x e_adc_conv_bit, keeps bands/scale).
    Linear between integer points; outside the measured range linear per bit from the end point (the old rule)."""
    lo, hi = min(pts), max(pts)
    if bits <= lo:
        e = pts[lo] * bits / lo
    elif bits >= hi:
        e = pts[hi] * bits / hi
    else:
        b0 = int(math.floor(bits))
        b1 = min(b0 + 1, hi)
        e = pts[b0] + (bits - b0) * (pts[b1] - pts[b0])
    return e * e8_fj / pts[8]


def load_table(path: Path = TABLE) -> dict[str, dict]:
    rows = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            assert r["source"].strip(), r["key"]
            r["value"], r["band_lo_x"], r["band_hi_x"] = float(r["value"]), float(r["band_lo_x"]), float(r["band_hi_x"])
            assert r["band_lo_x"] <= 1.0 <= r["band_hi_x"], r["key"]
            r["placeholder"] = int(r["placeholder"])
            rows[r["key"]] = r
    return rows


@dataclass
class Arch:
    n: int                 # lanes
    w_bits: int = 0        # CiM weight bits (0 = no CiM array)
    arm: str = "da_offset"
    tcam_rows: int = 0     # TCAM-lite M rows (0 = off)
    row_tiles: int = 1     # R6 tiling: row tiles per column (each tile has its own ADC conversion; sums added digitally)
    i3: bool = False       # I3 penalty-ramp register + multiplier
    i5: bool = False       # I5 Vth-noise source per lane replaces the digital lane RNG (xoshiro)
    i11: bool = False      # I11 greedy: no lane RNG, no LUT; only the shared selection/kick RNG stays
    lane_rng: bool = False     # I11 with lane noise (R10 control / R12: fixed-T Metropolis or anneal-then-greedy): lane RNGs stay
    tabu: bool = False         # R6: one tabu flag + compare per lane and a shared tenure counter
    kick_target: bool = False  # R5: min-|gain| select mode (comparator per lane, same class as the I11 gating)
    burst: bool = False        # barrier burst: burst-length and uphill-budget counters (two stall-counter equivalents)
    lahc_len: int = 0          # late acceptance: lahc_len x 32-bit history registers + one comparator (one stall-counter equivalent)
    cc: bool = False           # configuration checking: 1 flag bit per lane, set by a neighbour's flip (coupling-row broadcast)
    breakout: bool = False     # breakout weights: 4-bit bias counter + 4-bit adder per lane, decay timer
    esc: bool = False          # RNG-free escalating offset: the offset adder of da_offset
    colour_par: bool = False   # colour-parallel commits: class-mask register (1 bit per lane) + class counter
    field_regs: int = 0        # T-1 full stack: field-register bits (flops; area and leakage through the digital gate count)


def canonical_table() -> dict[str, dict]:
    t = load_table(TABLE)
    t.update(load_table(TABLE_EXTRA))
    t.update(load_table(TABLE_TWEAKS))
    return t


TABLE_MEASURED_V1 = DOCS / "energy_table_measured_v1.csv"  # timing study v1: own Nangate45 synth/STA/P&R rows (t_clk, area, leakage)
TABLES = ("canonical", "measured_v1", "measured_v2")
TABLE_MEASURED_V1_BLOCKS = DOCS / "energy_table_measured_v1_blocks.csv"   # timing study v1 per-block rows (select-tree clock vs N, restart unit area / leakage vs N)


def measured_v1_table() -> dict[str, dict]:
    """timing study v1 'measured_v1': the canonical table with the rows of energy_table_measured_v1.csv overlaid (same keys replaced,
    nothing else changed). canonical_table() stays the default so earlier results reproduce bit for bit."""
    t = canonical_table()
    over = load_table(TABLE_MEASURED_V1)
    unknown = sorted(set(over) - set(t))
    assert not unknown, f"measured_v1 rows with no canonical key: {unknown}"
    t.update(over)
    return t


TABLE_MEASURED_V2 = DOCS / "energy_table_measured_v2.csv"                  # timing study v2: pipelined select tree clock, select latency
TABLE_MEASURED_V2_BLOCKS = DOCS / "energy_table_measured_v2_blocks.csv"    # timing study v2 per-block rows (pipelined tree, Kc2-only restart unit, N = 512)


def measured_v2_table() -> dict[str, dict]:
    """timing study v2 'measured_v2': measured_v1 with the rows of energy_table_measured_v2.csv overlaid. measured_v1 stays for reproducibility."""
    t = measured_v1_table()
    over = load_table(TABLE_MEASURED_V2)
    unknown = sorted(set(over) - set(t))
    assert not unknown, f"measured_v2 rows with no canonical key: {unknown}"
    t.update(over)
    return t


def table_by_name(name: str = "canonical") -> dict[str, dict]:
    """Select a cost table by name: 'canonical' (literature t_clk / gscl45nm area) or 'measured_v1' (timing study v1)."""
    assert name in TABLES, name
    return {"canonical": canonical_table, "measured_v1": measured_v1_table, "measured_v2": measured_v2_table}[name]()


def loglog_interp(n: float, pts: list[tuple[float, float]]) -> float:
    """Piecewise log-log interpolation of measured (N, value) points; the end segments extrapolate."""
    pts = sorted(pts)
    i = 1
    while i < len(pts) - 1 and n > pts[i][0]:
        i += 1
    (n0, v0), (n1, v1) = pts[i - 1], pts[i]
    return math.exp(math.log(v0) + (math.log(n) - math.log(n0)) * (math.log(v1) - math.log(v0)) / (math.log(n1) - math.log(n0)))


def table_hash(table: dict) -> str:
    """SHA-256 over the sorted (key, value, bands, placeholder) rows: equal hash = identical cost table."""
    import hashlib
    rows = sorted((k, r["value"], r["band_lo_x"], r["band_hi_x"], r["placeholder"]) for k, r in table.items())
    return hashlib.sha256(repr(rows).encode()).hexdigest()


class CostModel:
    def __init__(self, table: dict | None = None, scale: dict | None = None, band: str | None = None):
        self.t = table or canonical_table()
        self.scale = scale or {}
        assert band in (None, "lo", "hi")
        self.band = band

    def at(self, desc: dict) -> "CostModel":
        """Cost model for one machine record (desc). The base model is machine-independent."""
        return self

    def charge_restart_unit(self, desc: dict, blocks: dict, area: dict, time_ns: float) -> None:
        """Hook: extra restart-unit cost of one record (no-op in the canonical model)."""

    def adjust_counters(self, desc: dict, c: dict, steps: int) -> dict:
        """Hook (pricing.price): counters actually priced for one record. No-op here; measured_v2 adds select-tree latency cycles."""
        return c

    adc_curve = False   # B-2 fix (opt-in; False reproduces the frozen H8 pricing): ADC priced on the SPICE E(b) curve, not E(8)/8 per bit
    tile_bits = False   # B-3 fix (opt-in): a tiled ours array converts each tile at the tile full-scale bits (desc["adc_bits_tile"])
    adc_mixed_width_ok = False   # B2-LIN: allow a non-integer class mean width (approximate pricing) instead of failing
    adc_sar_logic = False        # B2-LIN sensitivity (opt-in, cost flag b2s): price SAR logic as one DFF write per conversion bit

    def adc_fj(self, c: dict) -> float:
        """ADC energy of counters c. Linear rule: conv_bits x e_adc_conv_bit. Curve rule: the full-width conversions at their mean
        width and the I7 low-bit conversions at theirs, each on the SPICE E(b) curve."""
        e_bit = self.v("e_adc_conv_bit")
        if not self.adc_curve:
            return c["adc_conv_bits"] * e_bit
        pts = adc_curve_points()
        total_e = 0.0
        lo_conv, lo_bits = c.get("adc_lowbit_conv", 0), c.get("adc_lowbit_bits", 0)
        for conv, bits in ((c["adc_conversions"] - lo_conv, c["adc_conv_bits"] - lo_bits), (lo_conv, lo_bits)):
            if conv > 0:
                mean = bits / conv
                # B2-LIN: the curve is applied at the class mean width, exact only if every conversion of the class has the same width.
                # True for every machine here (fixed b_hi / b_lo / tile bits / 1-bit sense); a mixed-width class must be split first.
                assert self.adc_mixed_width_ok or abs(mean - round(mean)) < 1e-6, f"mixed ADC widths in one class (mean {mean})"
                total_e += conv * adc_conv_fj(mean, 8 * e_bit, pts)
        if self.adc_sar_logic:      # B2-LIN sensitivity: SAR logic not in E(b); one flop write per resolved bit (measured DFF row)
            total_e += c["adc_conv_bits"] * self.v("e_shadow_bit")
        return total_e

    def v(self, key: str) -> float:
        r = self.t[key]
        f = r["band_lo_x"] if self.band == "lo" else r["band_hi_x"] if self.band == "hi" else 1.0
        return r["value"] * f * self.scale.get(key, 1.0)

    def energy(self, c: dict, arch: Arch, steps: int) -> dict[str, float]:
        """Energy in fJ per block from summed counters c over `steps` machine steps."""
        v = self.v
        restart = steps * v("e_stall_counter") if arch.arm != "none" else 0.0
        if arch.arm == "mesa":
            restart += c["best_updates"] * arch.n * v("e_shadow_bit")
        if arch.arm == "da_offset":
            restart += steps * v("e_offset_add")
        if arch.burst:                       # two counters updated every step
            restart += 2 * steps * v("e_stall_counter")
        if arch.lahc_len:                    # one history write (32 bits) + compare per step
            restart += steps * (32 * v("e_shadow_bit") + v("e_stall_counter"))
        if arch.breakout:                    # 4-bit bias add in every lane per step (1/4 of a 16-bit add)
            restart += steps * arch.n * 0.25 * v("e_add")
        if arch.esc:
            restart += steps * v("e_offset_add")
        if arch.cc or arch.colour_par:
            restart += steps * v("e_stall_counter")
        time_ns = c["cycles"] * v("t_clk")
        assert c["array_writes"] == 0 and c["tcam_searches"] == 0, "TCAM dropped: e_array_write / e_tcam_row_search are never charged"
        return {
            "array": c["array_cell_reads"] * v("e_array_cell_read"),
            "adc": self.adc_fj(c),
            "digital": (c["adds"] * v("e_add") + c["lut_reads"] * v("e_lut_read") + c["reg_writes"] * v("e_reg_write")
                        + c.get("ramp_updates", 0) * v("e_ramp_update")),
            "rng": (c["rng_draws"] * v("e_rng_draw") + c.get("vth_samples", 0) * v("e_vth_noise_sample")
                    + (steps * v("e_i5_hold_ctl_rtl") if arch.i5 else 0.0)),
            "tcam": 0.0,
            "restart": restart,
            "leakage": self.leak_fj(sum(self.gate_eq(arch).values()), time_ns) + (steps - c["gated_cycles"]) * v("e_adc_bias_step"),
        }

    def leak_fj(self, gate_eq: float, time_ns: float) -> float:
        """Static energy in fJ of `gate_eq` NAND2-eq powered for `time_ns` (liberty leakage per NAND2-eq)."""
        return gate_eq * self.v("p_leak_nand2_nw") * time_ns * FJ_PER_NW_NS

    def program_cost(self, n_cells: int, n_zero_cells: int, verify_level0: bool, window: str = "bin") -> dict[str, float]:
        """One-time (write-once, many-solve) programming of a binary CiM array, cell by cell (P1.07 fallback).
        Level-7 cells: one write. Level-0 cells: one erase attempt as measured; with verify (ruling R7, provisional)
        n_l0_attempts_<window> attempts, each = erase + verify read. Serial time (upper bound)."""
        v = self.v
        on = n_cells - n_zero_cells
        a = v(f"n_l0_attempts_{window}") if verify_level0 else 1.0
        e0 = a * (v("e_cim_write_l0") + (v("e_cim_verify_read") if verify_level0 else 0.0))
        t0 = a * (v("t_cim_write") + (v("t_cim_verify_read") if verify_level0 else 0.0))
        return {"e_program_fJ": on * v("e_cim_write_l7") + n_zero_cells * e0,
                "t_program_us": on * v("t_cim_write") + n_zero_cells * t0, "attempts_l0": a}

    def time_ns(self, c: dict) -> float:
        return c["cycles"] * self.v("t_clk")

    def gate_eq(self, arch: Arch) -> dict[str, float]:
        """NAND2-eq per block (digital, rng, restart): the synthesised counts behind both the area and the leakage."""
        v, n = self.v, arch.n
        restart = 0.0
        if arch.arm != "none":
            restart += v("g_stall_counter")
        if arch.arm == "mesa":
            restart += n * v("g_shadow_per_bit")
        if arch.arm == "da_offset":
            restart += v("g_offset_adder")
        if arch.tabu:
            restart += n * v("g_shadow_per_bit") + v("g_stall_counter")
        if arch.kick_target:
            restart += n * v("g_i11_greedy_per_lane_rtl")
        if arch.burst:
            restart += 2 * v("g_stall_counter")
        if arch.lahc_len:
            restart += arch.lahc_len * 32 * v("g_shadow_per_bit") + v("g_stall_counter")
        if arch.cc:
            restart += n * v("g_shadow_per_bit")
        if arch.breakout:
            restart += n * (4 * v("g_shadow_per_bit") + 0.25 * 122.5) + v("g_stall_counter")   # 4-bit adder = 1/4 of the 16-bit add (122.5 NAND2-eq)
        if arch.esc:
            restart += v("g_offset_adder")
        if arch.colour_par:
            restart += n * v("g_shadow_per_bit") + v("g_stall_counter")
        return {
            "digital": n * v("g_digital_per_lane") + (v("g_ramp_unit") if arch.i3 else 0.0) + arch.field_regs * v("g_shadow_per_bit")
                       + (n * v("g_i11_greedy_per_lane_rtl") if arch.i11 else 0.0),
            "rng": (n * v("g_rng_per_lane") if arch.i11 and arch.lane_rng
                    else v("g_rng_per_lane") if arch.i11
                    else v("g_rng_per_lane") + n * v("g_vth_noise_per_lane") + v("g_i5_hold_ctl_rtl") if arch.i5
                    else n * v("g_rng_per_lane")),
            "restart": restart,
        }

    def area(self, arch: Arch) -> dict[str, float]:
        """Area in um2 per block: array cells + column ADCs + digital gate counts x NAND2 area."""
        v, n, cols = self.v, arch.n, 2 * arch.w_bits * arch.n
        g, gates = v("a_nand2"), self.gate_eq(arch)
        return {
            "array": n * cols * v("a_array_cell"),
            "adc": cols * arch.row_tiles * v("a_adc_col"),
            "digital": gates["digital"] * g,
            "rng": gates["rng"] * g,
            "tcam": arch.tcam_rows * n * 2 * v("a_array_cell"),
            "restart": gates["restart"] * g,
            "leakage": 0.0,
        }


class MeasuredCost(CostModel):
    """measured_v1 with the H7 clock and restart-unit policy (prereg/hw/H7_scaleup.md sections 2 and 7), all rows from timing study v1.
    * t_clk of a machine = max(select-tree path at its padded N, lane path, RNG path); the select tree is log-log interpolated
      between the synthesised N = 64 / 256 / 1024 (tt_t_sel_*). B1 / B3 were never synthesised: baseline_clock='same_tree'
      gives them the same select-tree rule at their own N (stated limitation); 'lane_path' gives them the 2.41 ns lane path
      (sensitivity: the baseline needs no N-wide select tree).
    * Arms with a restart unit (kc2, mesa) are charged the measured restart_unit area and leakage at their padded N
      (tt_a_restart_*, tt_p_leak_restart_*, log-log in N). Its dynamic energy was not measured and stays the canonical row."""

    def __init__(self, table: dict | None = None, scale: dict | None = None, band: str | None = None, baseline_clock: str = "same_tree"):
        assert baseline_clock in ("same_tree", "lane_path")
        super().__init__(table or measured_v1_table(), scale, band)
        self.baseline_clock = baseline_clock
        self.blocks = load_table(TABLE_MEASURED_V1_BLOCKS)
        self._n = None

    @staticmethod
    def pad(desc: dict) -> int:
        n = int(desc.get("n_pad") or desc["n_act"])
        return 1 << (n - 1).bit_length()

    def _pts(self, stem: str) -> list[tuple[float, float]]:
        return [(float(n), self.blocks[f"{stem}_n{n}"]["value"]) for n in (64, 256, 1024)]

    def t_clk_at(self, n: int, kind: str) -> float:
        b = self.blocks
        lane = max(b["tt_t_lane_path"]["value"], b["tt_t_rng_path"]["value"])
        if kind in ("b1", "b1bs", "b3") and self.baseline_clock == "lane_path":
            return lane
        return max(loglog_interp(n, self._pts("tt_t_sel")), lane)

    def at(self, desc: dict) -> "MeasuredCost":
        import copy
        c = copy.copy(self)
        c._n = self.pad(desc)
        target = self.t_clk_at(c._n, desc["kind"])
        c.scale = {**self.scale, "t_clk": self.scale.get("t_clk", 1.0) * target / self.t["t_clk"]["value"]}
        return c

    def charge_restart_unit(self, desc: dict, blocks: dict, area: dict, time_ns: float) -> None:
        if desc.get("restart") not in ("kc2", "mesa"):
            return
        n = self.pad(desc)
        area["restart"] = area.get("restart", 0.0) + loglog_interp(n, self._pts("tt_a_restart"))
        blocks["leakage"] += loglog_interp(n, self._pts("tt_p_leak_restart")) * time_ns * FJ_PER_NW_NS


def tiled_counts(c: dict, n: int, w_bits: int, tile_rows: int) -> tuple[dict, int]:
    """R6 tiling rule for a monolithic-array design: columns of n rows are cut into ceil(n/tile_rows) row tiles; each tile
    column is converted separately (extra ADC conversions and conversion-bits, same bits) and the partial sums are
    added digitally ((tiles-1) adds per column per array read). Returns (counters, tiles); tiles == 1 leaves c unchanged."""
    tiles = math.ceil(n / tile_rows)
    c = dict(c)
    if tiles > 1:
        cols = 2 * w_bits * n
        c["adc_conversions"] *= tiles
        c["adc_conv_bits"] *= tiles
        c["adc_lowbit_conv"] *= tiles
        c["adc_lowbit_bits"] *= tiles
        c["adds"] += c["array_reads"] * (tiles - 1) * cols
    return c, tiles


def placeholders(table: dict | None = None) -> list[str]:
    return [k for k, r in (table or canonical_table()).items() if r["placeholder"]]


def total(blocks: dict[str, float]) -> float:
    return math.fsum(blocks.values())


class MeasuredCostV2(MeasuredCost):
    """measured_v2 (timing study v2). Everything of MeasuredCost (H7 clock policy, restart-unit charge) plus, each switchable for the
    increment table of docs/hw/results/TIMING_PIPELINE_V2.md:
    * pipelined=True : the select tree is the pipelined select_tree_pipe at the cut mask chosen per padded N (tt_*_selp_n*, rule A = shortest
      QUBO step time; tree="lane" selects rule B = fewest SEL cycles with the tree path <= 2.5 ns, tt_*_selq_n*): its
      post-P&R path replaces the single-cycle tree in the clock rule, and every step takes sel_lat(N) - 1 extra cycles (state SEL stretched; the
      selected spin is unchanged, so raw counters of the old-behaviour runs are re-priced exactly; counters.CycleCfg.sel_lat). False = the
      single-cycle tree of v0 / measured_v1 behaviour (selection latency 1), but with N = 512 measured.
    * kc2_only=True  : arm kc2 is charged the measured Kc2-only restart unit (restart_unit MESA = 0: stall counter + epoch best + Fisher-Yates
      kick, no MESA differing-spin encoder) instead of the full unit; arm mesa (B1) keeps the full unit. Both units are the pipelined RTL
      (R_DRAW / R_SWAP / R_RD kick, R_ENC / R_CHK differing-spin encoder).
    * restart_in_clock: ONE rule for every machine with a restart unit (ours Kc2, B1 MESA): t_clk = max(tree, lane, RNG, controller, that machine's restart unit
      as pipelined and measured). False reproduces the measured_v1 policy (restart unit not in any clock).
    * charge_select  : area and leakage of the select tree and the controller (tim_ctrl CIM = 1) are charged to every machine that has them
      (same-tree assumption for B1 / B3, as for the clock; not charged to baselines under baseline_clock = lane_path).
    * idle_charge    : the energy a clock cycle costs when nothing happens, measured by gate-level simulation of the quiet netlists (gl_idle.py), charged to
      EVERY machine for every cycle of the run under one rule: per lane (lane logic flops; lanes = padded N for ours, n_act for B1 / B3), the generator
      clock gates, the select tree and the controller (machines with the tree), and the restart unit (machines with one). On top of the per-operation
      table rows (which are then conservative by at most the clock part of an operation).
    * gen_gated      : True = lane / selection generators on gated clocks (RTL RNG_CG = 1; idle generator energy = the two clock gates only, for every
      machine); False = ungated generators (RNG_CG = 0), every lane generator pays its clock every cycle (sensitivity).
    * restart_cycles : the cycles the restart unit spends in S_RST are priced (they were not in measured_v1 or the golden `cycles`): Kc2 6 per kick + 1, MESA
      4 per differing spin + 3 (rtl/src/restart_unit.v, verified cycle-exact against the RTL: golden `restart_cycles`, tb `rs_cycles`). New counters carry
      `restart_cycles`; the stored Stage 3 / 4 raw records do not, so they are priced from the restart count: Kc2 kick L = desc["kick_L"] if present else 10 (capped at
      n_act - 1), MESA differing spins = mesa_flip_frac x n_act (the raw records do not keep the Hamming distance; 0.5 is the stated assumption, 0 and 1 bound it).
    * clock_stat     : N = 1024 clocks and areas from the P&R seed / utilisation set (docs: timing study v2 variance): "median" over the runs (primary) or "worst" (largest path).
    * settle_ns      : CiM array settle time in ns (None = one cycle, counters.CycleCfg.cim_array_lat = 1, the v1 rule). With a number the settle
      costs ceil(settle_ns / t_clk) cycles per performed read, so a faster clock does not make the analog settle free.
    Every per-N value is a measured point at N = 64 / 128 / 256 / 512 / 1024 (log-log between them for other N)."""

    def __init__(self, table: dict | None = None, scale: dict | None = None, band: str | None = None, baseline_clock: str = "same_tree",
                 pipelined: bool = True, kc2_only: bool = True, charge_select: bool = True, settle_ns: float | None = None,
                 tree: str = "step", restart_in_clock: bool = True, idle_charge: bool = True, gen_gated: bool = True,
                 restart_cycles: bool = True, mesa_flip_frac: float = 0.5, clock_stat: str = "median"):
        assert clock_stat in ("median", "worst")
        self.restart_cycles, self.mesa_flip_frac, self.clock_stat = restart_cycles, mesa_flip_frac, clock_stat
        assert tree in ("step", "lane")
        self.sfx = "p" if tree == "step" else "q"
        self.restart_in_clock = restart_in_clock
        super().__init__(table or measured_v2_table(), scale, band, baseline_clock)
        self.blocks = load_table(TABLE_MEASURED_V2_BLOCKS)
        self.pipelined, self.kc2_only, self.charge_select, self.settle_ns = pipelined, kc2_only, charge_select, settle_ns
        self.idle_charge, self.gen_gated = idle_charge, gen_gated
        self._kind, self._steps, self._cycles = "ours", 0, 0

    def _pts(self, stem: str) -> list[tuple[float, float]]:
        return [(float(n), self.blocks[f"{stem}_n{n}"]["value"]) for n in (64, 128, 256, 512, 1024) if f"{stem}_n{n}" in self.blocks]

    def _at(self, stem: str, n: int) -> float:
        k = f"{stem}_n{n}"
        if self.clock_stat == "worst" and stem.startswith("tt_t_") and f"{k}_worst" in self.blocks:
            return self.blocks[f"{k}_worst"]["value"]
        if k in self.blocks:
            return self.blocks[k]["value"]
        return loglog_interp(n, self._pts(stem))

    def _own_tree(self, kind: str) -> bool:
        """Does this machine kind carry the N-wide pipelined select tree (and its latency)?"""
        return self.pipelined and not (kind in ("b1", "b1bs", "b3") and self.baseline_clock == "lane_path")

    def restart_stem(self, arm: str | None) -> str | None:
        """Block stem of the restart unit a machine of this arm carries (None = no restart unit)."""
        if arm == "kc2":
            return "restartk" if self.kc2_only else "restart"
        return "restart" if arm == "mesa" else None

    def t_clk_at(self, n: int, kind: str) -> float:
        lane = max(self.blocks["tt_t_lane_path"]["value"], self.blocks["tt_t_rng_path"]["value"])
        if kind in ("b1", "b1bs", "b3") and self.baseline_clock == "lane_path":
            return lane
        if self.pipelined:
            return max(self._at(f"tt_t_sel{self.sfx}", n), self._at(f"tt_t_ctrl{self.sfx}", n), lane)
        return max(self._at("tt_t_sel", n), lane)

    def sel_lat_at(self, n: int, kind: str) -> int:
        return int(round(self._at(f"tt_sel_lat{self.sfx}", n))) if self._own_tree(kind) else 1

    def at(self, desc: dict) -> "MeasuredCostV2":
        import copy
        c = copy.copy(self)
        c._n, c._kind = self.pad(desc), desc["kind"]
        target = self.t_clk_at(c._n, desc["kind"])
        stem = self.restart_stem(desc.get("restart"))
        if self.restart_in_clock and stem:
            target = max(target, self._at(f"tt_t_{stem}", c._n))
        c.scale = {**self.scale, "t_clk": self.scale.get("t_clk", 1.0) * target / self.t["t_clk"]["value"]}
        return c

    def adjust_counters(self, desc: dict, c: dict, steps: int) -> dict:
        c = dict(c)
        self._steps = steps
        n, kind = self.pad(desc), desc["kind"]
        c["cycles"] += steps * (self.sel_lat_at(n, kind) - 1)
        if self.restart_cycles:
            if "restart_cycles" in c:
                c["cycles"] += c["restart_cycles"]
            elif c.get("restarts") and self.restart_stem(desc.get("restart")):
                n_act = int(desc.get("n_act") or n)
                if desc.get("restart") == "mesa":
                    per = 4 * self.mesa_flip_frac * n_act + 3
                else:
                    per = 6 * min(int(desc.get("kick_L", 10)), max(n_act - 1, 0)) + 1
                c["cycles"] += c["restarts"] * per
        if self.settle_ns is not None and c.get("array_reads"):
            c["cycles"] += c["array_reads"] * (math.ceil(self.settle_ns / self.t_clk_at(n, kind) - 1e-9) - 1)
        self._cycles = c["cycles"]
        return c

    def _row(self, key: str) -> float:
        return self.blocks[key]["value"]

    def charge_restart_unit(self, desc: dict, blocks: dict, area: dict, time_ns: float) -> None:
        n, arm, kind = self.pad(desc), desc.get("restart"), desc["kind"]
        stem = self.restart_stem(arm)
        if self.charge_select and self._own_tree(kind):
            sel, ctl = (f"sel{self.sfx}", f"ctrl{self.sfx}") if self.pipelined else ("sel", "ctrl")
            area["digital"] = area.get("digital", 0.0) + self._at(f"tt_a_{sel}", n) + self._at(f"tt_a_{ctl}", n)
            blocks["leakage"] += (self._at(f"tt_p_leak_{sel}", n) + self._at(f"tt_p_leak_{ctl}", n)) * time_ns * FJ_PER_NW_NS
        if self.idle_charge:
            cyc = self._cycles
            lanes = n if kind == "ours" else int(desc.get("n_act") or n)
            act = getattr(self, "_t6_act", None)
            if act is None:
                blocks["digital"] = blocks.get("digital", 0.0) + cyc * lanes * self._row("tt_e_idle_lane_fj")
            elif getattr(self, "_t6_split", False):   # t6s: per-machine split (ours whole lane, B3 field register only)
                import arch_t
                blocks["digital"] = blocks.get("digital", 0.0) + cyc * lanes * arch_t.t6s_lane_idle(kind, act, self)
            else:                         # T-6: only lanes whose field changed are clocked; every lane pays its clock gate
                blocks["digital"] = blocks.get("digital", 0.0) + cyc * lanes * (act * self._row("tt_e_idle_lane_fj") + self._row("tt_e_idle_icg_fj"))
            blocks["rng"] = blocks.get("rng", 0.0) + cyc * (lanes * self._row("tt_e_idle_gen_fj") if not self.gen_gated
                                                             else 2 * self._row("tt_e_idle_icg_fj"))
            if self._own_tree(kind):
                sel, ctl = (f"sel{self.sfx}", f"ctrl{self.sfx}") if self.pipelined else ("sel", "ctrl")
                blocks["digital"] = blocks.get("digital", 0.0) + cyc * (self._at(f"tt_e_idle_{sel}", n) + self._at(f"tt_e_idle_{ctl}", n))
            if stem:
                blocks["restart"] = blocks.get("restart", 0.0) + cyc * self._at(f"tt_e_idle_{stem}", n)
        if not stem:
            return
        area["restart"] = area.get("restart", 0.0) + self._at(f"tt_a_{stem}", n)
        blocks["leakage"] += self._at(f"tt_p_leak_{stem}", n) * time_ns * FJ_PER_NW_NS
