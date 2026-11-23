# Stage 3.2 supplementary report-only contrasts (exploratory; added after the registered evaluator run)

B = 3000; margin -0.10 verdict class shown for orientation only (these contrasts are outside the Holm family).

| contrast (p3n480, nominal) | instances x seeds | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | verdict class |
|---|---|---|---|---|
| ours_stack vs ours_new | 64 x 3 | 0.358 [0.268, 0.466] | -0.01 [-0.11, +0.08] | inconclusive |
| ours_stack vs B1_sel | 64 x 3 | 0.042 [0.0185, 0.0653] | +0.56 [+0.45, +0.65] | win |

## Success per arm (192 / 128 / 100 runs)

| cell | arm | success | mean best_E |
|---|---|---|---|
| maxcut | B3_h8 | see Max-Cut table | -6632.3 |
| maxcut | B3_sel | see Max-Cut table | -6624.1 |
| maxcut | ours_stack | see Max-Cut table | -6597.6 |
| p3n480 | B1_sel | 0.10 (colouring) | 2.61 |
| p3n480 | B3_h8 | 0.65 (colouring) | 0.55 |
| p3n480 | B3_sel | 0.36 (colouring) | 1.12 |
| p3n480 | ours_new | 0.67 (colouring) | 0.47 |
| p3n480 | ours_stack | 0.66 (colouring) | 0.48 |
| p3n960 | B3_h8 | 0.40 (colouring) | 1.30 |
| p3n960 | B3_sel | 0.17 (colouring) | 2.07 |
| p3n960 | ours_stack | 0.20 (colouring) | 1.72 |
| p4n480 | B3_h8 | 0.00 (colouring) | 17.59 |
| p4n480 | B3_sel | 0.61 (colouring) | 0.49 |
| p4n480 | ours_stack | 0.71 (colouring) | 0.38 |

## Max-Cut success under the three rules (cut >= frac x reference; raised = reference replaced by the best cut found by any arm)

| arm | 0.99 x ref | 0.995 x ref | 0.99 x raised | mean cut / ref | runs |
|---|---|---|---|---|---|
| B3_h8 | 1.00 | 0.91 | 1.00 | 0.9969 | 100 |
| B3_sel | 1.00 | 0.63 | 1.00 | 0.9956 | 100 |
| ours_stack | 0.70 | 0.14 | 0.70 | 0.9916 | 100 |
