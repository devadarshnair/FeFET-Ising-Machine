# Aramon et al. 2019 (arXiv 1806.08815v3): Fujitsu Digital Annealer sheet (B3)

Source: arXiv 1806.08815v3 (Front. Phys. 2019), read 15 Nov 2026 via alphaXiv page text (P0.08). Section/figure refs are the paper's.

## Hardware (Sec. I, Sec. II.D)
| Item | Value | Ref |
|---|---|---|
| Max variables, gen 1 | 1024, fully connected QUBO | Abstract, Sec. I |
| Precision, gen 1 | 26-bit biases, 16-bit couplers (fixed) | Sec. I; also Sec. V: max coefficients 2^25-1 (linear), 2^15-1 (quadratic) |
| Precision, gen 2 prototype | 64-bit both | Sec. VI.B |
| Next gen | up to 8192 variables, faster anneal, PT swaps on hardware | Abstract, Sec. II.D |
| Time per iteration | each MC step takes same time whether flip accepted or not; anneal time independent of N and density; absolute ns/iteration: not published | Sec. II.B, VI.B |
| RNG | twisted generalized feedback shift register, period 2^19937 | Sec. II.B |

## Algorithm 2 (transcribed, Sec. II.B)
1. initial state <- an arbitrary state (same for all runs; 100 runs each starting at vector of zeros in the benchmark, App. A)
2. for each run: initialise to initial state; E_offset <- 0
3. for each MC step (iteration):
   - if due for temperature update, update temperature (benchmark: after every iteration, App. A)
   - for each variable j in parallel: propose flip using dE_j - E_offset (Metropolis); record if accepted
   - if at least one accepted: choose one uniformly at random, apply, update state and effective fields in parallel, **E_offset <- 0** (reset rule)
   - else: **E_offset <- E_offset + offset increase rate** (dynamic escape)
- Parallel trial: P_p = 1 - prod_i(1 - A(dE_i,T)), A = exp(-dE_i/T) (Eq. 2). At low T, P_p ~ sum_i A, i.e. up to factor N boost over single trial P_s = (1/N) sum_i A (Sec. III, Fig. 2).
- Offset increase rate value: **not published**. App. A states the DA was best with the dynamic offset **turned OFF** for the spin-glass benchmark ("indifferent to the dynamic offset").
- T schedule: **linear in inverse temperature**, updated every iteration; linear-in-1/T found better than exponential (App. A). Th/Tl from Table I (unitless):
  - DA: 2D-bimodal 2 / 0.66; 2D-Gaussian 2e4 / 4e2; SK-bimodal 40 / 4; SK-Gaussian 2e5 / 1e4 (App. A Table I).
  - Rule for choosing: Tl near 5th-10th percentile, Th near 80th-85th percentile of the |dE| distribution of proposed moves (App. A).
- Runs: 100 runs per instance; iterations 1e7 (up to 1e8 for 2D-Gaussian N>=400); one sweep = N iterations (Sec. IV).

## Numeric calibration targets (at least 3)
| # | Target | Value | Ref |
|---|---|---|---|
| C1 | DA TTS speedup over single-core SA and PT on fully connected SK (bimodal and Gaussian), largest sizes | "at least two orders of magnitude", constant, no strong scaling advantage | Abstract; Sec. VI.B, Figs. 7a, 8 (values read from log-plots only; no table) |
| C2 | TTS80 scaling exponent beta (y = 10^(alpha+beta N)) | DA 0.0021(7) bimodal, 0.0019(3) Gaussian; SA 0.0027(6), 0.0028(5) | Sec. VI.B "The DA versus SA" |
| C3 | 2D-bimodal N=1024: DA higher success prob than SA in 52 of 100 instances (10^4 sweeps SA, 1e7 iterations DA) | 52/100 | Fig. 4b, Sec. VI.A |
| C4 | Parallel-trial acceptance boost at low T | factor ~N (all classes except 2D-bimodal) | Sec. III, Fig. 2 |
| C5 | Instance sets | 9 sizes, 64 to 1024, 100 random instances each; SK-bimodal/Gaussian, 2D torus bimodal/Gaussian (couplings sigma=1 scaled 1e5) | Sec. V |
| C6 | TTS definition | R99 = ln(1-0.99)/ln(1-p), TTS = R99 * time per run, bootstrapped (B=5000) percentiles TTS50, TTS80 | Sec. IV, Alg. 4 |
- Max-Cut TTS: **none** reported in this paper (only spin-glass classes). 2D/3D: only **2D** spin glass is benchmarked; 3D spin glass **none**. DA shows no speedup for sparse 2D (Sec. VI.A, Fig. 3).
- Absolute TTS numbers (seconds) are given only graphically (Figs. 3, 7, 8); not extractable as exact values from the text.

## Interpretation notes for B3
- B3 = our golden machine configured as DA: parallel-trial acceptance, E_offset rule as above (offset rate [U]: default off, matching the paper's final benchmark; a second arm with small positive rate is an ablation), linear-in-1/T schedule, 16-bit coupler quantisation, same start state.
