# Stage 2 report (DRAFT; energy primary)

A not-resolved outcome is read as **no energy advantage shown**, never as parity.

## Primary pricing (corrected: B-1, B-2, B-3)

cost flags: ['b1', 'b2', 'b3']

| cell | comparator | ETS ratio ours_new / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 6) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 1.48 [0.973, 2.12] | +0.21 [+0.09, +0.33] | 1 | **inconclusive** |
| p3n480 | B3_h8 | 1.23 [0.842, 1.69] | +0.00 [-0.12, +0.11] | 1 | **inconclusive** |
| p3n480 | B1_sel | 0.0781 [0.0244, 0.145] | +0.52 [+0.41, +0.62] | 0.0006 | **win** |
| p4n480 | B3_sel | 1.11 [0.745, 1.48] | +0.02 [-0.09, +0.12] | 1 | **inconclusive** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.73 [+0.64, +0.82] | 0.0006 | **win** |
| p4n480 | B1_sel | 0.131 [0.0726, 0.182] | +0.52 [+0.42, +0.62] | 0.0006 | **win** |

**Dual-B3 decision (p3n480): NO ENERGY ADVANTAGE SHOWN (inconclusive, tie, or not evaluable against at least one B3 comparator; not parity)** ({'B3_sel': 'inconclusive', 'B3_h8': 'inconclusive'})

## Sensitivity: frozen H8 pricing

cost flags: none (frozen H8 pricing)

| cell | comparator | ETS ratio ours_new / comparator [95 % CI] | d success [95 % CI] | Holm p (m = 6) | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 1.64 [1.08, 2.37] | +0.21 [+0.09, +0.33] | 1 | **loss** |
| p3n480 | B3_h8 | 1.37 [0.936, 1.88] | +0.00 [-0.12, +0.11] | 1 | **inconclusive** |
| p3n480 | B1_sel | 0.075 [0.0233, 0.139] | +0.52 [+0.41, +0.62] | 0.0006 | **win** |
| p4n480 | B3_sel | 1.23 [0.825, 1.64] | +0.02 [-0.09, +0.12] | 1 | **inconclusive** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.73 [+0.64, +0.82] | 0.0006 | **win** |
| p4n480 | B1_sel | 0.124 [0.0685, 0.172] | +0.52 [+0.42, +0.62] | 0.0006 | **win** |

**Dual-B3 decision (p3n480): FALSIFIED: loss to at least one B3 comparator at p3n480** ({'B3_sel': 'loss', 'B3_h8': 'inconclusive'})

## Report-only contrasts (primary pricing)

| contrast | instances x seeds | ETS ratio [95 % CI] | d success [95 % CI] |
|---|---|---|---|
| p3n240 nominal: ours_new vs ours_h8 (bridge) | 16 x 3 | 0.447 [0.164, 1.02] | +0.27 [+0.10, +0.46] |
| p3n240 ideal: ours_new vs ours_h8 (bridge) | 16 x 3 | 0.466 [0.164, 1.02] | +0.27 [+0.10, +0.46] |
| p3n480 nominal: ours_new vs ours_h8 (bridge) | 64 x 3 | 0.158 [0.0901, 0.401] | +0.43 [+0.32, +0.54] |
| p3n480 ideal: ours_new vs ours_h8 (bridge) | 64 x 3 | 0.161 [0.0918, 0.406] | +0.43 [+0.32, +0.54] |
| p4n240 nominal: ours_new vs ours_h8 (bridge) | 16 x 3 | 0.563 [0.279, 1.11] | +0.15 [-0.04, +0.33] |
| p4n240 ideal: ours_new vs ours_h8 (bridge) | 16 x 3 | 0.563 [0.278, 1.11] | +0.15 [-0.04, +0.33] |
| p4n480 nominal: ours_new vs ours_h8 (bridge) | 64 x 3 | 0.21 [0.132, 0.319] | +0.45 [+0.34, +0.56] |
| p4n480 ideal: ours_new vs ours_h8 (bridge) | 64 x 3 | 0.21 [0.132, 0.319] | +0.45 [+0.34, +0.56] |
| p3n240 nominal: ours_new vs B3_sel | 16 x 3 | 0.559 [0.206, 0.895] | +0.40 [+0.21, +0.58] |
| p3n240 nominal: ours_new vs B3_h8 | 16 x 3 | 0.503 [0.23, 0.796] | +0.15 [+0.00, +0.29] |
| p3n240 nominal: ours_new vs B1_sel | 16 x 3 | 0.125 [0.0453, 0.192] | +0.58 [+0.42, +0.75] |
| p3n480 nominal: ours_new vs B1_bs | 64 x 3 | 0.148 [0.0737, 0.231] | +0.46 [+0.35, +0.56] |
| p4n240 nominal: ours_new vs B3_sel | 16 x 3 | 0.811 [0.398, 1.43] | +0.02 [-0.12, +0.17] |
| p4n240 nominal: ours_new vs B3_h8 | 16 x 3 | 0 [0, 0] | +0.77 [+0.58, +0.94] |
| p4n240 nominal: ours_new vs B1_sel | 16 x 3 | 0.179 [0.0722, 0.305] | +0.38 [+0.21, +0.56] |
| p3n480 nominal: ETS-selected ours_ets vs ETS-selected B3_ets (sensitivity) | 64 x 3 | 1.06 [0.494, 1.67] | +0.52 [+0.42, +0.62] |

## Energy per run and block shares

| arm | cell | cond | runs | energy / run (fJ) | restart share | rng share | success |
|---|---|---|---|---|---|---|---|
| B1_bs | p3n480 | nominal | 192 | 1.14e+12 | 0.0000 | 0.0679 | 0.11 |
| B1_sel | p3n240 | nominal | 48 | 1.09e+11 | 0.0000 | 0.0794 | 0.38 |
| B1_sel | p3n480 | nominal | 192 | 1.04e+12 | 0.0000 | 0.0679 | 0.06 |
| B1_sel | p4n240 | nominal | 48 | 1.16e+11 | 0.0000 | 0.0746 | 0.40 |
| B1_sel | p4n480 | nominal | 192 | 1.13e+12 | 0.0000 | 0.0620 | 0.21 |
| B3_ets | p3n480 | ideal | 192 | 5.42e+11 | 0.0000 | 0.1230 | 0.08 |
| B3_h8 | p3n240 | ideal | 48 | 6.88e+10 | 0.0000 | 0.1214 | 0.81 |
| B3_h8 | p3n480 | ideal | 192 | 5.68e+11 | 0.0000 | 0.1172 | 0.57 |
| B3_h8 | p4n240 | ideal | 48 | 6.95e+10 | 0.0000 | 0.1202 | 0.00 |
| B3_h8 | p4n480 | ideal | 192 | 5.69e+11 | 0.0000 | 0.1170 | 0.00 |
| B3_sel | p3n240 | ideal | 48 | 6.11e+10 | 0.0000 | 0.1365 | 0.56 |
| B3_sel | p3n480 | ideal | 192 | 5.27e+11 | 0.0000 | 0.1263 | 0.36 |
| B3_sel | p4n240 | ideal | 48 | 6.66e+10 | 0.0000 | 0.1253 | 0.75 |
| B3_sel | p4n480 | ideal | 192 | 5.54e+11 | 0.0000 | 0.1204 | 0.71 |
| ours_ets | p3n480 | nominal | 192 | 8.26e+11 | 0.0803 | 0.0002 | 0.60 |
| ours_h8 | p3n240 | ideal | 48 | 7.98e+10 | 0.0872 | 0.0005 | 0.69 |
| ours_h8 | p3n240 | nominal | 48 | 8.76e+10 | 0.0872 | 0.0005 | 0.69 |
| ours_h8 | p3n480 | ideal | 192 | 7.08e+11 | 0.0798 | 0.0002 | 0.14 |
| ours_h8 | p3n480 | nominal | 192 | 8e+11 | 0.0798 | 0.0002 | 0.14 |
| ours_h8 | p4n240 | ideal | 48 | 8.13e+10 | 0.0870 | 0.0005 | 0.62 |
| ours_h8 | p4n240 | nominal | 48 | 8.9e+10 | 0.0870 | 0.0005 | 0.62 |
| ours_h8 | p4n480 | ideal | 192 | 7.38e+11 | 0.0793 | 0.0002 | 0.28 |
| ours_h8 | p4n480 | nominal | 192 | 8.31e+11 | 0.0793 | 0.0002 | 0.28 |
| ours_new | p3n240 | ideal | 48 | 8.21e+10 | 0.0873 | 0.0005 | 0.96 |
| ours_new | p3n240 | nominal | 48 | 8.98e+10 | 0.0873 | 0.0005 | 0.96 |
| ours_new | p3n480 | ideal | 192 | 7.19e+11 | 0.0801 | 0.0002 | 0.57 |
| ours_new | p3n480 | nominal | 192 | 8.12e+11 | 0.0801 | 0.0002 | 0.57 |
| ours_new | p4n240 | ideal | 48 | 8.33e+10 | 0.0871 | 0.0005 | 0.77 |
| ours_new | p4n240 | nominal | 48 | 9.1e+10 | 0.0871 | 0.0005 | 0.77 |
| ours_new | p4n480 | ideal | 192 | 7.48e+11 | 0.0795 | 0.0002 | 0.73 |
| ours_new | p4n480 | nominal | 192 | 8.42e+11 | 0.0795 | 0.0002 | 0.73 |
