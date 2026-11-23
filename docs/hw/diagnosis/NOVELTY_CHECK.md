# Novelty check: FeFET CiM Ising design (I11 + Kc2 + mitigations + T-1/T-2 + barrier fixes)

Date 2026-11-22. This is version 2, from a full search. Sources were alphaXiv (discover and full-text reads), Consensus (four searches) and WebSearch (six searches).
I read the full text of the four closest papers: Salim 2026, SKI-SAT, BEOL FeFET SB, and the DA abstract plus its offset rule. Every citation was confirmed against a search record or the paper itself. Citations I could not confirm were removed.
CLAIMS_NARROWED.md does not exist in this worktree.
Context: S2 reports **no energy advantage shown** against B3 at n480 (under frozen pricing it is a loss). H8 shows wins against B1, the Yin-type FeFET SA. Any novelty claim must sit inside these limits.

## Verified references
- [Y24] X. Yin, Y. Qian, A. Vardar et al., "Ferroelectric compute-in-memory annealer for combinatorial optimization problems", Nat. Commun. 15, 2419 (2024). https://www.nature.com/articles/s41467-024-46640-x
- [Q24] Y. Qian, Z. Yang, K. Ni, A. Vardar, T. Kämpfe, X. Yin, "HyCiM: A hybrid computing-in-memory QUBO solver for general combinatorial optimization problems with inequality constraints", DAC 2024. https://arxiv.org/abs/2410.14111
- [Q25] Y. Qian et al., "Device-Algorithm Co-Design of Ferroelectric Compute-in-Memory In-Situ Annealer for Combinatorial Optimization Problems", DAC 2025. https://arxiv.org/abs/2504.21280 . It reformulates the problem as **incremental-E, cutting the VMV from O(n^2) to O(n) in a DG-FeFET crossbar**.
- [Q25b] Y. Qian, A. Vardar, ..., K. Ni, T. Kämpfe, X. Yin, "BEOL Ferroelectric Compute-in-Memory Ising Machine for Simulated Bifurcation", arXiv 2512.17165 (2025). It uses a 32x256 FeFET chip running deterministic "light SB" with column ADCs and shift-add.
- [H26] X. Huang et al., "A Scalable Compute-in-Memory Ising Machine for Combinatorial Optimization Problems", IEEE-NANO 2026. It uses a 1FeFET1R array, compression of sparse J, and MESA.
- [B25] M. K. Bashar et al., "FIMA: A Scalable Ferroelectric Compute-in-Memory Annealer for Accelerating Boolean Satisfiability", IEEE JxCDC (2025).
- [S23] T. Soliman et al., "First demonstration of in-memory computing crossbar using multi-level cell FeFET", Nat. Commun. (2023).
- [C20] F. Cai et al., "Power-efficient combinatorial optimization using intrinsic noise in memristor Hopfield neural networks", Nat. Electron. 3, 409-418 (2020).
- [J23] M. Jiang, K. Shan, C. He, C. Li, "Efficient combinatorial optimization by quantum-inspired parallel annealing in analogue memristor crossbar", Nat. Commun. 14, 5927 (2023).
- [YU24] W. Yue et al., "A scalable universal Ising machine based on interaction-centric storage and compute-in-memory", Nat. Electron. 7, 904-913 (2024). It uses coarse-grained CSR sparse storage on 40 nm RRAM.
- [A19] M. Aramon, G. Rosenberg, E. Valiante, T. Miyazawa, H. Tamura, H. G. Katzgraber, "Physics-Inspired Optimization for Quadratic Unconstrained Problems Using a Digital Annealer", Front. Phys. 7:48 (2019). https://doi.org/10.3389/fphy.2019.00048 . Its features are parallel trial with incremental fields, and a **dynamic offset that is raised when no flip is accepted**.
- [YA21] K. Yamamoto et al., "STATICA: A 512-Spin 0.25M-Weight Annealing Processor With an All-Spin-Updates-at-Once Architecture ...", IEEE JSSC 56(1), 165-178 (2021). https://ieeexplore.ieee.org/document/9222223 . It has delta-driven updates of only the flipped spins.
- [G19] H. Goto, K. Tatsumura, A. R. Dixon, "Combinatorial optimization by simulating adiabatic bifurcations in nonlinear Hamiltonian systems", Sci. Adv. 5, eaav2372 (2019).
- [SA26] A. Y. Salim, J. Wu, ..., Z. Ignjatovic, "A 64-Spin All-to-All CMOS Ising Machine with Landscape Perturbation Achieving 2.28 nJ/Edge-Bit Energy-to-Solution", arXiv 2603.27402 (2026). It runs **gradient descent (greedy, no noise) plus periodic deterministic column-zeroing perturbation**.
- [SK25] A. Y. Salim, B. Selman, H. Kautz, Z. Ignjatovic, S. Köse, "SKI-SAT: A CMOS-Compatible Hardware for Solving SAT Problems", IEEE TCAS-I (2025). arXiv 2411.01028. It runs **greedy gradient descent plus a global perturbation pulse** (random onset, decaying rate) that disconnects satisfied clauses.
- [L25] Y. Liu et al., "Integrated Hardware Annealing Based on Langevin Dynamics for Ising Machines", DATE 2025.
- [CH26] T. Chen et al., "Fully Parallel Ising Machine with MRAM based p-bit Probabilistic Simulated Annealing", ISCAS 2026. It is stochastic SA with a "scaling back-off" **to prevent stagnation**.
- [N26] J. Núñez et al., "A neuromorphic digital Ising solver with Tabu-inspired inhibitory dynamics for scalable graph optimization", Neuromorph. Comput. Eng. (2026). It runs deterministic fixed-point tabu on an FPGA, with no RNG and no annealing schedule.
- [AA22] N. A. Aadit et al., "Massively parallel probabilistic computing with sparse Ising machines", Nat. Electron. 5, 460-468 (2022).
- [SR24] S. Sundara Raman, L. John, J. Kulkarni, SACHI (all-digital SRAM near-memory Ising), HPCA 2024; extended version at arXiv 2605.12959.
- [HZ26] M. Hizzani et al., "Impact of memory device precision in analog combinatorial optimization solvers", npj Unconv. Comput. (2026).
- [MO22] N. Mohseni, P. L. McMahon, T. Byrnes, "Ising machines as hardware solvers of combinatorial optimization problems", Nat. Rev. Phys. 4, 363-379 (2022).
- Algorithmic classics (standard references, not searched): Burke & Bykov, "The late acceptance hill-climbing heuristic", EJOR 258(1), 70-78 (2017); Lourenço, Martin & Stützle, "Iterated Local Search", Handbook of Metaheuristics (2003); Selman, Kautz & Cohen, "Noise strategies for improving local search", AAAI 1994.

## Per-element verdicts
| Element | Closest prior | Difference | Verdict |
|---|---|---|---|
| Multi-level FeFET crossbar, in-array fields, per-tile ADC | Y24, Q25b, H26, S23, B25 | Q25b already has a FeFET chip with column ADCs and shift-add; we differ only in tiling and ADC sizing | **Prior art exists** |
| I11 greedy, RNG-free, LUT-free acceptance with parallel select | A19 (parallel trial + select), SA26 and SK25 (greedy descent in hardware), N26 (deterministic, RNG-free), G19 and Q25b (deterministic SB) | Greedy best-flip selection in a NVM CiM array is new in its exact form, but every ingredient is published | **Incremental** |
| Kc2 stall-triggered random kick | A19 (offset raised on zero acceptance, which is stall-triggered but softens the barrier rather than kicking), SA26 (periodic deterministic perturbation), SK25 (randomly timed perturbation pulses), CH26 (anti-stagnation back-off), ILS and WalkSAT restarts | Our trigger is a stall counter (window K) and the move is an L-spin kick. I found no published Ising hardware that uses exactly this trigger and move | **Incremental** (the algorithm is classic ILS) |
| **(a)+(b) combination**: greedy acceptance plus a stall-triggered hardware kick in a CiM Ising machine | SA26 and SK25 are the nearest: greedy descent plus a hardware perturbation, but CMOS rather than NVM CiM, and periodic or random rather than stall-triggered. A19 is stall-triggered but non-greedy SA | **No exact prior found.** The novelty is narrow: the trigger type and the substrate. A reviewer can reasonably call it ILS in hardware. SA26 and SK25 must be cited and compared | **Narrowly novel, as a design point** |
| Variation mitigations (write-verify, differential coding, column calibration, bit-slicing) | Standard CiM practice; HZ26 (coupling precision in Ising solvers); S23 | The C2C-conditional, preregistered variation study is ours | **Prior art** (techniques); the study is a modest contribution |
| T-1 incremental field update | **Q25 (FeFET CiM, incremental-E, O(n))**, A19, YA21 (delta-driven) | We differ only in using row read plus 1-bit sense with digital field registers | **Prior art exists** (downgraded from v1) |
| T-2 sparse coupling storage | YU24 (CSR on RRAM), H26 (FeFET compression), Y24, AA22 | none | **Prior art exists** |
| Barrier fixes: burst accepting gain >= -1, late acceptance | Burke & Bykov 2017; threshold accepting; A19 offset; N26 tabu in hardware | Hardware versions; untested | **Prior art** (algorithm) |

## Overall verdict
- The only defensible novelty candidate is the **combination** of a temperature-free, RNG-free greedy acceptance with a stall-triggered kick in a multi-level FeFET CiM. It needs a direct comparison with SA26 and SK25 (greedy plus perturbation, CMOS) and with the DA offset (A19). It is a design-point contribution, not a new principle.
- Stronger framing: a **preregistered, variation-aware, energy-priced comparison** of that design against a Yin-type FeFET SA (large H8 win) and a DA-like digital baseline (S2: no advantage). Few Ising hardware papers report a negative result against a digital baseline, so this rigor is publishable as an empirical contribution.
- Do not claim T-1 or T-2 as novel; Q25 and YU24/H26 anticipate them. With T-1 the design converges on the DA/STATICA data flow, and reviewers will ask what the FeFET adds.

## Must-cite
Y24, Q24, Q25, Q25b, H26, B25, C20, J23, YU24, A19, YA21, G19, SA26, SK25, N26, CH26, AA22, SR24, HZ26, MO22, Burke & Bykov 2017, Lourenço ILS.
