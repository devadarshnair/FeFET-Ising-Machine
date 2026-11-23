# Format of `circuit/tcam/char_v0.csv` (TCAM word characterisation, v0)

Purpose: give the RTL stand-in TCAM (`rtl/`) latency, energy and count-error numbers taken from the
transistor-level simulation, instead of numbers typed in by hand.

Written by `circuit/tcam/check_t3d.py` from the Monte Carlo runs of test 3d (25 decks × 8 samples ×
9 counts, seed 20261031; each deck reports ngspice `meas` values, no waveforms). Plain CSV, comma
separated, one header row, no comment lines, one row per mismatch count. `inf` and `nan` are written
as those words (count 0 has no discharge).

## What one row describes

One search of one **8-cell word** (one sub-match-line) of 2-FeFET cells (set-C FeFET, stand-in
45 nm MOSFETs), with a binary key that has `count` mismatching cells and 8 − `count` matching cells.
Monte Carlo over FeFET threshold variation: every FeFET gets an independent gate-referred V_th shift,
σ = 0.10 V for low-V_th FeFETs and 0.15 V for high-V_th FeFETs (Ni 2019 SI Fig. 5).
Fixed conditions (see `circuit/tcam/tcam_build.py`, `make_tcam.py`): VDD = 1.0 V, search lines at
V_S = 1.1 V, ML precharged for 0.8 ns, evaluation window 2.8 ns, wire parasitics 3.2 Ω + 0.1 fF per
cell on ML and 0.1 fF per search line, room temperature, nominal MOSFETs.

The count is read from the time the sense-amplifier output switches after the search-line edge:
count 0 = no switch inside the window; between counts m and m+1 the boundary sits where the two
fitted log-normal time distributions are equally many standard deviations away.

## Columns

| Column | Unit | Meaning |
|---|---|---|
| `count` | – | true number of mismatching cells, 0 … 8 |
| `n_mc` | – | Monte Carlo samples for this count |
| `t_mean_ps` | ps | mean discharge time (search-line input edge to SA output at VDD/2); `inf` for count 0 |
| `t_sigma_ps` | ps | standard deviation of the discharge time (`nan` for count 0) |
| `t_p01_ps`, `t_p99_ps` | ps | 1st and 99th percentile of the discharge time |
| `e_mean_fJ`, `e_sigma_fJ` | fJ | energy of one search cycle (precharge + evaluate) for the whole word: VDD (precharge, SA) plus the search-line supply, for this row only |
| `p_err_emp` | – | fraction of samples read as a different count |
| `p_err_gauss` | – | the same, estimated from the fitted log-normal (resolves rates below 1/n_mc) |
| `p_read_low`, `p_read_high` | – | empirical fraction read as a lower / higher count |
| `t_bound_fast_ps` | ps | a discharge faster than this is read as count + 1 (0 for count 8; for count 0: the window length, below which any switch is read as ≥ 1) |
| `t_bound_slow_ps` | ps | a discharge slower than this is read as count − 1 (`inf` for count 0) |

## How the RTL stand-in should use it

- Latency of a search: the evaluation window (2.8 ns) plus precharge (0.8 ns) and margins, i.e. the
  cycle length of the testbench (4.0 ns), not the per-count discharge time, because the count can
  only be read after the slowest level's boundary has passed.
- Energy per search of a 64-cell segment built as eight 8-cell sub-words: sum the eight sub-word
  energies for their counts.
- Count errors: draw the read count from (`p_read_low`, 1 − `p_err_emp`, `p_read_high`) per
  sub-word (errors are almost always ±1). For a 64-cell segment of eight sub-words the segment
  count is the sum of eight sub-word reads. This assumes sub-word errors are independent.
- A 64-cell single match line (test 3c) is **not** described by this table; see
  `docs/device/STATUS.md` for why it is not the recommended segment.

## Version

v0, 31 Oct 2026. Every number depends on uncalibrated stand-in MOSFET cards and the set-C fit;
treat them as order-of-magnitude until a real PDK card is used.
