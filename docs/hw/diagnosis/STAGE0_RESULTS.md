# Stage 0 results (the experiment plan II.2), executed locally

Code `7d8117e` + the commit of this file; `prereg/hw/H8_full.md` and the H8 results/raw records were not modified (the raw records are read-only inputs).
All runs through `~/research/shared/local job queue` with declared RSS, one CPU-heavy job at a time, no cloud. Evidence: `s0_evidence/` (re-pricing reports, sweep JSONL, field MC, re-flip, driver logs).
Scripts: `scripts/testing/{s0_sweep,s0_sweep_summary,s0_h4_field,s0_reflip,s0_r13_960,s0_reprice_compare,s1_joblist}.py`.
Fresh tuning-tag instances: `Spec.tag = 10`, planted p3 keys 2101-2112, p4 keys 2201-2212 (disjoint from H8 tag 9 and from the confirmatory keys 2301/2401 reserved in the plan). 
Not data for any claim: these are Stage 0 diagnostics on tuning instances, with 60 runs per point (Wilson 95 % CIs); stand-in device models, ratios only.

## 0.1 Re-pricing H8 under B-1..B-3 (zero new simulation)
Frozen evaluator `evaluate_h8.py --tier core --cost-flags {all,b1,b2,b3}` on the 486 stored raw files (12 min per run, 2.7 GB RSS). Full table: `s0_evidence/reprice/verdict_table.md`, reports `report_flags_*.json/.md`.
- **Verdict-class flips among the 20 primary (nominal, global Holm m = 20) contrasts: 0, for every flag combination.** Six wins, four losses, three inconclusive, seven not evaluable, exactly as in H8.
- **Pricing sensitivity flips:** unchanged: the same two loss -> inconclusive flips under the canonical table (Max-Cut vs B1, p3n240 vs B3) and no others.
- Size of the ratio changes (ETS ratio ours / comparator, frozen -> all flags): p3n240 vs B3 2.58 -> 2.48; p3n480 vs B3 5.41 -> 4.82; Max-Cut vs B3 18.8 -> 16.6; Max-Cut vs B1 2.85 -> 3.05 (B-2 alone 3.45, B-3 alone 2.68);
  DIMACS vs B3 0.0066 -> 0.0055; p4n480 vs B1 0.110 -> 0.116 (win kept, p_glob 0.0063 -> 0.008); p3n240 vs B1 0.546 -> 0.582 (inconclusive kept, p_glob 0.003 -> 0.012); p3n120 vs B3 0.606 -> 0.581 (inconclusive kept, p_glob 0.155 -> 0.103).
- B-1 alone moves ratios by under 1 %, as B predicted. B-2 and B-3 move ours-vs-B3 by 0.83-0.97 and Max-Cut vs B1 by x0.94 (B-3) to x1.21 (B-2).
- Decision consequence: pricing version is a non-issue for the H8 verdicts; the new stage can use the corrected pricing as primary (author's decision) without changing any H8 reading.
- Cost: 4 evaluator runs, about 48 CPU-min total.

## 0.2 C2C-share sweep (k = 1, nominal mitigation, 12 fresh instances x 5 seeds = 60 per point)
Success = best_E 0. Ideal device reference in the first row.
| share | ours p3n240 (wv+diff+cal) | ours p4n240 | B1_best p3n240 (wv+cal; 8 inst x 4 seeds = 32) |
|---|---|---|---|
| ideal | 0.63 [0.51, 0.74] | 0.75 [0.63, 0.84] | 0.50 [0.34, 0.66] (ideal, same 32) |
| 0 | 0.02 [0.00, 0.09] | 0.03 [0.01, 0.11] | 0.00 [0.00, 0.11] |
| 0.01 | 0.22 [0.13, 0.34] | | |
| 0.02 | 0.28 [0.19, 0.41] | | |
| 0.03 | 0.50 [0.38, 0.62] | | |
| 0.05 | 0.52 [0.39, 0.64] | | |
| 0.07 | 0.50 [0.38, 0.62] | | |
| 0.1 | 0.62 [0.49, 0.73] | 0.70 [0.57, 0.80] | 0.00 [0.00, 0.11] |
| 0.2 | 0.57 [0.44, 0.68] | 0.72 [0.59, 0.81] | 0.00 [0.00, 0.11] |
| 0.3 | 0.63 | 0.77 | |
| 0.4 | 0.63 | 0.75 | |
| 0.5 | 0.63 | 0.75 | 0.41 [0.26, 0.58] |
| 0.75 | 0.63 | 0.75 | |
| 1.0 | 0.63 | 0.75 | 0.50 [0.34, 0.66] |
- **The cliff is real and sits at a very low share for ours.** At k = 1, ours drops from ideal-equal success (0.63 / 0.75, bit-identical to ideal for share >= 0.3) to 0.02-0.03 at share 0 and recovers over 0 -> 0.1 (half of ideal at about 0.03; 0.1 is already within noise of ideal).
  So at the nominal variation (k = 1) the required C2C share is about 0.03-0.1, well under the registered "0.25" assumption. The earlier H8 reading "ours needs 0.5 at k = 2" is a statement at doubled variation, not a contradiction: the critical share rises with k.
  **Caveat:** this is k = 1 only. The H8 stress grid (k = 2, 3) is the more exposed region; a k x share grid is the natural follow-up (cheap, 2-3 CPU-h) and is added to the Stage 1 list as 1c.k.
- **B1 is much more exposed than ours at k = 1:** 0 of 32 at share 0.2, only 0.41 at 0.5, ideal-level at 1.0. The cliff for B1 lies between 0.2 and 0.5. Ours and B1 are therefore not equally exposed to H-1; ours tolerates a ~10x lower C2C share on this cell. B1's wv+cal stack is the registered one (a bit-sliced B1 arm is still missing: H-2, in 1c).
- Cost and timing: ours nominal 4.6 s/run (RSS 0.59 GB), B1 nominal 8.1 s/run (0.32 GB); ideal ours 2.2 s/run. Total sweep about 2.7 CPU-h (as planned).

## 0.3 H-4 leakage falsifier
Field-error distribution (read field minus exact field P x for random Bernoulli(1/3) states) of the nominal ours machine (wv+diff+cal), 10 programming draws x 20 states x 240 lanes, fresh p3n240 key 2101.
| share | level-0 model | mean error | sd | nonzero | negative / positive |
|---|---|---|---|---|---|
| 0 | real (MC mean 1.32 nA, p99 33 nA) | +0.055 | 0.76 | 21.4 % | 9.0 % / 12.5 % |
| 0 | leakage-free | 0 | 0 | 0 % | 0 / 0 |
| 0.5 | real | 0 | 0 | 0 % | 0 / 0 |
| 0.5 | leakage-free | 0 | 0 | 0 % | 0 / 0 |
Walk-level test (60 runs each, share 0, nominal): ours with leakage-free level 0 gives **0.63 on p3n240 and 0.75 on p4n240, identical to ideal** (real leakage: 0.02 / 0.03).
- **The level-0 leakage tail is the cause of the share-0 collapse** (falsifier "collapse unchanged without leakage" is rejected: it vanishes entirely).
- **The mechanism is not a one-sided bias under the registered diff mitigation.** The error is mostly zero-mean and quenched (per programming draw): 21 % of fields are off by +-1..3 cells, mean +0.055, with a slightly heavier positive tail (12.5 % vs 9.0 %). The H-4 falsifier "field error symmetric about 0" is therefore met. A symmetric 20 % noise on the fields is still enough to destroy the zero-gain plateau walk,
  because I11 needs exact signs. Consequence for the fixes: R9 (mean-cancelling reference column) targets a mean that is nearly zero here; R10 (dither) would add more noise to an already noisy field, and R11 would not help either. What helps at share 0 is reducing the **variance** of the level-0 leakage per column (e.g. wv on level 0 is already used; a smaller leakage tail, shorter columns/tiles, or per-column calibration at the operating state), not its mean. This reorders the Stage 1 robustness list: **R13 tiled columns first (shorter columns carry fewer leaky cells), R9/R11 only as variance reducers if 1c shows it, R10 deprioritised.**
  Caveat: measured for the diff stack on p3n240 only; the no-diff case (where the leakage is one-sided: strictly positive currents) was not tested, and B's original H-4 argument was about single-sign columns.
- N = 960 field MC: **deferred to the cloud instance** (see 0.5).

## 0.4 Re-flip diagnostic (A1 mechanism; R6 vs R5)
Ideal ours_kc2_i11, registered config (L = 10, K = 2n colouring / n Max-Cut), full budget. returned = fraction of the kicked spins whose value after the repair (at the next kick) equals their pre-kick value; drift = fraction of the non-kicked spins that differ.
| run | n | kicks | returned | drift of non-kicked | median Hamming between successive pre-kick states |
|---|---|---|---|---|---|
| p3n480 2101 r0 | 480 | 129 | 0.904 | 0.017 | 7 |
| p3n480 2102 r0 | 480 | 131 | 0.885 | 0.014 | 6 |
| p3n480 2103 r1 | 480 | 129 | 0.866 | 0.019 | 8 |
| p3n960 2101 r0 | 960 | 274 | 0.875 | 0.010 | 9 |
| p3n960 2102 r1 | 960 | 272 | 0.879 | 0.010 | 9 |
| Max-Cut G43 r0 | 1000 | 125 | 0.979 | 0.011 | 9 |
| Max-Cut G44 r0 | 1000 | 134 | 0.985 | 0.007 | 6 |
- **Falsifier (< 30 % returned) rejected.** Every kick set is 87-98 % undone by the repair, while only 1-2 % of the other spins move. The repair puts the kicked spins back; the machine does not leave the basin. Per kick, 100 % of kicks had >= 50 % of their spins returned.
- **R6 (tabu on kicked spins) ranks above R5 (conflict-targeted kick)**: it attacks exactly this mechanism, at one bit per lane. R5's premise (kicks miss the conflict region) was not measured here; it needs the colouring conflict map and stays untested.
- The effect is stronger on Max-Cut (98 %), consistent with A4 (greedy plateau walk).
- G43/G44 are tuning-grade Max-Cut instances (used in P4.02 calibration, not as test); generated G-set-like graphs do not exist yet (Stage 0.6 item below).

## 0.5 R13 tiled identity at N = 960: DEFERRED to the cloud instance
The job (`s0_r13_960.py`, `--rss 7`) sat in the local job queue FIFO from 20:28 to 20:48 IST: MemAvailable was about 8.0-8.1 GB but another project's job held a 0.6 GB reservation, so admission (7 + 1.0 GB + reservations) never passed. Per the instruction (run only if MemAvailable allows) I cancelled it and removed my own stale queue ticket
(`/tmp/ml-hardware-bench.lock.q/*.1100322`), and did not retry with a smaller declared RSS, because the H8 measure of 5.0 GB at 960 spins is the programming array of the non-tiled model and the tiled model's peak is unknown. The jobs (R13 identity, 2 records; field MC at 960, shares 0/0.5, tile 0/256) are in `STAGE1_JOBLIST.tsv` as stage 0d, 5 jobs, about 0.8 CPU-h.
R13 identity at N <= 480 was already established earlier (`eng_evidence/r13_tiled_identity_n480.json`, 9/9).

## 0.6 Not done in Stage 0
- Generated G-set-like Max-Cut instances and the proxy cut (rudy-style generator, instance-supply tests): needs code; Stage 1 job list uses the `gk` cell label for them and G43-47 until then.
- No kick/robustness fix (R4-R12) was run: they need the the code (listed in the job list `needs` column).

## 6. Timings and RSS from the smokes (local, single core, the local job queue)
| job | seconds | peak RSS |
|---|---|---|
| ours ideal p3n240 / p4n240 | 2.2 / 2.2 per run | 0.10 GB |
| ours ideal p3n480 | 12 (re-flip incl. start-up) | 0.20 GB |
| ours ideal p3n960 | 86 | 0.54 GB |
| ours ideal Max-Cut 1000 | 25 | 0.27 GB |
| ours nominal p3n240 / p4n240 (mitigated) | 4.6 per run | 0.59 GB |
| B1_best ideal p3n240 | 8.7 per run | 0.11 GB |
| B1_best nominal p3n240 (wv+cal) | 8.1 per run | 0.32 GB |
| field MC, 10 draws x 20 states, p3n240 | 6 | 0.58 GB |
| evaluator `--cost-flags` run | 740 | 2.7 GB |
`STAGE1_JOBLIST.tsv` (270 jobs, generated by `scripts/testing/s1_joblist.py`) uses these numbers: **41.5 CPU-h in total** (1a 29.2, 1b 2.4, 1c 6.1, 1d 1.8, 1e 1.2, 0d 0.8), longest job 38 min, every job under 1 h; about Rs 105 on the cloud instance at 1.15 tail + 0.4 h set-up.
n480 and n960 mitigated RSS and B1 at larger N are estimates (1.5 GB, 5 GB) until measured on the cloud instance; the 960-spin jobs are flagged `lane = cloud`.

## 7. What changes in the plan
1. Re-pricing: no flips; pricing is not a blocker. Corrected pricing as primary is safe.
2. H-1: ours' cliff is at C2C share about 0.03 at k = 1 (not 0.25-0.5); B1's at 0.2-0.5. The remaining exposure is at k = 2-3, not tested here. Add a k x share grid (1c.k).
3. H-4: leakage is the cause of the collapse, but through a zero-mean quenched error, so R9 and R10 as designed (mean-cancel, dither) are probably the wrong tools; test variance reducers (R13 tiling, per-column calibration at the operating state) first.
4. A1: confirmed with a number (87-98 % of the kick is undone): R6 tabu before R5, and R4 alone cannot be expected to fix it unless L is large enough to survive the repair.
5. The Stage 1 gate note from the review stands: an effect of about 0.25 is needed to pass the +0.15 gate on 8 x 3 paired runs; add instances if a smaller gain is of interest.

## 8. STAGE1_JOBLIST.tsv revision (review fix list, internal review section 7)
Regenerate with `python scripts/testing/s1_joblist.py > STAGE1_JOBLIST.tsv` (cost line on stderr). 252 jobs, 30.3 CPU-h, longest job 34 min, **Rs 112 including 0.4 h set-up and a 0.25 h gate job (budget Rs 125: within)**.
1. Added `1c.k`: k in {2, 3} x share {0, 0.03, 0.1, 0.25, 0.5} on p3n240 for ours (M0), B1 wv+cal and B1 bit-sliced, plus B1 bit-sliced at k = 1 (needs a `--k` option in `s0_sweep.py`).
2. Rebuilt `1c` at the measured cliff (k = 1, shares 0 / 0.01 / 0.03): one R10 arm with its matched Metropolis control, a no-diff stack walk test, and n480 variance tests (one-column legacy vs tiled-256 M0, tiled + R9, tiled + R11), plus four field-MC jobs (no-diff n240, tiled n480). M0 n240 at k = 1 reuses Stage 0.2. Full R10/R9 grids dropped.
3. Equalised 1a: every arm has 12 configurations in round 1 and top 4 in round 2; ours is labelled by (c, K) with L = max(10, ceil(c n)), aliases (same L) run once but still count. To fit the budget round 2 is p3n960 only; p4n960 uses a config transferred by the same rule for every arm (all arms were near 0 % there in H8).
4. `gk` jobs are labelled TUNING-ONLY on G43-47 (P4.02-used): no result on them is confirmatory.
5. `0.5.r13_960` is row 1, the first cloud job; every noisy p3n960 / p4n960 / gk job lists `GATE:0.5.r13_960` in `depends_on`.
Caveats kept: the zero-mean/quenched error finding is for the diff stack on one instance (the no-diff test is exactly what 1c adds); "B1 about 10x more exposed" is not a claim until the bit-sliced B1 arm has run.

## 9. Stage 1 Cloud bundle (built, NOT launched)
- Payload: `$PROJECT/00_admin/bundles/s1_payload` (29 MB; pin `d7d178a`, branch `hw/p4-baselines`; ship it and run `bash s1_payload/s1/go_s1.sh`). Built by `scripts/cloud/s1/build_payload_s1.sh DEST` from the committed tree; contents follow the H8 pattern (git bundle, data tarballs, SHA256 manifest, `s1/` scripts: `setup_s1.sh`, `go_s1.sh`, `s1_sched.py`, `collect_s1.sh`, `jobs_s1.tsv`, `jobs_s1_smoke.tsv`, `STAGE1_JOBLIST.tsv`, `cost_estimate.txt`).
- Code: `scripts/testing/gen_jobs_s1.py` (single source of the job files), `run_s1.py` (run / gate / select / report), `prereg/hw/S1_tuning_grids.json` (DRAFT grids and selection rule, tuning-only; B3 grid = 6 percentile pairs x 2 final-temperature knobs = 12; ours_none/B1 12; kc2c 12; ours 12 labels), `tests/hw/test_s1_jobs.py`.
- Scheduler: `s1_sched.py` = the H8 scheduler with dependencies instead of barriers. `0.5.r13_960` is row 1 (fresh ideal vs tiled-256 nominal at p3n960, 2 records; the stored H8 records are not shipped); every noisy p3n960 / p4n960 / gk job depends on it, so a failing gate (rc 1, difference reported) means those jobs never start. `SEL.1a` (after all round-1 rows) writes the round-2 / 1b selections, `SEL.2` writes the final stack and the Stage 1 -> 2 gate (`stage2_go`; 1e rows skip themselves if it is false), `report_s1` runs last.
- 320 executable jobs (the 252 of the earlier list were not chunked; every job is now <= 18 min estimated) after two cost trims: p4n480 is not tuned in round 1 and round 2 uses 6 x 3 runs (p4n960 and p4n480 use the config transferred by the same rule for every arm); 1c.k uses 6 B1 instances; 1d is 5 x 5.
- **Cost: 33.4 CPU-h (incl. x1.3 margin), simulated makespan 79 min on 32 slots, Rs 120** = (0.3 h set-up + 0.15 h smoke gate + 79 min + 0.1 h collect) x Rs 64.28/h. Within the Rs 125 budget but with only Rs 5 of slack: the n480/gk tiled nominal runtimes and the 960 gate are estimates (a measured 1-sweep gk nominal tiled run took 122 s and 5.6 GB, dominated by programming). The go script's deadline is 150 min and its hard cap 165 min (ceiling about Rs 223); decide whether to lower it before launch.
- Local clean-unpack smoke (not on the cloud instance): payload copied, `SETUP_OFFLINE=1` set-up into an empty root, gate tests (stage-1 hooks, cost bugs, variation_v2), then the REAL scheduler on `jobs_s1_smoke.tsv` (136 rows = every job type once at 1 sweep, plus full round 1 of p3n480 and gk so that the selection step reads real files): **136/136 done, 0 failed**, R13 smoke gate passed, `SEL.1a` / `SEL.2` / `report_s1` ran and the report read 129 run rows. Evidence is under `$PROJECT/00_admin/bundles/s1_clean_test` (go.log, scheduler log, smoke outputs).
- Caveats: the 960-spin and gk nominal smokes were run at their local-RSS limit (5.7 GB declared, 5.6 GB measured); the selection/gate rules were exercised on 1-sweep outputs (all success 0), so their thresholds are untested on real data. `/tmp` (a 4.9 GB tmpfs) was 99 % full during this work from files outside this task; the clean test therefore ran under `00_admin/bundles/`.
