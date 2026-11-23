# S2 prereg (FROZEN): confirmatory energy test of the retuned stack at 480 spins (FROZEN 22 Nov 2026 IST; rewritten 22 Nov 2026 after internal review item 9-10)

Status: **FROZEN by this commit (22 Nov 2026 IST), before any Stage 2 record exists**, after internal review (7c5e928). Bundle pin a02aa80. Where the loss-condition wording here differs from `evaluate_s2.py` (H8 loss class), the evaluator governs, as noted in the internal review. Untagged. `prereg/hw/H8_full.md` is untouched.
**Gate status (relabelled):** the Stage 1 -> 2 gate was a *formal PASS via a non-informative tuning-only cell (gk) and a substantive FAIL at p3n960* (STAGE1_RESULTS sections 2 and 7). Stage 2 is therefore **not licensed by the gate**; it is a scoped author decision: confirm the one validated change (shorter stall window K, and a modest kick) **where Stage 1/1b show a real effect, at 480 spins**, with **energy as the primary question**.
Inputs: STAGE1_RESULTS.md, STAGE1B_RETUNE.md, `prereg/hw/S1_tuning_grids.json`, `s1b_evidence/selection_1a.json`.

## 1. Primary question and falsifier (energy)
**Does success parity at 480 spins survive the energy accounting?** Stage 1b shows that ours' success rises from 0.21 to 0.83 after the retune and reaches parity with tuned B3 (0.71-0.79), but ours spends 1.3-1.5x more energy per run than B3 (7.2e11 vs 4.9-5.7e11 fJ); the first ETS look gives ours/B3 = 1.49 [0.47, 2.93] (B3 grid-selected) and 0.92 [0.33, 1.30] (B3 H8-registered), ideal device, 24 runs, not resolved. The kick itself is not the cost (restart block 0.09 % of ours' energy), but the nominal condition adds the mitigation energy of ours (H8 +10-21 %), so an ETS **loss** to B3 with success parity is a live outcome.
- **S2-A (primary, nominal condition, mitigation per machine as in H8; cells p3n480 and p4n480):** ETS99 ratio ours_new / comparator for the comparators B3_sel, B3_h8 and B1_sel; Holm over m = 6 contrasts (2 cells x 3 comparators); verdict classes and rules as H8 (win: ratio <= 0.95, Holm p < 0.05, ETS CI upper bound < 1, success difference not worse than -1 pp).
- **Fixed dual-B3 decision rule (decided before data; evaluated at p3n480; implemented in `evaluate_s2.py`):** the hypothesis "retuned ours is energy-competitive with B3 at 480 spins" is
  - **SUPPORTED** only if ours_new **wins** against **both** B3_sel and B3_h8;
  - **FALSIFIED** if ours_new **loses** to **either** (ratio >= 1.0 with the CI lower bound above 1);
  - otherwise **"no energy advantage shown"** (inconclusive, tie or not evaluable against at least one B3 comparator). **A not-resolved outcome is anticipated (Stage 1b intervals contain 1) and is read as "no energy advantage shown", never as parity.**
  Prior from Stage 1b (not a result): ratio about 1.0-1.8 at nominal, so "no advantage shown" or a loss is the expected outcome; p4n480 is reported with the same rule but does not enter the decision.
- **S2-B (bridge, report-only):** ours_new vs ours_h8 (frozen H8 configuration L = 10, K = 2n): the retune alone, in success and ETS (Stage 1b: 0.11x ETS).
- **S2-C (NOT RUN in this scope, dropped for cost; Stage 1b gives the first look):** ours_new vs ours_none_sel and ours_kc2c_sel (what I11 + Kc2 adds over a retuned SA / Kc2 on our hardware; Stage 1b: 3-5x lower ETS).
- **S2-D (report-only, no regression):** p3n240 and p4n240 (the retune must not lose the H8 position there: ours_new vs ours_h8 and vs B3).

## 2. Arms and configurations (Stage 1b selections after the edge probe: unchanged, so they are final unless the author changes the rule)
| label | spec | colouring config at the time of writing |
|---|---|---|
| ours_new | ours.kc2.fs.i11, wv+diff+cal (tiled-256 simulator above 256 lanes) | kick_c 0 (L = 10), K = 0.25n (interior after the probe: K 0.0625n-0.5n gives 0.75-0.83) |
| ours_h8 (bridge) | H8 ours_kc2_i11 | L = 10, K = 2n |
| B3_sel | b3.b3v2 | T_start x1.5, T_final x0.0625 T_end (probe: x1/32 and x1/64 are worse) |
| B3_h8 | b3.b3v2 | H8-registered p90/5, knob 0.5 (beats every new B3 grid configuration in Stage 1b: 0.79 vs 0.71; carried as a second B3 comparator) |
| B1_sel | b1.none.fs, wv+cal (native cells) | ours_none selection (T_start x2, T_end x0.5, fraction 0.5; probe: T_start x3, x4 worse) |
| B1_bs (report-only) | b1.none.fs, wv+diff+cal+bin | same schedule |
| ours_ets, B3_ets (ETS-selected sensitivity, p3n480 only) | as ours_new / B3 | ours: c 0.04, K = 0.125n; B3: T_start x1.5, T_final x1/64 | (pre-declared sensitivity: same-data ETS selection of Stage 1b) |
| ours_none_sel, ours_kc2c_sel (S2-C, not run) | as Stage 1b selections (kc2c: T_end x0.25, K = n, c = 0.08; none as B1_sel) | probe: unchanged |
**Edge probe done (STAGE1B_RETUNE section 3):** 4 configurations beyond each edge winner for all four arms; no winner changed. Selection rule: success first (registered), ties by mean best_E. Because ETS takes the minimum over the budget grid, an ETS-selected configuration per arm differs (and B3's ETS-best has success 0.25): the primary keeps the success-first rule, and the ETS-selected variant is a pre-declared sensitivity (ours/B3 1.08 [0.21, 2.51] on the tuning data). The p4 config is the transferred p3 config for every arm (p4 was not tuned).

## 3. Cells, instances, seeds (fresh, tag 11; disjoint from H8 tag 9 and Stage 0/1/1b tag 10)
Planted p3 keys 2301.., p4 keys 2401..; seeds 9000+ common across arms; budgets as H8 (300 sweeps at 480, 150 at 240); success target 0.
| cell | instances x seeds | role | MDE of the success difference at p = 0.5 / 0.2 (alpha = 0.05 / 6, 80 % power, rho = 0.25) |
|---|---|---|---|
| p3n480 | **64 x 3 = 192** | primary | 0.15 / 0.12 |
| p4n480 (transferred config) | **64 x 3 = 192** | primary | 0.15 / 0.12 |
| p3n240, p4n240 | 16 x 3 = 48 each | report-only (S2-D) | 0.31 / 0.25 |
ETS power rationale (internal review item 11.2.1): the H8 bootstrap resamples instances first, so the ETS interval width scales roughly with 1/sqrt(instances); the Stage 1b intervals on 8 instances (log half-widths 0.7-0.9) imply about 0.25-0.3 at 64 instances, which resolves a ratio of about 1.3 against 1 before Holm; smaller true differences will not be resolved. Instances were therefore preferred to seeds (64 x 3 instead of 30 x 5). Report-only cells were trimmed to keep the worst case within Rs 150: B1 bit-sliced and the ETS-selected sensitivity arms run on p3n480 only; the 240-spin no-regression cells use 16 x 3.
Primary Holm family: m = 2 cells x 3 comparators (B3_sel, B3_h8, B1_sel) = 6 (conservative towards B3: both B3 comparators stay in the family). **Out of scope and stated as limitations:** p3n960/p4n960 (Stage 1: ours 0.17 vs B3 0.39; expensive: about 290-300 s per nominal run, so not worth confirming a likely loss), Max-Cut (no fresh 1000-node instances; G43-47 tuning-only; the H8 Max-Cut loss stands), DIMACS-type generated graphs (already a win in H8, unchanged here). A 960 or Max-Cut claim cannot be made from this study.

## 4. Pricing and statistics
Primary pricing `measured_v2` with corrected flags (`--cost-flags all`: B-1, B-2, B-3); frozen H8 pricing reported as sensitivity next to every verdict (H8 re-pricing produced 0 flips). ETS99 by the H8 two-level paired bootstrap (B = 10000, seed fixed at the freeze), Wilson/Newcombe for success, single look, no interim analysis. Below the MDE a difference is "not resolved". The energy table also reports the energy per run and the restart/RNG block shares so that the kick cost can be read directly.

## 5. Decision rules
As H8 section 7; every variation statement carries "conditional on the unmeasured C2C share" (k = 1 cliff at about 0.03; k >= 2 needs 0.25-0.5); no Stage 0/1/1b number is used as a result; nothing is pooled with H8. A positive S2-A result is a statement about p3/p4 planted colouring at 480 spins only.

## 6. Known limitations
Stand-in device models (ratios only, about x2); all baselines are our implementations; B1 conclusions depend on its mitigation stack (native wv+cal collapses at k >= 2; bit-sliced behaves like ours); tuning evidence is success-only on tuning instances plus the 24-run ideal ETS look; every arm's Stage 1b optimum first sat at a grid edge; the edge probe (STAGE1B_RETUNE section 3) bracketed all four, no winner changed; p4 transferred, not tuned; 960 and Max-Cut not tested.

## 7. Cost (budget ceiling Rs 150 total including set-up; account balance Rs 162.90)
Measured Stage 1 s/run (16 vCPU cloud instance): ours nominal tiled p3n480 34, ideal 9.8; B3 6.7; B1 nominal 50; B1 bit-sliced about 100 (extrapolated); 240-spin cells ours 4.6 / 2.5, B3 1.5, B1 6.5; p4 x 1.15; margin x1.3 on every job. Job list: `gen_jobs_s2.py` (263 jobs, every job <= 10 min estimated), 33.4 CPU-h including margin, dependency scheduler with R13 identity gate `0.5.r13_480` first.
| profile | simulated makespan | expected cost (0.3 h set-up + 0.15 h gate + makespan + 0.1 h collect) | worst case with the go-script caps |
|---|---|---|---|
| **16 vCPU, Rs 32.14/h (recommended)** | 132 min | **about Rs 89** | **Rs 133** (set-up 20 + tests 8 + smoke 10 + hard cap 205 (deadline 190 + 15) + collect 5 = 248 min) |
| 32 vCPU, Rs 64.28/h | 69 min | about Rs 109 | Rs 153 with a 100-min hard cap (deadline 85): over the Rs 150 ceiling; Rs 148 needs deadline 80 / hard cap 95, only 16 % above the simulated makespan, so 32 vCPU is not recommended |
The go script refuses to start if the worst case of the configured caps exceeds `S2_CAP_RS` (default 150). **Exact launch environment (16 vCPU):** `S2_RATE_RS_H=32.14 S2_DEADLINE_MIN=190 S2_HARD_MIN=205 S2_CAP_RS=150 bash s2_payload/s2/go_s2.sh` (defaults already equal these values; `--smoke-only` stops after the gate). The 960 and Max-Cut scopes remain withdrawn.

## 8. Cloud bundle (built, NOT launched, NOT frozen)
`$PROJECT/00_admin/bundles/s2_payload` (pin `a02aa80`; built by `scripts/cloud/s2/build_payload_s2.sh`; contents as Stage 1: git bundle, data tarballs, SHA256 manifest, `s2/` with `go_s2.sh`, `s2_sched.py` (dependency scheduler), `setup_s2.sh`, `collect_s2.sh`, `jobs_s2.tsv` (263 jobs), `jobs_s2_smoke.tsv`, `STAGE2_JOBLIST.tsv`, `cost_estimate.txt`). Evaluator `scripts/testing/evaluate_s2.py` (validated on the Stage 1b records: it reproduces the 1.49 and 0.92 ratios). Go gate: S2 go-gate tests (`s2_instances.S2_GATE_TESTS`: tag-11 instances disjoint from every earlier stage by content hash; refuses to launch on failure), job-list tests, stage-1 hook and cost-bug tests, then the smoke through the real scheduler (every job type at 1 sweep, R13 gate, report with the dual-B3 decision). **Local clean-unpack smoke: 46 tests passed (1 skipped), 33/33 smoke jobs done, gate passed, report produced** (`00_admin/bundles/s2_clean_test`).
Launch (16 vCPU): `S2_RATE_RS_H=32.14 S2_DEADLINE_MIN=190 S2_HARD_MIN=205 S2_CAP_RS=150 bash s2_payload/s2/go_s2.sh`; worst case Rs 133, refused automatically if the caps would exceed S2_CAP_RS (checked: S2_HARD_MIN=400 is refused at Rs 237). The freeze (author tag of this draft) must precede launch.
