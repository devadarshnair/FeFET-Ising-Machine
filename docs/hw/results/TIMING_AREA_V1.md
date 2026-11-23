# timing study v1: own synthesis, timing, P&R area and leakage (measured_v1)

Goal: replace the literature clock period (t_clk = 2 ns, KLIMA) and the generic-gate area with our own numbers for the
confirmed digital datapath (lane with the I11 greedy pin, xoshiro128**, select tree, tim_ctrl CIM = 1, restart unit), then
re-price the Stage 3 records offline (no new runs).

## Tools and library

| item | version / source |
|---|---|
| Yosys + ABC | 0.69 (`~/tools/yosys`, already installed) |
| OpenSTA | 3.1.0 (`~/tools/sta`, already installed) |
| OpenROAD | 2.0-12381-g01bba3695, NEW conda env `openroad` (litex-hub + conda-forge; `fmt=8` added so it loads). No other env touched |
| Library | Nangate45 / FreePDK45 Open Cell Library, typical corner (1.1 V, 25 C), from OpenROAD-flow-scripts `flow/platforms/nangate45` (lib, tech LEF, macro LEF, setRC.tcl, LICENSE) in `~/tools/pdk/nangate45`; lib SHA-256 8d540a4d...4e9b1 |

The OSU `gscl45nm` liberty used by P3.09 / ENERGY_RECONCILE has no LEF set for OpenROAD here, so Nangate45 (same FreePDK45
process) is the mapped library. This changes the cell library, not the process.

## Flow (`rtl/pnr/run_timing_v1.sh`)

1. Yosys: `synth` (flattened; the select tree keeps its hierarchy during ABC and is flattened afterwards, because flat ABC did not
   finish N = 256 in 10 min), `dfflibmap` + `abc -liberty` (target 1 ns), tie cells. Netlist + `stat -liberty`.
2. OpenSTA: ports stand for flops (input delay 0.10 ns = DFF clk-to-Q, output delay 0.05 ns = setup), DFF_X1 drivers, 4 fF loads.
   Synthesis STA has ideal wires and NO buffering: one 2176-fanout enable gave a false 30 ns path in tim_ctrl N = 1024.
3. OpenROAD (`--pnr`): floorplan at 60 % utilisation (25 % retry for pin-limited blocks), global placement, `repair_design`,
   CTS, `repair_timing`, detailed placement, global route, parasitics from the route. **The P&R numbers are the reported ones.**
   No detailed routing, no signoff extraction, typical corner only.
4. `scripts/hw_timing/timing_v1_report.py <out> --write .` writes `timing_v1_summary.json` and `docs/hw/energy_table_measured_v1.csv`.

Heavy runs went through the local job queue (synthesis `--rss 4`, P&R `--rss 4`, each under 1 h). Raw outputs: `sim/out/hw/timing_v1/full/`
(gitignored); summary copied to `docs/hw/results/timing_v1/timing_v1_summary.json`.

## Results (post-global-route, Nangate45 typical)

Register-to-register path per step phase (each phase is one cycle in the RTL as written: ACC, SEL, RD, UPD):

| block | N = 64 | N = 256 | N = 1024 |
|---|---|---|---|
| lane ACC path (field + accept_unit, I11 pin free) | 2.41 ns | 2.41 ns | 2.41 ns |
| xoshiro128** | 2.32 ns | 2.32 ns | 2.32 ns |
| select tree (partitioned, SEL) | **3.18 ns** | **5.64 ns** | **9.15 ns** |
| tim_ctrl (CIM = 1) | 1.43 ns | 1.58 ns | 2.10 ns |
| restart_unit (reported apart) | 2.25 ns | 3.46 ns | 14.08 ns |
| **t_clk (max excluding restart_unit) / f_max** | 3.18 ns / 314 MHz | 5.64 ns / 177 MHz | 9.15 ns / 109 MHz |

The restart_unit path at N = 1024 is its N-wide MESA "first differing bit of x vs best_x" encoder. Kc2 does not use it and
arm `none` has no restart unit, so it is excluded from t_clk; a Kc2-only build would drop it.

Area (post-P&R cell area incl. buffers and clock tree): lane 5351 um2, xoshiro 1951 um2, select tree 1938 / 4869 / 16935 um2,
tim_ctrl 3514 / 6534 / 18037 um2, restart_unit 10131 / 37887 / 173681 um2 (N = 64 / 256 / 1024). Lane + RNG = 7302 um2 for
8602 generic NAND2-eq: **0.849 um2 cell area per generic NAND2-eq, 1.415 um2 at 60 % utilisation** (canonical 1.88 = gscl45nm
NAND2X1, no utilisation).

Power (OpenSTA, vectorless activity 0.1 on inputs, no VCD): leakage lane 138 uW + RNG 50 uW = **21.8 nW per generic NAND2-eq**
(canonical gscl45nm 3.29 nW, 6.6x lower). Dynamic power at 1 GHz: lane 19.9 mW, RNG 7.0 mW. Vectorless propagation through the
multipliers and the select tree overstates glitch activity (select tree N = 64 alone reported 95 mW), so **the dynamic numbers
are not used**: measured_v1 keeps the gscl45nm-derived energy rows. A VCD/SAIF-annotated power run from an RTL simulation
was not done.

## measured_v1 table

`docs/hw/energy_table_measured_v1.csv` overlays three rows on the canonical table; nothing else changes:

| row | canonical | measured_v1 | band |
|---|---|---|---|
| t_clk | 2.0 ns (literature) | 9.1527 ns (sel tree, N = 1024 = Max-Cut n_pad) | 0.8-1.5x |
| a_nand2 | 1.88 um2 | 1.4147 um2 (effective, incl. 60 % utilisation) | 0.8-1.3x |
| p_leak_nand2_nw | 3.29 nW | 21.81 nW | 0.5-2x |

`cost_model.py` (additions only): `TABLE_MEASURED_V1`, `measured_v1_table()`, `table_by_name("canonical" | "measured_v1")`.
`CostModel()` still defaults to the canonical table, so every earlier result reproduces (test pins the hash).

Analog area stays cited, now explicit in `scripts/hw_timing/area_model.py`: `tile_area(arch, a_array_cell=, a_adc_col=)` and
`tile_area_range()` at the band corners (a_array_cell 0.15 um2, 0.015-0.30; a_adc_col 430 um2, 129-1290). Example, w_bits = 2,
Kc2 + I11: N = 256 tile 2.55 / 2.90 / 3.82 mm2, N = 1024 10.3 / 12.1 / 16.2 mm2 (lo / nom / hi); the digital lanes dominate
(N = 1024: 9.7 mm2 digital vs 0.63 mm2 array + 1.76 mm2 ADC).

## Max-Cut L2 under measured_v1 (offline re-price of the Stage 3 records)

`scripts/hw_timing/reprice_stage3.py` runs the frozen `evaluate_h6` with the cost table swapped (B3's table too); the canonical
re-run reproduces `stage3_eval/h6_report.md` exactly (only the added cost-table header line differs). Outputs: `docs/hw/results/timing_v1/h6_report_measured_v1*.{json,md}`.

| Max-Cut contrast | canonical | measured_v1 | t_clk = lane path 2.41 ns | t_clk = restart 14.08 ns | Nangate t_clk, gscl45 leakage |
|---|---|---|---|---|---|
| ours_none_off vs B1_best (ETS99) | 0.652 win | **1.090 loss** | 0.815 win | 1.191 loss | 0.743 win |
| ours_none_fs vs B1_best (ETS99) | 0.474 win | **0.800 win** [0.759, 0.841] | 0.595 win | 0.875 win | 0.542 win |
| area ratio | 0.80 | 0.74 | 0.74 | 0.74 | 0.74 |

**Verdict.** The full-scale-ADC L2 win (0.474) survives as a smaller win (0.80, CI below 1 in every sensitivity row). The
nominal-ADC L2 (0.652) does **not** survive measured_v1: it becomes a loss (1.09). Reason: both machines run the same
trajectory, but ours takes about 1.38x B1's time (fs: 1.06x); with a 4.6x longer clock and 6.6x higher leakage per gate,
leakage becomes the dominant energy block and the time penalty outweighs ours' lower dynamic energy. The result therefore
hangs on two choices: the single-cycle select tree (pipelining it gives the 2.41 ns row, where both wins hold) and Nangate45's
leakage (gscl45nm leakage gives both wins). Colouring L1 (Kc2 + I11) stays a win (col3p 0.15-0.22).

## Open risks

- One t_clk for all machines and N: B1's own select logic was not synthesised; B1 is assumed to share the clock.
- Typical corner only; no detailed route or signoff RC; band 0.8-1.5x.
- Dynamic energy not measured (vectorless only); no VCD/SAIF annotation.
- The canonical cost model charges Kc2 only the stall counter (892 um2 at the canonical a_nand2), but the RTL restart_unit is
  173,681 um2 at N = 1024 (perm table + MESA encoder). Not changed here; it does not affect arm `none` (L2).
- Nangate45 leakage is high for a typical corner; the gscl45nm-leakage row brackets it.
- Smoke test: `tests/hw/test_timing_v1.py::test_flow_smoke` (N = 16, lane + RNG + select, about 10 s, skipped if the tools are absent).
