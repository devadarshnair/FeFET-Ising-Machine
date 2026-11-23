# H6 prereg: Stage 3 confirmatory follow-up (fresh instances, fresh seeds)

**FROZEN by the commit that adds this file (16 Nov IST), untagged, before any Stage 3 run.**
Untagged. Code that implements it is in the parent commit (scripts/testing/plan_h6.py,
gen_jobs_stage3.py, evaluate_h6.py, run_cell.py `--h6-cfg`). Preregs H0/H2/H3/H5 (a5f2866) are not changed.

## 0. Status of the leads (read first)
Leads L1-L3 and the I7 / H5 / B1-MESA diagnoses were selected **post hoc** from Stage 2 results (docs/hw/results/
STAGE2_RESULTS.md). Stage 2 data are therefore exploratory for them and are never pooled with Stage 3. **Only fresh Stage 3
data count** for every H6 verdict: instances not used in Stage 2 and a fresh seed stream (Spec.tag = 6, so every run seed
is mix_seed(BASE, family, 200 + i, r, 6), disjoint from Stage 2's tag 0; H5 B2 seeds r = 100..109 vs Stage 2's 0..4).

## 1. Hypotheses (confirmatory)
- H6-L1 (colouring): ours Kc2 + I11 (I10 off pricing) has >= 5 % lower ETS99 than the B1 comparator at equal success, on
  each of two fresh colouring families at larger N (col3p, col4p).
- H6-L2 (Max-Cut): ours no-tweak ("none", I10 off pricing) has >= 5 % lower ETS99 than the B1 comparator at equal success;
  also reported vs B3. B2 is QKP-only and ours is not run on QKP: L2 vs B2 is **not applicable** (stated, not run).
- H6-L3 (Max-Cut budget): ours Kc2 + I11 at 150, 300, 600 sweeps vs the B1 comparator at 150 sweeps: does the Stage 2
  success gap (-13 pp) close with budget, and is the ETS99 win kept at equal success? Reported per budget (3 contrasts).
- H6-I7v2: (a) a full scale set from the max column sum ("fs", lossless) vs v1 full scale n; (b) I7v2 (stall-adaptive
  b_lo = b_hi - 1 on that full scale) vs fs alone; per family. I7v2 survives only if (b) is an energy win at equal success.
- H6-R (restart threshold, request 16 Nov): with K and kick size tuned on a fresh TUNE split, does any restart rule
  (Kc2, MESA-epoch, DA offset) beat no restart on fresh TEST data? Restart counts per run are logged so "never triggered"
  and "triggered but unhelpful" are distinguishable.
- H6-H5 (report-only, H5 rules): variation re-run with arms that do not contain I7 v1 or B1-MESA (Stage 2 floor).

## 2. Design changes since Stage 2 (implemented and tested before freezing)
| Change | What | Check |
|---|---|---|
| I7v2 | ADC full scale = max column sum of the programmed array (cim_field.max_column_sum; CimCfg.fs; RTL cim_field_unit `adc_fs`, tim_top cfg offset 32, 0 = N rows = v1); b_hi = bitlen(fs) exact (LSB 1), b_lo = b_hi - 1 (LSB 2); K_p = 5 as Stage 2 | rtl_spotcheck 44/44 bit-exact incl. 6 new I7v2 cells; tests/hw 285 passed |
| Counter | unchanged and documented (power.py): resets only on a strict best-so-far improvement, so I7 sits at b_lo for most of the run; the fix is the range, not the counter | power.py docstring |
| fs pricing | the noise-free I7-off trajectory re-priced at bitlen(fs) bits (pricing.ours_fs_rebits): exact, same trajectory | test_h6 |
| B1-MESA harness (finding c) | **harness mismatch, fixed**: Stage 2 ran MESA on one whole-run cooling schedule; MESA resets T := T0 at every stall (K ~ n steps), so it never cooled (a hot walk) and scored 0 % on Max-Cut/MaxSAT. B1 calibration attempt 2 (P4.02a), which reached ~99 % of best-known, cools T0 -> T_end **within each epoch** (10 sweeps) and holds T_end. H6 runs MESA with that epoch harness (machines.py cfg `epoch_sweeps`, temperature floor) | test_h6::mesa_epoch |
| Kc2 kick size | cfg `kick_L` (default 10 = the reference software study) | sweep grid test |

## 3. Instances, seeds, budget
| Family | TUNE split (sweep only) | TEST split | Spins | Test seeds |
|---|---|---|---|---|
| Max-Cut (G-set, 800 nodes, fresh) | G9, G20 | G8, G10, G17, G19, G21 | 800 (pad 1024) | 20 |
| col3p: planted 3-colourable, n = 40, deg 4.5 | seeds 601-604 | seeds 501-515 | 120 (pad 128) | 10 |
| col4p: planted 4-colourable, n = 30, deg 8 | seeds 701-704 | seeds 511-525 | 120 (pad 128) | 10 |
Generator: scripts/testing/h6_instances.py (planted colouring, optimum 0 by construction, so the target is exact without
enumeration). TUNE and TEST are disjoint; no TEST run is used for any selection. Tune seeds: 4 per instance. Budget 150
sweeps (L3 also 300, 600). Max-Cut target 0.99 x best-known; colouring target energy 0 (a proper colouring).

## 4. Arms and configurations (no re-tuning except H6-R)
Configs of existing arms are the Stage 2 tuning selections (docs/hw/results/stage2_eval/tuned.json, sha256 prefix
9b96c4c567b29820; tuning data only); col3p/col4p use the Stage 2 colouring entry. I7v2 arms use the config of their I10
base arm. Arms (TEST): ours_none, ours_kc2_i11, ours_none_i7v2, ours_kc2_i11_i7v2, ours_{kc2,mesa,da}_swept, B1_best
(b1.none, the Stage 2 rung-3 B1 selection), B1_mesa_epoch (MESA, K = n, epoch 10 sweeps = P4.02a k1_e10, Stage 2 b1.mesa
percentile pair), B3; Max-Cut also ours_kc2_i11 at 300 and 600 sweeps.
**B1 comparator** per family = whichever of B1_best and B1_mesa_epoch has the lower observed ETS99 on the TEST data
(best-of-two favours B1; conservative for ours).
**H6-R sweep** (TUNE split): K in {n/8, n/4, n/2, n, 2n, 4n}; Kc2 also L in {10, 40} (12 configs); MESA-epoch K only (6);
DA offset: the equivalent knob, rate divisor in {0.5, 1, 2, 4, 8, 16} (6); percentile pair = Stage 2 tuned pair of the
arm. Selection = the registered H2 rule: lowest mean normalised end gap, ties by lower energy. Per-config mean restarts and
the never-triggered fraction are written to h6_sweep.json; per-arm restarts on TEST are in the report.

## 5. Statistics and decision rules (same as H2, frozen)
Paired two-level bootstrap (instances, seeds within), 10 000 resamples, 95 % percentile CIs; ETS99/TTS99 with
R99 = max(1, ln 0.01 / ln(1-p)). **Win (energy)**: ETS99 ratio <= 0.95, Holm-adjusted p < 0.05, CI upper < 1, at
equal-or-better success (success diff >= -1 pp, point and CI lower bound). **Tie**: success CI inside +-1 pp and ETS99
ratio CI inside [0.95, 1.05]. **Loss**: ratio >= 1 with CI lower > 1. Else inconclusive (never a win). Area +-5 %
deterministic; quality = success-diff CI vs +-1 pp. A ratio with a comparator at 0 % success is "not evaluable", never a win.
**Multiplicity**: Holm over every registered contrast of a family (14 on Max-Cut, 12 per colouring family; the list is
evaluate_h6.contrasts_for). Families are reported separately; L1 needs a win on BOTH colouring families to be confirmed;
L2 is a single-family (Max-Cut) claim and is worded as such. H6-H5 is report-only under the frozen H5 rules (10 %-loss
point, nominal-vs-dev_x0 escalation, false stalls); arms ours.none.off, ours.kc2.off.i11, ours.none.i7v2 on the first 3
Max-Cut TEST instances x 10 seeds x 18 evaluable non-duplicate points; B2 QKP 6 points x 10 instances x 10 fresh seeds.
MaxSAT is not in H6 (Stage 2 success <= 9 %, uninformative); no MaxSAT claim follows.

## 6. Power (stated, not a guarantee)
Max-Cut: 100 runs per arm. L2's Stage 2 ratio arose from identical trajectories priced by two cost tables, so its CI is
narrow and a 5 % margin is easily resolved if it replicates. L3: a 13 pp success gap with 100 paired runs has a 95 % CI
half-width of roughly 8-12 pp, so "gap closed to within 1 pp" can only be shown as a tie if the gap essentially vanishes;
otherwise L3 will read inconclusive. Colouring: 150 runs per family; Stage 2's 20-27x ETS ratio at 100 % success would be
resolved; if the larger planted families do not reach the target often, ratios become wide or not evaluable (reported).
H6-R: 8-16 tuning runs per config is a coarse selection; the TEST contrast is the confirmatory part.

## 7. Compute
Per-run cloud seconds measured in Stage 2 (Max-Cut ours 18.2, I11 15.5, B1 78.4, B3 6.9, perturbed ours 26.3) and, for
col3p/col4p, local timing x 1.5 margin x 0.709 cloud/local. Jobs 26.0 CPU-h (tune 1.3, test 11.8, H5 12.9), x 1.15 packing
+ 12 vCPU-h setup/gate = **41.9 vCPU-h, about Rs 84 at Rs 2.01 / vCPU-h, ~1.3 h wall on 32 vCPU** (cap 110 CPU-h). Nothing
was trimmed for the restart sweep. Gate: STAGE0_GREEN for the pinned commit (tests/hw incl. the RTL spot check with
Verilator 5.050, smoke_all, run_cell --smoke-h6).

## 8. What would change this file
Any change after this commit requires a new committed revision before any Stage 3 run is read.
