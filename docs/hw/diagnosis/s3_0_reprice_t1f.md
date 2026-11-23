# Stage 3.0-A: energy re-pricing screen on the stored Stage 2 records (exploratory; NOT a Stage 2 re-analysis)

t1f rows: FULL T-1 stack priced (refresh reads, screening verify/re-erase once per run, spare rows, remap + lcor tables with leakage, lcor checks per update, field registers with leakage); B3 rows use bare t1 flags, which do not touch B3 (CiM-only). Estimates flagged in arch_t.py; x2 / x0.5 rows bound them.

ETS99 ratio ours_new / comparator, nominal, p3n480 and p4n480, 64 instances x 3 seeds, H8 bootstrap B = 2000; verdict by the H8 evaluator rule WITHOUT Holm (screening). Energy per run = mean e_final.

| configuration | cell | vs B3_sel | vs B3_h8 | vs B1_sel | ours e/run (fJ) | B3_sel e/run |
|---|---|---|---|---|---|---|
| base (corrected pricing, as Stage 2) | p3n480 | 1.48 [0.95, 2.12] inconclusive | 1.23 [0.84, 1.68] inconclusive | 0.08 [0.03, 0.14] win | 8.12e+11 | 5.27e+11 |
| base (corrected pricing, as Stage 2) | p4n480 | 1.11 [0.74, 1.48] inconclusive | 0.00 [0.00, 0.00] win | 0.13 [0.07, 0.18] win | 8.42e+11 | 5.54e+11 |
| t1 incremental field | p3n480 | 0.90 [0.58, 1.29] inconclusive | 0.75 [0.51, 1.02] inconclusive | 0.05 [0.02, 0.09] win | 4.91e+11 | 5.27e+11 |
| t1 incremental field | p4n480 | 0.66 [0.44, 0.87] inconclusive | 0.00 [0.00, 0.00] win | 0.08 [0.04, 0.11] win | 4.9e+11 | 5.54e+11 |
| t2 sparse storage (ours only; B3 not offered) | p3n480 | 1.32 [0.85, 1.90] inconclusive | 1.10 [0.75, 1.50] inconclusive | 0.07 [0.02, 0.13] win | 7.25e+11 | 5.27e+11 |
| t2 sparse storage (ours only; B3 not offered) | p4n480 | 1.00 [0.67, 1.33] inconclusive | 0.00 [0.00, 0.00] win | 0.12 [0.06, 0.16] win | 7.57e+11 | 5.54e+11 |
| t3 64-row tiles | p3n480 | 1.93 [1.25, 2.77] loss | 1.61 [1.10, 2.19] loss | 0.10 [0.03, 0.18] win | 1.06e+12 | 5.27e+11 |
| t3 64-row tiles | p4n480 | 1.39 [0.93, 1.86] inconclusive | 0.00 [0.00, 0.00] win | 0.16 [0.09, 0.23] win | 1.05e+12 | 5.54e+11 |
| t4 skip read after reject | p3n480 | 1.37 [0.88, 1.96] inconclusive | 1.14 [0.77, 1.55] inconclusive | 0.07 [0.02, 0.13] win | 7.38e+11 | 5.27e+11 |
| t4 skip read after reject | p4n480 | 1.05 [0.70, 1.39] inconclusive | 0.00 [0.00, 0.00] win | 0.12 [0.07, 0.17] win | 7.68e+11 | 5.54e+11 |
| t5 overlap read with select | p3n480 | 1.27 [0.82, 1.82] inconclusive | 1.06 [0.72, 1.44] inconclusive | 0.07 [0.03, 0.13] win | 6.96e+11 | 5.27e+11 |
| t5 overlap read with select | p4n480 | 0.96 [0.64, 1.28] inconclusive | 0.00 [0.00, 0.00] win | 0.12 [0.07, 0.17] win | 7.28e+11 | 5.54e+11 |
| t6 lane clock gating, every machine | p3n480 | 1.36 [0.87, 1.95] inconclusive | 1.13 [0.77, 1.54] inconclusive | 0.08 [0.03, 0.14] win | 6.25e+11 | 4.36e+11 |
| t6 lane clock gating, every machine | p4n480 | 1.03 [0.69, 1.37] inconclusive | 0.00 [0.00, 0.00] win | 0.13 [0.07, 0.17] win | 6.51e+11 | 4.63e+11 |
| b3b idle sees SAR savings | p3n480 | 1.46 [0.94, 2.09] inconclusive | 1.22 [0.83, 1.65] inconclusive | 0.08 [0.03, 0.14] win | 8.01e+11 | 5.27e+11 |
| b3b idle sees SAR savings | p4n480 | 1.10 [0.73, 1.47] inconclusive | 0.00 [0.00, 0.00] win | 0.13 [0.07, 0.18] win | 8.33e+11 | 5.54e+11 |
| t1+t5 | p3n480 | 0.72 [0.47, 1.04] inconclusive | 0.60 [0.41, 0.82] inconclusive | 0.04 [0.01, 0.08] win | 3.97e+11 | 5.27e+11 |
| t1+t5 | p4n480 | 0.52 [0.35, 0.70] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.09] win | 3.96e+11 | 5.54e+11 |
| t1+t5+t6 (B3 also gated) | p3n480 | 0.64 [0.42, 0.92] win | 0.54 [0.36, 0.73] inconclusive | 0.04 [0.01, 0.07] win | 2.95e+11 | 4.36e+11 |
| t1+t5+t6 (B3 also gated) | p4n480 | 0.47 [0.31, 0.62] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 2.95e+11 | 4.63e+11 |
| t1+t5+t6, B3 NOT gated (fairness bound) | p3n480 | 0.54 [0.35, 0.77] win | 0.45 [0.31, 0.61] inconclusive | 0.04 [0.01, 0.07] win | 2.95e+11 | 5.27e+11 |
| t1+t5+t6, B3 NOT gated (fairness bound) | p4n480 | 0.39 [0.26, 0.52] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 2.95e+11 | 5.54e+11 |
| t1+t5+t6+b3b | p3n480 | 0.64 [0.42, 0.92] win | 0.54 [0.36, 0.73] inconclusive | 0.04 [0.01, 0.07] win | 2.95e+11 | 4.36e+11 |
| t1+t5+t6+b3b | p4n480 | 0.47 [0.31, 0.62] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 2.95e+11 | 4.63e+11 |
| t1+t2+t5+t6 (t2 ours only) | p3n480 | 0.64 [0.42, 0.92] win | 0.54 [0.36, 0.73] inconclusive | 0.04 [0.01, 0.07] win | 2.95e+11 | 4.36e+11 |
| t1+t2+t5+t6 (t2 ours only) | p4n480 | 0.47 [0.31, 0.62] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 2.95e+11 | 4.63e+11 |
| t1f full (R 100, spare 2 %, screen 1 %, k 4, est x1) | p3n480 | 1.03 [0.66, 1.47] inconclusive | 0.86 [0.58, 1.16] inconclusive | 0.05 [0.02, 0.10] win | 5.58e+11 | 5.27e+11 |
| t1f full (R 100, spare 2 %, screen 1 %, k 4, est x1) | p4n480 | 0.75 [0.50, 0.99] inconclusive | 0.00 [0.00, 0.00] win | 0.09 [0.05, 0.12] win | 5.57e+11 | 5.54e+11 |
| t1f+t5 | p3n480 | 0.83 [0.54, 1.19] inconclusive | 0.69 [0.47, 0.94] inconclusive | 0.05 [0.02, 0.09] win | 4.54e+11 | 5.27e+11 |
| t1f+t5 | p4n480 | 0.60 [0.40, 0.80] inconclusive | 0.00 [0.00, 0.00] win | 0.08 [0.04, 0.11] win | 4.52e+11 | 5.54e+11 |
| t1f+t5+t6 (B3 also gated) PRIMARY STACK | p3n480 | 0.76 [0.49, 1.10] inconclusive | 0.64 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.51e+11 | 4.36e+11 |
| t1f+t5+t6 (B3 also gated) PRIMARY STACK | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.5e+11 | 4.63e+11 |
| t1f+t5+t6, B3 NOT gated | p3n480 | 0.64 [0.42, 0.92] win | 0.53 [0.36, 0.72] inconclusive | 0.05 [0.02, 0.09] win | 3.51e+11 | 5.27e+11 |
| t1f+t5+t6, B3 NOT gated | p4n480 | 0.47 [0.31, 0.62] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.5e+11 | 5.54e+11 |
|   sens R = 25 | p3n480 | 0.79 [0.51, 1.13] inconclusive | 0.66 [0.45, 0.89] inconclusive | 0.05 [0.02, 0.09] win | 3.61e+11 | 4.36e+11 |
|   sens R = 25 | p4n480 | 0.57 [0.38, 0.76] inconclusive | 0.00 [0.00, 0.00] win | 0.08 [0.04, 0.11] win | 3.62e+11 | 4.63e+11 |
|   sens R = 50 | p3n480 | 0.77 [0.50, 1.11] inconclusive | 0.64 [0.44, 0.87] inconclusive | 0.05 [0.02, 0.09] win | 3.54e+11 | 4.36e+11 |
|   sens R = 50 | p4n480 | 0.56 [0.38, 0.75] inconclusive | 0.00 [0.00, 0.00] win | 0.08 [0.04, 0.10] win | 3.54e+11 | 4.63e+11 |
|   sens R = 200 | p3n480 | 0.76 [0.49, 1.09] inconclusive | 0.63 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.49e+11 | 4.36e+11 |
|   sens R = 200 | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.49e+11 | 4.63e+11 |
|   sens R = 1000 | p3n480 | 0.76 [0.49, 1.09] inconclusive | 0.63 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.47e+11 | 4.36e+11 |
|   sens R = 1000 | p4n480 | 0.55 [0.37, 0.73] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.47e+11 | 4.63e+11 |
|   sens no refresh (R = 0, upper bound) | p3n480 | 0.76 [0.49, 1.09] inconclusive | 0.63 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.47e+11 | 4.36e+11 |
|   sens no refresh (R = 0, upper bound) | p4n480 | 0.55 [0.37, 0.73] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.47e+11 | 4.63e+11 |
|   sens spare 0 % | p3n480 | 0.76 [0.49, 1.10] inconclusive | 0.64 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.5e+11 | 4.36e+11 |
|   sens spare 0 % | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.5e+11 | 4.63e+11 |
|   sens spare 5 % | p3n480 | 0.76 [0.50, 1.10] inconclusive | 0.64 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.51e+11 | 4.36e+11 |
|   sens spare 5 % | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.51e+11 | 4.63e+11 |
|   sens screen 3 % retired | p3n480 | 0.76 [0.49, 1.10] inconclusive | 0.64 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.51e+11 | 4.36e+11 |
|   sens screen 3 % retired | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.5e+11 | 4.63e+11 |
|   sens lcor k = 16 | p3n480 | 1.08 [0.70, 1.55] inconclusive | 0.90 [0.61, 1.22] inconclusive | 0.07 [0.02, 0.12] win | 4.95e+11 | 4.36e+11 |
|   sens lcor k = 16 | p4n480 | 0.78 [0.52, 1.04] inconclusive | 0.00 [0.00, 0.00] win | 0.11 [0.06, 0.14] win | 4.94e+11 | 4.63e+11 |
|   sens T-1 estimates x2 | p3n480 | 0.90 [0.58, 1.29] inconclusive | 0.75 [0.51, 1.02] inconclusive | 0.06 [0.02, 0.10] win | 4.13e+11 | 4.36e+11 |
|   sens T-1 estimates x2 | p4n480 | 0.65 [0.44, 0.87] inconclusive | 0.00 [0.00, 0.00] win | 0.09 [0.05, 0.12] win | 4.13e+11 | 4.63e+11 |
|   sens T-1 estimates x0.5 | p3n480 | 0.69 [0.45, 1.00] win | 0.58 [0.39, 0.79] inconclusive | 0.04 [0.01, 0.08] win | 3.19e+11 | 4.36e+11 |
|   sens T-1 estimates x0.5 | p4n480 | 0.50 [0.34, 0.67] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.09] win | 3.19e+11 | 4.63e+11 |
|   sens screening amortised over 10 runs | p3n480 | 0.76 [0.49, 1.10] inconclusive | 0.64 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.51e+11 | 4.36e+11 |
|   sens screening amortised over 10 runs | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.5e+11 | 4.63e+11 |
