# P4 multi-level note: how B1 (P4.01, 3-bit weights per cell) must handle P1.10 t4e

Input: P1.10 t4e (hw/p1-device 7750dff): under Ni-2019 Vth variation only levels 0 and 7 are reliable open-loop
(sigma/mu 0.39-1.03 on levels 1-6); multi-level cells need per-cell write-verify. P4.06 adds: unverified level-0
cells (sigma 4.86 nA vs a 14.16 nA unit) dominate the column error when many cells are empty.

**AUTHOR DECISION (flagged):** IMPL_PLAN P4.01/P4.02 does not fix write-verify vs bit-slicing for B1. B1 code is not
changed here. Registered handling proposed for the B1 calibration/variation study, pending author confirmation:

1. Default = per-cell write-verify, same model as B2 (prereg/calib/P4.06.md): verified levels uniform in target +-5 %,
   attempts per level 1/P(|N(0, sigma/mu)| < 0.05) from cim_cell_v1 (levels 1-6), each attempt e_write + verify read,
   t_write 2.02 us + 20 ns, cell-by-cell programming (P1.07 fallback). Costs go in the one-time programming budget and
   are reported, not hidden. Reason: keeps Yin's 3-bit cell/area/ADC geometry (literature-parameterised label) and
   matches B2.
2. Level 0 must be treated explicitly: either verified like the other levels (state the cost) or reported as the
   open-loop term; B1's variation study must report both, because P4.06 shows level 0 alone can dominate.
3. Alternative (if the author prefers): bit-slice into 3 binary cells (levels 0/7 only) per weight -> 3x columns and
   ADC conversions, shift-add in digital; the area/energy change must be priced from the same table and labelled
   "B1 bit-sliced (deviation from Yin)".
4. The P4.02 calibration (algorithm level, sigma = 0) is unaffected; the choice matters only for the H5 variation and
   cost rows. Whichever is chosen must be registered before the first B1 variation run.
