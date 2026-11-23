# P4.08: level-0 spread applies to every CiM design (P4_CHECK M2)

Label: analytic, model-level (not a registered study; no design change made). Source rows: circuit/cim/cim_cell_v1.csv
(hw/p1-device 7750dff): level 0 mu 0.059 nA, **sigma 4.86 nA**; level 7 99.15 nA, sigma 0.15 nA; 3-bit step 14.16 nA.
Code: scripts/baselines/level0_variation.py (seconds, no RNG) -> docs/hw/results/P4_level0_variation.csv.
Method: CLT normal sum of independent cell currents per column; a column code is wrong iff |sum error| > half a code
step. Two level-0 models: `gauss` N(mu0, sigma0) and `rect` max(0, N) (the P4.06 stand-in; its +1.9 nA/cell excess bias
depends on how many zero cells are active, so it cannot be trimmed by a fixed offset). `L` = active (x_j = 1) cells that
hold level 0 in one column. "Verified" level 0 = uniform within +-5 % of the code step around 0 (the t4a window; a real
"target 0" verify is a deep-erase-below-threshold check, so this is a model).

## (a) Ours: binary bit-planes (levels 0/7), differential P+/P- columns, full-resolution ADC (LSB = 1 cell)
P(column code wrong) / P(field sign flip at |h| = 1 cell, single plane):

| L | gauss | rect | level 0 verified |
|---|---|---|---|
| 16 | 1.1 % / 3.4 % | 4.9 % / 0.1 % | 0.0015 % / 0.09 % |
| 32 | 7.2 % / 10 % | 76 % / 1.8 % | 0.22 % / 1.5 % |
| 64 | 20 % / 18 % | ~100 % / 7.0 % | 3.0 % / 6.2 % |
| 256 | 52 % / 33 % | 100 % / 23 % | 28 % / 22 % |
| 1024 | 75 % / 41 % | 100 % / 36 % | 59 % / 35 % |

Our design is affected too. The binary unit (99 nA) gives 7x more margin than a 3-bit step, but past about 32 active
empty cells per column the count is no longer exact. A coarser ADC (LSB 2^s cells, cim_field.py) hides errors below
2^(s-1) cells and adds its own quantisation error, so the full-resolution numbers above are the strict ones.
The differential pair cancels the common mean (mostly the rect bias in the sign test) but **adds** variance (2L-1 cells).

## (b) B1 3-bit cells, Yin 32-row tile column, error iff off by >= half a level step (7.08 nA)

| f0 (share of level-0 cells) | WV 1-6, level 0 open-loop (gauss / rect) | WV 1-6, level 0 verified | open-loop 1-6 |
|---|---|---|---|
| 1/8 | 57 % / 59 % | 37 % | 96 % |
| 1/2 | 73 % / 97 % | 25 % | 95 % |
| 7/8 | 79 % / 100 % | 5.3 % | 91 % |

At this window, even verified levels 1-6 (+-5 % of up to 85 nA) are too wide for exact 32-row 3-bit sums. Verifying
level 0 helps only when most cells are empty. **B1 bit-sliced** (levels 0/7 only, 32 rows) = row L = 32 of (a): 7.2 %
(gauss) / 76 % (rect) / 0.22 % (level 0 verified) per column. Level 0 is about half of all its cells.

## (c) B2 HyCiM filter (P4.06, measured on the shared model)
57-65 % of SA-proposal decisions wrong, with or without write-verify of levels 1-4. The 1.2-2.0 % "level-0 ideal" figure
sets level-0 cells to exactly zero, so it is a **lower bound**. A verified (not ideal) level 0 would be at or above it.

## Mitigations (all available to every machine on the same terms; nothing chosen here)
| Option | Effect | Cost (shared table / cim_cell_v1) |
|---|---|---|
| Verify (deep-erase) level 0 | sigma 4.86 -> ~2.9 nA (binary, +-5 % of 99 nA) or ~0.4 nA (+-5 % of 14 nA) | attempts ~1.44 (binary window) / ~8.6 (14 nA window), if each erase redraws N(mu0, sigma0) (no erase-physics model): ~5.0 fJ, 2.9 us / ~30 fJ, 17.6 us per cell (e_write 3.32 fJ + verify read 0.15 fJ, t_write 2.02 us + 20 ns), one-time programming budget |
| Differential cancel (already in ours) | cancels the common mean only; variance x2 | 2x columns (ours already pays it) |
| Larger margin: binary cells / bit-slice | 7x larger unit than 3-bit | B1: 3x columns and ADC conversions + shift-add (priced by the same table) |
| Shorter columns / tiling (fewer active zeros per conversion) | error falls fast with L (table a) | more ADC conversions and digital adds per field |
| Gate unused / empty rows (B2 replica, zero weights) | removes their level-0 cells from the sum | row-gating logic; B2 replica redesign |

Caveats: Gaussian CLT sums; independent cells; no read noise, ADC offset or drift on top; the max(0, N) shape is a
stand-in for the real skewed erase distribution; the sign test covers one plane at the smallest field, not a full search.
