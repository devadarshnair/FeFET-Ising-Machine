# Device inputs copied for P4.06 (read-only copies; never edit, re-copy on change)

| File here | Source | Commit |
|---|---|---|
| circuit/cim/cim_cell_v1.csv | branch hw/p1-device, circuit/cim/cim_cell_v1.csv (P1.10, Yin 1FeFET1R cell, shared with ours/B1) | 7750dff |
| circuit/adc/adc_energy.csv | branch hw/p1-device, circuit/adc/adc_energy.csv (P1.11, StrongARM comparator pdk45) | 726723c |
| circuit/tcam/char_v0.csv | hw main, circuit/tcam/char_v0.csv (already on this branch) | 9cbb0bd |

char_v0.csv is labelled "char_v0 (P1.08/P1.09 not done)". It is NOT used by the B2 filter, which the plan specifies as a
1FeFET1R matchline comparator (IMPL_PLAN P4.06, PLAN B2 row); it is listed only so a later FeFET-TCAM variant has a
recorded source. char_v1 (P1.12) does not exist yet: the filter uses the P1.10 cell rows that feed char_v1.
