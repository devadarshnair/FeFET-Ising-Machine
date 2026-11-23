# Stage 3.2 report (DRAFT; energy and success primary)

A not-resolved outcome is read as **no energy advantage shown**, never as parity. A 'supported' statement also requires the verdict at hardware estimates x2.

## Primary (nominal estimates, margin -0.10, corrected pricing + b3b, T-1 screening-only stack, B3 gated)

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.501 [0.324, 0.65] | +0.29 [+0.19, +0.40] | 0.0008 | **win** |
| p3n480 | B3_h8 | 0.537 [0.35, 0.695] | +0.01 [-0.10, +0.12] | 0.0008 | **inconclusive** |
| p4n480 | B3_sel | 0.428 [0.281, 0.577] | +0.09 [-0.01, +0.20] | 0.0008 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.0008 | **not evaluable** |
| p3n960 | B3_sel | 1.22 [0.599, 2.5] | +0.02 [-0.09, +0.13] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.49 [0.866, 2.69] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 13.2 [7.61, 20.6] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 9.12 [5.61, 13] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Sensitivity: margin -1 pp

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.501 [0.325, 0.648] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.537 [0.347, 0.693] | +0.01 [-0.10, +0.12] | 0.00267 | **inconclusive** |
| p4n480 | B3_sel | 0.428 [0.279, 0.583] | +0.09 [-0.01, +0.20] | 0.00267 | **inconclusive** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.22 [0.602, 2.47] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.49 [0.872, 2.68] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 13.2 [7.56, 20.7] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 9.12 [5.58, 13.1] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **NO ENERGY ADVANTAGE SHOWN**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Sensitivity: frozen H8 pricing (no corrections, no tweaks)

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 1.24 [0.807, 1.61] | +0.29 [+0.19, +0.39] | 1 | **inconclusive** |
| p3n480 | B3_h8 | 1.33 [0.861, 1.72] | +0.01 [-0.10, +0.12] | 1 | **inconclusive** |
| p4n480 | B3_sel | 1.12 [0.728, 1.52] | +0.09 [-0.01, +0.20] | 1 | **inconclusive** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 3.7 [1.84, 7.54] | +0.02 [-0.09, +0.14] | 1 | **loss** |
| p3n960 | B3_h8 | 4.54 [2.66, 8.15] | -0.20 [-0.33, -0.08] | 1 | **loss** |
| maxcut | B3_sel | 47.3 [27.2, 74.4] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 32.8 [20.1, 47] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **NO ENERGY ADVANTAGE SHOWN**; p3n960: **FALSIFIED**; maxcut: **FALSIFIED**

## Sensitivity: B3 un-gated (favourable to ours)

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.42 [0.273, 0.543] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.45 [0.291, 0.582] | +0.01 [-0.10, +0.12] | 0.00267 | **inconclusive** |
| p4n480 | B3_sel | 0.359 [0.234, 0.489] | +0.09 [-0.01, +0.20] | 0.00267 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.03 [0.511, 2.1] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.26 [0.741, 2.27] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 11.2 [6.43, 17.6] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 7.75 [4.74, 11.1] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Sensitivity: hardware estimates x2

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.528 [0.343, 0.682] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.565 [0.365, 0.73] | +0.01 [-0.10, +0.12] | 0.00333 | **inconclusive** |
| p4n480 | B3_sel | 0.45 [0.293, 0.613] | +0.09 [-0.01, +0.20] | 0.00267 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.27 [0.631, 2.59] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.56 [0.915, 2.81] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 13.8 [7.91, 21.6] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 9.53 [5.83, 13.7] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Sensitivity: hardware estimates x0.5

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.488 [0.317, 0.631] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.523 [0.338, 0.675] | +0.01 [-0.10, +0.12] | 0.00267 | **inconclusive** |
| p4n480 | B3_sel | 0.417 [0.272, 0.568] | +0.09 [-0.01, +0.20] | 0.00267 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.19 [0.588, 2.41] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.45 [0.851, 2.61] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 12.9 [7.39, 20.2] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 8.91 [5.45, 12.8] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Sensitivity: correction table 4

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.582 [0.377, 0.751] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.623 [0.403, 0.804] | +0.01 [-0.10, +0.12] | 0.005 | **inconclusive** |
| p4n480 | B3_sel | 0.496 [0.324, 0.676] | +0.09 [-0.01, +0.20] | 0.00267 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.43 [0.709, 2.91] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.75 [1.03, 3.15] | -0.20 [-0.33, -0.08] | 1 | **loss** |
| maxcut | B3_sel | 15.5 [8.9, 24.4] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 10.7 [6.57, 15.4] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **FALSIFIED**; maxcut: **FALSIFIED**

## Sensitivity: correction table 16

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.823 [0.533, 1.06] | +0.29 [+0.19, +0.39] | 0.342 | **inconclusive** |
| p3n480 | B3_h8 | 0.881 [0.569, 1.14] | +0.01 [-0.10, +0.12] | 0.575 | **inconclusive** |
| p4n480 | B3_sel | 0.701 [0.457, 0.955] | +0.09 [-0.01, +0.20] | 0.0956 | **inconclusive** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 2.08 [1.03, 4.23] | +0.02 [-0.09, +0.14] | 1 | **loss** |
| p3n960 | B3_h8 | 2.54 [1.49, 4.57] | -0.20 [-0.33, -0.08] | 1 | **loss** |
| maxcut | B3_sel | 22.5 [12.9, 35.4] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 15.6 [9.53, 22.3] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **NO ENERGY ADVANTAGE SHOWN**; p3n960: **FALSIFIED**; maxcut: **FALSIFIED**

## Sensitivity: screening double-counted (mitigation_cost + t1f)

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.501 [0.325, 0.648] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.537 [0.347, 0.693] | +0.01 [-0.10, +0.12] | 0.00267 | **inconclusive** |
| p4n480 | B3_sel | 0.428 [0.279, 0.583] | +0.09 [-0.01, +0.20] | 0.00267 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.22 [0.602, 2.47] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.49 [0.872, 2.68] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 13.2 [7.56, 20.7] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 9.12 [5.58, 13.1] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Sensitivity: Max-Cut target 0.995

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.501 [0.325, 0.648] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.537 [0.347, 0.693] | +0.01 [-0.10, +0.12] | 0.00267 | **inconclusive** |
| p4n480 | B3_sel | 0.428 [0.279, 0.583] | +0.09 [-0.01, +0.20] | 0.00267 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.22 [0.602, 2.47] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.49 [0.872, 2.68] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 20.9 [8.47, 55.8] | -0.49 [-0.66, -0.29] | 1 | **loss** |
| maxcut | B3_h8 | 24.1 [11.5, 58.6] | -0.77 [-0.88, -0.65] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Sensitivity: Max-Cut reference raised post hoc

| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 8) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.501 [0.325, 0.648] | +0.29 [+0.19, +0.39] | 0.00267 | **win** |
| p3n480 | B3_h8 | 0.537 [0.347, 0.693] | +0.01 [-0.10, +0.12] | 0.00267 | **inconclusive** |
| p4n480 | B3_sel | 0.428 [0.279, 0.583] | +0.09 [-0.01, +0.20] | 0.00267 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.00267 | **not evaluable** |
| p3n960 | B3_sel | 1.22 [0.602, 2.47] | +0.02 [-0.09, +0.14] | 1 | **inconclusive** |
| p3n960 | B3_h8 | 1.49 [0.872, 2.68] | -0.20 [-0.33, -0.08] | 1 | **inconclusive** |
| maxcut | B3_sel | 13.3 [7.58, 20.7] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| maxcut | B3_h8 | 9.17 [5.61, 13.1] | -0.30 [-0.43, -0.18] | 1 | **loss** |

Decision per cell: p3n480: **NO ENERGY ADVANTAGE SHOWN**; p4n480: **SUPPORTED**; p3n960: **NO ENERGY ADVANTAGE SHOWN**; maxcut: **FALSIFIED**

## Supported at hardware estimates x2?

p3n480: n/a; p4n480: yes; p3n960: n/a; maxcut: n/a

## Success and energy per run (primary pricing)

| cell | arm | n instances x seeds | success | energy per run (fJ) |
|---|---|---|---|---|
| p3n480 | ours_stack | 64 x 3 | 0.66 | 3.06e+11 |
| p3n480 | B3_sel | 64 x 3 | 0.36 | 4.38e+11 |
| p3n480 | B3_h8 | 64 x 3 | 0.65 | 4.77e+11 |
| p4n480 | ours_stack | 64 x 3 | 0.71 | 3.05e+11 |
| p4n480 | B3_sel | 64 x 3 | 0.61 | 4.65e+11 |
| p4n480 | B3_h8 | 64 x 3 | 0.00 | 4.79e+11 |
| p3n960 | ours_stack | 64 x 2 | 0.20 | 2.77e+12 |
| p3n960 | B3_sel | 64 x 2 | 0.17 | 4.02e+12 |
| p3n960 | B3_h8 | 64 x 2 | 0.40 | 4.15e+12 |
| maxcut | ours_stack | 20 x 5 | 0.70 | 7.24e+11 |
| maxcut | B3_sel | 20 x 5 | 1.00 | 1.12e+12 |
| maxcut | B3_h8 | 20 x 5 | 1.00 | 1.12e+12 |
