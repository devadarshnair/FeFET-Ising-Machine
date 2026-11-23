# Yin 2024 (Nat. Commun. 15:2419) B1 parameter sheet

Sources: main text via PMC10948773 (WebFetch extraction); Supplementary Information PDF
(41467_2024_46640_MOESM1_ESM.pdf, 17 pages, text read with mutool). Read 15 Nov 2026 (P0.07).
Labels: [FT] = found in text, with ref; [U] = not published, literature/engineering default chosen with its source.
Main text: "Main"; Supplement: "SI". The Supplement contains NO MESA numeric parameters (Count_max, T0, cooling) and no numeric Fig. S7 values (plots only).

| # | Parameter | Value | Label | Source / default rationale |
|---|---|---|---|---|
| 1 | Array size | 32 x 32 (1 kb) FeFET macro | [FT] | Main Results (1FeFET1R), Fig. 2b; SI Sec. 3 ("1kb (32x32)") |
| 2 | Cell | 1FeFET1R (1 FeFET + series resistor) | [FT] | Main Fig. 2g |
| 3 | Series resistor | 1 MOhm, integrated MOSFET-based | [FT] | Main Fig. 2h caption / Results |
| 4 | Technology | 28 nm HKMG FeFET; TiN/doped HfO2 (8 nm)/SiO2 (1 nm); RTA ~1000 C | [FT] | Main Methods |
| 5 | ON/OFF ratio | >1000 for 1FeFET1R | [FT] | Main Results |
| 6 | Write voltage / pulse | +4 V / -4 V gate pulses, 1 us | [FT] | Main Fig. 2e discussion |
| 7 | Write-disturb scheme | V_W/3 inhibit | [FT] | Main Results (ref. 46 there) |
| 8 | Read gate (WL) voltage | 1.2 V for logic 1, 0 V for 0 | [FT] | SI Sec. 3 ("0V and 1.2V ... read phase") |
| 9 | Read bitline voltage | 0.1 V | [FT] | SI Sec. 3 ("designated bitline voltage of 0.1V") |
| 10 | Read V quoted in intro comparison | V_read 1 V (write/read 4/1 V, t_write ~10 ns generic FeFET) | [FT] | Main Introduction; differs from #8 (generic comparison, not the array bias) |
| 11 | Retention | stable up to 1e5 s | [FT] | Main; SI Fig. S5c |
| 12 | Read cycle | whole x^T Q y obtained in a single read cycle; external load clock <= 50 MHz | [FT] | SI Sec. 3 |
| 13 | Weight precision, demo | ternary Q, 2 FeFET per element, no ADC / shift-add needed | [FT] | SI Sec. 3; Main Fig. 4 text |
| 14 | ADC bits | not published; general statement only that higher weight precision needs higher ADC resolution | [U] | SI Sec. 6 text near Fig. S9. Default: ADC bits = weight bits + ceil(log2(32)) = m+5 at full-column sum; reduced to 8 b if m<=3 (own design choice; source: standard CiM sizing, mark as ours) |
| 15 | Shift-add width | not published | [U] | Default: m + ceil(log2 N) bits accumulate (own design) |
| 16 | Coupling bits (M) | M-bit in M cells, M unspecified in main; PFP study (323=17x19, 10 vars) shows 5-bit sufficient, 3/7/9-bit compared | [FT]/[U] | SI Sec. 6, Fig. S8c; Fig. S9. Default for Max-Cut: 3-bit (hardware in 2512.17165 uses thermometer-coded weights in +-4 -> 3-4 bit; see bfe_cim file) |
| 17 | Count_max | referenced as Count_max^max (Count_max period of stagnant energy ends an epoch); numeric value not stated | [U] | Main Results. Default Count_max = 2n steps (matches the reference software study Kc2 schedule; our choice, flagged) |
| 18 | Epoch end / stall criterion | energy stagnant for Count_max period -> epoch ends, temperature reset | [FT] | Main Results (MESA description) |
| 19 | Cooling function | not stated | [U] | Default: geometric (exponential) cooling per epoch; Aramon 2019 App. A finds linear-in-1/T better for DA (second option). Pick geometric, ablate |
| 20 | T0 (initial temperature) | not stated | [U] | Default: set so initial acceptance ~0.6-0.8 (Aramon App. A rule: Th from 80-85th percentile of |dE| distribution) |
| 21 | Perturbation size | "flipping a few bits" (number not stated) | [U] | Main Results. Default 3 bit flips (own choice) |
| 22 | Iteration counts (per epoch / total) | not stated numerically; Fig. S7a x-axis runs to ~1200 iterations, Fig. S10 shows optimum within 100 iterations (toy graph coloring), Fig. 4i curves | [FT-fig]/[U] | SI Fig. S7a, Fig. S10 text ("within 100 iterations") |
| 23 | Acceptance rule | Metropolis-type probability tied to T | [FT] | Main Results |
| 24 | RNG location | not stated | [U] | Default: off-array digital LFSR in controller (Aramon: DA uses on-chip Mersenne-twister-like RNG) |
| 25 | Max-Cut instances | 30 problems, 800-3000 nodes; Stanford Gset collection (ref. 49); individual IDs not stated | [FT]/[U] | Main Fig. 4b caption and text. SI Fig. S7: "Gset1 (800 node Max-Cut)" = G1-G5 class, exact ID not stated. Default: G1-G5, G22-G26 ... pick 30 by node count 800-3000 and state as inferred |
| 26 | Fig. S7 comparison | MESA vs conventional SA, 800-node Max-Cut: MESA reaches 100% solved with iteration count; SA stays 0% until ~1000 iterations, ends at 90%; no numeric time given | [FT-fig] | SI Fig. S7a,b and text, p. 11 |
| 27 | "+27 %" definition | "up to 27 % improvement in cut value for 3000-node problems"; baseline/formula not given in text (baseline = SA, inferred from figure 4b context) | [FT]/[U] | Main Results Fig. 4b text; abstract "up to 27 % better solution" |
| 28 | "~2x speed-up" definition | from Fig. S7 (success rate / time-to-solution of MESA vs SA); no numeric TTS | [FT-fig] | Abstract; SI Fig. S7 |
| 29 | Compression results | 75 % chip-size saving (Max-Cut); 71.88 % sparsity reduction and 84.38 % chip area saving for PFP example; 1.84x for toy graph colouring | [FT] | Abstract; SI Sec. 4 text near Fig. S6c; Main Fig. 4c |
| 30 | QUBO sparsity | >85 % zeros typical | [FT] | Main Results |
| 31 | Measurement counts | 3 dies; 9 repeated runs on one die (Fig. 4i); 20 arrays for column-current linearity (Fig. 2k); 64 devices I-V | [FT] | Main |
| 32 | Energy / time absolute | none published in main text (no J, no seconds) | [FT: absent] | Main. R2 target waived (IMPL_PLAN P3.xx note): label B1 "literature-parameterised" |
| 33 | Data / code | Zenodo 10.5281/zenodo.10697395, 10.5281/zenodo.10697394 | [FT] | Main Data/Code availability (not downloaded) |
| 34 | Prime-factorisation example | 323 = 17x19, 10 input variables, 5-bit QUBO coefficients | [FT] | SI Sec. 6, Fig. S8 |
| 35 | Graph-colouring demo | 7 nodes, 3 colours, 21x21 -> 16x15 compressed, mapped to 32x15 array; solved within 100 iterations on 3 prototypes | [FT] | Main Fig. 4c,f; SI Fig. S10 |

## R1 interpretation choices (max 3)
1. **Count_max**: not published. Choose 2n stagnant iterations (n = spin count; matches the reference software study Kc2 restart schedule so MESA and Kc2 are comparable); sensitivity runs at n and 4n.
2. **Stall criterion**: "energy stays stagnant for Count_max" read as: no strict improvement of best-so-far energy for Count_max consecutive iterations (not "no change in current energy"); on stall, reload best state and reset T to T0.
3. **RNG location**: off-array digital LFSR in the controller (not published); noise is not drawn from device variation.

## Notes for review
- Main-text figures were obtained through a text-extraction of PMC HTML; the SI numbers (rows 8, 9, 12, 13, 26, 29, 34, 35) come directly from the SI PDF text. Rows 1-7, 10, 11, 25, 27, 28, 30, 31 rely on the PMC extraction and should be spot-checked in the PDF (5-row spot check planned).
- Technology node row 4 (28 nm) comes from the PMC Methods extraction; the 2512.17165 paper uses a different (180 nm BEOL) chip.
