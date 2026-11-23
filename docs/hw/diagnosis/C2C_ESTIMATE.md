# C2C-share and level-0 tail: best-available ESTIMATES (until lab data arrives)

**Every number in sections 1 and 2 is an estimate, not a measurement.** No source I could read gives a table of C2C and D2D sigma for our device. The values below are reasoned brackets.
The simulations in section 3 are tuning-tag screens: p3n240, keys 2101–2112 × 3 seeds = 36 runs per point, k = 1, stand-in device model.

## 1. C2C share of sigma(Vth)^2 at the erased (level-0) state

### Evidence (what the sources actually give)
- **Manna et al., TED 2024 (arXiv 2312.15444)**, GF 28 nm HKMG, W/L = 1/1, 0.5/0.24 and 0.24/0.24 µm.
  - C2C: 50 cycles on 1 device per size. D2D: only 3 devices per size.
  - Numbers exist only in their Fig. 2 and 4 (error bands). The text says C2C is "appreciable for all devices and almost insensitive to device size", while D2D "increases drastically with scaling and dominates over C2C for highly scaled devices".
  - Their variation is largest at weak programming pulses. At strong pulses "domains switch more deterministically", and σ decays. A full −4 V reset (our level 0) is the strong-pulse limit.
  - Not digitised: I could read the text, not the figures. Uncertainty is unknown, and a 3-device D2D estimate is itself about ±50 % (1σ).
- **Phadke et al., IEDM 2025 / TED 2026** (28 nm): Vth variation is driven mainly by the *localized* FE/DE phase distribution. That distribution is fixed per device, so it acts as D2D. No share number is given.
- **Beyer et al., IMW 2020** (GF 28 nm production FeFET): a memory window of 1.4 V with state distributions "approaching 6 sigma". That implies a total σ per state of at most about 0.12 V at production size, with no split between C2C and D2D.
- **De et al. 2022**: networks tolerate up to 400 mV of C2C. That is a tolerance figure, not a measurement.
- **Li et al., Nat. Commun. 2025**: a PUF that is built on 28 nm FeFET C2C variation. C2C is therefore large enough to re-randomise a bit, but the paper (not read in full) gives no share.

### Bracket (scaled to our model: sigma_vth(0) = 0.15 V, a scaled 28 nm-class cell)
| | share | reasoning |
|---|---|---|
| low | **0.02** | Scaled device, D2D-dominant (Manna, Phadke), and a full reset is near-deterministic |
| central | **0.10** | C2C "appreciable" but dominated by D2D at scaled size: roughly a 1:3 σ ratio, i.e. 0.1 in variance |
| high | **0.30** | Large-area devices, where C2C ≈ D2D in σ (Manna 1 × 1 µm) |
A share of 0.5 or more (the H8 default) is above the high bracket.

### Update R3: values read off Manna 2024 Fig. 2 (rendered at 400 dpi, read by eye)
The ± band is the shaded 1σ at V_read 1.2 V. Uncertainty from reading the plot is about ±3 µS. D2D comes from a single pulse on each of 3 devices, so it is the total spread (D2D + C2C). Share = σ_C2C² / σ_total².
| device W/L | state | σ_C2C (µS) | σ_total (µS) | share |
|---|---|---|---|---|
| 1/1 µm | mid (G ≈ 35–55) | ≈ 10 | ≈ 8 | ≈ 1 (C2C ≥ total within error) |
| 0.5/0.24 | high (G ≈ 110–155) | ≈ 20 | ≈ 25 | ≈ 0.6 |
| 0.24/0.24 | mid (V_PRG ≈ 3.0 V) | ≈ 15 | ≈ 33 | ≈ 0.2 |
| 0.24/0.24 | high (G ≈ 55–62) | ≈ 10 | ≈ 23 | ≈ 0.19 |
| all sizes | erased (V_PRG ≤ 2.7 V, our level 0) | < 2 | < 2 | **not resolvable**: the subthreshold tail is invisible on a linear µS axis |

With only 3 devices, σ_total has a 95 % CI of about ×0.5–6, so the share for the smallest device is 0.2 with a range of about 0.01–0.8.
**Revised bracket for a scaled cell: low 0.05 / central 0.2 / high 0.6.** The earlier 0.02 / 0.10 / 0.30 bracket is superseded. 0.02 remains a stress point.
No paper I could read reports the C2C split at the erased state itself.

## 2. Level-0 read-current tail at our read bias (V_BL 0.1 V through 1 MΩ, 20 ns read)
The tail follows from σ_L0 through the SPICE transfer curve (`variation_v2.Transfer`; 2e5 draws).
| σ_L0 (V) | basis | p50 | p90 | p99 | p99.9 | max | > 8 nA |
|---|---|---|---|---|---|---|---|
| 0.10 (low) | Beyer production 6σ; Das 2026 ≤ 40 mV at the best | 0.06 nA | 0.70 | 4.9 | 18 | ON-clamped 99.5 | 0.46 % |
| 0.15 (central, model) | Ni 2019 SI, scaled devices | 0.06 | 2.3 | 33 | 99.5 | 99.5 | 4.0 % |
| 0.20 (high) | scaled, ×1.33 | 0.06 | 7.3 | 99.5 | 99.5 | 99.5 | 9.5 % |
At high σ, about 1 % of erased cells read as ON, which is a hard bit error.

## 3. Simulated success at the bracket points
Implementation: env `S0_L0_SIGMA_MULT` scales σ only for level 0 (`scripts/testing/s0_sweep.py`, `_l0_sigma`). Scripts are in `c2c_evidence/run_bracket.sh` and `summarize.py`; results in `summary.csv`.

**(a) Registered H8 stack** (ours_kc2_i11, wv+diff+cal). Ideal 0.69 [0.53, 0.82].
| σ_L0 \ share | 0.02 | 0.10 | 0.30 |
|---|---|---|---|
| 0.10 | 0.67 | 0.69 | 0.69 |
| 0.15 | 0.33 [0.20, 0.50] | 0.58 | 0.69 |
| 0.20 | **0.00** [0, 0.10] | 0.17 | 0.58 |

**(b) Stage 3 stack** (Kc2 c 0, K 0.25n, esc, incremental field R 200, screening 8 nA; wv+diff+cal+scr8). Ideal 0.83 [0.68, 0.92]. The 3.1b screen measured 0.92 on these keys under its own base configuration; here esc is on.
| σ_L0 \ share | 0.02 | 0.10 | 0.30 |
|---|---|---|---|
| all three σ_L0 | 0.83 | 0.83 | 0.83 |
All nine points equal ideal (30/36 each).

### 3c. R3 checks
- **0.83 vs 0.92 is the escape setting.** The Stage 3 stack without esc (3.1b base: c 0, K 0.25n, incremental R 200, scr8), ideal: 0.92 [0.78, 0.97], n = 36, the same keys. With esc: 0.83.
- **Sections 3(b) assumed ideal per-cell retirement.** `mit.scr` (`variation_v2.py`, `_fix_zeros`) redraws *each* leaky zero as a fresh cell, up to 3 times. That is per-cell sparing, which row spares cannot provide (A's R3-A7).
  Re-run with a realistic model: no per-cell redraw, and a per-cell correction table of k entries per column (`lcorK`: the top-k leaky zeros of each column are measured once and subtracted digitally). The measurement is assumed exact.
  | stack, σ_L0 = 0.20 V (high tail) unless stated | share 0.02 | 0.10 | 0.30 |
  |---|---|---|---|
  | Stage 3, no screening, no table | **0.00** [0, 0.10] | | |
  | Stage 3 + table k = 16 | 0.83 | 0.83 | 0.83 |
  | Stage 3 + table k = 64 | 0.83 | | |
  | Stage 3 + table k = 16, σ_L0 = 0.15 V | 0.83 | | |
  So a per-cell table of **k = 16 per 240-row column** restores ideal across the whole bracket. Without it the stack collapses at the worst point.
  This is consistent with A's sizing (2.6–51 entries per 512-row column). k = 16 per 240 rows is about 34 per 512, and the k = 64 SRAM pricing (p4 0.61) covers it.
  Caveats: 36 runs per point; p3n240 only; an exact one-time measurement of the leak is assumed. Drift of the leak after measurement is not modelled.

## 4. Reading (estimate-conditional)
- At the central estimate (share 0.1, σ 0.15 V) the H8 stack keeps 0.58 of 0.69. At the low share it drops to 0.33, and with a high tail at a low share it reaches 0.
  The H8 robustness claim therefore fails inside the literature bracket.
- The Stage 3 stack is insensitive across the whole bracket. Screening retires leaky zeros above 8 nA (0.5–10 % of cells), and the incremental single-row read is exact. That moves the dependence from the C2C share to the **spare-cell budget**, which must cover up to about 10 % of zeros at σ 0.20.
  Caveat: the screening and refresh hardware is a priced estimate, and this is one cell (p3n240) with 36 runs. A difference below about 0.2 is not resolvable.
- *Falsifiers:* a measured same-device repeat-erase σ of at least 0.7 × the population σ (share ≥ 0.5) would make (a) moot. A measured level-0 p99.9 above 99 nA in more than 10 % of cells would exceed the spare budget assumed for (b).
