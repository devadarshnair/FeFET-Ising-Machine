# P4_v2 amendment 1 (written before any run it governs; P4_v2_reproduction.md is NOT edited)

Committed alone, 17 Nov 2026 (IST). Known at writing: P4_v2 R1 FAIL, R2 PASS, R3 FAIL, R4 PASS (docs/hw/results/baselines_v2/
p4v2_result.json); R5 partly run (32 of 48 tuning files, not inspected); R6 not run.

## A. Faithful B1 ("B1_yin") as a priced harness machine
`scripts/baselines/b1_native.py`: Yin's move set (one proposal per iteration, m in {1,2,3} bits, single trial, no select tree),
energy from one tiled-array read per iteration, MESA v2 rules (epoch from best, per-epoch cooling + hold, trap counter after
cooling, Count_max). Arms `b1y.sa` (knob = schedule fraction {1, 0.5}) and `b1y.mesa` (knob = Count_max {n, 2n}), 8 configs
each under P4_v2 section 5. Priced by the unchanged pricing.price (kind b1, native 3-bit cells, full-scale ADC), clock =
OwnClockCost (lane path, no tree). The earlier harness B1 is kept unchanged and is named "B1_ours_mesa" from now on.

## B. R1b: re-attempt of Yin SI Fig. S7 with the faithful B1 (kernel = b1_native._run, same algorithm as R1)
R1 failed because neither arm reached the exact best-known cut in 1200 sweeps. Two unpublished readings are changed, chosen
before running and not tuned on R1 numbers beyond that fact:
1. "Solved" = best cut >= 0.99 x best-known (the P4.02 T2 definition), instead of the exact best-known.
2. Epoch length E in {10, 100} sweeps (E is not published; 10 = P4.02a value, 100 = one tenth of the budget, so about ten
   epochs, the order of Yin's Fig. S7 epoch count is unknown). Count_max = 2n.
Everything else as R1 (G1 scored, G2-G5 reported, 1200 sweeps, 40 seeds, T rule, TTS definition, three pass conditions:
S_MESA >= 0.90, S_MESA >= S_SA, TTS_SA / TTS_MESA in [1, 4]). New seed stream (tag 6 in repro_v2). PASS iff either E value
meets all three conditions on G1; which one is named. Multiplicity: two readings, so a PASS is labelled "under reading E = ...".
`RESULT P4v2 R1b`.

## C. R3 extended to Aramon's full size range (cloud job C-B3-scale)
Sizes 512 and 1024 added with the identical rule (20 instances, L in {25..800} n, 50 runs, 10 reference runs at 4000 n,
Table I temperatures, Jeffreys TTS, L* by lowest mean). beta is refitted over 64, 128, 256, 512, 1024 (Aramon's fit range
64-1024). PASS band unchanged. `RESULT P4v2 R3full`. For time limits the 1024 jobs split each instance into its grid runs and
its reference runs (same seeds as the unsplit job would use).

## D. R5 / R6 extended
R5 adds b1y.sa and b1y.mesa (same rule). R6 adds b1y.sa and b1y.mesa to the 240-spin TEST (report-only; the R6 PASS rule
concerns B3 v2 only and is unchanged) and runs all R6 arms on p3n480, p4n480 (Stage 4 budgets) and DIMACS (per-graph Stage 4
budgets), report-only (cloud job C-R6-480).
