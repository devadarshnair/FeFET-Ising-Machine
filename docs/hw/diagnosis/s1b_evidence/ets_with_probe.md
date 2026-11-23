# Stage 1b ETS first look (ideal device, p3n480 tuning instances 2101-2108 x 3 seeds; corrected pricing B-1..B-3; fixed H8 evaluator machinery)

ETS99 in fJ, pooled over the (instance, seed) rectangle with the H8 paired bootstrap (B = 2000). Not confirmatory: tuning instances, 24 runs per configuration, ideal device (no mitigation energy).

| arm | cid | success | ETS99 (fJ) | e_final/run (fJ) | restarts/run | restart block share | rng block share |
|---|---|---|---|---|---|---|---|
| B3 | knob1_t_hi_mult1.5_t_lo_mult0.015625 | 0.25 | 8.65e+11 | 5.23e+11 | 0 | 0.0000 | 0.2879 |
| B3 | knob1_t_hi_mult1.5_t_lo_mult0.0625 | 0.71 | 9.39e+11 | 4.89e+11 | 0 | 0.0000 | 0.3366 |
| B3 | knob1_t_hi_mult2.5_t_lo_mult0.0625 | 0.62 | 9.55e+11 | 5.13e+11 | 0 | 0.0000 | 0.3001 |
| B3 | knob1_t_hi_mult1.5_t_lo_mult0.03125 | 0.42 | 1.11e+12 | 4.93e+11 | 0 | 0.0000 | 0.3299 |
| B3 | knob1_t_hi_mult1.5_t_lo_mult0.125 | 0.71 | 1.47e+12 | 5.54e+11 | 0 | 0.0000 | 0.2542 |
| B3 | knob1_t_hi_mult2_t_lo_mult0.03125 | 0.29 | 1.5e+12 | 5.05e+11 | 0 | 0.0000 | 0.3113 |
| B3 | B3_ref_H8 | 0.79 | 1.52e+12 | 5.68e+11 | 0 | 0.0000 | 0.2409 |
| B3 | knob1_t_hi_mult1_t_lo_mult0.0625 | 0.46 | 1.81e+12 | 5.26e+11 | 0 | 0.0000 | 0.2836 |
| B3 | knob1_t_hi_mult1_t_lo_mult0.125 | 0.67 | 1.86e+12 | 5.53e+11 | 0 | 0.0000 | 0.2547 |
| B3 | knob1_t_hi_mult2.5_t_lo_mult0.125 | 0.58 | 2.16e+12 | 5.54e+11 | 0 | 0.0000 | 0.2540 |
| B3 | knob1_t_hi_mult2_t_lo_mult0.015625 | 0.08 | 2.71e+12 | 5.56e+11 | 0 | 0.0000 | 0.2518 |
| B3 | knob1_t_hi_mult1_t_lo_mult0.25 | 0.17 | 1.43e+13 | 5.69e+11 | 0 | 0.0000 | 0.2396 |
| B3 | knob1_t_hi_mult2.5_t_lo_mult0.25 | 0.17 | 1.43e+13 | 5.69e+11 | 0 | 0.0000 | 0.2396 |
| B3 | knob1_t_hi_mult1.5_t_lo_mult0.25 | 0.08 | 3.01e+13 | 5.69e+11 | 0 | 0.0000 | 0.2396 |
| B3 | knob1_t_hi_mult1_t_lo_mult0.5 | 0.00 | inf | 5.69e+11 | 0 | 0.0000 | 0.2396 |
| B3 | knob1_t_hi_mult1.5_t_lo_mult0.5 | 0.00 | inf | 5.69e+11 | 0 | 0.0000 | 0.2396 |
| B3 | knob1_t_hi_mult2.5_t_lo_mult0.5 | 0.00 | inf | 5.69e+11 | 0 | 0.0000 | 0.2396 |
| kc2c | tfinal1_t_lo_mult0.1_knob2_kick_c0.08 | 0.46 | 5.94e+12 | 8.67e+11 | 78 | 0.0006 | 0.2175 |
| kc2c | tfinal1_t_lo_mult0.25_knob1_kick_c0.08 | 0.46 | 6.44e+12 | 8.73e+11 | 133 | 0.0006 | 0.2173 |
| kc2c | tfinal1_t_lo_mult0.1_knob1_kick_c0.04 | 0.42 | 6.98e+12 | 8.67e+11 | 158 | 0.0006 | 0.2176 |
| kc2c | tfinal1_t_lo_mult0.25_knob0.5_kick_c0.04 | 0.42 | 7.35e+12 | 8.73e+11 | 264 | 0.0006 | 0.2174 |
| kc2c | tfinal1_t_lo_mult0.1_knob0.5_kick_c0.08 | 0.42 | 7.38e+12 | 8.82e+11 | 222 | 0.0006 | 0.2173 |
| kc2c | tfinal1_t_lo_mult0.25_knob0.5_kick_c0.08 | 0.38 | 8.29e+12 | 8.82e+11 | 223 | 0.0006 | 0.2173 |
| kc2c | tfinal1_t_lo_mult0.1_knob0.5_kick_c0.04 | 0.38 | 8.56e+12 | 8.73e+11 | 272 | 0.0006 | 0.2175 |
| kc2c | tfinal1_t_lo_mult0.25_knob1_kick_c0.04 | 0.29 | 1.07e+13 | 8.67e+11 | 149 | 0.0006 | 0.2174 |
| kc2c | tfinal1_t_lo_mult0.1_knob2_kick_c0.04 | 0.25 | 1.16e+13 | 8.64e+11 | 86 | 0.0006 | 0.2176 |
| kc2c | tfinal1_t_lo_mult0.1_knob1_kick_c0.08 | 0.25 | 1.33e+13 | 8.73e+11 | 135 | 0.0006 | 0.2174 |
| kc2c | tfinal1_t_lo_mult0.25_knob2_kick_c0.08 | 0.21 | 1.71e+13 | 8.67e+11 | 75 | 0.0006 | 0.2174 |
| kc2c | tfinal1_t_lo_mult0.25_knob2_kick_c0.04 | 0.17 | 1.96e+13 | 8.64e+11 | 81 | 0.0006 | 0.2174 |
| kc2c | tfinal1_t_lo_mult0.25_knob0.5_kick_c0.12 | 0.08 | 4.28e+13 | 8.89e+11 | 201 | 0.0006 | 0.2173 |
| kc2c | tfinal1_t_lo_mult0.25_knob1_kick_c0.12 | 0.08 | 4.51e+13 | 8.78e+11 | 122 | 0.0006 | 0.2173 |
| kc2c | tfinal1_t_lo_mult0.25_knob1_kick_c0.16 | 0.00 | inf | 8.82e+11 | 116 | 0.0006 | 0.2173 |
| kc2c | tfinal1_t_lo_mult0.25_knob0.5_kick_c0.16 | 0.00 | inf | 8.96e+11 | 187 | 0.0006 | 0.2173 |
| none_B1 | knob0.5_t_hi_mult2_t_lo_mult0.5 | 0.38 | 4.58e+12 | 7.95e+11 | 0 | 0.0000 | 0.2182 |
| none_B1 | knob0.25_t_hi_mult1_t_lo_mult0.5 | 0.21 | 5.02e+12 | 7.95e+11 | 0 | 0.0000 | 0.2185 |
| none_B1 | knob0.5_t_hi_mult3_t_lo_mult0.5 | 0.25 | 7.27e+12 | 7.95e+11 | 0 | 0.0000 | 0.2181 |
| none_B1 | knob0.5_t_hi_mult2_t_lo_mult1 | 0.29 | 7.55e+12 | 7.96e+11 | 0 | 0.0000 | 0.2178 |
| none_B1 | knob0.5_t_hi_mult2_t_lo_mult0.25 | 0.21 | 7.61e+12 | 7.96e+11 | 0 | 0.0000 | 0.2180 |
| none_B1 | knob0.25_t_hi_mult2_t_lo_mult0.5 | 0.12 | 8.17e+12 | 7.95e+11 | 0 | 0.0000 | 0.2184 |
| none_B1 | knob0.5_t_hi_mult1_t_lo_mult0.5 | 0.21 | 8.83e+12 | 7.96e+11 | 0 | 0.0000 | 0.2179 |
| none_B1 | knob0.5_t_hi_mult4_t_lo_mult1 | 0.21 | 1.1e+13 | 7.96e+11 | 0 | 0.0000 | 0.2179 |
| none_B1 | knob0.5_t_hi_mult4_t_lo_mult0.5 | 0.17 | 1.11e+13 | 7.96e+11 | 0 | 0.0000 | 0.2178 |
| none_B1 | knob0.25_t_hi_mult2_t_lo_mult0.25 | 0.08 | 1.11e+13 | 7.96e+11 | 0 | 0.0000 | 0.2178 |
| none_B1 | knob0.5_t_hi_mult3_t_lo_mult1 | 0.21 | 1.11e+13 | 7.96e+11 | 0 | 0.0000 | 0.2177 |
| none_B1 | knob0.5_t_hi_mult1_t_lo_mult1 | 0.21 | 1.13e+13 | 7.96e+11 | 0 | 0.0000 | 0.2177 |
| none_B1 | knob0.5_t_hi_mult1_t_lo_mult0.25 | 0.12 | 1.33e+13 | 7.96e+11 | 0 | 0.0000 | 0.2180 |
| none_B1 | knob0.25_t_hi_mult2_t_lo_mult1 | 0.08 | 1.63e+13 | 7.96e+11 | 0 | 0.0000 | 0.2180 |
| none_B1 | knob0.25_t_hi_mult1_t_lo_mult0.25 | 0.04 | 2.07e+13 | 7.96e+11 | 0 | 0.0000 | 0.2178 |
| none_B1 | knob0.25_t_hi_mult1_t_lo_mult1 | 0.04 | 3.79e+13 | 7.95e+11 | 0 | 0.0000 | 0.2181 |
| ours | kick_c0.04_knob0.125 | 0.75 | 9.35e+11 | 7.32e+11 | 639 | 0.0009 | 0.0006 |
| ours | kick_c0_knob0.0625 | 0.79 | 1.01e+12 | 7.34e+11 | 1356 | 0.0009 | 0.0006 |
| ours | kick_c0_knob0.125 | 0.75 | 1.32e+12 | 7.25e+11 | 991 | 0.0009 | 0.0006 |
| ours | kick_c0_knob0.25 | 0.83 | 1.4e+12 | 7.17e+11 | 665 | 0.0009 | 0.0006 |
| ours | kick_c0.04_knob0.25 | 0.79 | 1.54e+12 | 7.24e+11 | 467 | 0.0009 | 0.0006 |
| ours | kick_c0.04_knob0.5 | 0.75 | 2.13e+12 | 7.17e+11 | 321 | 0.0009 | 0.0006 |
| ours | kick_c0.08_knob0.25 | 0.54 | 2.28e+12 | 7.3e+11 | 310 | 0.0009 | 0.0006 |
| ours | kick_c0.08_knob0.5 | 0.62 | 2.35e+12 | 7.23e+11 | 226 | 0.0009 | 0.0006 |
| ours | kick_c0.04_knob0.0625 | 0.46 | 2.59e+12 | 7.42e+11 | 858 | 0.0009 | 0.0006 |
| ours | kick_c0.08_knob1 | 0.62 | 2.82e+12 | 7.17e+11 | 157 | 0.0009 | 0.0006 |
| ours | kick_c0.04_knob1 | 0.62 | 3.02e+12 | 7.12e+11 | 201 | 0.0009 | 0.0006 |
| ours | kick_c0.16_knob0.25 | 0.12 | 4.39e+12 | 7.4e+11 | 213 | 0.0009 | 0.0006 |
| ours | kick_c0_knob0.5 | 0.38 | 5.91e+12 | 7.12e+11 | 409 | 0.0009 | 0.0006 |
| ours | kick_c0_knob1 | 0.29 | 7.57e+12 | 7.08e+11 | 236 | 0.0009 | 0.0006 |
| ours | kick_c0.16_knob1 | 0.08 | 1.15e+13 | 7.23e+11 | 116 | 0.0009 | 0.0006 |
| ours | ours_ref_H8 | 0.21 | 1.29e+13 | 7.05e+11 | 130 | 0.0009 | 0.0006 |
| ours | kick_c0.16_knob0.5 | 0.12 | 2.4e+13 | 7.31e+11 | 159 | 0.0009 | 0.0006 |

## Contrasts of the selected configurations (ratio < 1 favours the first)

| contrast | ETS ratio [95 % CI] | d success [95 % CI] |
|---|---|---|
| ours selected (kick_c0_knob0.25) vs ours H8 reference (L=10, K=2n): the energy cost / gain of the retune | 0.109 [0, 0.241] | +0.62 [+0.33, +0.88] |
| ours selected vs B3 selected (knob1_t_hi_mult1.5_t_lo_mult0.0625) | 1.49 [0.473, 2.93] | +0.12 [-0.12, +0.42] |
| ours selected vs B3 H8 reference | 0.922 [0.33, 1.3] | +0.04 [-0.12, +0.25] |
| B3 selected vs B3 H8 reference (retune effect on B3) | 0.619 [0.292, 1.26] | -0.08 [-0.29, +0.12] |
| ours selected vs ours_kc2c selected (tfinal1_t_lo_mult0.25_knob1_kick_c0.08) | 0.217 [0.0389, 0.417] | +0.38 [+0.12, +0.67] |
| ours selected vs ours_none selected (knob0.5_t_hi_mult2_t_lo_mult0.5; priced as ours hardware) | 0.305 [0.0674, 0.528] | +0.46 [+0.21, +0.71] |

## ETS-selected variant (lowest ETS99 per arm among its configurations; same-data selection bias for every arm)

| arm | config | success | ETS99 (fJ) |
|---|---|---|---|
| B3 | knob1_t_hi_mult1.5_t_lo_mult0.015625 | 0.25 | 8.65e+11 |
| kc2c | tfinal1_t_lo_mult0.1_knob2_kick_c0.08 | 0.46 | 5.94e+12 |
| none_B1 | knob0.5_t_hi_mult2_t_lo_mult0.5 | 0.38 | 4.58e+12 |
| ours | kick_c0.04_knob0.125 | 0.75 | 9.35e+11 |

| contrast | ETS ratio [95 % CI] | d success [95 % CI] |
|---|---|---|
| ours (ETS-selected) vs B3 (ETS-selected) | 1.08 [0.207, 2.51] | +0.50 [+0.29, +0.71] |
| ours (ETS-selected) vs B3 H8 reference | 0.617 [0.235, 1.47] | -0.04 [-0.25, +0.21] |
