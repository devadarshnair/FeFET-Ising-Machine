# H2 prereg: approximate-model screen with ablation ladder (hardware phase)

**FROZEN by the commit that adds this line (16 Nov IST), untagged.** Frozen before any Stage 2 scored value was read; open MINORs of the pre-Stage 2 internal review resolved below/in the evaluators.

(superseded status line) **DRAFT — untagged, author review required.** Nothing here is registered until the author tags it (IMPL_PLAN A8).
No scored experiment has been run for this file. Placeholders in [AUTHOR] brackets are author-only decisions
(margins filled 16 Nov IST by ruling; tagging still pending). Compute: docs/hw/results/P6.02_budget.md. Sources: design plan §3-§4, design review §2-§3,
rulings R1-R7 and A1-A5, decisions D1-D9.

## 1. Question and hypotheses (bounded; a tie or "baseline wins" is a valid, reported outcome)
- H2-a (restart rule): under one cost model and equal tuning, Kc2 (restart from current, K = 2n) is equivalent to,
  better or worse than MESA (restart from best, Count_max tuned), the DA dynamic offset, and no restart (rungs 2a-2d).
  If rung 2d is not better than 2c by the margin, the restart rule is reported as a tie and any headline must come from rungs 4-5.
- H2-b (counter-driven power/precision): I10 (stall-gated array/ADC power-down) and I7 (stall-adaptive ADC) lower
  energy-to-solution at equal quality, each alone before any pair.
- H2-c (full design): the full machine versus B1-tuned (MESA), B2 (QKP only) and B3 (DA) on energy, area and
  quality, per metric. "Beats all three" is not assumed; design review §3 expects ties on quality and wins, if any, in energy/area.
- Not claimed: silicon numbers; novelty of a stall restart (MESA/DA already contain one); any visited-state memory benefit.

## 2. Arms (every arm on the same mapped QUBO, SHA-256 equal, scripts/problems/load.py)
Machine models: scripts/golden (ours), scripts/baselines (B1 yin_mesa, B2 hycim_b2, B3 fujitsu_da). One canonical
cost table for all (cost_model.canonical_table, hash-equal test). Level-0 verify ON for every CiM machine (A2, R7
final); as-measured (unverified) level 0 appears only as the H5 variation arm. Tiling per R6 for every CiM machine.

Cost-rule caveats (one rule for all machines; P4.08): ADC bias is charged per ungated step to ours, B1 and B2 (B3 has no ADC); extra tiles add conversions on every machine; B3 leakage covers logic only, the SRAM coupler array is charged area but no leakage (conservative against ours).

| Rung | Arm | Machine | Simulated trajectories |
|---|---|---|---|
| 1 | B1 as published (MESA, K = 2n, untuned default; native 3-bit cells with write-verify, A1) | B1 | test only |
| 2a | B1-tuned, restart = none | B1 | tuned |
| 2b | B1-tuned, restart = DA offset | B1 | tuned |
| 2c | B1-tuned, restart = MESA from best | B1 | tuned |
| 2d | B1-tuned, restart = Kc2 from current (K = 2n, L-kick per R1) | B1 | tuned |
| 2' | same four restart arms on our machine (binary differential crossbar, full-res ADC) | ours | tuned |
| 3 | best of 2a-2d per family (selected on the tuning instances only) | | |
| 4a | + I10 stall-gated power (priced from skipped-read counters; trace identical at sigma = 0, pre-check below) | ours | counters only |
| 4b | + I7 stall-adaptive ADC (alone, then I7 + I10 only if each passes alone) | ours | tuned |
| 4c | + I11 greedy + Kc2 kick (IMPLEMENTED in golden, scripts/golden/tweaks.py; no lane RNG / LUT, deoff 0, Kc2 stall kick only; RTL pending, docs/hw/results/RTL_TODO_I11_I3_I5.md) | ours | tuned |
| 4d | + I3 ramped penalty gain: fixed / ramped / HyCiM filter on knapsack (IMPLEMENTED in golden, as 4c; ramp lam_lo to lam over ramp_steps, knapsack rules hw/penalty); runs "ours" on the knapsack family only (not QKP by default, see the section 7 open item) | B2 ladder | tuned |
| 4e | + I5 Vth-spread acceptance noise (IMPLEMENTED in golden as hold/group correlation knobs; cost rows derived (liberty x RTL synth, 0 placeholder rows); noise statistics still author-set; run only if I11 fails and RNG energy leads) | ours | tuned |
| 5 | full design = best surviving tweaks (anything not paying for itself is removed, not rescued) | ours | |
| 6 | TCAM-lite visited-state arm (OPTIONAL, D2; golden tcam_lite.py; off unless the author enables) | ours | |
| side | B1 bit-sliced MESA (secondary B1 reading, A1) | B1 | tuned |
| B2 | HyCiM filter-SA, 16 x 100, 5-level cells with write-verify, QKP only (D1) | B2 | tuned |
| B3 | Fujitsu DA, offset knob {off, on} tuned (D4) | B3 | tuned |
| pre-check | I10 trace identity: off vs I10 on 3 instances x 3 seeds, final state and trace equal (P2.04) | | |

Pre-set fairness (design plan §4, all binding): (F1) same instances, seeds, budget definition, stopping rule and mapped
QUBO for every machine; (F2) baseline tuned as hard as ours, equal grid budget, tuning on a disjoint instance set,
tuning set reported; (F3) same device and MOSFET model for every FeFET and transistor, one cost table; (F4)
memoryless-restart parity: any memory/restart baseline gets Kc2 in the control arm; (F5) negatives and ties in the headline
table, no family cherry-picking, equivalence margins fixed here; (F6) wording per sw_ref/docs/CLAIMS.md and claim-audit
policies; (F7) a machine that cannot hold the mapped problem is charged tiling (R6) and never filtered out.

## 3. Instances, families, seeds
Families (headline: Max-Cut and MaxSAT per D8; colouring secondary table; QKP for B2 only):
| Family | Test set | Tuning set (disjoint) | Spins |
|---|---|---|---|
| Max-Cut | G1-G5, G11-G15 (10, 800 nodes) | G6, G7, G16, G18 (4) | 800 (padded 1024) |
| MaxSAT | random 3-SAT n = 60, m = 256, seeds 1001-1010 (10) | seeds 2001-2004 (4) | 316 (padded 512) |
| Colouring | G(12, 0.3), k = 3, seeds 301-310 (10) | seeds 401-404 (4) | 36 |
| QKP (B2 only) | Billionnet-Soutif 30 of the 40 instances | 10 disjoint | 100 |
Instance lists are the defaults of this draft (author may still change them before tagging); all are fixed before any scored run. Explicit lists: Max-Cut test G1, G2, G3, G4, G5, G11, G12, G13, G14, G15, tuning G6, G7, G16, G18; MaxSAT (uf-series style random 3-SAT, n = 60, m = 256, 316 spins) test seeds 1001-1010, tuning 2001-2004; colouring G(12, 0.3), k = 3, test seeds 301-310, tuning 401-404; QKP Billionnet-Soutif, B2 only. Seeds: run r of instance i
uses mix_seed(BASE, family, i, r), BASE fixed at tagging, common to every arm (common random numbers). Test: 10
seeds per instance (QKP 20); tuning: 2 seeds per instance. Budget: 150 sweeps (= 150 x spins single-flip steps) per run;
QKP 1e4 and 1e5 proposals. The time/energy budget definition is the same for every machine (steps x per-step cost from the table).

## 4. Tuning (parity grid)
Every arm that has knobs gets the same grid size: 8 configs = 4 (T_end/T_start rule pairs, percentile rule of P4.02)
x 2 (restart knob: K in {n, 2n} for stall arms, offset rate in {Tl/4, Tl/2} for DA, a second schedule length for "none").
Kc2 keeps K = 2n in its control arm as registered by the reference software study; its grid uses the same 8 configs so the tuning effort is equal.
Selection criterion: mean normalised gap at end of budget on the tuning instances; ties broken by lower energy. Tuned
configs are frozen before the test runs start; test results are never used for selection.

## 5. Metrics (frozen; all reported, none dropped)
1. TTS99 and ETS99: TTS99 = min over t of t x R99(p(t)), R99 = max(1, ln(0.01)/ln(1-p)) (1 if p = 1; floor at one run, frozen MINOR 2); ETS99 = same with t
   replaced by cumulative energy; success = best-so-far reaches the target. Target: G-set best-known x 0.99 (Max-Cut);
   MaxSAT/colouring: best objective found by any run in the reference set R (20 seeds x 10x budget, run before the
   scored ladder, self-referenced and labelled), colouring exact optimum by enumeration; success is "reaches R's best".
2. Solution quality at fixed time and fixed energy budgets (25 %, 50 %, 100 % of the budget): mean normalised gap.
3. Area by block (mm^2), writes per solve (0 after programming for every CiM arm; every program-cost table states "ours: level-7 cells written once, unverified; B1/B2 verify levels 1-7", so e_program_fJ favours ours; level-0 verify programming reported
   once: attempts, fJ, us; reported with and without amortisation over S in {1, 100} solves), iterations to target.
4. Block energy breakdown (array, ADC, digital, RNG, SRAM, filter, restart, leakage) per arm.
All headline contrasts are ratios of the arm over B1-tuned (and over B3, B2): paired by instance and seed.

## 6. Statistics, margins and decision rules
- Paired bootstrap over instances (10 000 resamples; seeds nested inside instances), 95 % percentile CI; Holm
  correction across the registered contrasts of a family.
- Equivalence margin (ruling 16 Nov IST, "go with your recommendations"; still DRAFT until tagged): two arms are
  equivalent when success rate differs by at most +-1 percentage point AND energy-to-solution differs by at most +-5 %
  (both paired CIs inside the band).
- Win margin (same ruling): an arm wins when its energy-to-solution (ETS99) is >= 5 % lower than the comparator's with the
  95 % CI excluding "no change", at equal-or-better success rate (success not lower by more than the 1 pp equivalence band
  point estimate-wise and CI-wise), on >= 2 problem classes (Max-Cut and MaxSAT). A "win" is registered per metric
  (energy, area, quality); the 5 % rule is the energy win.
- Gate H2 pass: full machine or at least one rung beats B1-tuned by the win margin on ETS99 on >= 2 families.
  Kill: CI includes "no change" or the energy saving is < 5 % after the ladder, or the advantage appears in one family only. Then the
  report states "a restart rule is not a hardware win over a tuned FeFET CiM annealer" and the phase stops before H4.
- Rung 2d versus 2c: not better by the win margin = tie, reported as such.
- Area and quality verdicts (frozen MINOR 4): area win = total area <= 0.95 x comparator, loss >= 1.05 x,
  else tie (deterministic, no CI). Quality = end-of-budget success difference with its paired CI against the +-1 pp band
  (win: CI lower >= +1 pp; loss: CI upper <= -1 pp; tie: CI inside the band). Any "inconclusive" verdict (energy, area or
  quality) is never counted as a win and is reported as "not evaluable (inconclusive)" in prose.
- Per-metric reporting: energy, area, quality, each with its own verdict (win / tie / loss / not evaluable).
- Integer-vs-float: the rankings use the integer machine; the registered TOST gate G1 (A4, prereg/drafts/G1_tost.md) must have passed.

## 7. Outputs and what would change this file
Outputs: per-run JSON, per-arm table, ladder table, headline table. Changing any number above after tagging requires a
new tagged revision. Open items: win margin, equivalence margin, instance lists, whether rung 6 is enabled,
whether ours is also run on QKP (default no; B2 is QKP-only).
