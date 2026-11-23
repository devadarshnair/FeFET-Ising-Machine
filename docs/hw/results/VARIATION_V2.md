# VARIATION_V2: why every machine fails at nominal variation, a physical model, mitigations under one rule

Label: model-level study (smoke grid, not a registered study). Code: `scripts/testing/variation_v2.py`; tests:
`tests/hw/test_variation_v2.py`; generated tables: `docs/hw/results/variation_v2/smoke_var_report.md` and
`smoke_var_summary.csv`; raw rows: `sim/out/hw/variation_v2/*.jsonl` (gitignored, reproducible by the command below).
All energies use the canonical table (`energy_table_v1_p309.csv`) and char_v1; ratios only, as everywhere in this project.

## 1. Root cause (checklist B1)

**Step 1: which v1 term kills success.** Stage 3/4 used the H5 model `machines.PerturbedCim` ("v1"). One term at a
time at nominal, p3n240 instance 801, 6 seeds, 150 sweeps (diagnostic run, `docs/hw/results/variation_v2/diag_v1_terms.txt`):

| term alone at x1 (others 0) | ours Kc2+I11 mean conflicts / success | B1_best mean conflicts / success |
|---|---|---|
| none (dev_x0, ideal) | 0.67 / 2 of 6 | 1.0 / 1 of 6 |
| read noise | 0.67 / 2 of 6 | 1.0 / 1 of 6 |
| write band (+-5 % on ON cells) | 0.67 / 2 of 6 | 1.0 / 1 of 6 |
| device sigma (level-0 cells) | 6.5 / 0 | 21.2 / 0 |
| ADC offset mismatch | 8.2 / 0 | 22.5 / 0 |
| all (nominal) | 11.7 / 0 | 28.8 / 0 |

Two terms kill it, each alone: the error of the **empty (level-0) cells** and the **per-column ADC offset**. Both are
dominated in v1 by a modelling defect, not by physics:

* **D1 (structural bug): errors are added after the ADC.** v1 adds the static cell error and the ADC offset to the
  field as a continuous number, scaled by 2^plane, after conversion. In a real bit-plane CiM each column's error is
  added to that column's current before its own ADC. With LSB = 1 cell, a column error below half a cell rounds away.
  v1 throws away this noise immunity and charges every column's sub-LSB error, times 2^p, on every read. A 0.25 LSB
  sigma offset gives 4.6 % wrong codes in a real ADC; v1 treats it as a continuous +-0.25 x 2^p field error on every lane.
* **D2 (magnitude bug): the +-5 % multi-level write-verify band is applied to binary ON cells.** char_v1 gives level 7
  an open-loop sigma of 0.15 nA (0.15 %), because the 1 MOhm series resistor saturates the ON current. v1 uses
  5 %/sqrt 3 = 2.9 %, about 19x too large. The term table above shows this term is harmless alone, because ON cells are
  sparse. The bug is real but not the killer.
* **D3 (shape bug): level 0 is modelled as zero-mean Gaussian (2.9 nA "verified").** The SPICE Monte Carlo
  (P1.10 t4e, 200 cells) shows a one-sided, exponential leakage tail instead: median 0.06 nA, mean 1.32 nA,
  sigma 4.86 nA, p99 33 nA. This is a subthreshold slope of about 119 mV/dec with only about 0.38 V (2.5 sigma) between
  the erased Vth and the 1.2 V read WL. The tail carries a mean bias that grows with the number of active empty cells
  in a column. v1's zero-mean noise does not have this bias.

**Step 2: the physical model (v2).** v2 removes D1-D3. Each level k gets its SPICE transfer curve I_k(dVth), taken
from the 200 t4e samples (re-extracted bit-exactly to `docs/hw/char/t4e_mc_samples.csv`; test
`test_transfer_samples_reproduce_char_v1`). Each cell is then given a D2D shift and a C2C shift. The errors are summed
per column into that column's analog current, then pass through ADC offset and gain, Johnson read noise, and the
column's own ADC (rounding and clipping), then the shift-add. One term at a time under v2 at nominal (5 seeds, tables in
the report):

* **ours:** D2D alone gives 0 % success on p3n240 and vmc240. ADC offset alone gives 0 % on p3n240 and 60 % on
  vmc240. Read noise alone gives the ideal result. C2C alone gives 0 % open-loop, which write-verify repairs.
* **B1:** D2D alone and the multi-level C2C spread each give 0 %. ADC offset alone gives 0 % on p3n240.

**Root-cause verdict.** With correct physics the binding term is still the device: **D2D Vth spread of the empty
(level-0) cells**. Their leakage tail sums over every active row of a column, about 80-240 rows here. For B1's native
3-bit cells the open-loop spread of levels 1-6 (sigma/mu 0.39-1.03) adds to this. The **uncalibrated ADC offset** is
the second killer. Read noise is not a problem at any k tested.

## 2. Are the nominal sigmas realistic? (checklist B2)

| term | nominal value used | literature | verdict |
|---|---|---|---|
| sigma(Vth) | 0.15 V HVT, 0.10 V LVT, quoted directly from Ni 2019 SI Fig. 5 (the source of char_v1 t4e) | **Inference, not a quoted value:** Beyer 2020 reports a 28 nm HKMG foundry FeFET with MW 1.4 V and state distributions "approaching a mature 6Sigma" separation. Reading this as 1.4 V spanning about 6-12 sigma gives sigma of roughly 0.1-0.2 V; that derivation is ours ([Beyer 2020](https://consensus.app/papers/details/w:cbe7855a-c32e-4332-b54d-78c2f1469ddc/)); scaled cryogenic HZO about 40 mV ([Das 2026](https://consensus.app/papers/details/w:2b68d2d7-7d09-4cdd-8bd7-80f8c60a6219/)); D2D set by domain count and phase ([Ni 2019 VLSI](https://consensus.app/papers/details/w:91190ca5-e514-48ba-bc2c-eb0e3652d9b3/), [Choe 2021](https://consensus.app/papers/details/w:3d8d31d1-3571-4127-bf54-0194d9a1b96a/)); D2D and C2C both measured at 28 nm ([Phadke 2026](https://consensus.app/papers/details/w:313e9ece-798e-4d99-bc3e-218827ef96ec/)) | **realistic** (mid-range for a foundry 28 nm device) |
| memory window / read margin | MW about 1.0 V, read WL 1.2 V, so HVT is about 2.5 sigma from conduction | 1.4 V ([Beyer 2020](https://consensus.app/papers/details/w:cbe7855a-c32e-4332-b54d-78c2f1469ddc/)), 1.6 V ([Dutta 2022](https://consensus.app/papers/details/w:48539059-e204-4eee-ad89-43c9757e3961/)), about 3 V with 20 nm HfO2 ([Mulaosmanovic 2019](https://consensus.app/papers/details/w:47aac256-7af8-4edd-92ab-23be50d0f83d/)) | **pessimistic** design point (low-end MW, not a bug); see section 6 |
| level-7 spread | 0.15 % (R_S-saturated) | follows from the 1FeFET1R circuit | correct in char_v1; **v1 used 2.9 %: bug D2, fixed in v2** |
| level-0 distribution | v1: Gaussian 2.9 nA | char_v1 MC: heavy one-sided tail | **v1 wrong shape: bug D3, fixed in v2** |
| read noise | v1: 0.15 % x sqrt(rows/2) (static spread reused as dynamic noise) | Johnson noise of R_S: sqrt(4kT x 25 MHz / 1 MOhm) = 0.64 nA rms per conducting cell (physics) | v2 uses Johnson noise; not limiting at any k tested |
| ADC offset | 0.25 LSB (7.4 mV, P1.11) | typical uncalibrated SAR comparator offset is mV-scale | plausible; harmful only without calibration |
| C2C share | not modelled in v1 | measured but not separated in the cited data | **[ASSUMPTION]** 50 % of the sigma^2, labelled |

**Verdict:** the nominal device sigma is realistic. The failure at "nominal" was partly a modelling bug (D1-D3, now
fixed and preserved as model v1 for the record) and partly real physics: the erased-cell leakage tail at a low-end
memory window. Fixing the bugs alone does not restore success. Under v2 with no mitigation, every CiM machine is at
0 % on all four smoke families (tables in section 4).

## 3. Mitigations, one rule for every machine, true costs (checklists B3, B4)

Switches in `Mitigation` (`variation_v2.py`). Each one applies identically to ours, B1 and B2. B3 is digital and has
no analog array, so it has nothing to mitigate and pays 0 (`test_b3_has_no_overhead`). Costs come from each machine's
own priced blocks (`mitigation_cost`):

| switch | physics | runtime cost | one-time / area cost |
|---|---|---|---|
| `wv` write-verify, all levels | multi-level: ISPP (one coarse pulse per 50 mV of the cell's dVth, then bisection fine pulses), residual uniform within +-5 %; level 0: re-erase redraws only the C2C part until I < 5 % of a unit (cap 32, best attempt kept; D2D cannot be erased away); level 7: one verify read | 0 | every pulse (char_v1 per-level e_write, 2.02 us) and verify read (level read energy, 20 ns), serial |
| `diff` complementary 2-cell coding | each cell has a partner at level kmax-k; the pair is converted differentially and the count is recovered as (D + kmax L)/2, so the common leakage becomes a gain error and the decision threshold doubles | partner cells read (x2 array energy), +1 SAR bit per conversion, +1 cycle per read | 2x cells (area, programming), ADC C-DAC doubles (x1.3 ADC area) |
| `cal` per-column ADC offset/gain calibration | deployment patterns x = 0 and all rows, 64 reads each; 4-bit offset trim (1/8 LSB), 8-bit reference trim (0.1 %); does not track drift or temperature after deployment | reference-DAC switching of about one conversion bit per conversion | 2 x 64 conversions per column; 12 DFF plus 272 unit caps per column |
| `bin` binary cells | B1 becomes B1 bit-sliced (its existing b1bs pricing); B2 gets unary binary filter cells (4x rows); ours is already binary (no-op) | B1: 3x columns/conversions (b1bs price); B2: binary-cell filter read energy | B2: 4x filter cells |
| `r3` redundant reads | 3 conversions per column per read, median (majority) code; dynamic noise only | 3x array + ADC energy and read cycles, compare-adds | 2 code registers per column |

Fix found while wiring B1 bit-sliced: under the H7 "fs" rule, `b1bs` was priced with the native 3-bit full-scale
bits. It now uses the bit-plane tile sums (`machines.build`, `test_b1bs_fs_bits_are_bitplane_sums`). b1bs+fs was never
used in Stages 2-4, so no earlier result changes.

## 4. Stress test (checklists B5, B6, B7)

`python -I scripts/testing/variation_v2.py --smoke-var [--machine M] [--chunk i/N]`, then `--summarize`. The grid
covers 4 instances (col3p 501 = 120-spin colouring; p3n240 801 = 240-spin colouring; vmc120/vmc240 = G(n, 4n) Max-Cut,
reference cut from 200 x 20000-sweep SA in `docs/hw/char/vmc_reference.json`) plus 2 QKP instances for B2. All terms
are scaled together (k = 0, 0.5, 1, 1.5, 2, 3). It also includes the drift sweep and one-term-at-a-time points. Each
cell runs 5 seeds at 150 sweeps (QKP: 10^4 proposals) with the Stage 2 tuned configs. Ran locally through
the local job queue, each chunk under 1 h: 2530 runs, wall about 3.5 h.

ADC clipping under noise is simulated for every machine: each column ADC clips at its own top code
(`test_adc_clipping_is_simulated`). This covers B5 for ours and B1. I7v2 (variable ADC bits) is supported by the engine
(the LSB/top are read live from the machine) but is not an arm of this grid.

**Success at nominal (k = 1), 5 seeds, success rate per family (col3p / p3n240 / vmc120 / vmc240):**

| machine | ideal device | no mitigation (v2) | v1 model (old) | cheapest restoring combo | its success | runtime energy overhead | one-time energy | area overhead |
|---|---|---|---|---|---|---|---|---|
| ours Kc2+I11 | 1 / 0.2 / 1 / 1 | 0 / 0 / 0 / 0 | 0 / 0 / 0.2 / 0 | **wv+diff+cal** | 1 / 0.2 / 1 / 1 | **+33.6 %** | 23.5 nJ (calibration dominates; programming 1.05 pulses/cell) | +11.9 % |
| B1_best (native 3-bit) | 1 / 0.2 / 1 / 1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | **wv+cal** | 1 / 0.4 / 1 / 1 | **+11.6 %** | 61.5 nJ (1.63 pulses/cell) | +15.8 % |
| B1, robust choice | | | | wv+diff+cal+bin | 1 / 0.2 / 1 / 1 | +40.1 % | 141 nJ | +46.2 % |
| B3 (digital) | 0 / 0 / 0 / 0 | unaffected | unaffected | none needed | 0 / 0 / 0 / 0 | 0 | 0 | 0 |
| B2 (QKP) | q 0.974 / 0.970 | q 0.268 / 0.831 | q 0.953 / 0.971 | **wv** (quality) | q 0.944 / 0.979 | 0 % | 0.042 nJ | 0 % |

(p3n240 is at 0.2 even on the ideal device at this budget, Stage 4's L1 finding; "restored" means within 10 pp of the
ideal device on every family. B3 fails the 0-conflict / 0.99 targets at this small budget on the ideal device too, so
it is no comparator here.)

**Robustness beyond nominal (mean success over the four families; ideal = 0.80):** ours wv+diff+cal holds 0.80 at
k = 0.5-2 and 0.75 at k = 3. B1 wv+cal / wv+diff+cal holds to k = 2 (0.75) and collapses at k = 3 (0.20). B1 with the
binary (bit-sliced) cells plus wv+diff+cal holds 0.85 at k = 3. Write-verify alone is not enough for either machine
(ours 0.05, B1 0.35 at k = 1). Redundant reads buy nothing, because read noise is not the limit, and cost +157 % to
+258 % energy.

**Drift (B6, parametric).** The retention fit is unfitted (k = 0 in char_v1), so drift is a sweep: MW loss
drift_v_dec x 6 decades, split +-1/2 between HVT and LVT, through the transfer curves; calibration at deployment is not
repeated. With wv+diff+cal, success holds to 0.01 V/dec (ours 0.80, B1 0.75), halves at 0.02 V/dec (0.45 / 0.25) and
is 0 at 0.05 V/dec for both. Retention, not static variation, becomes the next limit; periodic recalibration or refresh
is not modelled. **Stated limitation:** this is a parametric sweep, not a retention prediction.

### 4b. B2 (HyCiM, QKP)

The smoke runs 10^4 proposals on jeu_100_25_1 and jeu_100_50_1, 5 seeds (530 runs). At this budget the 0.99 x optimum
success target is not informative: the ideal device reaches it in 1 of 10 runs. The comparison therefore uses mean
quality q = profit/optimum (ideal device 0.974 / 0.970):

| B2 at k = 1 | q (25_1 / 50_1) | runtime overhead | area overhead | one-time |
|---|---|---|---|---|
| v2, no mitigation (open-loop multi-level filter cells) | 0.268 / 0.831 | 0 | 0 | 0.012 nJ |
| v1 (old model) | 0.953 / 0.971 | 0 | 0 | - |
| wv | 0.944 / 0.979 | 0 | 0 | 0.042 nJ (2.99 pulses/cell) |
| wv+cal | 0.952 / 0.964 | 0 | +2.8 % | 0.044 nJ |
| wv+diff+cal | 0.949 / 0.975 | +10.7 % | +28 % | 0.090 nJ |
| wv+diff+cal+bin | 0.951 / 0.978 | +85 % | +182 % | 0.142 nJ |

Open-loop B2 loses most of its quality. **Write-verify alone restores B2 to within about 3 % of ideal quality** at no
runtime cost. The other switches add cost without a clear gain at 5 seeds. B2's success-vs-k curves are flat at 0 for
the budget reason above, so no "restoring combo" can be claimed from success. That is a stated gap: a 10^5-proposal B2
rerun is needed for a success verdict.

## 4c. Statistical re-run (review fixes 1-4)

Grid `variation_v2.py --smoke-var --stat` (`grid_stat`): 13710 runs, about 50 % local (local job queue) and 50 % rented cloud CPU
(25 jobs, checksums in `00_admin/cloud_cpu/offload/return/variation_v2b.sha256`). Raw rows are in `sim/out/hw/variation_v2b/*.jsonl`.
Tables are in `docs/hw/results/variation_v2b/stat_report.md`, `stat_summary.csv`. The decision points are k = 1 and k = 3: 20 seeds x 3
instances x 4 families = 240 runs per cell; B2 runs 3 QKP instances x 10 seeds at 10^5 proposals. Success carries Wilson 95 % CIs.

**Selection rule (fix 1).** A combination restores success iff (a) pooled over the families, the Newcombe 95 % lower bound of
p - p_ideal is above -0.10 (non-inferiority), and (b) no family is significantly worse than the ideal device. A per-family 10 pp
test cannot be resolved at 60 runs: identical counts at p about 0.6 already give a lower bound of about -0.17. The pick is the
restoring combination with the lowest runtime energy overhead.

| machine | ideal device, pooled | pick at k = 1 (pooled diff, lower bound) | runtime / once / area | pick at k = 3 |
|---|---|---|---|---|
| ours Kc2+I11 (fs) | 0.87 | **wv+diff+cal** (+0.00, -0.06) | +33.9 % / 25.5 nJ / +11.9 % | wv+diff+cal (-0.03, -0.09) |
| ours I7v2 | 0.41 (I7v2 itself is lossy) | **wv+diff+cal** (+0.02, -0.07) | +33.4 % / 25.5 nJ / +11.9 % | wv+diff+cal (+0.04, -0.10) |
| B1_best | 0.85 | **wv+cal** (-0.01, -0.08) | +11.8 % / 59.5 nJ / +15.8 % | **only wv+diff+cal+bin** (+0.01, -0.05): +39.8 % / 147 nJ / +46.2 % |
| B2 (QKP, 1e5) | 0.57 [0.39, 0.73] (n = 30) | **none restores** | best: v1 0.50, wv+diff+cal+bin 0.40, wv 0.33 | none |
| B3 | digital: no analog variation | n/a | 0 | n/a |

At k = 1 B1 also restores with wv+diff (+15.1 %) and wv+diff+cal (+26.9 %). The 5-seed pick "wv+cal" therefore survives at
240 runs per cell. Under write-verify, B2 keeps about 0.33-0.40 vs 0.57 ideal at 10^5 proposals: write-verify restores quality to
within about 3 % (section 4b), but success at the 0.99 x optimum target is not restored by any combination in the grid.

**C2C-share sensitivity (fix 3; p3n240 + vmc240 pooled, k = 1, 3 instances x 10 seeds):**

| machine, mitigation | C2C 0 | 0.25 | 0.5 (default) | 0.75 |
|---|---|---|---|---|
| ours wv+diff+cal | 0.40 [0.29, 0.53] | 0.80 | 0.74 | 0.77 |
| B1 wv+diff+cal | 0.00 [0.00, 0.06] | 0.65 | 0.72 | 0.77 |
| B2 wv+diff+cal | 0.27 | 0.33 | 0.33 | 0.33 |

The conclusion depends on this unmeasured parameter. If all of the sigma(Vth)^2 is static D2D (share 0), re-erase cannot remove the level-0
tail. ours then keeps only about half of its restored success, and B1 is not restored at all. At k = 2 the same holds more strongly
(share 0: ours 0 %, B1 0 %; share 0.25: ours 0.43, B1 0 %). The restoring claims above hold for a C2C share of at least
about 0.25 (ours) / 0.5 (B1 at k = 2). Measuring the D2D/C2C split on silicon is the first gap to close.

**I7v2 (fix 4):** the engine reads I7v2's live b_hi/b_lo ADC bits. Unmitigated it fails at k >= 1 like ours (0 %); with
wv+diff+cal it holds its own ideal level (0.41-0.45) over k = 0.5-3. I7v2 is not less robust than ours under mitigation; its
low ideal success is the I7v2 quantisation loss already known from Stage 3.

Bug found and fixed during the re-run: run as a script, `variation_v2.py` was loaded twice (`__main__` and the `variation_v2`
that `machines.py` imports). The C2C share set by the harness therefore did not reach the ours/B1 cell programming in the first
C2C runs: all shares gave identical counts. Those 1440 rows were moved to `sim/out/hw/variation_v2b_invalid_c2c/` and re-run
(`c2cfix_*.jsonl`); the module now aliases itself (`test_script_and_import_share_module_state`). B2 and every C2C = 0.5 row were
not affected, because they read the same module.

## 5. Answer

* **Root cause:** D2D Vth spread of the erased (level-0) cells. Their leakage tail sums over every active row of a
  column. Add the uncalibrated per-column ADC offset, and for B1 the open-loop multi-level spread. v1 inflated these by
  injecting errors after the ADC (D1), using a 19x too wide ON-cell band (D2) and using zero-mean Gaussian level-0 noise
  (D3).
* **Sigma realism:** sigma(Vth) of 0.10-0.15 V is realistic for 28 nm foundry FeFETs. The low memory window (about
  1.0 V) is pessimistic. D1-D3 were bugs and are fixed (v1 kept bit-exact for the record).
* **Superseded by section 4c (240-run cells, CI rule):** ours wv+diff+cal (+33.9 %); B1 wv+cal (+11.8 %) at k = 1 and
  bit-sliced wv+diff+cal at k = 3 (+39.8 %); B2 not restored on success; all conditional on a C2C share of at least 0.25-0.5.
* **First-pass (5 seeds), kept for the record. What restores success at nominal:** ours needs wv+diff+cal (+33.6 % run energy, +11.9 % area, 23.5 nJ one-time).
  B1 needs wv+cal (+11.6 %, +15.8 % area, 61.5 nJ), or bit-sliced + wv+diff+cal for k = 3 robustness (+40 %, +46 %
  area). B2 needs wv (0 % runtime overhead, about 3 pulses/cell), judged on quality; success is not resolvable at the smoke budget. B3 needs nothing.
* **Effect on the comparison:** after mitigation ours and B1 return to their ideal-device success, but only if the C2C share of the Vth spread is at least about 0.25 (ours) / 0.5 (B1 at k = 2), which is unmeasured. B2 is not restored on success by any combination at 10^5 proposals (best 0.40 vs 0.57 ideal). The cheapest B1
  restore costs less runtime overhead than ours, because ours already pays the differential P+/P- columns. Energy
  ratios from Stages 2-4 therefore need these overheads applied per machine before any hardware claim at non-ideal
  devices.

## 6. Known gaps

* Write-verify level 0 assumes the C2C part is redrawn on re-erase (C2C_SHARE = 0.5, assumption; swept in section 4c: at share 0 the restoring claims fail). If the variance were
  all D2D, re-erase could not remove the tail, and diff+cal would have to carry it alone. The v2 "diff+cal" rows (no
  wv) show this case: ours restores col3p/vmc120 but not vmc240 (0.6).
* The level-0 tail beyond the 200 SPICE samples (p99.5+) is a log-linear extrapolation of the transfer curve. It is a
  little more pessimistic than the sample sigma (7.7 vs 4.86 nA).
* Not mitigated here but promising: a larger read margin (lower read WL or larger MW). Shifting the HVT 0.18 V further
  from the read bias cuts the level-0 mean leakage 17x (1.61 to 0.094 nA; transfer-curve estimate). It needs a SPICE
  re-characterisation of level 7 at the lower bias.
* Calibration does not track temperature or drift (no periodic recalibration modelled). Temperature/supply stay the
  parametric v1 gain.
* B2 success at 10^5 proposals uses 3 QKP instances x 10 seeds (n = 30 per cell, ideal 0.57 [0.39, 0.73]). The k = 1 and k = 3 decision cells use 20 seeds x 3 instances x 4 families = 240 runs, with Wilson 95 % CIs and the pooled Newcombe rule (section 4c).
* The C2C share is unmeasured. Section 4c sweeps it over 0, 0.25, 0.5 and 0.75 only, so the restore claims are conditional on it.

## Internal review

### Response to the internal review fix list (commits 69ac6de, b037206 and the final commit of this update)

| fix | done | evidence |
|---|---|---|
| 1 statistics | 240 runs per decision cell (20 seeds x 3 instances x 4 families), Wilson CIs, pooled Newcombe non-inferiority + no-family-worse rule | `grid_stat`, `wilson`, `newcombe_diff`, `restoring`; `test_stat_grid_design`, `test_wilson_and_newcombe`, `test_restoring_selection_rule`; section 4c; `variation_v2b/stat_report.md` |
| 2 B2 at 1e5 | 3 instances x 10 seeds, all combos at k = 1, ideal/none/wv/wv+cal (+v1) at k = 2, full set at k = 3 | section 4c; B2 tables in `stat_report.md` |
| 3 C2C share | 0 / 0.25 / 0.5 / 0.75 for wv and wv+diff+cal at k = 1, 2, for ours, B1 and B2 | section 4c table; `test_c2c_share_context_and_effect`, `test_script_and_import_share_module_state` |
| 4 I7v2 | `ours_i7v2` arm, whole k grid with none and wv+diff+cal | section 4c; `stat_report.md` ours_i7v2 tables |
| 5 B2 calibration rule | `calib_cost` shared by every converter (ours/B1 column ADCs, B2 filter comparator): trim area, deployment conversions, runtime term | `calib_cost`; `test_calib_cost_rule`, `test_b2_calibration_uses_the_shared_rule` |
| 6 checkout independence | QKP data via `$HW_PROJECT_ROOT` / `$HW_QKP_DIR` + `$HW_QKP_OPTIMA`, the checkout ancestors, or the git common dir; B2 tests skip with a reason if absent | `hycim()`, `qkp_available()`; `test_qkp_paths_resolve_or_skip_reason`; clean detached worktree of 69ac6de under /tmp: 53 passed; final suite 54 passed |
| 7 Beyer label | Ni 2019 SI Fig. 5 values quoted directly; the 0.1-0.2 V reading of Beyer 2020 is labelled as our inference | section 2 table |


**Commits:** see `git log --grep VARIATION_V2` on branch hw/p4-baselines (one commit; the hunks in the shared files
`machines.py` and `plan.py` are additive and listed below).

**Changes to shared files (added, nothing rewritten):**
* `scripts/testing/machines.py`: `build/drive/execute` take an optional `mit=None` (None = unchanged). In `build`, a
  v2 Mitigation selects `variation_v2.PerturbedCimV2` instead of `PerturbedCim`. `drive` adds `mit`, `counters` and
  `prog_v2` to the record only when `mit` is given. `mapped()` gains the `vmc120`/`vmc240` smoke Max-Cut families.
  b1bs+fs full-scale bits fix.
* `scripts/testing/plan.py`: `FAMILY_ID` gains `vmc120: 14`, `vmc240: 15`.
* New: `scripts/testing/variation_v2.py`, `tests/hw/test_variation_v2.py`, `docs/hw/char/t4e_mc_samples.csv`
  (extracted from hw-p1 `sim/out/t4/t4e_mc_l*.{cir,csv}`, current at T_READ - 10 ns as check_t4.py),
  `docs/hw/char/vmc_reference.json`, `docs/hw/results/variation_v2/{smoke_var_summary.csv,smoke_var_report.md,diag_v1_terms.txt}`.

| item | claim | evidence |
|---|---|---|
| B1 | killer terms = level-0 D2D leakage + ADC offset; v1 defects D1-D3 | `diag_v1_terms.txt` (v1 one-term runs); report "one term at a time" tables; section 1 |
| B2 | sigma(Vth) realistic (cited); D2 (19x ON band), D1, D3 were bugs and are fixed in v2 | section 2 table with citations; `test_transfer_samples_reproduce_char_v1`, `test_transfer_monotone_and_nominal` |
| B3 | write-verify of all levels with char_v1 costs (ISPP multi-level, re-erase level 0, verify read level 7) | `program_cells`, `program_cost`; `test_write_verify_level0_and_multilevel`, `test_program_ideal_exact_and_cost`; pulses/cell column in the report |
| B4 | diff, cal, bin, r3 under one rule with costs | `ColumnField`, `b2_filter_v2`, `mitigation_cost`; `test_diff_and_calib_cancel_common_leakage`, `test_calibration_removes_adc_offsets`, `test_redundant_reads_reduce_dynamic_errors`, `test_cost_off_is_zero_and_reads_triple`, `test_cost_diff_and_calib_charge_area_and_once`, `test_b3_has_no_overhead`, `test_b2_filter_ideal_exact[*]`; off = bit-exact: `test_v1_mitigation_is_legacy_bit_exact[ours,b1]`, `test_v2_ideal_device_bit_exact_to_unperturbed[*]` (21 cases) |
| B5 | clipping simulated for every machine; I7v2-capable engine | `test_adc_clipping_is_simulated`, `test_column_engine_matches_cimfield_rounding`; I7v2 swept in section 4c |
| B6 | parametric drift sweep in the harness; retention unfitted stated | `DRIFT_GRID`, `drift_shift`, `test_drift_shift_signs`; report drift tables; section 4 |
| B7 | `--smoke-var` harness, success/energy vs k per machine x mitigation | `variation_v2.py --smoke-var/--summarize`; `test_grid_and_points`, `test_smoke_job_ours_runs`, `test_b2_v2_run_and_cost`; `smoke_var_summary.csv`, `smoke_var_report.md` |

Commands: `python -m pytest -q tests/hw/test_variation_v2.py` (54 passed; 46 at the first pass);
`python -I scripts/testing/variation_v2.py --smoke-var --stat --machine M --chunk i/N` then `--summarize-stat`;
`python -I scripts/testing/variation_v2.py --smoke-var --machine {ours,b1,b2,b3} --chunk i/N` then `--summarize`.
Environment: conda env `swref` (numba). Set OPENBLAS_NUM_THREADS=1 under the local job queue: the first B2 chunk died with
an OpenBLAS allocation error and was re-run single-threaded.

## Internal review verdict (2026-11-17, independent)

Checks: read sections 1-6, the internal review and `mitigation_cost`/C2C code at c3518f5 (identical to the working tree).
Ran `pytest tests/hw/test_variation_v2.py` on a clean detached worktree of c3518f5 under the local job queue: 41 passed and
5 B2 tests failed. All 5 failures are FileNotFoundError on `../../09_next_phase/benchmarks/qkp_billionnet_soutif/`,
because the QKP path resolves relative to the checkout location. This is a portability defect, not a logic failure.

| item | verdict | evidence / reason |
|---|---|---|
| B1 root cause | PASS (provisional) | The one-term tables and the D1-D3 argument are mechanistic and consistent with char_v1 t4e. They rest on 5-6 seeds, but a 0 % vs 100 % contrast survives that. |
| B2 sigma realism | PASS with fix | Values trace to Ni 2019 SI Fig. 5 and the code (`sigma_vth`, line 16). The cited sources exist as literature links. The "approaching 6 sigma, so sigma 0.1-0.2 V" inference is the implementer's derivation and must be labelled that way. The C2C_SHARE = 0.5 assumption has no sensitivity sweep (fix 3). |
| B3 write-verify all levels | PASS | `program_cells`/`program_cost` use char_v1 pulse energy and time and are charged as one-time costs for every analog machine. |
| B4 mitigations, one rule | FAIL (minor) | The runtime rule is shared by ours and B1. B2 calibration is a different rule (fixed 4 DFF + 16 caps, no runtime term). "Cheapest restoring combo" is chosen per machine on 5 seeds: B1 wv+cal beats wv+diff+cal on one p3n240 seed (0.4 vs 0.2), which is within noise. |
| B5 I7v2 / clipping | FAIL | Clipping is simulated for all machines. I7v2 is in the ablation ladder and is the flagged least-robust arm, but it was not swept. |
| B6 drift | PASS | Parametric sweep plus a stated limitation (section 4, section 6). |
| B7 harness | PASS with fix | `--smoke-var` exists, and success/energy vs k per machine x mitigation is reported. Statistics are too thin for "restored" claims (fix 1). |

**Not yet accepted. Fix list:**
1. `scripts/testing/variation_v2.py:661` (SMOKE_SEEDS = 5) and `SMOKE_INST`: at the k = 1 and k = 3 decision points, use
   at least 20 seeds and at least 3 instances per family, and report Wilson 95 % CIs. "Restored = within 10 pp" cannot
   be resolved at 5 seeds, where one seed equals 20 pp. Re-select each machine's cheapest combo under the same
   CI-based rule.
2. B2 at 10^5 proposals (`B2_PROPOSALS`, the variation_v2.py smoke grid): a full success verdict needs it,
   because quality-only is a stated gap. Run ideal, none, wv and wv+cal at k = 0, 1, 2 with at least 10 seeds.
3. C2C_SHARE sensitivity (`variation_v2.py:68`): sweep 0, 0.25, 0.5 and 0.75 for wv and wv+diff+cal at k = 1 and 2,
   for ours, B1 and B2.
4. I7v2 arm: add `ours` with I7v2 to `MACHINE_ARMS` and run the k-grid with none and wv+diff+cal.
5. `mitigation_cost` B2 calibration branch: state why its trim hardware differs from the per-column ADC rule, or
   align the two. Also add the calibration runtime term if one applies.
6. `tests/hw/test_variation_v2.py` (B2 tests): resolve the QKP benchmark path from a configured root, or skip with a
   reason, so that a clean checkout passes.
7. Section 2 table: mark the sigma = 0.1-0.2 V derivation from Beyer 2020 as an inference, and quote Ni 2019 SI
   Fig. 5 values directly.

## Re-check 2 (2026-11-20, internal review)

Checks: read section 4c, the internal review response, `calib_cost` and `mitigation_cost` at 73a2621. Ran
`pytest tests/hw/test_variation_v2.py` on a clean detached worktree of 73a2621 (swref python, local job queue): **54 passed**.
I did not repeat the 13710-run grid. Its design (240 runs per cell, Wilson CIs and the pooled Newcombe rule) is tested and
is applied identically to every machine.

| fix | status |
|---|---|
| 1 statistics + CI pick rule | done. The B1 wv+cal pick survives at 240 runs. |
| 2 B2 at 1e5 | done. No combination restores B2 (best 0.40 vs 0.57 ideal), and this is reported as a negative. |
| 3 C2C sweep | done. The restore claims depend on it; it is stated as unmeasured and flagged as the first gap. |
| 4 I7v2 | done. I7v2 holds its own ideal under wv+diff+cal. |
| 5 one calibration rule | done. `calib_cost` is shared by the ours/B1 ADCs and the B2 comparator. |
| 6 checkout independence | done. 54/54 pass on a clean checkout. |
| 7 Beyer label | done. |

B1-B7: B1, B2, B3, B4, B5, B6 and B7 all PASS on the evidence.

Fixed C2C dependence and B2 failure are accepted as stated limitations only if every summary carries them. Three
statements in the doc still do not:
1. Section 5, "Effect on the comparison" (line 210): "after mitigation ours and B1 return to their ideal-device success"
   is stated unconditionally. Add "for C2C share >= 0.25 (ours) / >= 0.5 (B1 at k = 2); B2 is not restored on success at
   1e5 proposals".
2. Section 6, lines 227-228: the bullets "Smoke-scale statistics: 5 seeds, one instance per family" and "B2 success is uninformative at
   10^4 proposals" are superseded by section 4c. Mark them as first-pass only, or replace them.
3. Section 6, line 229: the claim of 6 failures in `test_timing_v2.py` is stale (that work has since been fixed upstream).
   Re-run the suite, or date-stamp the bullet.

**Verdict: accepted on the science and code, conditional on doc edits 1-3.** These are wording changes only, so no further
review run is needed if the edits match the text above.
Re-check 2 close-out: the three wording edits are applied in the commit that adds this line; accepted.
