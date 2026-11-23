# Energy and gate-count reconcile (pre-bundle)

Scope: reconcile the I3/I5 tweak rows with the RTL (hw/p3-rtl 65b0a71) and derive the remaining digital energies from the
OSU gscl45nm liberty file. Script: `scripts/derive_digital_energy.py <gscl45nm.lib> --write` (re-runnable; reads the old
values from git HEAD). Library: `gscl45nm.lib`, SHA-256 69c0641df1dc737e5c8dbd3950f2daf3b52c6e7767aa081e35e9b0739bf62d6f,
FreePDK45 mirror baichen318 commit a75cb116 (the file P3.09 used; it was not stored in a worktree, so it was refetched and
the hash matched). The library has `internal_power` tables.

## Method

- e_toggle = NAND2X1 internal_power (rise + fall)/2 averaged over pins A, B at the smallest load/slew entry
  + 0.5 C V^2 with C = fanout 2 NAND2X1 inputs, V = 1.1 V: **4.658 fJ per output toggle**.
- e_gate = activity 0.1 x e_toggle = **0.4658 fJ per NAND2-eq per active cycle**. No wire capacitance, clock tree or glitching.
- e_dff = DFFPOSX1 CLK + D + Q internal power + load = **34.40 fJ per flop write**.
- The liberty file states no energy unit; read as pJ (pF load unit, 1 V). Check: 16 b adder 122.5 NAND2-eq x e_gate =
  57.1 fJ, against Horowitz ISSCC 2014 (0.03 pJ per 8 b, 0.1 pJ per 32 b add): consistent.
- Band 0.3-3 for derived rows, source labelled "derived (lib x synth)", placeholder=0.

## Rows changed (energy_table_v1_p309.csv, canonical)

| Row | Old (placeholder) | New | Derivation |
|---|---|---|---|
| e_add | 30.0 (1) | 57.06 | 122.5 NAND2-eq x e_gate |
| e_reg_write | 7.16 KLIMA (1) | 34.40 | one DFF write (KLIMA now only a cross-check) |
| e_shadow_bit | 7.16 (1) | 34.40 | one DFF write |
| e_rng_draw | 365 KLIMA (1) | 901.96 | 1936.25 NAND2-eq xoshiro128** x e_gate (KLIMA is a different generator) |
| e_stall_counter | 37.16 (1) | 1331.12 | (630.25 - 32 x 4.25) x e_gate + 32 DFF writes |
| e_offset_add | 30.0 (1) | 970.77 | (413.5 - 24 x 4.25) x e_gate + 24 DFF writes |

## Rows changed (energy_table_tweaks_i11_i3_i5.csv)

| Row | Old | New | Note |
|---|---|---|---|
| g_ramp_unit | 549.0 (standalone module, not the RTL) | 1877.50 | RTL lam_ramp.v, hw/p3-rtl 65b0a71 |
| g_vth_noise_per_lane | 119.75 (standalone, not the RTL) | 887.25 | RTL lane_rnd_mux.v at N = 256, 65b0a71; emulation of group sharing, an upper bound for a physical I5 that shares one sense sample by wiring |
| e_ramp_update | 30.0 (1) | 3468.41 | 1537.5 comb x e_gate + 80 DFF writes |
| g_i3_lam_ramp_rtl, g_i11_greedy_per_lane_rtl (87.25), g_i5_hold_ctl_rtl (293.0), g_i5_group_mux_per_lane_rtl (887.25) | new | copied | rows copied from hw/p3-rtl 65b0a71 |
| e_i3_ramp_update_rtl | new (949.33, 1) in hw-p3 | 3468.41 | recomputed, same as e_ramp_update |
| e_i5_hold_ctl_rtl | new (169.66, 1) in hw-p3 | 655.25 | 225 comb x e_gate + 16 DFF writes |

Cost-model change (`scripts/golden/cost_model.py`): I11 now pays g_i11_greedy_per_lane_rtl per lane (digital area); I5 now adds the
shared g_i5_hold_ctl_rtl (area) and e_i5_hold_ctl_rtl per step (rng energy). Tests updated accordingly.

Effect: all four machines share the table, so digital and RNG energies rise 2-30x (largest for the restart-arm rows). Earlier
absolute energies in the smoke CSV are superseded (re-run 15-16 Nov IST); ratios between arms are what the studies use.

## Placeholder rows: all 8 resolved (zero placeholder=1 rows)

Script: `scripts/derive_residual_rows.py <gscl45nm.lib> --write` (checks the liberty SHA-256 69c0641d...62d6f first; the file refetched
earlier was re-hashed and matched). Values, with every source in the table row text:

| Row | Old | New | Basis |
|---|---|---|---|
| p_leak (10 uW, one constant) | placeholder | **removed**; replaced by `p_leak_nand2_nw` = 3.29145 nW per NAND2-eq (band 0.5-5x) | liberty NAND2X1 `cell_leakage_power`; derived (lib x synth) |
| e_lut_read | 100 fJ (1) | 111.80 fJ | read path of the 1024 x 12 b LUT as a mux tree: 10 levels x 12 b x MUX2X1 (2.0 NAND2-eq) x e_gate; ROM bits are not synthesised (behavioural in RTL) |
| e_array_write | 1000 fJ (1) | 4.785 fJ per cell | mean of char_v1 crossbar_write levels 0-7; TCAM dropped, never charged |
| e_tcam_row_search | 15.4 fJ (1) | 0, unused | TCAM dropped (R5); `CostModel.energy` asserts `array_writes == 0` and `tcam_searches == 0` (test added) |
| e_adc_bias_step | 200 fJ (1) | 194.9 fJ | char_v1 ADC e_cmp_fJ at 8 b (comparator energy of one conversion, held as bias for one step). One shared bias per step, not scaled by column count: a lower bound for column-parallel ADCs (open caveat) |
| t_clk | 2.0 ns (1) | 2.0 ns, source=lit | KLIMA Table S1; band 0.5-3x also covers the 6 ns Methods value. No Yosys/OpenSTA timing output exists (generic synth), so no critical path is available. char_v1 ADC t_conv (4-9 ns) exceeds one cycle and is not added to the cycle count (open caveat) |
| a_array_cell | 0.15 um2 (1) | 0.15 um2, source=lit, band 0.1-2x | Zhou NC 2025 2FeFET cell as upper value for 1FeFET1R |
| a_adc_col | 300 um2 (1) | 430 um2, source=lit-assumption | C-DAC 2^8 x 1 fF at an assumed 2 fF/um2 (128) + SAR logic from gscl45nm (252) + comparator 50 (assumed); the density and comparator area are assumptions, no 45 nm layout; band 0.3-3x. Literature numbers were not fetched here, so no new citation is claimed |

New row `g_b2_logic` = 2249.25 NAND2-eq (2 adders + 16 b register + one xoshiro128**), used for B2 leakage only (B2 area keeps digital 0).

## Leakage model (one rule, all four machines)

`leak = NAND2-eq x p_leak_nand2_nw x time`, with NAND2-eq = that machine's own synthesised count (the same counts as its area):
ours `CostModel.gate_eq(arch)` (lane logic + RNG + restart block + I3/I5/I11 additions), B1 `b1_gate_eq`, B3 `b3_gate_eq`
(includes select tree and offset adder), B2 `g_b2_logic`. It therefore scales with N and with the machine. At N = 256 the
lane logic + RNG is about 2.2 M NAND2-eq, about 7 mW (the old constant was 10 uW, about 700x too low; a test pins the milliwatt scale).
I10: the digital logic stays powered (no power gating is modelled), so I10 reduces leakage only through shorter time (skipped reads drop their
cycles) and through the ADC bias term, charged on ungated steps only. Limits: DFFs are counted at 4.25 NAND2-eq although
DFFPOSX1 leaks 54.98 nW (16.7 NAND2-eq), so flop leakage is under-counted about 4x (band hi 5x); LUT/coupling storage and the array
(non-volatile FeFET) are not included; typical corner, no temperature scaling.

Effect: leakage was negligible and is now a material block, so earlier absolute energies, and in particular the I10 stall-gated power
comparison, are superseded; re-run after this change (smoke re-run 16 Nov IST).
