# Hardware prior art for a TCAM-augmented Ising machine (this project)

Notes for the RTL and circuit designers. Compiled 2026-10-30.

**Scope.** Design facts from past hardware relevant to:
- a DA-style parallel-trial annealer in Verilog;
- a transistor-level FeFET TCAM constraint pricer (MOSFETs + FeFET Verilog-A), with a visited-state TCAM kept as a negative control.

Third-party architecture simulators (CAMASim, NeuroSim, DESTINY, Eva-CAM) appear only as sources of comparison numbers, never as design-flow tools.

**How to read this.**
- Every literature fact carries a link and, where available, a section, figure, table or page.
- "Uncertain" marks facts from snippets, secondary sources, abstracts only, or internally inconsistent papers.
- "[Inference]" marks my own reasoning or arithmetic. "[PRIOR]" means the fact was verified in an earlier project note (linked) and not re-read today.
- Project files are cited by absolute path and treated as ground truth.

**Method.** Two literature surveys covered TCAM circuits and Ising-machine RTL; a third mapped `sw_ref`. We checked the load-bearing items myself:
- HyCiM §3.3, KLIMA §2.2 and Table S1;
- Zhou 2025 Eqs. 1–4 and Table 1, Narla 2024 Fig. 3;
- Aramon 2019 §II;
- `qkp_nb.py` lines 37–255 and `kernels.py` lines 115–155.

Nothing was cloned, installed or run.

**Companion notes (not repeated here).**
- [this project plan](<$PROJECT/02_research_reports/reports/this project TCAM Ising hardware plan.md>)
- [devices_models_tools.md](<$PROJECT/02_research_reports/research_notes/this project TCAM Ising hardware plan/devices_models_tools.md>) (FeFET cost tables, endurance, Verilog-A models, simulators)
- [rtl_fpga_staging.md](<$PROJECT/02_research_reports/research_notes/this project TCAM Ising hardware plan/rtl_fpga_staging.md>) (flow, benchmarking, pre-registration)
- [r3_ising_core_energy_budgets.md](<$PROJECT/02_research_reports/research_notes/TCAM hardware cost and new domains/r3_ising_core_energy_budgets.md>) (pJ/flip budgets)
- [r5_tcam_native_optimization_primitives.md](<$PROJECT/02_research_reports/research_notes/TCAM hardware cost and new domains/r5_tcam_native_optimization_primitives.md>) (HyCiM, KLIMA, SAIM full-text checks)


## 1. Summary and recommended v0 architecture

**v0 at a glance** [Inference; details in §1.2–1.6]

| Item | v0 choice |
|---|---|
| Host | DA-style parallel-trial QUBO annealer: all N flips tried per step, at most one applied. Bring-up N = 64; science configuration N = 256 (fits the D5c n = 200 instances). A Max-Cut mode is kept for the H4 control |
| Widths | P/J 8-bit signed; bias 8-bit; constraint weight 6-bit; load/C/slack 16-bit; field 18-bit signed; Q-scaled gain 24-bit |
| ΔE update | Incremental. On a flip of k, broadcast k; every lane reads its byte of the P-column memory (word k = P[:,k]) and adds ±P_ik in one cycle. The m load registers add ±w_jk. No per-step MVM |
| Acceptance | geff_i + E_off > −T·L(u_i), with L(u) ≈ −ln u from a small LUT (the DA patent's T·f⁻¹(u) form) and one multiplier per lane. Dynamic offset E_off as in the DA |
| RNG | xoshiro128\*\* per lane plus one for selection, seeded by a splitmix64 chain. Selection is an exactly uniform count-tree walk |
| Schedule | One global T register (per-step geometric, matching the golden model) or a host-loaded (T_k, N_k) staircase table |
| TCAM pricer | 2 searches per step: ADD with rows where x = 0 enabled, then REM with rows where x = 1 enabled. Each row returns a 7-bit mismatch count per 64-cell segment; a digital segment adder sums them; geff = Q·g ∓ Λ·count |
| TCAM word | Row = item. Each constraint takes Q thermometer cells of its quantised weight. v0: 8 constraints × 8 levels = 64 cells; science configuration: 16–32 constraints → 2–8 segments. Written once per instance. Queries are "0" above the slack level (ADD) or below the overload level (REM), X elsewhere |
| Controls in the same RTL | Digital-equivalent pricer (C2); exact and adaptive digital hinge (C3); TCAM off with area reallocated (C1); visited-state TCAM restart trigger vs lockout counter (H4; ternary stored rows, threshold match, written at stalls) |
| Verification | An integer golden model derived from `qkp_nb.py`, bit-exact per-step traces, scrub assertions, and a DA-transition-matrix histogram test at N ≤ 8 |

### 1.1 What the prior art says, in six lines

1. **Host.** The best-documented digital host is the Fujitsu-DA-style parallel-trial step:
   - every spin's flip is evaluated in parallel each step;
   - one accepted flip is chosen uniformly at random and applied;
   - all local fields update in constant time by broadcasting one column of J;
   - a dynamic offset E_off rises when nothing is accepted and resets on acceptance;
   - the first generation used 26-bit biases and 16-bit couplers on up to 1024 variables;
   - β rises linearly, updated every iteration;
   - parallel-tempering swaps ran on the CPU ([Aramon et al. 2019](https://arxiv.org/abs/1806.08815) §I, §II.2–II.4, Alg. 2).

   the reference software study's `qkp_nb.py` already implements exactly this step for QMdKP (§6).
2. **CAM role.** Every published CAM-in-solver writes the problem once per instance and searches it every iteration: KLIMA clauses, the HyCiM inequality filter, FeFET CiM QUBO arrays. None stores search history except IMC-MCTS (exact-match game-tree states) (§4). A write-once constraint pricer is therefore inside published practice. A visited-state TCAM is not, and the reference software study says it should only be a control.
3. **Cell and match line.** A pricer must output a mismatch **count**, not match/miss. That forces a NOR-type match line (or a current- or charge-domain count line), never NAND (§2.1). Measured multi-level Hamming sensing stops at 8 levels in an 8-cell word ([Ni 2019 SI](https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41928-019-0321-3/MediaObjects/41928_2019_321_MOESM1_ESM.pdf)). Linear counts need a clamped current or charge-domain readout (§2.4).
4. **Constraint encoding.** The pricer's thermometer code is the packet-classification "fence" encoding (DIRPE, SIGCOMM 2005): a Q-level value becomes Q cells, and a range becomes a single ternary word (§5). Our query uses only {0, X} against binary stored bits. The operation is popcount(stored AND unmasked), so stored X is needed only for the visited-state control (§5).
5. **Bit widths in practice.**

   | Design | J / coefficient | Other widths | RNG |
   |---|---|---|---|
   | Fujitsu DA v1 | 16-bit couplers | 26-bit biases | per-lane, threshold T·f⁻¹(u) from a RAM table (EP3852028) |
   | Anechoic (open RTL) | 1-bit (2/4-bit variant) | 12-bit fields, Q16.16 decision | xoshiro128\*\* per lane |
   | PoliTo dSB | 8-bit | 256 spins, 200 MHz | – |
   | Camsari p-bit FPGA | 10-bit s{6}{3} | – | 32-bit xoshiro per p-bit |
   | Pegasus 28 nm chip | 10-bit | – | LFSR |
   | DSSA / SSA / STATICA | 4-bit | – | xorshift, one bit shared per 16 spins (DSSA) |

   For energy, PRNGs dominate CAM SAT solvers: 365 fJ per draw in KLIMA, about 80% of iteration energy in XOR-CNF (§3, §4).
6. **Verification practice.** The common flow is C++/Python float model → fixed-point model → SystemVerilog → FPGA counters ([PoliTo](https://arxiv.org/html/2510.12407v2); [Niazi](https://arxiv.org/html/2303.10728v2)).
   - Two open designs show **bit-exact per-step trace equality** against a software reference, in simulation and on board: Anechoic, Oct 2026, 60/60 trials per image; tsjshg/fpga-max-cut, BSD-3 (§3).
   - No paper co-simulates a SPICE CAM inside a full Ising machine. Characterise one word in SPICE and back-annotate a behavioural block.
   - The DA's stationary distribution is not Gibbs, so statistical checks must use the exact DA transition matrix ([arXiv 2303.08392](https://arxiv.org/abs/2303.08392)).

### 1.2 Recommended v0 parameters [Inference, from §2–§6]

| Parameter | v0 bring-up | v0 science configuration | Basis |
|---|---|---|---|
| Spins / lanes N | **64** | **256** (hosts the D5c n = 200 instances) | D5c used n = 200/500 ([qhinge.py]($PROJECT/sw_ref/experiments/d5c_qhinge/qhinge.py)); PoliTo fits 256 spins on a KV260 |
| Problem modes | QMdKP (P, d, W, C) | QMdKP plus Max-Cut (J = ±1) for the H4 control | Golden models in §6 |
| Coupling P / J | 8-bit signed (P ∈ 0..100, J ∈ ±1) | same | Instance law U{1..100} ([qkp_nb.py:37–47]($PROJECT/sw_ref/experiments/d5c_qhinge/qkp_nb.py)); PoliTo 8-bit J |
| Bias d | 8-bit | same | U{1..100} |
| Constraint weight w | 6-bit unsigned (1..50) | same | U{1..50} |
| Capacity C, load, slack | 16-bit signed | same | load ≤ 256·50 = 12,800 |
| Local field h | 18-bit signed | 18-bit (20-bit for n = 500) | ≤ 100 + 100·255 = 25,600 |
| Scaled gain Q·g and geff | 24-bit signed | 24-bit | Integerisation in §1.4 |
| Constraints m | **8** | 16 and 32 | H1 held at m = 16/32 and was mixed at m = 4 (D5c erratum) |
| Levels Q | 8 | 8 and 16 | Q = 16 ties the exact hinge in 4/6 cells |
| TCAM row (per item) | **64 cells = one segment** (m·Q = 8·8) | 128–512 cells = 2–8 segments of 64 | 64 cells is the standard simulated FeFET word (TAP-CAM, Qian DATE'21, FeCAM). 128-bit words were simulated with degraded precision (Narla 2024), and only 8 levels are measured (Ni 2019) |
| Count width | 7 bits per segment | 7 bits per segment, 9–10-bit total after the segment adder | ⌈log₂(mQ + 1)⌉ ([cost_note.py]($PROJECT/sw_ref/experiments/d5c_qhinge/cost_note.py)) |
| Searches per step | 2 (ADD, REM) | 2 | D5c design |
| TCAM writes | once per instance (n rows × m·Q cells) | once per instance; optional λ rewrite per anneal | D5c; λ-replication variant |
| RNG | **xoshiro128\*\* per lane** (xorshift32 if area-bound) plus a separate selection generator. Seed through a splitmix64 shift chain (Anechoic §5.1) | same, plus a shared-RNG ablation (DSSA: 1 bit per 16 spins) | Anechoic per-lane xoshiro128\*\*; Aadit 32-b LFSR per p-bit; repo xoshiro256\*\* + splitmix |
| Clock target | 100–200 MHz (FPGA) | same | PoliTo 200 MHz; MFC 100 MHz |

### 1.3 Datapath in words (one step)

**Storage**
- **J/P memory.** One wide memory, depth N, word = N × 8 bits. Word k holds column k of P, which equals row k by symmetry.
  - On a flip of item k, every lane j reads its byte of word k and adds ±P_jk to its field. That is one read and one add, in constant time.
  - This is the DA "neighbour fields updated in parallel" mechanism ([Aramon 2019](https://arxiv.org/abs/1806.08815)).
  - At N = 256 it is 512 kbit: about 29 BRAM36 at 72-bit simple-dual-port width, or 57 at 36-bit (my arithmetic). Compare 134/144 BRAM36 used by PoliTo dSB at 256 spins.
- **W memory.** Depth N, word = m × 6 bits, column k = item k's weights. On a flip, the m load registers add ±w_jk.
- **Per-lane state:** x_i (1 bit), h_i (18 bits) and an RNG.
- **Global state:** m load registers (16 bits), E_off, T, and best-so-far f and x.

**Per-step pipeline**

| Stage | What happens | Cycles (est.) |
|---|---|---|
| S0 | Slack and query encode. sl_j = C_j − load_j; flo_j = ⌊Q·max(sl_j, 0)/w_max⌋ clipped to Q; fov_j = ⌊Q·max(−sl_j, 0)/w_max⌋ clipped to Q. Thermometer mask generator: ADD query column (j, k) = "search 0" if k > flo_j, else X; REM query = "search 0" if k ≤ fov_j, else X | 1 (m small dividers become multiply-by-constant, since Q/w_max is fixed per instance) |
| S1 | **ADD search.** row_en = ¬x, so only rows that could be added are evaluated (selective precharge). Each enabled row returns cnt_add_i per segment | L_s (TCAM macro latency parameter) |
| S2 | **REM search.** row_en = x; returns cnt_rem_i | L_s; can overlap S1 in a two-port model (one array, so sequential in the device) |
| S3 | Pricing ALU per lane. g_i = (1 − 2x_i)·h_i; geff_i = Q·g_i − Λ·cnt_add_i (if x_i = 0) or Q·g_i + Λ·cnt_rem_i (if x_i = 1), with Λ = round(λ·unit·w_max) | 1–2 |
| S4 | Acceptance per lane: acc_i = [geff_i + Q·E_off > −θ_i], where θ_i = T·L(u_i) and L(u) ≈ −ln u from a small LUT. This is the DA patent form: threshold T·f⁻¹(u) from a RAM conversion table, so no exp or log logic (EP3852028 ¶0049–0052). T and E_off are in Q-scaled units | 1–2 (one DSP multiplier per lane, as in Anechoic §5.1) |
| S5 | Selection: a **count-tree walk**. Use the same log₂N tree of 2:1 nodes as the DA selector (EP3852028 ¶0136–0139), but each node also carries its subtree popcount. c = popcount(acc); if c = 0, E_off += ΔE_off and skip to the next step. Else draw r = ⌊rand16·c / 2¹⁶⌋; at each node go left if r < n_L, else r −= n_L and go right. Exactly uniform up to the ≤ c/2¹⁶ multiply-shift bias, and 8 levels deep at N = 256. The DA's 1-bit-tie-break tree is *not* uniform (§3.2); keep it only as a cheap optional mode. Avoid random-rotate + priority encoder, which favours bits after runs of zeros. Must be bit-identical to the golden model | 1–2 |
| S6 | Commit: x_k ^= 1; broadcast word k of P (all lanes h += ±P_·k); load_j += ±w_jk; f += g_k; E_off = 0; feasibility check (m comparators) and best-so-far update | 2 |
| S7 | Schedule: T ← (T·α) >> s once per step (the golden model uses per-step geometric T), or β += Δβ per step (the DA uses β linear, updated every iteration), or a staircase per stage. Pick one and make the golden model match | 0 (overlapped) |

**Step time.** About 8–12 cycles + 2·L_s. At 200 MHz with L_s ≈ 2–4 cycles, that is ≈ 60–100 ns per step (my estimate). For scale, PoliTo dSB takes 254 ns per step at 256 spins ([arXiv 2510.12407](https://arxiv.org/html/2510.12407v2)).

### 1.4 Integer golden model (needed before RTL) [Inference]

Write `qkp_int` from [qkp_nb.py]($PROJECT/sw_ref/experiments/d5c_qhinge/qkp_nb.py) with five changes:
1. **Scale by Q.** Scale all energies by Q so dq = w_max/Q disappears. ⌊v/dq⌋ = ⌊Q·v/w_max⌋ is exact integer division, and λ·unit·dq·S becomes Λ·S/Q, compared against Q·g.
2. **RNG.** Replace PCG64 with per-lane xoshiro128\*\* (Anechoic's choice), a 32-bit-output sibling of the repo's xoshiro256\*\*/splitmix code ([kernels.py:121–155]($PROJECT/sw_ref/histmem/fast/kernels.py)). Seed every lane with splitmix64 in the same order the RTL shift chain uses.
3. **Acceptance.** Replace u < exp(z) with the integer threshold test of §1.3 S4. Use L(u) = round(2^F·(−ln((u_top + 0.5)/2^b))) with b = 8–10 address bits, or −log₂ u ≈ LZC(u) + L16[mantissa]. The second needs only a priority encoder plus a 16-entry LUT per lane.
4. **Temperature.** T becomes a 24-bit fixed-point register with an integer α multiply.
5. **Selection.** `rng.integers(0, Eg)` over the index-ordered accepted list becomes the count-tree walk: r = ⌊rand16·c/2¹⁶⌋, then take the r-th set bit in index order. That is the same ordering as the `elig` list (qkp_nb.py:245–247), so only the draw changes.

Gate: the integer model must reproduce the D5c ranking (Q = 8 vs exact hinge vs filter) on the stored tune/test seeds within the pre-registered 0.17-point margin before any RTL comparison counts. ptemp's host-tabulated `etab` acceptance table is the in-repo precedent for a LUT acceptance that is bit-identical across back-ends ([ptemp/cpu.py:9–10]($PROJECT/sw_ref/histmem/ptemp/cpu.py)).

### 1.5 TCAM pricer block: interface (behavioural SystemVerilog first, SPICE word later)

```
module tcam_array #(N=256, SEG=64, NSEG=1..8, CW=7) (
  // write port: once per instance (pricer) or at stall events (visited-state control)
  input  wr_en, wr_row[log2N], wr_seg[log2NSEG], wr_bits[SEG], wr_care[SEG],  // care = all-1 in pricer mode
  output wr_busy,                       // models FeFET write: 0.2-10 us per row, +-4 V (parameter W_LAT)
  // search port: twice per step (pricer) or once per step (control)
  input  s_valid, s_key[SEG*NSEG], s_care[SEG*NSEG],   // per-column search bit and mask (care=0 -> X)
  input  row_en[N],                     // selective precharge: ADD -> ~x, REM -> x
  input  s_thr[CW],                     // threshold for the visited-state "word" rule
  output r_valid, r_cnt[N][NSEG][CW],   // per-row, per-segment mismatch counts (pricer)
  output r_hit[N],                      // AND over segments of (cnt <= thr) (control)
  // verification hooks (behavioural only)
  input  err_en, err_seed,              // count-error injection from the SPICE per-level error table
  output stat_searches, stat_rows_en, stat_cells_eval, stat_writes  // for the energy model
);
```

**Pricer word contents.** Row i is item i. Segment g holds constraints j ∈ group g. Constraint j occupies Q consecutive cells holding the thermometer code of Wq_ij = ⌊Q·w_ij/w_max⌋: cell (j, k) = 1 iff Wq_ij ≥ k, for k = 1..Q. The v0 word is 64 cells = 8 constraints × 8 levels.

**Query.** ADD: column (j, k) searches "0" iff k > flo_j, else X. REM: "0" iff k ≤ fov_j, else X. A stored 1 under a "0" query is a mismatch. The ADD count equals Σ_j max(0, Wq_ij − flo_j) and the REM count equals Σ_j min(Wq_ij, fov_j). These are exactly the S values of `qkp_nb._kernel` :139–153.

**Segment adder.** A digital tree sums the NSEG segment counts to a 9–10-bit total. Optional per-segment λ_g weights give the "segmented adaptive" variant.

**Visited-state control word.** Row r holds a stored n-bit state with care mask (ternary), as in [trap_ideal.py]($PROJECT/sw_ref/histmem/memory/trap_ideal.py). It is written at stall events and searched once per step with the current x. r_hit triggers a restart (H4).

The digital twin of the pricer (control C2) is the same interface implemented with per-lane clip-and-add, Σ_j max(0, Wq_ij − flo_j). That gives "TCAM off, same RTL".

### 1.6 Controls that must exist in the same RTL (from the this project plan)

- **C1:** TCAM off, area reallocated to extra lanes or replicas.
- **C2:** digital-equivalent pricer, bit-exact.
- **C3:** exact digital hinge and adaptive hinge (best memoryless rules).
- **H4:** visited-state TCAM restart trigger vs lockout counter vs exact hash vs random-time placebo.

([this project plan](<$PROJECT/02_research_reports/reports/this project TCAM Ising hardware plan.md>))

## 2. TCAM circuit facts (transistor level)

Read depth: Pagiamtzis & Sheikholeslami 2006, Arsovski 2003, Ni 2019 **SI only** (main text paywalled), Yin 2022, TAP-CAM, Kazemi 2021, Li 2020, Zhou 2025, Mattar 2025 and Narla 2024 were opened as full text. Survey Tables IV–V are images, so their values were not extracted. Cost numbers already in the [devices notes](<$PROJECT/02_research_reports/research_notes/this project TCAM Ising hardware plan/devices_models_tools.md>) are not repeated unless needed.

### 2.1 Cell schematics in words

- **16T NOR TCAM (SRAM).** Pagiamtzis & Sheikholeslami, IEEE JSSC 41(3):712–727, 2006, §II-A/D, Fig. 5a, Fig. 7a, Table II, pp. 714–715.
  - Structure: two 6T SRAM cells (D and D̄ for ternary) plus four minimum nMOS compare transistors M1–M4. They form two series pull-down stacks from ML to GND, in parallel.
  - Stack 1 is gated by SL and D̄; stack 2 by SL̄ and D. All cells of a word share one ML, so the word is a wide dynamic NOR.
  - Stored encoding (Table II): "1" = D 1 / D̄ 0; "0" = D 0 / D̄ 1; "X" = D = D̄ = 1 (both stacks off). D = D̄ = 0 is disallowed. Search-X = SL = SL̄ = 0.
  - Placement for precharge-high sensing: put the stored-bit transistor on top, next to ML (Fig. 12b, p. 718). Otherwise the internal stack node charge-shares with ML.
  - Placement for precharge-low / current-race sensing: put SL on top (Fig. 12a), so ML capacitance does not depend on the stored data (p. 719).
- **NAND TCAM.** Same survey, §II-B/D, Figs. 5b, 7b, 9, Table III, pp. 714–717.
  - Pass nMOS M_D and M_D̄ carry SL or SL̄ to node B, which is the XNOR of stored and search bit. B gates a series nMOS Mi.
  - The Mi of all cells form one chain from ML to GND, with a pMOS precharge at the top and an nMOS evaluate device at the foot.
  - Polarity is inverted: a **match** discharges ML.
  - Ternary: a mask SRAM forces Mi on. Search-X = SL = SL̄ = 1.
  - Node B reaches only VDD − Vtn. Delay is quadratic in chain length, so chains are 8–16 cells, and intermediate nodes need precharging against charge sharing (p. 716).
  - **[Inference]** A NAND ML cannot count mismatches, so the pricer cannot use it.
- **2FeFET TCAM.** Ni et al., Nat. Electron. 2:521–529, 2019; SI Figs. 2–4, 6, 9.
  - FeFET-L gate on SL, FeFET-R gate on SL̄. Both drains on ML, both sources on a grounded source line ScL. Devices: 8 nm HfO₂ from GF Dresden, 28 nm HKMG.
  - Store "0": L low-VT, R high-VT. On a mismatch the high gate voltage lands on the low-VT device, which discharges ML.
  - X can be stored (both high-VT) or searched (both SLs at 0 V or negative).
  - Simulation used a pMOS precharge with ML floating during evaluation. The measurement used a passive pull-up resistor (SI p. 10).
  - Writes: ±4 V, 10 µs pulses, with ML and ScL grounded.
- **1FeFET1R CAM.** Yin et al., arXiv 2203.07948 (2022), Figs. 3–5, S4–S6.
  - One FeFET per bit: gate on its own SLᵢ, drain to ML through series R_S = 1 MΩ, source on ScL. ML is held at V_ML = 0.1 V and its current is sensed.
  - "0" = low-VT, "1" = high-VT.
  - Two-step search: step 1 drives V_SL = −0.4 V for search-0 and 1 V for search-1; step 2 drives 1 V for search-0 and 2 V for search-1.
  - HD ∝ I_ML,step2 − I_ML,step1, with I_cell ≈ V_D/R_S whenever the device is on. The series R clamps I_ON variation.
  - Function measured on 8 cells; 64 cells Monte-Carlo simulated. Serial thermometer ADC, so energy and delay scale with word length.
- **2FeFET-2R threshold CAM (TAP-CAM).** Ni C. et al., arXiv 2502.05787 (2025), Fig. 4a, Fig. 5, Tables I–II.
  - Two 1FeFET-1R branches. Drain on ML; source through R_S = 0.3 MΩ to ScL; gates on BL/SL and BL̄/SL̄.
  - Write: V_write = 4 V in two steps via ScL (+4 V VGS on M1, then ScL raised for −4 V on M2), with ML grounded.
  - Search: SL = 1 V for "1". A pMOS T1 (gate CLK) precharges; an evaluate nMOS T2 sits between ML and the SA node.
  - The Hamming threshold is set by V_eval: 1 / 0.75 / 0.63 / 0.52 / 0.43 / 0.37 V for Th0–Th5, at a fixed sense time.
  - The paper's "1 = high-VT" mapping conflicts with the usual n-FeFET convention. **Uncertain**: check polarity against the Verilog-A model.
- **6T2M analog CAM.** Li et al., Nat. Commun. 11:1638 (2020), arXiv 1907.08177, Fig. 2, SI Figs. 1–2.
  - Two pull-down nMOS T1 and T2, from ML to VSS.
  - T1's gate is the midpoint of an nMOS (gate = DL = analog search voltage) in series with memristor M1, between SL_hi = 0.5 V and SL_lo = GND. M1 sets the lower bound.
  - T2 is driven by a second nMOS + M2 divider through a 2T inverter. M2 sets the upper bound.
  - pMOS ML precharge; the search starts when SL_hi rises.
  - Measured search energy split per cell per search (SI Table 2, 86×12 array): ML precharge 0.10, SL_hi driver 0.29, DAC 0.05, other 0.08; total 0.52 fJ.
- **2T1C FeFET charge-domain CAM.** Yin G. et al., arXiv 2102.01442 (2021), simulated.
  - FeFET gates on BL/BL̄, sources on WL/WL̄. The shared node X couples to a per-cell C_M = 1.2 fF on a floating ScL, so V_ScL = VDD·M/N (M = matches).
  - σ(C_M) = 5% gives σ < 0.25% of full scale at N = 128.
  - This is the charge-domain option that stays within **MOSFET + FeFET** (plus a MOS/MOM capacitor).
- **2FCM (ferroelectric capacitor) CAM.** Zhou et al., Nat. Commun. 16:8047 (2025), Eqs. 1–4, Figs. 2–5, Table 1.
  - Two FCM capacitors per cell. Top electrodes tied together as ML; bottom electrodes on SL and SL̄. The pair is a capacitive divider.
  - Row output: V_ML = [(N − n_mis)C_HCS + n_mis·C_LCS] / [N(C_HCS + C_LCS)]·VDD ≈ (N − n_mis)/N·VDD. Linear, time-independent, no precharge.
  - Note: this is a ferroelectric *capacitor* device, not a FeFET, so it falls outside our MOSFET + FeFET device set. It is useful as a comparison point.

### 2.2 Search sequence and timing

- **Precharge-high NOR** (survey §III-A, Figs. 10b, 11, pp. 716–718).
  1. *slpre*: all SLs low, so no pull-down path is active.
  2. *mlpre*: ML precharged to VDD, then released.
  3. Search word driven on the SLs. Each mismatching cell discharges ML; the MLSA (inverter plus keeper) latches the result.
  - Model: match = C_ML alone; miss = C_ML ∥ R_ML/m, with m the number of mismatches. Worst case is m = 1, the slowest fall.
  - 0.18 µm values: R_ML 5–10 kΩ, C_ML up to "a few hundred fF", evaluate ≈ 0.69·R_ML·C_ML ≈ 1 ns (RC estimate). Energy per missing ML ≈ C_ML·VDD².
  - A replica ML programmed to a permanent 1-bit miss times the latch (Fig. 13).
- **Current-race** (Arsovski, Chandler, Sheikholeslami, JSSC 2003, Fig. 6, Table I). MEASURED, 0.18 µm, 256×144, 17.54 µm² cell.
  - ML is reset to GND, then MLEN connects a current source to every ML.
  - The MLs race a dummy full-match ML; when it trips, MLOFF cuts the currents and latches.
  - Numbers: swing 960 mV; ML1 at least 140 mV below the dummy at 1 ns programmable delay; match time 3 ns at 1.2 V, 260 µA max. SL activity cut by 50% because no SL precharge is needed.
- **Other schemes** (survey).
  - Selective precharge (Zukowski & Wang 1997): 3 of 144 bits checked first, ≈88% ideal ML saving.
  - Pipelined / hierarchical ML: activity as low as 25%.
  - Low-swing charge injection (Kasai CICC 2003): 300 mV ML precharge.
  - Current-saving: > 50% ML power saving.
- **Search lines.** P_SL ≈ N_rows·C_SL·VDD²·f, plus ≈25% for exponentially sized drivers. Precharge-low schemes cut SL power by 50%, which "can be as large as or larger than" the ML saving (survey §IV).
- **Encoders.** Words are 36–144 bits and tables run from a few hundred to 32K entries. Priority-encoder delay numbers were **not found** (survey p. 712 gives concept only).

### 2.3 Facts table

| Design | Node / model | Cell | Word | ML / search V | Write | E (fJ/bit/search) | Delay | Area (µm²) | Sensing and margin | Variation handling | Status | Citation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16T NOR | 45 nm PTM | 16T | 64 | 1 V | SRAM | 0.59–1.0 (tabulated) | 582 ps | 1.12–1.2 | Inverter SA | – | Sim | Qian DATE'21 Table I; [TAP-CAM](https://arxiv.org/abs/2502.05787); [SEE-MCAM](https://arxiv.org/abs/2310.04940) |
| Current-race TCAM | 0.18 µm | SRAM + compare | 144 | 0 V start; 960 mV swing | SRAM | not given | 3 ns | 17.54 | Dummy-ML race, ≥140 mV | Programmable current and MLOFF delay | **Meas.** | [Arsovski JSSC 2003](https://www.eecg.utoronto.ca/~ali/papers/jssc2003-1.pdf) Fig. 6, Table I |
| 28 nm SRAM TCAMs | 28 nm | 14T / 6T-pair | 320 Kb macro | – | SRAM, 3-cycle write | 0.422 / 0.74 | – | – | – | – | **Meas.** | [Xue JSSC 2019](https://scholars.nthu.edu.tw/esploro/outputs/journalArticle/A-28-nm-320-Kb-TCAM-Macro-Using/9957772703906774); [Jeloka 2016](https://blaauw.engin.umich.edu/wp-content/uploads/sites/342/2018/02/Jeloka-A-28nm-configurable-memory.pdf) [PRIOR] |
| 2FeFET (Ni) | GF 28 nm HKMG FeFET; Preisach + 45 nm parasitics | 2FeFET | 1×6 meas.; 8–64 sim | pMOS precharge; search V not obtained (main text unread) | ±4 V, 10 µs | 0.40 | 355 ps | 0.15 | Precharge + clocked self-referenced SA. **8 HD levels resolve only in 1×8**; in 1×64 only HD ≤ 8 resolves (SI Fig. 8a) | Segment 1×64 into 8 × (1×8) (SI p. 16) | Meas. + sim | [Ni 2019 SI](https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41928-019-0321-3/MediaObjects/41928_2019_321_MOESM1_ESM.pdf) Figs. 5–8 |
| 2FeFET-1T | 45 nm PTM | 2FeFET + 1T | 64 | V_S = 1 V | ±4 V; ±V_W/2 inhibit | 0.195 | 253 ps | 0.36 | Inverter SA | – | Sim | Qian DATE 2021 Fig. 4, Table I ([PDF](https://past.date-conference.com/proceedings-archive/2021/pdf/1478.pdf)) |
| FeCAM | 45 nm PTM | 2FeFET | 64 | 0.5 V ML drop; ≈25 nA/cell | ≤ 4 V; unselected ScL ±2 V | 0.182 | – | – | 3-buffer SA | Search time adapted to N | Sim | Yin TED 2020 Eqs. 1–3 (arXiv 2004.01866) |
| 1FeFET1R | Fraunhofer/GF FeFET, W/L 0.5/0.5 and 1/1 µm | 1FeFET + 1R (1 MΩ) | 8 meas.; 64 MC | V_ML 0.1 V; V_SL −0.4 / 1 / 2 V | 200 ns MLC pulses | scales with word (serial ADC) | serial | densest | Two-step current difference | R_S clamps I_ON | **Meas.** + MC | [arXiv 2203.07948](https://arxiv.org/abs/2203.07948) Figs. 3–5, S4–S6 |
| TAP-CAM | 45 nm PTM + Preisach | 2FeFET-2R (0.3 MΩ) | 64 | VDD 0.6–1 V; V_eval 1.0→0.37 V for Th0–Th5 | ±4 V | 0.059 | 1.2 ns | 0.15 | Fixed sense time; threshold via V_eval; narrowest margin at Th-5 | σVT 54 mV, R ±8%, 100 MC | Sim | [arXiv 2502.05787](https://arxiv.org/abs/2502.05787) Table II, Figs. 6–9 |
| MCAM | GF 28 nm, 450 × 450 nm | 2FeFET (multi-VT) | 64 sim | ML 0.8 V sim; 0.1 V meas. | Erase −5 V 500 ns; program 1–4.5 V 200 ns | +56% vs TCAM | ≈ TCAM | – | Slowest-discharging ML wins | Tolerates σ ≤ 80 mV | Meas. 2-bit + sim | [arXiv 2011.07095](https://arxiv.org/abs/2011.07095) §IV-D |
| 6T2M aCAM | 16 nm sim; 180 nm chip | 6T2M | 86×12 sim | SL_hi 0.5 V | Memristor < 1 V, program-verify | 0.52 per cell | < 100 ps | – | V_ML sampled at 100 ps | Program-and-verify | Meas. + sim | [arXiv 1907.08177](https://ar5iv.labs.arxiv.org/html/1907.08177) Figs. 3–5, SI Table 2 |
| 2FCM charge-domain | SOI FCM (10 nm Al:HfO₂); 45 nm projection | 2 FE capacitors | 16 meas. (16×16) | VDD 0.5 V meas., 1 V sim; no precharge | ±5.5 V, 10 µs; V/3 inhibit | **0.005** (no periphery); 0.74 pJ per 256×128 search with periphery | 0.75 ns | 0.024 | V_ML linear in HD, R² = 0.9983, mean error 0.126 LSB over 16 levels; 96.8% of searches < 1-bit error | ≈5.1–6.1× lower σ(V_ML) than 2FeFET at σ = 0.09/0.18 V; endurance ≈10⁶ | **Meas.** + sim | [Zhou NC 2025](https://www.nature.com/articles/s41467-025-63190-y) Eqs. 1–4, Figs. 3–5, Table 1 |
| Same paper, Table 1 comparison (SPICE, 256×128, 1 V, with periphery) | 45 nm | 16T SRAM / 2.5T-1R / 2FeFET | 128 | 1 V | – | 1.0 / 0.7 / 0.4 (no periphery) | 1.0 / 1.0 / 1.4 ns | 1.12 / 0.28 / 0.15 | – | – | Sim by Zhou et al. | 33.3 / 23.8 / 13.7 pJ per search incl. periphery ([Zhou Table 1](https://www.nature.com/articles/s41467-025-63190-y)) |
| FeFET CAM at 7 nm | ASAP7 + StarRC; FeFET MW 0.46 V | 2FeFET | 128 | – | – | 0.78 / 1.66 / 3.15 / 3.95 pJ per search (ideal / 64 / 128 / 256 rows) | 0.4–1.2 ns | 9F × 15F | Discharge-time thresholding. Precision at HD ≤ 20 falls 93% → 65% → 24% at 64 / 128 / 256 rows from SL RC | Wider M4 SLs (S2x) or clock RC matching | Sim | [Narla et al., arXiv 2403.15328](https://arxiv.org/abs/2403.15328) Fig. 3–5, Table IV |
| Time-domain macro | GF 28SLPe, FeFET 90 × 90 nm | 2FeFET as tail of current-starved inverter | 3×3 | VDD 0.85 V | +4 V on WL (LVT); −4 V with bulk −2 V on unselected rows | 1887 TOPS/W (binary MAC) | 550 ps per delay step | – | Flash TDC | Multilevel trim to ≤ 100 ps | **Meas.** | [arXiv 2504.03925](https://arxiv.org/abs/2504.03925) Figs. 4–7, 11, Table I |

**ML capacitance.** C_ML ≈ C_pMOS + N·(2·C_drain + C_parasitic) for a 2FeFET row (Qian DATE 2021, Eq. 2). No explicit fF-per-cell value was found. Back-calculating from E ≈ C_ML·VDD² at 1 V gives about 0.06–0.4 fF per cell at 45 nm (**[Inference]**, uncertain).

### 2.4 Mismatch-count readout options (the pricer needs a 0…64 count per row per search)

| Option | How it works | Linearity | Demonstrated | Main problem | Source |
|---|---|---|---|---|---|
| ML voltage at fixed time + comparator/ADC | Sample the precharged ML after t_eval | Exponential RC decay, so nonlinear in m | 8 levels in 8 cells measured. In 64 cells only HD ≤ 8 resolves | Timing- and variation-sensitive | [Ni 2019 SI](https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41928-019-0321-3/MediaObjects/41928_2019_321_MOESM1_ESM.pdf) Fig. 8a |
| Threshold sensing (V_eval or timed latch) | Gives HD ≤ θ, not a count | – | Th0–Th5 at 64 cells (sim) | Gives a threshold only. A count needs log₂ or linear sweeps of θ (several searches) | [TAP-CAM](https://arxiv.org/abs/2502.05787) |
| Discharge time + TDC | Time-to-threshold ∝ 1/m | t_n − t_{n−1} ∝ **1/(n(n−1))**, so high counts crowd together | 128-bit sim at 7 nm; position-dependent SL RC degrades it further | Resolution collapses at large m | [Narla 2024](https://arxiv.org/abs/2403.15328) Fig. 3 |
| Delay-chain time domain | One delay element per bit; total delay linear in count | Linear, 550 ps/step measured | 3×3 array | Serial: latency ≈ N·step | [Mattar 2025](https://arxiv.org/abs/2504.03925) |
| Clamped current sum | ML clamped (≈0.1 V); I_ML ≈ m·V_D/R_S | Linear | 8 cells measured, 64 MC | Needs a current ADC; static current during evaluation | [Yin 2022](https://arxiv.org/abs/2203.07948) |
| Charge domain | Per-cell capacitor onto a floating count line; V ∝ matches | Linear, time-independent | 16 cells measured (2FCM); 128 sim (FeFET 2T1C) | Per-cell capacitor area; still needs an ADC | [Zhou 2025](https://www.nature.com/articles/s41467-025-63190-y); Yin G. arXiv 2102.01442 |

**[Inference] Recommendation for our 64-cell pricer word.**
- **Primary: FeFET charge-domain.** A 2FeFET pass-gate XOR (or the 2T1C cell) drives a per-cell MOS/MOM capacitor of about 1–2 fF onto a floating count line.
  - At 64 cells, LSB ≈ VDD/64 ≈ 12–16 mV at 0.8–1 V.
  - Total C ≈ 77 fF, so kT/C noise ≈ 0.23 mV, which is negligible.
  - Digitise with a shared 7-bit single-slope or SAR ADC.
- **Fallback: current domain.** 1FeFET1R or 2FeFET-2R with R_S = 0.3–1 MΩ.
  - Segment each 64-cell row into 8 × 8 cells, following Ni's segmentation proposal.
  - Give each 8-cell sub-ML a 9-level flash comparator and sum the eight 4-bit results digitally.
  - This trades area for staying inside the only measured multi-level regime (1×8).
- **Avoid** single-ML discharge-time sensing across the full 0…64 range (Narla's 1/(n(n−1)) result).
- **Reference rows.** Program replica words with known counts (0, 8, 16, …, 64) for ADC references and PVT tracking, plus a dummy ML for timing (survey Fig. 13; Arsovski's dummy ML).
- **SPICE plan.**
  - Corners TT/FF/SS/FS/SF; 0–85 °C; VDD ±10%.
  - Monte Carlo with σVT 54 mV (TAP-CAM), 80 mV (Kazemi) and 90–180 mV (Zhou's FeFET assumption); R ±8%; C mismatch 1–5%.
  - Patterns m = 0, 1, 2, 32, 63, 64 and 50% toggling.
  - Extracted or estimated SL/ML RC, with the row farthest from the driver as worst case.
  - Write disturb: V/2 or V/3 inhibit, |V_GS| ≤ 2 V on unselected cells (FeCAM, Qian DATE 2021), or bulk −2 V (Mattar).
  - Read disturb after 10⁶ searches at ≤ 1 V.
  - Report DNL/INL, a per-level error-probability table (this feeds the RTL error-injection hook) and the energy split SL / ML-count line / ADC.

## 3. Ising / annealing hardware with enough detail to write RTL

Conventions: "n/f" means not found in any primary source that could be opened. Fujitsu patents other than EP3852028 were unreadable (Google Patents 503; Justia, USPTO and FPO 403). The Fujitsu FSTJ 2017 PDF redirected away. Amorphica is **512 spins × 4 replicas per chip**; the 2,048 figure is a 4-chip system.

### 3.1 Machine table

| Machine (year) | Spins / topology | J & h bits | Field register | ΔE / field update | Acceptance + RNG | Schedule | Parallelism + selection | Clock | Resources / node | Power / energy | Verification vs software | Citation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Fujitsu DA v1/v2** (2017–19) | 1,024 fully connected; v2 8,192 | J 16 b, h 26 b (v1). Patent: 128 kbit SRAM per lane, so weight precision is traded against scale: 128 b @ 1k, 64 @ 2k, 32 @ 4k, 16 @ 8k bits | n/f. h initialised to the bias (≥ 27 b inferred for v1) | ΔE_i = ±h_i, sign set by flip direction. On an accepted flip j every lane does h_i += W_ij·Δx_j in parallel, "constant time, regardless of the number of neighbours" | Metropolis on ΔE_i − E_off. Patent: flag F_i = 1 if ΔE_i < −T·f⁻¹(u); f⁻¹ from a **RAM conversion table**, so no exp or log logic. Per-lane RNG "favorably", sharing allowed. v1 RNG "similar to twisted GFSR, period 2^19937" (Aramon §II.B per survey agent; not re-verified) | β linear, updated every iteration (paper). Patent: T changes every N1 iterations, N2 times. E_off += inc if nothing accepted, reset to 0 on acceptance | All N trials per step, at most one flip. **Selection = log₂N tree of 2:1 nodes**: a node prefers the input with F = 1; if both are 1, a 1-bit random picks; each level appends one index bit. Early PT replica exchange ran on the CPU | n/f | ASIC (DAU), node n/f; FPGA prototype with 1,024 bits | n/f | n/f; algorithm benchmarked against CPU SA/PT | [Aramon 2019 §I, §II.2–II.4, Alg. 2](https://arxiv.org/abs/1806.08815); [EP3852028 A1 ¶0029, 0049–0053, 0055–0058, 0119, 0126, 0136–0139, 0146–0147](https://data.epo.org/publication-server/rest/v1.2/patents/EP3852028NWA1/document.html) (verified by me); [Shibasaki, ITU-AJ 2019 §2.2–2.4, Fig. 2](https://www.ituaj.jp/wp-content/uploads/2019/01/nb31-1_web-07-Special-CombinatorialOptimization.pdf) |
| **Hitachi CMOS annealer** (2015/16) | 20k = 128×80×2 3-D lattice folded into 256×80; ≤ 5 neighbours | ±1 couplings in experiments; h unused; width n/f | none | SRAM cells, logic and an analog majority circuit set s_i so that s_i·F_i > 0 | Random flips from two external Mersenne-Twister pulse streams (flip when both high), or low-VDD (~0.7 V) SRAM errors | Flip mark-rate 0.75 → 0.01 → 0 | All spins at once | 10 MHz interaction clock, 100 ns/step (JSSC abstract says 100 MHz: uncertain) | 65 nm, 4 × 3 mm | 49.2 mW interaction | Statistical accuracy vs CPU algorithms | [Yoshimura/Yamaoka, Sci. Rep. 5:16213 (2015) Figs. 1, 3, 6–8](https://pmc.ncbi.nlm.nih.gov/articles/PMC4653651/); JSSC 51(1):303 (2016) (abstract) |
| Later Hitachi | 2×30k King's graph PIM (ISSCC'19); 9×16k, 40 nm, 100 MHz, **1-b** couplings (ISSCC'21) | | | | | | | | | | | Secondary via [DSSA Table 6, §5.5](https://arxiv.org/abs/2609.09559) (uncertain) |
| **STATICA** (ISSCC'20 / JSSC'21) | 512 fully connected, 0.25M weights, 1.3 Mb SRAM | J 4 b (secondary); h n/f | n/f | Stochastic cellular automata: all spins every step. "Delta-driven": only spins that flipped last step feed accumulation | SCA: P ∝ e^{β/2(h̃+qσ)s}/2cosh(·) with pinning q. Linear clamp clamp(z/4T + ½), z = s·h + q, as re-implemented by Anechoic. RNG n/f | K2000: q = 4, T0 = 30, 560 steps, geometric (secondary) | Spin–replica pairs, fully parallel | 320 MHz @ 1.1 V (uncertain) | 65 nm, 3 × 4 mm (uncertain) | 649 mW, ≈4 pJ per spin-update (DERIVED) | n/f | [Tokyo Tech PR 2020](https://www.titech.ac.jp/english/news/pdf/tokyotechpr_en_motomura_20200227_5237qzfb.pdf); [Fukushima-Kimura et al. arXiv 2211.06809 Eqs. 1.2–1.6](https://arxiv.org/abs/2211.06809); [Anechoic Eq. 3](https://arxiv.org/abs/2610.13368) |
| **Amorphica** (ISSCC'23) | 512 fully connected × 4 replicas; 4 chips via FPGA = 2,048 | 8 b per Pegasus paper Fig. 6; DSSA says "not explicitly specified" (**conflict**) | n/f | Programmable policies: SA, SCA, RPA (ε-SCA) | n/f | Programmable | Compressed-spin-transfer multichip, double-buffered | 134–336 MHz | TSMC 40 nm, 3 × 3 mm (uncertain); 4,814 µm²/spin | 152–475 mW chip; 606–1,900 mW system; 1,146 pJ/flip (DERIVED by third party) | n/f | [Tokyo Tech 2023](https://www.titech.ac.jp/english/news/2023/065901); [Pegasus arXiv 2609.07907 Fig. 6](https://arxiv.org/abs/2609.07907); [DSSA Table 6](https://arxiv.org/abs/2609.09559) |
| **Toshiba SB on FPGA** (FPL'19; Nat. Electron.'21) | 2,048/4,096 fully connected; 8 FPGAs: 16,384 (uncertain) and 32,768 | J ternary for Max-Cut; a 4096² J is 16 Mbit (1,024 BRAMs). "J coded in 1 bit; x, p in 16 bits". h FP32 for some problems | Δp accumulators | Full MVM Δp = ΣJx every step, then a time-evolution pipeline with mixed fixed/float stages | Deterministic; initial p ~ U(±0.1) from Mersenne Twister | α ramps linearly per step | 32×32×8 = 8,192 MAC PEs at 92% activity. Cycles/step = (N/Pc)(N/Pr/Pb + 1) + λ. Double-buffered x′, broadcast | 269 MHz; 266–303 MHz multi-FPGA | Arria 10 GX1150: ALM 40%, BRAM 56%, DSP 7%; OpenCL HLS | 49 W; K2000 TTS 0.055 ms, 2.7 mJ | Measured cycles vs analytic model; no bit-exact claim | [FPL 2019 slides pp. 11–22](https://fpl2019.bsc.es/sites/default/files/uploaded/A12.FPL2019-slides-FPGABasedSimulatedBifurcation.pdf); [Kashimata et al. arXiv 2311.17370 Alg. 1, App. C, Tables S1–S2](https://arxiv.org/abs/2311.17370) |
| **PoliTo dSB/HdSB** (2025) | 256 (parameter) | J 8 b; state Q5.15 | – | dSB with h via an ancillary spin; Pr = Pc = 16, Pb = 4 | Deterministic | Linear pump | Tiled MVM | 200 MHz | KV260: 16,766 LUT, 24,731 FF, **134/144 BRAM** | – | C++ float and fixed reference models; one-instance testbench | [arXiv 2510.12407](https://arxiv.org/html/2510.12407v2) [PRIOR] |
| **p-bit sparse IM** (Aadit et al., Nat. Electron. 5:460, 2022) | ≤ 5,375 p-bits; sparsified to max degree 4–5, 4–7 colours | 10-b J/h and 13-b sum per Fig. S2c labels (uncertain) | Full MAC over neighbours each update (mux ±J, add) | – | m = sgn[tanh(βI) − r]. LUT holds (1 + tanh)/2, then a comparator. **32-b LFSR per p-bit, taps [32, 22, 2, 1]**, chosen after testing LFSR, xoshiro128+ and MT | Linear β; βJ and βh computed in MATLAB and re-sent per β | Chromatic Gibbs: five phase-shifted 15 MHz clocks (0/72/…/288°) from a 250 MHz MMCM, one per colour. The MAC must settle in T/n_colours; overclocking gives inexact (Hogwild-like) Gibbs | 5 × 15 MHz | VCU118; resources n/f | n/f | Statistical: flip-rate counters; TTS vs serial MATLAB Gibbs | [arXiv 2110.02481 §II, §IV.B, §V, §VIII, SI B.3–4, Fig. S2](https://arxiv.org/abs/2110.02481) |
| Niazi et al. 2023 (same group) | 4,264 (Pegasus), 3,360 (Zephyr); DSatur 4–5 colours | 10-b s{6}{3} weights | – | – | 32-b xoshiro per p-bit; tanh LUT | – | Chromatic | 300 MHz system | Alveo U250 | not measured | – | [arXiv 2303.10728](https://arxiv.org/html/2303.10728v2) [PRIOR] |
| **Pervaiz weighted p-bit** (2018) | 4×4 tiles; up to 434 p-bits | J, h fixed-point s[x][2] (e.g. s[4][2]); LUT input clamped to s[3][2] (−8…7.75); output s[0][31] | as J | Full sum, clamp, mux | 32-b XNOR LFSR (taps 32/22/2/1), unique seed per p-bit, 32-b comparator | none | Sequential: 2 cycles + 1 gap per p-bit | 100 MHz | XCKU040; **1 p-bit = 42 LUT / 33 FF** | n/f | 10⁶-sample histograms match Boltzmann | [arXiv 1712.04166 §II, Table II, Figs. 6, 8](https://arxiv.org/abs/1712.04166) |
| **SSA on FPGA** (Shin, Onizawa, Gross, Hanyu, JETCAS 2023) | 800 spins (degree 4; King's degree 8) | h, J **4 b** (−8…7) | I_tanh = saturating up/down counter, range ±I0 | Recomputed every cycle: I = h + Σ mux(J, m) + n_rnd·r + I_tanh; m = sgn(I_tanh) | xorshift; 1 random bit per spin per cycle | I0 from I0min to I0max, ×2^β every τ cycles (a shift); n_rnd = 2, I0 1→32, τ = 100 | All spins every cycle | 100 MHz | Kintex-7 325T: 105,294 LUT, 13,692 FF, 356 BRAM | 2.14 W | Statistical vs Python SSA/SA | [arXiv 2601.18007 Eqs. 2, 4, Tables II, III, VII](https://arxiv.org/abs/2601.18007) |
| **DSSA** (Onizawa et al. 2026) | 2,048 fully connected | J 4 b | datapath labels 13–15 b (uncertain) | Recompute only for flipped spins | 128-b xorshift per cycle, **one bit shared by 16 spins** | Skips idle temperature steps | Spin-select circuit + priority encoder | 500 MHz | 28 nm post-layout; 16 Mb SRAM; VCU118 P&R only (198,586 LUT, 78,559 FF, 480 BRAM) | 316 mW (clock 71%); 40.4 pJ/spin/step | Equivalence with SSA argued, not tested | [arXiv 2609.09559 §4, Fig. 5, §5.2, §5.8, Tables 6–7](https://arxiv.org/abs/2609.09559) |
| **Pegasus 28 nm** (Wu et al. 2026) | 27,648 spins over 4 chips; 15 neighbours | 10-b coefficients | – | Sign-select ±J by s_j, adder tree + bias | tanh LUT + comparator; **LFSR** | – | 2-b colour index; one colour per cycle; 128 cycles per 6,912-spin sweep; banked SRAM 960 b/cycle | 140 MHz (4 chips), 250 MHz single | 1.5 mm² die, 74.1 µm²/spin | **0.939 pJ/update core**, 1.2 pJ with I/O (MEASURED) | – | [arXiv 2609.07907](https://arxiv.org/abs/2609.07907) [PRIOR-FULL] |
| **Anechoic** (Hong, Jeong, Jang, Oct 2026; **open RTL**) | 2,048 padded (K2000), fully connected | J 1 b (±1) as bit planes; K = 2/4-bit variant with sign + magnitude planes; bias enters only the initial fields | **12 b** | Incremental: up to 8 flips per cycle broadcast; each field adds Σ2σJ via an 8-input popcount, no multipliers | z in Q16.16 vs ((r − 2¹⁵)·4T) ≫ 16, r 16 b, **one DSP per lane**. **xoshiro128\*\* per lane**, seeded through a 256-stage shift chain from one splitmix64 | Per-step table (4T_t, q_t, γ_t), up to 4,096 entries | 256 decision lanes × 8 rounds; 8 priority-encoder flip extractors; cycles = 0.14·flips + 18.1·S + 886 | 250 MHz | Alveo V80: per engine 149,512 LUT, 131,555 FF, 258 BRAM36, 66 URAM, 282 DSP. GF22FDX P&R: 3.60 mm², 1.25 GHz, 1,660 mW | 5.4 mJ per solution (board); ASIC 0.20 mJ (estimated) | **Bit-exact vs a C++ reference** (spins, cut, flip count, per-step n_lin trace) in RTL sim and on board, 60/60 seeded trials per image; GPU port bit-exact 424/424 | [arXiv 2610.13368 §5.1–5.5, Eq. 7, Tables 3, 5–7](https://arxiv.org/abs/2610.13368) (verified by me) |
| **tsjshg/fpga-max-cut** (open, BSD-3) | 1,024 (4-regular; G48–50) | unweighted | – | Sequential-sweep Metropolis | xorshift64 per replica; **host-precomputed ⌊e^{ΔC/T}·2³²⌋ table** | Replica-exchange variant | 16 replicas interleaved in a 5-stage lane × ≤ 56 lanes | 125 MHz | PYNQ-Z1: 40,490 LUT, 114.5 BRAM | – | Bit-exact vs `sa.c`, an independent Python model and on board; xsim with random gaps and back-pressure | [github.com/tsjshg/fpga-max-cut](https://github.com/tsjshg/fpga-max-cut) (README, read only) |

**Correctness fact for verification.** The DA's stationary distribution differs from the Gibbs distribution whenever J ≠ 0. With the offset on, the state x alone is not Markov. Histogram checks of a DA-style RTL must therefore compare against the exact DA transition matrix, not Boltzmann ([Fukushima-Kimura, Kawamoto, Noda, Sakai, arXiv 2303.08392 Eq. 2.6, §3 Prop. 3.4, §5](https://arxiv.org/abs/2303.08392); brief-agent reading, not re-verified).

### 3.2 Block diagrams in words

**(a) Fujitsu DA parallel-trial datapath** (EP3852028; ITU-AJ Fig. 2; Aramon Alg. 2)
1. **Lanes ("LFE").** Lane i holds its row of W in local SRAM (128 kbit per lane, 128-b read word) and a field register h_i, initialised to b_i.
2. **Trial.** Each lane forms ΔE_i from h_i and the flip direction. Its comparator (the "ADB") tests ΔE_i − E_off against a threshold −T·f⁻¹(u_i). The threshold comes from a per-lane RNG and a shared RAM conversion table (Metropolis or Gibbs form), which yields flag F_i.
3. **Offset generator.** E_off += inc when no flag is raised; it resets on acceptance.
4. **Update selector.** A tree of 2:1 nodes carries {F, ΔE, idx}. A node prefers F = 1 and breaks ties with one random bit. The output is (flag, j, ΔE_j); the flag is 0 if nothing was accepted.
5. **Update.** x_j is toggled and j is broadcast. Every lane reads W_ij and adds W_ij·Δx_j to h_i; the energy register adds ΔE_j. The step takes constant time whether or not a flip is accepted.
6. **Cycle timing:** n/f.

**[Inference]** The patent tree is *not* uniform over accepted bits. If the left subtree has 3 accepted bits and the right subtree has 1, the right one wins with probability 1/2, not 1/4. Aramon's paper states "uniformly at random", and so does our golden model. Either implement an exactly uniform selector or change the golden model.

**(b) p-bit chromatic Gibbs datapath** (Aadit 2022 Fig. 1d, S2; Pegasus Figs. 2–3)
1. Colour the graph offline (≤ 4–8 colours).
2. Per p-bit: mux ±J_ij by m_j, adder tree with h, clamp, tanh LUT, compare with the RNG, write m_i. β is folded into J and h by the host.
3. Sequencing, Aadit: one phase-shifted clock per colour. Exact Gibbs needs the adder tree to settle in 1/n_colours of the period.
4. Sequencing, Pegasus: a 2-bit colour index, one colour per cycle, 128 cycles per 6,912-spin sweep. The LUT is addressed by the 7-bit clamped field magnitude.

**(c) Anechoic SCA engine** (§5.1–5.2), the most detailed open RTL found.
1. **Coupling storage.** Couplings live in 32 column banks (each 2048 × 64 b, 4 copies, 8 reads per cycle). Each group owns 64 12-bit fields and 8 decision lanes.
2. **Decision rounds.** A step is 8 rounds of 256 parallel decisions.
3. **Flip extraction.** Eight priority-encoder extractors drain the flip bits while later rounds are still deciding, and broadcast up to 8 flips (x, σ) per cycle to all groups.
4. **Field update.** Each group adds Σ2σJ by popcount. Field updates are visible 6 cycles after issue.

### 3.3 Open-source RTL Ising machines (read only; nothing cloned)

No licence means all rights reserved: use these as references only, never copy code. Last-commit dates were not visible.

| Repo | Licence | Language | Spins | J bits | Algorithm | Target | Testbench / reference model |
|---|---|---|---|---|---|---|---|
| [vlsi-nanocomputing/Simulated-Bifurcation-Machines](https://github.com/vlsi-nanocomputing/Simulated-Bifurcation-Machines) | **none at root** | SystemVerilog + C++ | 256 (param.) | 8 (state Q5.15) | dSB/HdSB | KV260, Vivado 2023.1, 200 MHz | `tb_AXIS_DSBwfile.sv` with one fixed instance; C++ float and fixed models. Host app and J→hex generator not included; `HDL/` differs from the implemented `src/` |
| [skethz/anechoic](https://github.com/skethz/anechoic) | none visible | Verilog (`fpga/v80_sca/src/v6/sca_core*.v`, GF22 ASIC RTL), C++17, CUDA, Lean/Rocq | 2,048 | 1 (K = 2/4 variant) | SCA + Onsager correction | Alveo V80, 250 MHz | Golden-model regression (Questa/xsim); bit-exact on board |
| [tsjshg/fpga-max-cut](https://github.com/tsjshg/fpga-max-cut) | **BSD-3-Clause** | Verilog + C/Python | 1,024 | unweighted | Sequential Metropolis, 16 interleaved replicas, replica exchange, xorshift64, host exp table | PYNQ-Z1, 125 MHz | xsim with random gaps; bit-exact vs `sa.c`, Python and board |
| [greenguyxoxo/qubo_solve_verilog](https://github.com/greenguyxoxo/qubo_solve_verilog) | none in file list | Verilog | 30 | Q 6 b | Combinational ΔE (16 b); 64×8-b exp ROM indexed by (\|ΔE\|≪7)/T (uses a divider); 8-b LFSR per spin; round-robin single flips; T×197/256 | Simulation only | Testbench + Python reference + brute-force checker |
| [jieruiz/pbit_kings](https://github.com/jieruiz/pbit_kings) | none stated | SystemVerilog | n/f | n/f | 4-colour King's-graph p-bits, tanh LUT, LFSR, UART | AXKU042 (inferred) | Unit testbenches, no reference model |
| [archnoid98/pbit-ising-pynq](https://github.com/archnoid98/pbit-ising-pynq) | none stated | Verilog + Python | 3 | Q8.8 | Sequential p-bit, 32-b Galois LFSR | PYNQ-Z2, 100 MHz | xsim testbench |
| [zachbe/digial-ising](https://github.com/zachbe/digial-ising) | MIT | Verilog | parametric | parametric | Ring-oscillator coupling (not MCMC) | AWS F1 | Icarus 5-node test |
| [harigovind1998/FPGA_BCP_acceleration](https://github.com/harigovind1998/FPGA_BCP_acceleration) | not stated | – | 630 vars / 22,400 clauses | – | SAT BCP clause processors | Zynq, 106.66 MHz | – ([arXiv 2312.11279](https://arxiv.org/html/2312.11279v1)) |

Not open: UCSB sIM/Niazi (code on request), Toshiba, Fujitsu.

**Verification practice that transfers to our build.**
1. A bit-exact C/Python model with the same RNGs, seeds, fixed-point widths and selection rule. Compare per-step traces (index, flag, E_off, T index, E) in simulation and on board (Anechoic §5.4; tsjshg).
2. Assertions: h_i equals a full recompute (periodic scrub), the running E is consistent, the grant is one-hot. the reference software study's `check_every` (qkp_nb.py:314–337) already does the software half.
3. For N ≤ 8 at fixed T with the offset off: state histograms vs the exact DA transition matrix, plus a chi-square test of selection uniformity on forced accept patterns.

## 4. CAM/TCAM (and CAM-like match lines) inside optimization or SAT hardware

Every system below except IMC-MCTS stores the problem: clauses, constraint weights or index maps. They write once per instance and search every iteration. IMC-MCTS stores exact search history in game-tree search. No hardware paper found stores visited states, tabu lists or learned nogoods in a CAM inside a local-search or Ising solver ([prior notes d2a](<$PROJECT/02_research_reports/research_notes/TCAM directions to beat tabu/d2a_hardware_cam_optimization.md>); [r5](<$PROJECT/02_research_reports/research_notes/TCAM hardware cost and new domains/r5_tcam_native_optimization_primitives.md>); a fresh alphaXiv search on 2026-10-30 found nothing new).

| System (venue, year) | CAM role and what a row stores | Query per iteration | Measured / simulated gain | Baseline (and weakness) | Status | Citation |
|---|---|---|---|---|---|---|
| **KLIMA** (Pedretti et al., HPE/UCSB/FZJ/1QBit, npj Unconv. Comput. 2025) | One k-SAT clause per 2T2R TaOx RRAM TCAM row. Cell '1' = [HRS, LRS], '0' = [LRS, HRS], X = [HRS, HRS]. Absent literal = X. A match (Hamming distance 0) means "clause violated", so the row stores the falsifying assignment | Current assignment on the SLs. ML current ∝ Hamming distance. Violated: one threshold, Θh = 1. Break/critical (exactly one true literal): window Θl = 0 < ML < Θh = 2. TIA + comparator sensing. A 1T1R DPE crossbar turns the violated and critical vectors into make/break; gain = make − break; uniform noise (64-bit xorshift + 4-bit R2R DACs) or Gaussian noise (alias LUT); VCDL-based WTA picks the flip | Up to 182× TTS and ETS for uniform random 4-SAT | WalkSAT-SKC on a *simulated* Xeon (SST + CACTI, "a lower bound for the CPU energy"). The paper itself says iterations-to-solution are "comparable" to WalkSAT-SKC, so the gain is all per-iteration hardware | Simulated, TSMC 28 nm + RRAM; V_DD 0.9 V, V_read 0.3 V, R_LRS 500 kΩ | [arXiv 2501.07733](https://arxiv.org/html/2501.07733) §2.2, Fig. 2, Alg. 1, SI Eqs. 9–12, Table S1 (XOR 1.84 fJ, comparator 5.5 fJ, **PRNG 365 fJ**, VCDL 7.9 fJ, WTA 3.4 fJ, register 7.16 fJ). Clock period inconsistent: 6 ns in Methods §4.3 vs 2 ns in Table S1 (uncertain) |
| **CAM SAT/SMT** (Pedretti et al., IEDM 2023) | CAMs "for asserting and solving" SAT/SMT | – | "~6.5× lower area and ~4× lower energy per search" than in-memory HNN solvers; "up to 175× faster" TTS at 150 variables | In-memory Hopfield-NN solvers | Abstract only | [IEEE 10413853](https://ieeexplore.ieee.org/document/10413853) (abstract-level) |
| **HyCiM** (Qian, Yang, Ni, Vardar, Kämpfe, Yin, DAC 2024) | CAM-like "inequality filter" for one knapsack constraint Σwᵢxᵢ ≤ C. 1FeFET1R multi-level cells, 5 levels (w = 0–4). Weight wᵢ (0–64) is split over the 16 cells of column i. Array 16×100 (rows × items), plus a 16×100 replica array encoding C | xᵢ gates column i (0 V if xᵢ = 0). ML precharged to VDD = 2 V. A 4-phase staircase read V_read4→V_read1 turns on a cell storing level k in k phases, so V_ML = VDD − k·(∫I_D dt / C_ML)·xᵢ (Eq. 7). Comparator: differential preamp, then dynamic latch, working ML vs replica ML. Infeasible → reject before the QUBO crossbar runs | 98.54% vs 10.75% success; QUBO size −88.06% to −99.96%; precision from 16–25 bits to 7 bits | D-QUBO: slack-variable penalty with fixed α = β = 2, untuned, on the same SA. Target was 95% of optimum. The gain is algorithmic (filter vs untuned penalty) and software-reproducible | Filter SPECTRE-simulated (Preisach FeFET + TSMC 28 nm); 32×32 FeFET crossbar fabricated but filter not. No filter energy, latency or area reported. Pulse widths, V_read, R and C_ML not given | [arXiv 2410.14111](https://arxiv.org/html/2410.14111v1) §3.3 (Eq. 7, Eq. 10), Fig. 4–5, §4.1–4.3, Table 1 |
| **IMC-MCTS** (Molom-Ochir et al., Duke + HP Labs, arXiv Jul 2026) | History-side, **exact match**. Each tree node's board state is a CAM pattern. One query returns the addresses of all children. 6T-SRAM selection-CAM cells 0.092 µm² and 16T FSM-TCAM cells 0.676 µm² at 22 nm; 1,024 entries = 0.049 mm² (≈2.7% of chip) | One query per tree step, replacing a 160 ns CPU hash lookup | 96× energy efficiency vs CPU (≈1.4× algorithmic × ≈68× hardware); 65–2,059× vs H100 | Threadripper PRO 5945WX hash table | Simulated at 22 nm with fabricated-RRAM parameters | [arXiv 2607.22869](https://arxiv.org/abs/2607.22869) [PRIOR-FULL in d2a notes] |
| **UMN FPGA-ASIC Ising orchestrator** (Yin…Kim, ICCAD 2026) | Bookkeeping only: row/column CAM pairs map global spin IDs to local 45×45 subproblem indices | Index lookup while building subproblems | 9.8–46.5× end-to-end TTS; 85–116× device power. "Proposes no new Ising-solving algorithm" | Optimised CPU orchestrator (i5-11500) | MEASURED (28 nm oscillator chip + FPGA) | [arXiv 2602.15985](https://arxiv.org/abs/2602.15985) §5.3 [PRIOR-FULL] |
| **Yue et al.** (CSTIC 2024) | RRAM CAM "for sparsity-aware" operation, alongside MAC and TRNG | – | – | – | Abstract only, no numbers | [OpenAlex](https://api.openalex.org/works/doi:10.1109/cstic61820.2024.10531826) (uncertain) |
| **HPE patents** US 12119061, 12277971, 11899965, 12307124 | TCAM clause rows (negated DNF), k-SAT verification, aCAM k-SAT | – | – | – | Patents; IP collision risk for "clauses in TCAM" | [US12119061](https://patents.google.com/patent/US12119061B2/en) [PRIOR] |
| **XOR-CNF SAT in memory** (Im, Böhm, Pedretti et al., Nat. Commun. 2026) | Memristor crossbars; no CAM in the abstract | – | ~10× speed and ~1000× energy vs SAT solvers. ≈90 pJ/iteration, **PRNG ≈80%**, clause evaluation ≈9% | – | Three 64×64 RRAM arrays | [OpenAlex](https://api.openalex.org/works/doi:10.1038/s41467-026-69465-2) [PRIOR, ABS] |
| **FPGA SAT/BCP accelerators** (Davis et al. DAC 2008; Thong & Nicolici; Govindasamy et al. 2023) | No CAM. Clauses go to clause processors or BRAM linked lists. Learned clauses are not described as held in hardware | Broadcast of decisions and implications | 175 vs 102 M BCP/s (1.7×) over Thong; up to 6.32× over software (Zynq, 106.66 MHz, 13,151 LUTs) | Prior FPGA BCP; software DPLL | MEASURED FPGA | [arXiv 2312.11279](https://arxiv.org/html/2312.11279v1) §I–III, Tables I–II; repo [harigovind1998/FPGA_BCP_acceleration](https://github.com/harigovind1998/FPGA_BCP_acceleration) (licence not stated) |
| **Hardware tabu** | Tabu state in BRAM or registers, never in a CAM. Kanazawa's FPGA swap-based tabu (max clique) does not say how tabu memory is stored. The NCE 2026 "tabu-inspired inhibitory" FPGA Ising solver keeps tabu state in BRAM, up to 850 spins (snippet only). Fujitsu DAv3 runs tabu in a CPU software layer | – | Up to 51.1× vs CPU SBTS (Kanazawa) | CPU original | MEASURED FPGA / snippet | [Kanazawa, JIP 30:513 (2022)](https://www.jstage.jst.go.jp/article/ipsjjip/30/0/30_513/_article); [IOP 10.1088/2634-4386/ae9006](https://iopscience.iop.org/article/10.1088/2634-4386/ae9006) (uncertain); [Shaglel et al. 2025](https://arxiv.org/html/2507.22117v2) |
| **the reference software study (our software)**: D5c thermometer hinge pricer | n rows (items) × m·Q cells: Q-level thermometer code of each item's weight on each constraint. Written once per instance | 2 searches per step (add, remove); query masks levels ≤ slack to X; mismatch count = hinge-penalty change | Q = 8 beat the strengthened HyCiM-style filter in 5 of 6 cells (+0.33 to +0.97 gap points). Worse than the exact digital hinge in 5 of 6 (+0.17 to +0.55). Q = 16 equivalent to the exact hinge in 4 of 6. Adaptive hinge best in 5 of 6. Under σ = 0.5 count noise it holds in only 1 of 6 | Exact hinge, adaptive hinge, swap-strengthened filter, at equal steps and pre-registered | Software, ideal or noisy device model | [D5c REPORT]($PROJECT/sw_ref/experiments/d5c_qhinge/REPORT.md) lines 10–27 and erratum |
| **the reference software study**: visited-state / trap TCAM | M = 256 rows of n-bit patterns plus care masks (ternary stored). Radius search | Per-candidate check each step; write on stall | Never beat the best memoryless restart rule (0 of 40 regimes with CI above 0). A lockout counter recovers 71% [61, 80] | Tuned memoryless restart rules | Software | [CLAIMS #3, #23]($PROJECT/sw_ref/docs/CLAIMS.md) |

**Pattern across the table.** Every published hardware gain is either (a) a constant-factor per-iteration gain over a CPU running the same search (KLIMA's iterations match WalkSAT; IMC-MCTS is ≈1.4× algorithmic), or (b) a quality gain over an untuned penalty QUBO (HyCiM). No paper compares against a tuned digital equivalent in the same hardware. Our H1 control (TCAM off, area reallocated) and C2 control (bit-exact digital pricer in the same RTL) would be new. **[Inference]**

## 5. How constraints were mapped into CAM words or penalty units

| Method | Constraint type | Hardware mapping | Cost / limits | Used by | Citation |
|---|---|---|---|---|---|
| **Slack-variable penalty QUBO** (D-QUBO) | Linear inequality Σwᵢxᵢ ≤ C | Binary slack bits added as extra spins; penalty α(Σwx + s − C)² folded into J | Extra spins: 200–2636 variables instead of 100. J range grows to 4×10⁴–2.6×10⁷ (16–25 bits). Untuned α, β = 2 gave 10.75% success | HyCiM's baseline; most CiM annealers | [HyCiM §4.2](https://arxiv.org/html/2410.14111v1) |
| **Match-line inequality filter** | Single inequality | Weights as multi-level FeFET states down a column, xᵢ on the gate, staircase read gives V_ML ∝ Σwᵢxᵢ. Replica ML encodes C. Latched comparator returns a feasible bit | One constraint only. Margin is smallest at Σwx ≈ C, where QKP optima lie (Ohno Prop. 1). Validation zoom 0.99–1.01 normalised; no error rate reported | HyCiM | [HyCiM §3.3](https://arxiv.org/html/2410.14111v1); [Ohno et al. 2024 §II.B](https://arxiv.org/abs/2403.19175) |
| **Clause as ternary row** | CNF clause | Store the falsifying literal pattern, X for absent variables. Hamming-distance thresholds give "violated" (d = 0) and "critical" (d = 1) | One row per clause, written once. Resources do not grow with k (vs O(k²α) for QUBO HNN, Eq. 7) | KLIMA, HPE patents | [KLIMA §2.2, Eq. 7](https://arxiv.org/html/2501.07733) |
| **Range → TCAM prefix expansion** (packet classification) | Integer range [a, b] on a W-bit field | Split the range into ternary prefixes | Worst case 2W − 2 entries per range (30 for 16 bits). SRGE Gray coding: 2W − 4. Rottenstreich–Keslassy: W entries, optimal for prefix encodings | Router TCAMs | [Bremler-Barr & Hendler, SRGE](https://www.cs.bgu.ac.il/%7Ehendlerd/papers/Bremler-barr-hendler-SRGE-Sep-19-2010.pdf); [Rottenstreich & Keslassy, Infocom 2010](https://webee.technion.ac.il/~isaac/p/infocom10_tcam.pdf) |
| **Fence (thermometer) encoding, DIRPE** | Integer range | Encode a k-bit value as a (2ᵏ − 1)-bit thermometer code. Any range becomes **one** ternary word (expansion 1) | Width is exponential in k, so it is practical only for coarse fields (k ≤ 3–4, i.e. Q ≤ 8–16 levels) | Lakshminarayanan, Rangarajan, Venkatachary, SIGCOMM 2005 | [Paper Digest entry](https://www.paperdigest.org/certificate/d7ed19e94dd99097); [USPTO 7555594](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7555594) |
| **Thermometer hinge (ours)** | m linear inequalities, soft | DIRPE-style fence code of each quantised weight. The query masks levels ≤ slack, so the **mismatch count** (not match/miss) equals the hinge increase Σⱼ max(0, Wqᵢⱼ − ⌊slackⱼ/dq⌋) | Row width m·Q (128–256 cells for the winning m = 16–32 at Q = 8). Needs a count readout of 7–9 bits. Q = 8 loses to the exact hinge in 5/6 cells; Q = 16 ties in 4/6 | the reference software study D5c | [qkp_nb.py:96–158]($PROJECT/sw_ref/experiments/d5c_qhinge/qkp_nb.py); [D5c REPORT]($PROJECT/sw_ref/experiments/d5c_qhinge/REPORT.md) |
| **Analog CAM interval cell** | Range [lo, hi] per variable | 6T2M cell: two memristor conductances set lo and hi; a match means the analog input lies inside | Match or miss only, no count. Analog input DAC needed | Li et al. 2020; Pedretti 2021 (trees); Yin 2024 FeFET ACAM | [arXiv 1907.08177](https://ar5iv.labs.arxiv.org/html/1907.08177) |
| **Native one-hot / inequality modes** | One-hot (1-way, 2-way), first-order inequality | Vendor hardware/firmware. With `set_inequalities=True` (default), first-order inequalities go to the DA's `inequalities` parameter; otherwise a penalty is generated | Internals undisclosed. No independent benchmark of native vs penalty mode found | Fujitsu DA3c/DA4 via Fixstars Amplify | [Amplify Fujitsu client docs](https://amplify.fixstars.com/en/docs/amplify/v1/clients/fujitsu.html) [PRIOR, DOC] |
| **Mean-field constraint (MFC)** | Balance / cardinality (Potts partitioning) | Population counts N per state are accumulated once per sweep (32-cycle batched popcount), filtered N̂ = αN + (1 − α)N̂, then broadcast as one bias per state. The local-field term is βλN̂_{s} − βλN̂_{c} − βλ, with βλ precomputed by the host per β-step. 37 cycles per sweep (2 for two colour groups, 35 for the controller) at 100 MHz on Alveo U250; β Q6.3 10-bit; 800-step staircase schedule | 304,363 LUTs, 123,046 FFs, 81 BRAM, 3 DSP; 10.7 W estimated; 1000 nodes. Exact constraint encoding *not* implemented on FPGA; CPU comparison shows ≤ 2.25% mean-cut difference | Callahan-Coray, Lee, Jiang, Camsari, npj Unconv. Comput. 3:50 (2026) | [arXiv 2602.04200](https://arxiv.org/html/2602.04200) §III, §VII.4–VII.6, Table 1, Eq. 10–12 |
| **Vectorized multistate encoding** | One-hot colour / permutation | Binary colour code with truth-table interactions; infeasible states unreachable | 1.5–4× fewer nodes than one-hot. VCU118, 1024 p-bits, 90 MHz, ≈5 W | Garg & Salahuddin 2025 | [arXiv 2505.20250](https://arxiv.org/abs/2505.20250) [PRIOR-FULL] |
| **Lagrangian multipliers (SAIM)** | Equality / inequality | Software. Multipliers updated once per anneal | 99.8% (QKP n = 100) vs 88.8% tuned penalty. MKP: only 5.1% feasible samples | Delacour 2025 | [arXiv 2501.04971](https://arxiv.org/abs/2501.04971) Tables II–V [PRIOR-FULL] |
| **Incremental ΔE crossbar** (not a constraint method, but the ΔE datapath alternative) | – | ΔE = 4σ_rᵀJσ_c, with σ_c = flipped spins and σ_r = the rest; only flipped columns are activated. DG-FeFET I_SL = x·G·y·z with back-gate voltage as temperature, so exp is replaced by f(T) = a/(bT + c) + d. 8:1 muxed ADCs dominate energy | 0.9 µJ / 4.6 ms TTS on 3000-node Max-Cut (SPECTRE, 22 nm) | Qian et al. DAC 2025 | [arXiv 2504.21280](https://arxiv.org/abs/2504.21280) §3.2–3.4, Eq. 9–11, Fig. 6–7, Table 1 |

**What this means for our word design [Inference].**
1. The pricer's queries are only ever "0" or "X", and its stored bits are only 0 or 1. Per query column, a row discharges iff stored = 1 and the column is unmasked. The arithmetic is popcount(stored AND mask): a binary-stored, masked-search count, the same AND-accumulate a CiM column does. A 1FeFET (or 1FeFET1R) binary cell would suffice for the pricer. Stored X is needed only for the visited-state control. If one cell type must serve both, use the 2FeFET TCAM cell and drive only one of its two search lines in pricer mode.
2. Fence encoding is the right primitive, and it explains the row-width problem: the width is m·Q, linear in Q, against W prefixes for binary ranges. Q = 8 gives 8 cells per constraint; Q = 16 gives 16.
3. Per-constraint multipliers λⱼ (the adaptive hinge, which won 5 of 6 cells) can be expressed as cell replication (λⱼ copies of constraint j's Q cells). That is a rewrite at multiplier-update events (≈10²–10³ per run). Alternatively, use segment-wise counts with a digital λⱼ multiply: one 64-cell segment per constraint group, then digital weighting. This matches the "segmented rows" move in the this project plan.

## 6. Reusable pieces from sw_ref (read-only inventory)

Source: read-only map of `$PROJECT/sw_ref`; key lines re-checked by hand on 2026-10-30. Nothing was run. Repo licence: MIT (`LICENSE`); CITATION title "the reference software study: when does search-history memory help local search? (histmem)".

| Path | What it does | Hardware reuse | Blockers for bit-exact RTL comparison |
|---|---|---|---|
| `$PROJECT/sw_ref/experiments/d5c_qhinge/qkp_nb.py` | Numba DA-style parallel-trial annealer for QMdKP. Rules: filter, penalty (exact hinge), count, qhinge (thermometer TCAM hinge), qhinge + noise, filter_swap, adaptive. `make_instance` :37, `_kernel` :56, `run` :358 | **Primary golden model** for the annealer + pricer, and the instance generator | PCG64 `default_rng` seeded `[seed,n,m,inst_seed,7]`; one `rng.random(n)` vector per step plus `rng.integers(0, Eg)` pick (:247). Float64 T, `np.exp`, E_off, λ·dq·S; dq = 50/8 = 6.25 is non-integer (:371) |
| `$PROJECT/sw_ref/experiments/d5_tcamscout/scripts/mkp_engine.py` | Vectorised NumPy pilot of the same engine. Docstring :1–40 is the clearest written spec of the thermometer encoding; qhinge :93–98 | Spec text for the TCAM word | Same RNG stream; NumPy vs libm `exp` may differ by 1 ulp |
| `$PROJECT/sw_ref/experiments/d5c_qhinge/qhinge.py` | Harness: NS = (200, 500), MS = (4, 16, 32), tune instances 5100–5103, test instances 5000–5019, seeds 100–109, budget = 100000·n/200; config grids :45–83 | Regression matrix (n, m, Q, seed) | λ = lsc·n/200; T in units of mean diagonal profit |
| `$PROJECT/sw_ref/experiments/d5c_qhinge/cost_note.py` | Per-step op counts: row = m·Q cells, 2 searches, 2·n·m·Q cell evaluations, count bits = ⌈log₂(mQ + 1)⌉ | Array sizing, count width | Energy numbers superseded by the erratum |
| `$PROJECT/sw_ref/experiments/d5c_qhinge/prereg/qhinge.md` | Pre-registered design: encoding :56–57, noise model :54–55, limits :195–198 | Written spec | – |
| `$PROJECT/sw_ref/histmem/fast/kernels.py` | Numba engines incl. `pt_core` :416 (parallel trial), `tcam_any` :249 and `row_threshold` :286 (TCAM search), `rng_next` :121 (**xoshiro256\*\***), `splitmix_fill` :149 | Best RNG to port to RTL; golden for Max-Cut DA + visited-state control | `rng_float` is a 53-bit double; acceptance uses float `np.exp`; pick = `int(rng_float·n)` |
| `$PROJECT/sw_ref/histmem/engines/parallel_trial.py` | Python DA-style parallel trial for Max-Cut with memory plug-in, offset escape, aspiration, stall restarts | Readable reference for H4 control | NumPy Generator with `shuffle`: not portable |
| `$PROJECT/sw_ref/histmem/fast/engine.py` | Method spec → kernel; PT_DEFAULTS T0 = 4, α = 0.999, T_min = 0.3, dE_off = 1, K = 2000, L = 10, C_MAX = 8 | Parameter defaults | – |
| `$PROJECT/sw_ref/histmem/ptemp/cpu.py` | Parallel tempering with a host-tabulated acceptance table `etab[slot,-d]`, integer weights, CPU = GPU bit for bit (:9–10) | **Closest existing pattern to an RTL acceptance LUT** | Table entries float; swap uses float exp |
| `$PROJECT/sw_ref/histmem/fast/sa.py`, `$PROJECT/sw_ref/histmem/engines/tabu_classic.py` | Sequential Metropolis SA (geometric β, xoshiro256\*\*); classic tabu | Software baselines | Float β·dE |
| `$PROJECT/sw_ref/histmem/memory/trap_ideal.py`, `$PROJECT/sw_ref/histmem/memory/bits.py`, `$PROJECT/sw_ref/histmem/memory/base.py` | Ideal ternary TCAM: `pats`/`cares` as (M, ⌈n/64⌉) uint64; 64-cell words; `word_mismatches = popcount((pat ^ key) & care)`; match rules "word" (≤ r_w per 64-cell word) and "total"; dedup-before-write; replacement ring or fewest-match; default M = 256 | **Golden model for the visited-state TCAM (negative control)** and the 64-cell word layout | Exact; **no noise or false-match hook** (noise exists only in qhinge) |
| `$PROJECT/sw_ref/histmem/memory/hash_visited.py`, `$PROJECT/sw_ref/histmem/memory/hash_trap.py` | Exact-set baselines (BLAKE2b-16 digests, FIFO 10⁶; fast kernel uses 64-bit Zobrist) | C2 digital-equivalent control for H4 | – |
| `$PROJECT/sw_ref/histmem/core/ideal.py` | Ideal integer fields h = Ws with incremental `update_after_flip` | Field-update golden | Integer when graph is integral |
| `$PROJECT/sw_ref/histmem/instances/` (`registry.py`, `rudy.py`, `gset.py`, `gsetlike.py`, `structured.py`, `small.py`, `planted.py`, `xorsat.py`, `biqmac.py`) | Seeded Max-Cut generators. Rudy text format ("n m" then "i j w", 1-indexed); `write_rudy` dumps. xorsat and biqmac have certified optima | Test-vector files with known optima for the Max-Cut mode | Generated in memory from seeds |
| `$PROJECT/05_external_tools/open_source_implementations/benchmarks_and_eval_tools/gset/stanford_yyye_Gset/` | G-set Rudy files + `gset_best_known_cuts_2026-10-17.csv` | Instance files, ±1 weights | – |
| Tests: `$PROJECT/sw_ref/tests/test_d5c_qhinge.py` (port bit-identical to pilot; Q = 50 equals exact hinge at :40; σ = 0 equals ideal; brute-force optimum), `test_d5_mkp_engine.py`, `test_trap_memory.py::test_search_equals_brute_force`, `test_fast_engine.py::test_kernel_tcam_equals_brute_force`, `test_core.py::test_core_check2_incremental_matches_recompute`, `tests/data/golden_round2.json` | Templates for RTL regression: pricer equivalence, brute-force optimum on tiny n, incremental vs recompute | – | – |
| Results: `$PROJECT/sw_ref/experiments/d5c_qhinge/results/confirm/` (`test.jsonl.gz`, `tune.jsonl.gz`, `selection.json`, `summary.csv`, `analysis.json`) | Per-run best_f and counters | Statistical (not trajectory) reference for "integerised model matches float model" | – |

**Instance value ranges → RTL widths** (from `make_instance`, qkp_nb.py:37–47). P upper triangle U{1..100} kept with density 0.5, symmetrised; diagonal d U{1..100}; W U{1..50} (m × n, int64); C_j = ⌊0.25·Σᵢ w_ji⌋. Nothing is on disk: instances are regenerated from (n, m, seed) with key `[20261021, n, m, seed]`. Widths for n ≤ 256 (my arithmetic): P, d 7-bit unsigned; w 6-bit; load ≤ 256·50 = 12,800 (14 bits); signed slack 15 bits; field h ≤ 100 + 100·255 = 25,600 (15 bits unsigned, 16 signed gain); objective f ≲ 1.7×10⁶ (21 bits). At n = 500: field 17 bits, objective 22–23 bits.

**Exact pricer semantics to reproduce in RTL** (qkp_nb.py, checked by hand):
- Per step and constraint: sl_j = C_j − load_j; flo_j = ⌊max(sl_j, 0)/dq⌋ (:96–105). Stored level k of cell (i, j) = [Wq_ij ≥ k], Wq = ⌊W/dq⌋ (:372).
- Add (x_i = 0): S = Σ_j max(0, Wq_ij − flo_j) (:139–143). TCAM query: "0" at levels k > flo_j, X at k ≤ flo_j; a stored 1 under a "0" query is a mismatch.
- Remove (x_i = 1): S = −Σ_j ⌊min(w_ij, ov_j)/dq⌋ with ov_j = max(−sl_j, 0) (:149–153). Query: "0" at levels k ≤ ⌊ov_j/dq⌋, X elsewhere.
- geff_i = gain_i − λ·unit·dq·S (:158). Acceptance: u_i < exp(min(0, (geff_i + E_off)/T)) (:169–178). Uniform pick among the accepted (:245–247). No acceptance → E_off += dE_off·unit, else E_off = 0. Flip k: h_q += ±P_qk for all q; load_j += ±W_jk (:249–255). T *= α every step (α = (T_min/T0)^(1/(budget−1)), :370). No restarts.
- Noise (qhinge + noise): c' = max(0, rint(c + σ_s·N(0,1) + off_row)), with off_add and off_rem ~ N(0, σ_o) fixed per row per run, drawn from a separate stream `[seed,n,m,inst,11]` (:144–157, :363–368).
- Integer-exact parts that can be checked per step: fields, gains, loads, slack, and the counts S. **Integerisation recipe [Inference]:** multiply everything by Q/w_max so dq disappears. flo_j = ⌊Q·max(sl_j, 0)/w_max⌋ and Wq = ⌊Q·w/w_max⌋ are exact integer divisions (or a w_max that is a multiple of Q, at the cost of changing the D5c instance law). Then compare Q·gain_i against Λ·S with integer Λ = λ·unit·w_max.

## 7. Risks and open questions

Ordered by how likely each is to stop the build or void the claim.

1. **Count readout, not the cells, decides energy and feasibility.**
   - The pricer needs a 7-bit count (0…64) from every enabled row on every search: N = 256 rows × 2 searches per step.
   - Measured multi-level Hamming sensing stops at 8 levels in a 1×8 word. In a 1×64 word only HD ≤ 8 resolves ([Ni 2019 SI Fig. 8a](https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41928-019-0321-3/MediaObjects/41928_2019_321_MOESM1_ESM.pdf)).
   - Discharge-time resolution shrinks as 1/(n(n−1)) and degrades with row position ([Narla 2024](https://arxiv.org/abs/2403.15328)).
   - The only linear measured readout (charge-domain 2FCM) is 16 cells, and it uses a capacitor device outside our FeFET set ([Zhou 2025](https://www.nature.com/articles/s41467-025-63190-y)).
   - The D5c erratum already found that an unverified 0.9 pJ/row readout moves digital/TCAM from 77× to 5–28× ([D5c REPORT erratum]($PROJECT/sw_ref/experiments/d5c_qhinge/REPORT.md)).
   - *Open:* which readout (charge-domain, segmented 8×8 flash, or clamped current) gives ≤ 0.5 LSB error at 64 cells and under 1 pJ per row? This is the first G4 question.
2. **The TCAM computes the second-best rule.**
   - Q = 8 lost to the exact digital hinge in 5 of 6 cells; Q = 16 tied in 4 of 6. A per-constraint adaptive hinge, which a single match line cannot compute, was best in 5 of 6.
   - Under σ = 0.5 count noise the gain survived in 1 of 6 ([D5c REPORT]($PROJECT/sw_ref/experiments/d5c_qhinge/REPORT.md)).
   - The C2 control (digital pricer in the same RTL) may simply win at equal area. Segment-wise λ_j weighting (§5) is the main mitigation. It adds a digital multiply per segment and must be costed.
3. **Device-model and tool fidelity.**
   - No validated, licensed, open full FeFET Verilog-A model exists. PFECAP (GPL-2.0) is a Preisach capacitor that needs a FET with a charge pin, and no simulator is listed as tested ([pfecap](https://github.com/supadupaplex/pfecap)).
   - ngspice says OpenVAF is unmaintained and will be removed ([ngspice OSDI](https://ngspice.sourceforge.io/osdi.html)).
   - Calibration targets come from papers only: σVT 54–180 mV, memory window 0.46–1.5 V, ±4 V / 0.2–10 µs writes.
   - Polarity conventions differ between papers (TAP-CAM, uncertain).
   - *Open:* does OpenVAF compile PFECAP plus a modified BSIM4/PTM, and does a 64-cell row transient converge in ngspice in reasonable time? Smoke-test before G4.
4. **Bit-exact verification needs a new golden model.**
   - Every existing golden model uses float64 T, `exp`, E_off and λ·dq·S, with PCG64 or float-converted xoshiro draws (§6).
   - An integerised model must be written (§1.4) and shown to reproduce the D5c statistics on the stored seeds. Otherwise RTL results are not comparable to the reference software study.
   - *Open:* which acceptance approximation (log-LUT threshold vs exp-LUT) keeps D5c gaps within the 0.17-point margin?
5. **Amdahl and equal-area accounting can erase the gain.**
   - In a DA, digital pricing is m clip-and-add units per lane, about 2·n·m operations per step.
   - The TCAM replaces these with 2 searches plus N readouts.
   - On FPGA, the TCAM is emulated in LUT/BRAM. It competes with the J memory, and BRAM was already the binding resource at 256 spins ([PoliTo arXiv 2510.12407](https://arxiv.org/html/2510.12407v2)).
   - FPGA energy says nothing about a FeFET ASIC: the FPGA/ASIC gap is about 35× area and 14× dynamic power at 90 nm ([Kuon & Rose 2007](https://www.eecg.utoronto.ca/~jayar/pubs/kuon/kuontcad06.pdf)).
   - The claim must be three separately labelled numbers: FPGA-measured, synthesis-estimated digital, and SPICE-projected TCAM.
6. **Variation and drift at the capacity boundary.**
   - Optima sit at Σwx ≈ C (Ohno Prop. 1), exactly where the masked levels change. A ±1 LSB count error there flips the sign of the hinge decision.
   - HyCiM reported no misclassification rate near the boundary ([HyCiM §4.1](https://arxiv.org/html/2410.14111v1)).
   - Retention and read disturb over 10⁸–10⁹ searches per instance are not characterised for any FeFET CAM.
7. **RNG energy and correlation.**
   - PRNG dominates energy in CAM SAT solvers: 365 fJ per draw in KLIMA, ≈80% of iteration energy in XOR-CNF.
   - DSSA shares one random bit across 16 spins ([arXiv 2609.09559](https://arxiv.org/abs/2609.09559)).
   - Per-lane 32-bit generators at N = 256 may cost more than the pricer. Shared or cheap generators risk correlated acceptances. Both must be in the energy model and the ablation list.
8. **Selection-circuit bias.** The golden model picks uniformly among accepted flips. Neither the DA patent tree (1-bit tie-break per node) nor a random-start priority encoder is uniform when accepted bits cluster. The RTL must use the count-tree walk, or the golden model must adopt whatever the RTL does (§1.3, §3.2).
9. **Negative control (H4) needs a different TCAM mode.**
   - The visited-state control needs stored X (care masks), threshold-match sensing, and writes at stall events. Writes are ≈10²–10³ per run, and Si FeFET endurance was 10⁴–10⁵ historically ([arXiv 2107.03854](https://arxiv.org/pdf/2107.03854)).
   - The same macro must support both modes, or the control is not "the same RTL".
10. **Licences and baselines.**
    - No open Fujitsu-DA RTL exists. The DA's internals come from papers and patents only.
    - The PoliTo SB repo is the only open memoryless reference found (see §3.3).
    - The leading p-bit FPGA code is "on request" ([Niazi et al.](https://arxiv.org/html/2303.10728v2)).
    - The HPE clause-in-TCAM patents constrain any SAT extension ([US12119061](https://patents.google.com/patent/US12119061B2/en)).

**Open questions to settle before RTL freeze.**
- (a) Q = 8 or Q = 16 for the science configuration? Q = 16 ties the exact hinge in 4/6 cells but doubles row width to 256–512 cells at m = 16–32.
- (b) A single 2FeFET cell for both modes, or 1FeFET1R for the pricer (half the area) plus a separate 2FeFET array for the control?
- (c) Per-step geometric T (as in the golden model) or a staircase schedule (as in MFC and most hardware), which lets the acceptance LUT be reloaded per stage?
- (d) Should rows with x_i = 1 be disabled (selective precharge) during the ADD search, which halves ML energy? Yes in the RTL; to confirm in SPICE that disabled rows do not disturb the count lines.
- (e) Is the `elig` ordering (index order, then uniform pick) acceptable as the hardware definition, or should the golden model change to the hardware selector?
