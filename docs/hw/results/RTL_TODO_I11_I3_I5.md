# RTL to-do for I11, I3, I5 (spec note; hw-p3 RTL not touched here)

Golden model: `scripts/golden/tweaks.py` (flags on `TweakCfg`, all default off, off = bit-exact). Counters and cost rows:
`counters.py`, `cost_model.py`, `docs/hw/energy_table_tweaks_i11_i3_i5.csv` (I3/I5 rows are placeholders).

- **I11 greedy + Kc2 kick.** Acceptance `acc_i = (geff_i + E_off >= 0)`; drop the LUT read, the theta multiply and the per-lane
  xoshiro (keep one shared selection/kick RNG). Force deoff = 0 (E_off stays 0, no E_off or T register writes). Restart arm
  fixed to Kc2 (stall counter + partial Fisher-Yates kick of L lanes from the selection stream; no schedule reset). Config
  bit `i11`; the golden asserts the arm is kc2.
- **I3 ramped penalty gain.** Knapsack modes `hw` (TCAM thermometer) and `penalty`. Penalty weight register
  `lam_t = lam_lo + ((lam - lam_lo) * min(t, ramp_steps)) // ramp_steps`, updated once per step while `t <= ramp_steps`, then
  frozen at `lam`. Replaces the constant `lam` in `geff = (gain << gsh) - lam*cnt_add + lam*cnt_rem` (`hw`) and in the hinge term
  (`penalty`). New config registers: `lam_lo`, `ramp_steps`. Needs a 16 b shift-add/multiplier and a step compare (placeholder
  gate row `g_ramp_unit`).
- **I5 Vth-spread acceptance noise.** Needs a device-level noise source per lane (FeFET Vth spread read through a sense decision)
  that replaces xoshiro + LUT; not expressible in RTL without a behavioural noise model. Open items: (a) a noise sample must
  supply the LUT's distribution (the golden keeps it and only models hold/group correlation), (b) `hold` (sample held `hold`
  steps) and `group` (lanes sharing one sample) are the correlation knobs the kill criterion tests, (c) characterise sample
  energy/area (rows `e_vth_noise_sample`, `g_vth_noise_per_lane` are placeholders). Recommend deferring RTL until I11 is scored.
