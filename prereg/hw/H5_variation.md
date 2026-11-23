# H5 prereg: variation, drift, temperature and supply (both machines)

**FROZEN by the commit that adds this line (16 Nov IST), untagged.** Frozen before any Stage 2 scored value was read; open MINORs of the pre-Stage 2 internal review resolved below/in the evaluators.

(superseded status line) **DRAFT — untagged, author review required.** Report-only gate unless noted. Compute: docs/hw/results/P6.02_budget.md.
Sources: design plan §7 (+ T7/I8/I9 notes), design review §4 (false stall), P4_level0_variation.md, P1.06, P1.07, P1.10.

## 1. Hypotheses
- H5-a: the quality and TTS of ours and of B1-tuned degrade with perturbation level; we report the point at which each
  machine loses 10 % of its nominal success probability (identical injected perturbations on both sides, Monte Carlo
  with registered seeds).
- H5-b (false stall): with the noisy measured energy in the stall counter, Kc2 (stall against epoch best, restart from
  current) and MESA (stall against best-so-far, restart from best) produce false stalls/resets at a rate that may change
  the H2 restart verdict. Tested explicitly (see §4).
- Gate: report-only. Robustness failure of ours is a finding, not a kill, unless ours fails at nominal sigma.
- Level-0 (A2): the default arm is verify ON; the as-measured (unverified, sigma 4.86 nA) setting is a variation arm.

## 2. Perturbations (every design plan §7 item), identical on both machines
| # | Perturbation | Levels (points) | Mapping into the golden model |
|---|---|---|---|
| 1 | FeFET Vth / conductance device-to-device sigma (Ni 2019 base) | x {0 (ideal), 2, 4}; x1 is the H2 nominal | per-cell static weight error from cim_cell_v1 (sigma/mu per level) |
| 2 | Level-0 as-measured (unverified) | 1 point | A2 variation arm, P4_level0_variation.md |
| 3 | Cycle-to-cycle write noise | x {1, 2, 4} | residual after write-verify (+-5 % band scaled) |
| 4 | Read noise | x {1, 2, 4} | dynamic cim_field noise, seeded |
| 5 | Retention drift (log-time, parametric) | 3 levels; set C retention is unfitted (k = 0 in the model, P1.06), so this is a sweep, not a prediction | MW loss per decade, levels 0, 0.02, 0.05 V per decade (author default 16 Nov; bracketing 0 to the 1.035->0.893 V spread) from P1.06 MW(2 s) = 1.035/1.016/0.893 V |
| 6 | Endurance fatigue | only if a write count is non-zero; Kc2/MESA/DA do zero array writes beyond programming, so reported as "not applicable, writes = 0" per arm | counter |
| 7 | Temperature | 0, 45, 85 C (25 C nominal) | needs Vth/mobility tempcos (model extension); until it exists, parametric effective-gain shift, labelled |
| 8 | Supply | x {0.9, 1.1} | read-current gain and energy scale |
| 9 | MOSFET mismatch (Pelgrom constants of the card) | x {1, 2} | ADC offset (7.4 mV, P1.11) and column offsets |
| 10 | Corners | SS, FF (TT nominal), only if a card with corners exists; otherwise "not evaluable" | cost and delay scaling |
| 11 | Combined worst case (all at their highest listed level) | 1 point | all |
24 points = the rows above plus the nominal (22 if corners (point 10) and the conditional temperature point 7 are absent). OPEN: no false-stall / false-reset tracking counter is implemented yet (section 4); it must exist before H5 is launchable. Sign-magnitude/differential weight coding (T7) is tried only as a
cheap extra arm: included, reported separately, not in the 24-point decision (default 16 Nov).

## 3. Arms, instances, seeds
Simulated arms: ours Kc2 / MESA / none (all with I7, frozen H2-tuned configs) and B1-tuned (MESA, native 3-bit with
write-verify, bit-sliced as an optional extra). B3 (digital) is perturbed only through supply, temperature and corner
cost scaling; B2 only on the QKP set through points 1, 4. Instances: Max-Cut first 3 H2 test instances; MaxSAT first
5; 5 seeds each; 150 sweeps; same seeds as H2. Both machines see the same perturbation draw per (instance, seed).

## 4. False-stall test (explicit)
In every noisy run the golden machine also tracks the noise-free energy. A **false stall** = the stall counter
reached its limit on the noisy readout although the true energy improved during the window; a **false reset** = the
counter was reset by a noisy "improvement" that the true energy did not show. Report per arm and noise level: restarts
per 1000 steps, false-stall rate, false-reset rate, and the TTS99 ratio with versus without noise. MESA (best-so-far
based) and Kc2 (epoch-best based) are compared on these rates; I10 freezing noise (P2.04) is reported as a separate arm.
This is the only place the rung 2c versus 2d verdict can be revised; the rule: if the Kc2-vs-MESA ratio CI at a
perturbation level moves outside the H2 equivalence band, the H2 verdict is reported as "level-dependent".

## 5. Metrics and rules (frozen)
Per point: success probability at the H2 target, TTS99, ETS99, normalised gap at end of budget; 10 %-loss point =
the smallest level at which success probability is below 0.9 x its nominal value, linear interpolation in the level,
bootstrap CI over instances (10 000). Machine robustness compared by the ratio of 10 %-loss points (report-only).
Nominal-sigma failure rule (frozen MINOR 6): if ours' H5 nominal success is more than 1 pp below its own H5 ideal point dev_x0
(same arm, instances, seeds) the finding is escalated to the author; the old H2 i7i10 comparison is reported only.
Supply points (frozen MINOR 7): energy rows of every machine (ours, B1, B3) are priced x supply^2. Wording follows CLAIMS.md; stand-in model labels stay on every table.

## 6. Open items
Retention levels, temperature model extension (blocking for point 7 as non-parametric), whether corners exist,
whether the combined point is credible, T7 as an extra arm.
