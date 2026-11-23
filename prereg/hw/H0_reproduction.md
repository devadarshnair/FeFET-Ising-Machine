# H0 prereg (summary): baseline reproduction status and frozen labels

**FROZEN by the commit that adds this line (16 Nov IST), untagged.** Frozen before any Stage 2 scored value was read; open MINORs of the pre-Stage 2 internal review resolved below/in the evaluators.

(superseded status line) **DRAFT — untagged, author review required.** This file does not restate or replace the calibration tolerance files
(prereg/calib/P4.02, P4.04, P4.05, P4.06, committed before their runs). It fixes what labels the testing phase will
print for each baseline, as a function of the registered outcomes. No calibration result has been read for this
draft: P4.02, P4.04, P4.05 and P2.08 are queued (00_admin/cloud_cpu/QUEUE.md, DONE-READY, not run); P4.06 and P4.01/P4.03 smoke results are committed.

## 1. Status table (filled from result files only after they exist)
| Baseline | Calibration | Tolerance file | Status at drafting | Label rule |
|---|---|---|---|---|
| B1 Yin 2024 MESA (primary) | P4.02 R1 algorithm level (T1 +27 %, T2 ~2x) | prereg/calib/P4.02.md | queued, not run | both PASS: "MESA reproduced at the algorithm level (R1), literature-parameterised cost"; any FAIL after repair: "literature-parameterised generic FeFET CiM annealer, R1 not reproduced" |
| B1 energy/time | R2 | P4.02.md | waived (no published energy/time in the main text) | always "literature-parameterised" |
| B2 HyCiM | P4.05 D-QUBO gap; P4.06 filter on shared models | P4.05.md, P4.06.md | P4.06 committed (PASS per its file; filter reproduction post-hoc v3); P4.05 queued | filter: "filter reproduced post-hoc v3"; D-QUBO PASS: "D-QUBO reproduced under reading X" (per-init reading labelled "best-of-100"); FAIL: "D-QUBO not reproduced under k registered interpretations" (DONE-NEG) |
| B3 Fujitsu DA | P4.04 vs Aramon 2019 (T1/T2 beta, T3 offset, T4 boost) | P4.04.md | queued, not run | PASS: "DA reproduced (scaling and boost)"; FAIL after repair: "literature-parameterised DA-style digital annealer, Aramon TTS scaling not reproduced" |
| Integer vs float | P2.08 (G1) | prereg/drafts/G1_tost.md (A4 = TOST) | queued | gate result printed unchanged |
Labels are copied from the registered tolerance files; nothing in this table may be re-worded after results exist.

## 2. Registered interpretation choices (at most 3 per baseline; a repair beyond them is author-only, A10)
- B1: (1) Count_max = 2n (repair: n or 4n); (2) stall = no strict improvement of best-so-far, reload best and reset T;
  (3) RNG = off-array digital generator. Yin's "flip a few bits" perturbation is not used (single-flip shared machine);
  flagged as a deviation, perturb_bits = 3 recorded.
- B2: (1) 5-level cells with per-cell write-verify; (2) the winning P4.05 reading B (selected by the script, no manual
  choice); (3) filter SA moves from post-hoc v3. Level-0 verify ON for the testing phase (A2).
- B3: (1) offset rate (default 0, paper's final setting; ON = Tl/4); (2) linear-in-1/T schedule with the Aramon percentile rule; (3) start x = 0.
Stated deviations carried into every table: "stand-in BSIM4 and FreePDK45 channel cards are not a silicon PDK; absolute
pJ/ns carry about x2 uncertainty; ratios only"; "retention unfitted; set B refit BLOCKED; set C iso-MW vs C6 conflict
and +2 V disturb known limits (A3)"; "digital area is a gate-count estimate, select_tree N = 256 an estimate".

## 3. Labels printed in the testing-phase tables (frozen vocabulary)
"reproduced (R1)", "literature-parameterised", "not reproduced", "post-hoc v3", "best-of-100 reading", "stand-in model",
"as-measured level 0", "level-0 verified". No other adjectives; "outperforms" style words are not allowed in the H0 table.

## 4. Open items
Whether a FAIL on any baseline drops it from the headline contrast (design plan §2.3 fail rule says the next candidate is taken; B1 is
the primary, so a B1 R1 FAIL means the generic-annealer label); acceptance of the tolerance interpretation "about 2x = 1.5-2.5".
