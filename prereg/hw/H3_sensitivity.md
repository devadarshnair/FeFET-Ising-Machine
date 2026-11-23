# H3 prereg: sensitivity grid on the H2 headline contrast

**FROZEN by the commit that adds this line (16 Nov IST), untagged.** Frozen before any Stage 2 scored value was read; open MINORs of the pre-Stage 2 internal review resolved below/in the evaluators.

(superseded status line) **DRAFT — untagged, author review required.** Win/equivalence margins follow the H2 ruling of 16 Nov IST (5 % energy, +-1 pp success); the advance rule is still author-only [AUTHOR]. Compute:
docs/hw/results/P6.02_budget.md. Sources: design plan §5, design review §2 (kill criteria), P6.01/P2.07 cost-model hooks.

## 1. Purpose and hypothesis
Re-run the H2 headline contrast (full machine and best rung versus B1-tuned, B3, and B2 where QKP applies) over a
registered grid. H3-a: the H2 win survives the credible range. Advance to H4 only if it holds in >= 80 % of the grid
cells and the break-even factor of every uncertain term is >= 2 (the stated x2 stand-in uncertainty) [margins]. Open untagged items (all author-only): advance thresholds, equivalence margins, whether a re-tuned arm is registered.
If H2 produced no win, H3 is not run.

## 2. Grid (every design plan §5 parameter)
| Parameter | Values | Implementation |
|---|---|---|
| FeFET read energy per cell/MAC | nominal x {0.2, 0.5, 1, 2, 5} | cost-only: scale hook on e_array_cell_read, recomputed from counters |
| Array / search-line capacitance and ADC energy | x {0.5, 1, 2, 3} | cost-only: scale hooks on array-RC and ADC rows (e_adc_conv_bit and e_adc_bias_step together, "ADC energy") |
| ADC bits | nominal {-2, -1, 0, +1, +2}; plus nominal - 3 if the nominal is <= 4 bits (paper value low) | trajectory for ours; for B1 a cost-only re-pricing of its nominal-bit runs (frozen MINOR 9: exact at sigma = 0, an approximation at sigma > 0 because noise quantises differently; B1 cells at adc_delta != 0 with sigma > 0 are labelled approximate and cannot by themselves carry an H3 pass) |
| Relative current noise sigma (Vth / conductance) | x {0.5, 1, 2, 5} | trajectory: cim_field sigma, new runs |
| RNG energy per draw | x {0.3, 1, 3} | cost-only |
| Clock / array settle time | x {0.5, 1, 2} | cost-only (time and leakage) |
Full grid = 5 x 4 x 5 x 4 x 3 x 3 = 3600 cells (4320 if the optional "nominal - 3 ADC bits" value is added; the registered count is 3600, without it). Only ADC bits x sigma (20 combinations) change trajectories; the other
180 energy/time combinations per trajectory configuration are recomputed from the logged counters (OpCounters), so
no extra simulation is needed. B3 (digital) has neither ADC bits nor sigma: it reuses the H2 runs and is scaled
only on RNG, clock and the shared digital rows. B2 reuses its H2 runs and is scaled on read, capacitance, clock.
Stall detection under noise is in H3 through the sigma axis; the explicit false-stall test is H5 (see H5 §4).

## 3. Runs and tuning
Arms: ours-best (config frozen from H2, including I7/I10 if they passed) and B1-tuned (config frozen from H2); no
re-tuning inside H3 (a re-tuned variant is a separate registered robustness arm [open decision]). Test instances: first 5 of each H2 test
set, 5 seeds, 150 sweeps, same seeds as H2. Families: Max-Cut and MaxSAT (colouring omitted, secondary). Trajectory runs: 20 configs x 2 arms x 25 runs per family.

## 4. Metrics and rules (frozen)
- Per cell: ratio of ETS99 and of TTS99 (H2 definition) of ours over each baseline, quality at fixed budget, area
  ratio; paired bootstrap 95 % CI over instances (10 000 resamples) per cell.
- Cell "wins" iff the H2 win margin is met on the registered metric with the CI excluding 1 and quality within the equivalence margin.
- Advance: win fraction >= 0.80 over all 3600 cells and >= 2 problem classes; break-even factor (the multiplier on a
  single term that makes the ratio 1) >= 2 for every term, **including terms that favour the baseline** (reported for
  every term, not only the ones that hurt us).
- Reported regardless of outcome: the full cell table, the break-even factor per term, the dominant uncertain term.
- Dominance sensitivity: ADC energy and read energy are reported first because the design review §3 table names ADC
  energy as the deciding term against B3.
- A fail ends the claim at H3 with the report "the H2 result does not survive the credible range".

## 5. Open items
Win margin is the H2 ruling (>= 5 % lower energy-to-solution at equal-or-better success; equivalence +-1 pp success and +-5 % energy); advance thresholds (provisional 80 %, 2), whether sigma x5 is credible for the machines, whether to add a
re-tuned arm, and whether B3 should be scaled on SRAM energy too (default yes, via the b3_extra rows).
