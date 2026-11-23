# H7 amendment 1: drop the 960-spin families from Stage 4 (budget)

**FROZEN by its commit, before any Stage 4 data (none exists).** `prereg/hw/H7_scaleup.md` is frozen and is not edited; this file
amends it. 

## Change
Both 960-spin planted families, **p3n960 and p4n960**, are removed from Stage 4. Reason: credit. The author has about Rs 103 left on
the cloud provider (Rs 64.28/h for 32 vCPU), and the 960 size was about 10 of 43.6 job CPU-h. It also had the weakest power (6 seeds, 5
instances; section 6 of H7) and was the size expected to end "not evaluable" (p3n960 pilot at about 5 end conflicts).
Not a result-driven change: no Stage 4 record exists.

Stage 4 size list (read by `plan_h7.py` and `evaluate_h7.py` from the line below):

STAGE4_SIZES: 240, 480

## Unchanged
Everything else in H7: hypotheses, arms, 240/480 instances, seeds and sweeps, DIMACS family, H7-V, pricing (measured_v1 primary
plus the two sensitivities), statistics, win/tie/loss rules, Holm over 4 contrasts per family, seed stream, configs.

## Rules that named 960, now applying to 240 and 480 only
- **Scale verdict** = the largest N in {240, 480} such that L1 holds at every size up to N. The maximum possible verdict is 480.
- **Kill rule**: the scale lead is killed at the first of 240 or 480 where either planted family is not a win. L1 is not replicated
  if it is not a win on both 240-spin families.
- "Not evaluable" (every hardware arm at 0 %) still means no claim at that size.
- Rule "B1_mesa_epoch not run at 960" is moot. B1_mesa_epoch runs at 240 and 480 as registered.
- No claim is made about 960 spins or larger; absence of a 960 result is a budget limit, not evidence.
- Section 7 compute and the Rs figures are superseded by the amended budget printed by `gen_jobs_stage4.py --budget`.
- The wall-clock cap is operational, not statistical: run_stage4.sh starts no new job after 70 min and collects at 80 min
  (STAGE4_DEADLINE_MIN). Unfinished jobs leave the report barrier unrun, and the lead is then reported incomplete, not negative.
