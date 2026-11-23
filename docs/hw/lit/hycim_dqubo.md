# HyCiM D-QUBO gap: diagnosis notes (P0.09, frozen before P4.05)

Written 15 Nov 2026 (IST), read-only; no runs. Gap: our D-QUBO 1.95 % per run (v3, alpha = beta = 2, 1e5 proposals)
vs the paper's 10.75 % (diagnostic band 5.75-15.75). Sources: arXiv 2410.14111v1 (read 15 Nov via alphaXiv; page
numbers are PDF pages), `sw_ref_wt/qkp_pricer/experiments/qkp_pricer/{REPRO_RESULT_v3.md,hycim_repro.py,
dqubo_min_check.py}`, `sw_ref_wt/hycim_debug/explore/{FINDINGS.md,LOG.md}`, `09_next_phase/items_work/09/REPRO_DESIGN.md`.

## What the paper fixes, and what it does not
- Fixed: E = x^T Q x + alpha (1 - sum_k y_k)^2 + beta (sum w x - sum_k k y_k)^2, one-hot slack k = 1..C (Fig. 1b p.1,
  Sec. 2.1 p.2; formulation cited to Quintero 2021 [10] and Bontekoe 2023 [12]); alpha = beta = 2 (Sec. 4.2 p.5);
  dimension n + C = 200..2636 (Fig. 9b) and Q_max 4e4..2.6e7 (Fig. 9a), both consistent with one-hot slack and
  unnormalised profits (HyCiM Q_max = 100 = raw profit range, so profits are NOT rescaled); 1000 MC initial states x
  100 SA runs x 1000 iterations; success threshold 0.95 x optimum (Sec. 4.3 p.6). Fig. 10 plots 1000 points, one per
  initial state; D-QUBO "mostly gets trapped with infeasible input configuration".
- Not fixed: move set, what one "iteration" is, schedule/T0, initial-state distribution, whether success is per run or
  per initial state, whether D-QUBO value is best-seen or final state, and how an infeasible final state is scored.
- Our check: the formulation matches term by term, and its minimum is infeasible at alpha = beta <= 100 on 40/40
  instances (multi-hot y absorbs the overweight; `dqubo_min_check.py`). So the paper's 10.75 % cannot come from SA
  finding the ground state; it is a property of where a short, cold-ish run stops. The gap is most likely in the
  run/scoring conventions, not the energy.

Excluded as primary (evidence already against them): profit normalisation (Q_max = 100 for HyCiM, Fig. 9a);
binary/log slack (would give n + ceil(log2 C) ~ 107-112, not 200..2636); larger alpha/beta (paper states 2; and our
ab = 5..20 lowered the rate to 1.52 %).

## Ranked hypotheses (<= 5), predicted direction, one discriminating test each

| # | Hypothesis | Predicted direction | Minimal test (P4.05, 5 registered instances then 40) |
|---|---|---|---|
| H1 | Success is per initial state (best of its 100 runs >= 0.95 opt), matching Fig. 10's 1000 points | Raises: v3 already reports 7.43 % per-init at alpha = beta = 2, inside the band | No new SA: recompute per-init rate from the frozen v3 run matrix at the paper's 1000-proposal-per-run length is not available, so one run: v3 settings, L = 1000 proposals, 100 init x 100 runs, report per-init; pass if 5.75-15.75 and the filter arm under the same reading stays 93.54-100 |
| H2 | One "iteration" = one sweep over all n + C bits (or a multi-bit hardware update), not one single flip | Raises per-run rate (x touched ~n times per iteration instead of n/(n+C)) | One run: L = 1000 sweeps (1000 x (n + C) flips), v3 T0 rule, per-run success; compare with 1.95 %; the filter must be scored with the same iteration meaning |
| H3 | Score is the value of the x part of the FINAL state (or of the best-energy state), feasible-only, rather than best feasible ever seen | Lowers vs our best-seen (if success remains > 10.75 under H1/H2, this pulls it back into band) | Same run as H1/H2 with a second scorer column: final-state feasible value and min-energy-state value; no extra SA |
| H4 | MC initial states are drawn as feasible x with a consistent one-hot y (or empty), not Bernoulli(1/2) over all n + C bits | Lowers per explore LOG (consistent/empty starts 0-0.25 %); would only matter if the paper's start is cleaner than ours | One run: v3 settings, init = consistent (feasible x, y = e_{w.x}); expected down; a rise rejects our reading of LOG rows 47-49 |
| H5 | Temperature: paper's T0 is on the profit scale applied to the full D-QUBO energy (our S4 T0 = 1e-4 x S1 found by exploration) | Either; the explore grid (1e-3..1e-5) moved the rate 0-2.75 %, so at most a few pp | One run per registered T0 multiplier {1e-3, 1e-5} at the H1/H2-winning reading; registered list only, no tuning on outcome |

Order of testing in P4.05: H1, then H2 (each alone and jointly with H1), H3 as an extra scorer column on every run,
then H4, H5. Stop rule and labelling as in IMPL_PLAN P4.05: if no registered interpretation lands both arms in band,
record DONE-NEG "D-QUBO not reproduced under k registered interpretations". Any interpretation that reproduces only
via H1 is labelled "reproduced only under the best-of-100 reading" (REPRO_DESIGN §3 ii).
