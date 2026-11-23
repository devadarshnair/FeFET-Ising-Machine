# Narrowed claims (R14; FIX_LEDGER PAPER-1..4). A repo document, not paper text

Sources:
- H8 (`prereg/hw/H8_full.md`, `docs/hw/results/H8_RESULTS.md`, frozen);
- Stage 2 (`prereg/hw/S2_confirmatory.md`, frozen, plus `S2_confirmatory_AMENDMENT_1.md`; `docs/hw/diagnosis/STAGE2_RESULTS.md`);
- the internal review, sections 9-14.

All numbers come from stand-in device and circuit models (BSIM4 / FreePDK45 / Nangate45). They support ratios only, with roughly x2 uncertainty in absolute values. No paper file was edited.

## 1. Claims that may be made (each with its qualifier)
1. **Structured colouring, success.** Retuned ours (I11 greedy + Kc2, K = 0.25n, L = 10) solves 57 % of fresh p3n480 runs, against 57 % for tuned B3 (B3_h8) and 36 % for B3_sel (Stage 2, 64 instances x 3 seeds, nominal). It also has the highest success of any machine at p4n480, where p4 used a transferred configuration (P4-1). Qualifier: planted colouring at 480 spins only.
2. **Against B1, energy.** Ours wins on ETS against B1 with its registered wv+cal stack: 0.078 [0.024, 0.145] at p3n480 and 0.131 at p4n480 (Stage 2). It also wins against bit-sliced B1 (Stage 2 report-only). Qualifiers (PAPER-1 / A6):
   - On the ideal device, B1_best is bit-identical to ours_none. So ours vs B1 is a comparison of our hardware and pricing plus I11 + Kc2, not of two independent algorithms.
   - The B1 result depends on B1's mitigation stack. Native wv+cal collapses at k >= 2, while bit-sliced B1 behaves like ours.
3. **Against B3, energy: no advantage shown.** At p3n480, ours/B3_sel = 1.48 [0.97, 2.12] and ours/B3_h8 = 1.23 [0.84, 1.69], both inconclusive. This is "no energy advantage shown", never parity.
   - Under the frozen H8 pricing, the B3_sel contrast is a loss (1.64 [1.08, 2.37]), so the "no loss" reading is pricing-fragile.
   - The p4 "wins" against B3_h8 are contrasts with a 0 %-success comparator and are not evaluable (EVAL-1, amendment A1.3).
4. **Where the energy gap comes from (R2-1..R2-3).** Ours needs 11.3-12 cycles per step against B3's 6.0. About 80-85 % of ours' energy is clocked idle and leakage that scales with cycles, and array + ADC conversion is only 12-19 %.
   - Do not write that "the gap is the analog array/ADC energy". That wording, in internal review s13.2 and STAGE2 s5.1, is wrong. The gap is the latency of the serial read in each step.
   - The kicks cost +1.6 % energy per run (amendment A1.1).
5. **Robustness is conditional (PAPER-2 / A7 / H-1 / R2-7).**
   - With the diff mitigation stack, ours matches the ideal device only above a cliff in the C2C share: about 0.03-0.1 at k = 1 and 0.25-0.5 at k >= 2.
   - The C2C share has not been measured. The literature "points to D2D-dominated" Vth spread (Phadke et al. 2025/2026), which would put us below the cliff.
   - Make no margin claim. The robustness is a sub-LSB/2 cliff.
   - Ours is about as robust as bit-sliced B1, at about half the mitigation area and energy.
6. **B3 and variation (PAPER-4).** Write "B3 has no modelled analog variation exposure" (SRAM failure is not modelled), not "B3 is immune".

## 2. Claims that may NOT be made
- Any energy win over B3, at any size.
- Anything about 960 spins or larger. Stage 1 gave ours 0.17 vs B3 0.39 at p3n960, which was out of Stage 2 scope (A3).
- Any Max-Cut claim. The H8 Max-Cut loss stands, and G43-47 are tuning-only. Fresh instances (`mc_fresh.py`) exist from round 2 but have not been run (MC-1).
- "Robust to device variation" without the C2C-share qualifier.
- "B1 is about 10x more exposed than ours". This was withdrawn: bit-sliced B1 behaves like ours.
- Any result from the round-2 architecture tweaks T-1..T-6, the barrier hooks (burst, conflict kick, late acceptance) or R7/R8. They are implemented and default-off but not yet evaluated in any registered study. Simulation-only observations (for example, T-2 sparse storage removing the share-0 field error on one instance) are exploratory and must not be presented as results.

## 3. Disclosure checklist for any write-up
A6 identity; corrected vs frozen pricing side by side; tuning-only status of gk; transferred p4 configuration; tuning-to-fresh shrinkage
(ours 0.83 -> 0.57, B3_sel 0.71 -> 0.36; SHR-1); per-cell runs below the MDE read as "not resolved"; stand-in models; the unmeasured
C2C share and the lab request (`LAB_REQUEST_C2C.md`).
