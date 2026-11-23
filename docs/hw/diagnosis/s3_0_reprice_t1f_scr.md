# Stage 3.0-A: energy re-pricing screen on the stored Stage 2 records (exploratory; NOT a Stage 2 re-analysis)

t1f rows: FULL T-1 stack priced (refresh reads, screening verify/re-erase once per run, spare rows, remap + lcor tables with leakage, lcor checks per update, field registers with leakage); B3 rows use bare t1 flags, which do not touch B3 (CiM-only). Estimates flagged in arch_t.py; x2 / x0.5 rows bound them.

ETS99 ratio ours_new / comparator, nominal, p3n480 and p4n480, 64 instances x 3 seeds, H8 bootstrap B = 2000; verdict by the H8 evaluator rule WITHOUT Holm (screening). Energy per run = mean e_final.

| configuration | cell | vs B3_sel | vs B3_h8 | vs B1_sel | ours e/run (fJ) | B3_sel e/run |
|---|---|---|---|---|---|---|
| t1f full (R 100, spare 2 %, screen 1 %, k 4, est x1) | p3n480 | 1.03 [0.66, 1.47] inconclusive | 0.86 [0.58, 1.16] inconclusive | 0.05 [0.02, 0.10] win | 5.58e+11 | 5.27e+11 |
| t1f full (R 100, spare 2 %, screen 1 %, k 4, est x1) | p4n480 | 0.75 [0.50, 0.99] inconclusive | 0.00 [0.00, 0.00] win | 0.09 [0.05, 0.12] win | 5.57e+11 | 5.54e+11 |
|   sens screen 3 % retired | p3n480 | 0.76 [0.49, 1.10] inconclusive | 0.64 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.51e+11 | 4.36e+11 |
|   sens screen 3 % retired | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.5e+11 | 4.63e+11 |
|   sens screening amortised over 10 runs | p3n480 | 0.76 [0.49, 1.10] inconclusive | 0.64 [0.43, 0.86] inconclusive | 0.05 [0.02, 0.09] win | 3.51e+11 | 4.36e+11 |
|   sens screening amortised over 10 runs | p4n480 | 0.55 [0.37, 0.74] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.10] win | 3.5e+11 | 4.63e+11 |
| t1f screening-only (k 0) | p3n480 | 0.92 [0.60, 1.32] inconclusive | 0.77 [0.52, 1.04] inconclusive | 0.05 [0.02, 0.09] win | 5e+11 | 5.27e+11 |
| t1f screening-only (k 0) | p4n480 | 0.67 [0.45, 0.89] inconclusive | 0.00 [0.00, 0.00] win | 0.08 [0.04, 0.11] win | 4.99e+11 | 5.54e+11 |
| t1f screening-only (k 0)+t5+t6 (B3 also gated) CANDIDATE PRIMARY | p3n480 | 0.66 [0.43, 0.95] win | 0.55 [0.37, 0.75] inconclusive | 0.04 [0.01, 0.07] win | 3.03e+11 | 4.36e+11 |
| t1f screening-only (k 0)+t5+t6 (B3 also gated) CANDIDATE PRIMARY | p4n480 | 0.48 [0.32, 0.64] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 3.03e+11 | 4.63e+11 |
| t1f screening-only (k 0)+t5+t6, B3 NOT gated | p3n480 | 0.55 [0.36, 0.79] win | 0.46 [0.31, 0.63] inconclusive | 0.04 [0.01, 0.07] win | 3.03e+11 | 5.27e+11 |
| t1f screening-only (k 0)+t5+t6, B3 NOT gated | p4n480 | 0.40 [0.27, 0.54] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 3.03e+11 | 5.54e+11 |
|   scr-only sens R = 25 | p3n480 | 0.68 [0.44, 0.98] win | 0.57 [0.39, 0.77] inconclusive | 0.04 [0.01, 0.08] win | 3.12e+11 | 4.36e+11 |
|   scr-only sens R = 25 | p4n480 | 0.49 [0.33, 0.66] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.09] win | 3.13e+11 | 4.63e+11 |
|   scr-only sens screen 3 % retired | p3n480 | 0.66 [0.43, 0.95] win | 0.55 [0.37, 0.75] inconclusive | 0.04 [0.01, 0.07] win | 3.03e+11 | 4.36e+11 |
|   scr-only sens screen 3 % retired | p4n480 | 0.48 [0.32, 0.64] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 3.03e+11 | 4.63e+11 |
|   scr-only sens T-1 estimates x2 | p3n480 | 0.69 [0.45, 0.99] win | 0.58 [0.39, 0.78] inconclusive | 0.04 [0.01, 0.08] win | 3.17e+11 | 4.36e+11 |
|   scr-only sens T-1 estimates x2 | p4n480 | 0.50 [0.34, 0.67] inconclusive | 0.00 [0.00, 0.00] win | 0.07 [0.04, 0.09] win | 3.17e+11 | 4.63e+11 |
|   scr-only sens T-1 estimates x0.5 | p3n480 | 0.64 [0.42, 0.92] win | 0.54 [0.36, 0.73] inconclusive | 0.04 [0.01, 0.07] win | 2.95e+11 | 4.36e+11 |
|   scr-only sens T-1 estimates x0.5 | p4n480 | 0.47 [0.31, 0.62] inconclusive | 0.00 [0.00, 0.00] win | 0.06 [0.03, 0.09] win | 2.95e+11 | 4.63e+11 |
