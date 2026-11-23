# BEOL Ferroelectric CiM Ising Machine for Simulated Bifurcation (arXiv 2512.17165v1, 19 Dec 2025)

Authors: Qian, Vardar, Seidel, Lehninger, Lederer, Shi, Zhuo, Ni, Kampfe, Yin (ZJU / Fraunhofer IPMS / Notre Dame). Read 15 Nov 2026 via alphaXiv (main text + first Supplement pages; no energy/area tables in the available pages) (P0.08).

## Architecture
- Chip: 32 x 256 FeFET CiM array (8 kb), FeFET = BEOL MFM capacitor (TiN/HfxZr1-xO2 10 nm/TiN on M4) on a front-end Si transistor, 180 nm CMOS platform. (Main, Fig. 2; Methods)
- Cell stores 1 bit of J; an N x N matrix with m-bit quantisation needs N x (N*m) cells; MUX -> ADC -> shift-and-add. ADC bits and shift-add width: not published in available pages. (Main, Fig. 2j,k)
- Operations: VMM (E = JX, X in {1,-1}) and VMV (E = X^T J Y, 1/0). Single FeFET computes x*J*y. (Main)
- Programming: +4 V / -4 V, 1 us gate pulses for J = 1 / 0 (same as Yin 2024). Measurement via NI PXIe SMU; board with ESP32 control, 5 V level shifters. (Main; SI Sec. 3.1)
- Algorithm: attention-inspired initialisation (scores S_i = Q_i^T K V_i via CiM, spin = sign(S_i - mean S)) then "light SB": ternary X, Y in {-1,0,1}, cubic term removed; Y = Y - K X^3 -(D-p)X + zJX (conventional), X = X + D Y. Ternary quantisation costs < 5 % cut quality alone (SI Fig. S1: normalised cut 0.995 at interval 1/64 to 0.954 at interval 1; SA baseline 0.904 on K2000). (Main Eq. 4-5, SI Sec. 1.2)

## Numbers
| Item | Value | Ref |
|---|---|---|
| Speed-up vs A6000 GPU conventional SB | 34.5-160.6x (Gset, 40 instances, 1000-7000 nodes); 19.7-175.9x (Yset, 60 instances, 10k-100k nodes) | Main Fig. 3c |
| Iteration reduction from init | 80 % (0.2x iterations) | Abstract, Fig. 1d, 3b |
| Cut improvement vs GPU SB | +0.53-6.54 % (Gset), +0.56-1.42 % (Yset) | Fig. 3d |
| Toy demo | 32-node, 10 % density, weights in {-4..4}; 5 dies; optimum within 20 iterations; <= 900 ns; 4.3-8.7 % better than SB | Fig. 4 |
| Method of "hardware" numbers | system-level model: CiM latency/energy extracted from measured prototype; digital periphery synthesised in TSMC 180 nm PDK; absolute energy/area/latency values: not published in pages read | Main, p. 14 |
| Largest FeFET array known to authors | 32 x 256 | Table 1 |

## Overlap with I7 / I10 (our ideas; see hw_phase PLAN)
- Same group and cell as Yin 2024 (B1 uses its +4/-4 V, 1 us write). Gives a second device-level data point for 1FeFET read/write numbers and linearity (10 arrays; Fig. 2i), which supports P0.07 defaults.
- It is an SB solver, not SA/MESA: no restarts, no stagnation detection, no best-so-far reload, no tabu or history/memory of visited states. The only "memory" is the initialisation from graph topology. Hence it does not pre-empt a restart/memory contribution (I7 nearby-state memory / I10), but it is a **competitor** for quality and speed claims on Gset (GPU-SB baseline, not a best-known-cut baseline).
- Quality claims are relative to their own GPU SB, not to best-known G-set cuts; no cut numbers vs best known in available pages. Do not quote 175.9x against our machine; different algorithm class and 180 nm model.
- Overlap risk: initialisation idea (topology-aware init) could be adopted by an annealer; flag as optional ablation, not part of B1.

## Missing
- Energy, area, clock, ADC bits, SB iteration counts, GPU baseline times: not published in the pages read (Supplement beyond Sec. 3.1 not retrieved).
