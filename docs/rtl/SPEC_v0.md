# TIM v0: specification of the digital machine (TCAM-augmented Ising machine, version 0)

Status: v0, written 31 Oct 2026 (IST) before the RTL, then kept in step with it. Source of the design choices:
`docs/lit/hw_prior_art.md` §1 (recommended v0 architecture) and §6 (the reference software study pieces). Plan:
`02_research_reports/reports/this project TCAM Ising hardware plan.md` (gates G0–G5).

v0 is infrastructure. It is small, exact and checkable, not fast. Every number the machine computes is defined
below as integer arithmetic, and the Python golden model (`scripts/golden/tim_golden.py`) computes the same numbers
bit for bit.

## 1. What the machine does

The machine maximises a QUBO objective over x ∈ {0,1}^N:

    f(x) = Σ_i d_i x_i + Σ_{i<j} P_ij x_i x_j        (P symmetric, P_ii = 0)

It is a parallel-trial annealer in the style of the Fujitsu Digital Annealer. In each step:
1. every lane i (one lane per spin) prices its own flip, using its local field h_i = d_i + Σ_j P_ij x_j;
2. every lane draws a random number and decides on its own whether it would accept its flip;
3. one of the accepting lanes is chosen, uniformly at random;
4. that one spin flips, and every lane updates its field by one add (no matrix-vector product).

If no lane accepts, a dynamic offset E_off grows, which makes acceptance easier in the next step. It resets to 0 when
a flip is applied. The temperature T is one global register.

Two modes:
- **QUBO mode** (`knap = 0`). Max-Cut is loaded as a QUBO (§6.3).
- **Knapsack mode** (`knap = 1`). It adds m linear constraints Σ_i w_ji x_i ≤ C_j as a soft hinge penalty. The
  penalty change of every candidate flip comes from two TCAM searches per step (the "pricer"). This is the D5c
  thermometer hinge of the reference software study (`sw_ref/experiments/d5c_qhinge/qkp_nb.py`, rule `qhinge`), made integer.

## 2. Block diagram in words

```
     host config bus (cfg_*)                                  host TCAM write port (tw_*)
        |                                                                 |
        +--> control regs (mode, T0, A, dE, Lambda, gsh, wmax, seed, K)   |
        |                                                                 v
        +--> constraint_unit (W, C, loads) --slack--> query_enc --masks--> tcam_stub (our behavioural TCAM)
        |                                                                 |  r_cnt: per row, per segment
        |                                                                 v
        +--> N x tim_lane  [ coupling_mem row (P_i., d_i) -> field_unit (h_i)                     ]
        |                  [ seg_adder -> cnt_add_i, cnt_rem_i                                     ]
        |                  [ accept_lut copy (L) + accept_unit:  acc_i = geff_i + E_off + T*L >= 0 ]
        |                        ^ x_i (spin_reg)   ^ T (temp_sched)   ^ E_off (offset_unit)
        |                        ^ u_i from lane xoshiro128** (generator chain, seeded by splitmix64)
        |                        |
        |                  acc[N] register --> select_tree <-- selection xoshiro128**
        |                                          | (valid, k)
        +----------------------------------------- tim_ctrl (FSM, step counter, f, best f and best x)
                                                   | k broadcast to all lanes and to the W memory
```

- One **lane** per spin (`tim_lane`): its row of P and its bias d_i (`coupling_mem`), h_i (`field_unit`), its own
  copy of the acceptance LUT (`accept_lut`), one `accept_unit`, a `seg_adder` for its TCAM row and its two count
  registers. x_i sits in `spin_reg`; the lane's xoshiro128** generator sits in the generator chain in `tim_top`.
- Each lane keeps its signals on its own nets. In an earlier draft, N-wide shared buses on the per-step path
  (sliced N ways) made Icarus run time grow as N^3 (one N = 64 step took about 1 s); per-lane nets brought it to
  about 2 ms per step at N = 64. The hardware is the same; only the RTL structure changed.
- **Global**: T, E_off, the loads and capacities, f, best f, best x, the step counter and the FSM.
- **Seeding**: one splitmix64 generator fills all generator states through a 64-bit shift chain (§5.6).

## 3. Parameters and fixed widths

Top-level parameters (`rtl/src/tim_top.v`):

| Parameter | Default | Meaning | Allowed in v0 |
|---|---|---|---|
| `N` | 64 | spins = lanes = TCAM rows | power of two, 4 ≤ N ≤ 1024 (tested: 8, 16, 64, 256) |
| `NCON` | 8 | constraints m (registers and TCAM columns) | 1 … 16 |
| `NLEV` | 8 | thermometer levels Q per constraint | power of two, 2 … 16 |
| `SEGW` | 64 | TCAM cells per segment (one match line) | 64 |
| `SEARCH_LAT` | 2 | TCAM search latency in cycles (s_valid cycle to done cycle) | ≥ 1 |
| `WRITE_LAT` | 4 | TCAM write busy time in cycles | ≥ 1 |
| `ERR_HOOK` | 1 | build the TCAM count-error injection hook | 0 or 1 |
| `LAB` | 10 | acceptance-LUT address bits | 4 … 12 |
| `SEL_PIPE` | 0 | 1: pipelined select tree (`select_tree_pipe`, timing study v2); 0: the single-cycle tree | 0 or 1 |
| `SEL_ADD_CUT` | 0 | pipeline register after adder level k = 1 … LOG2N if bit k-1 is set (only with SEL_PIPE = 1) | any |
| `SEL_WALK_CUT` | 0 | pipeline register after walk step j = 0 … LOG2N-2 if bit j is set (only with SEL_PIPE = 1) | any |
| `RS_MESA` | 1 | 0: restart unit without the MESA best-state reload (Kc2 / none / da builds; arm 2 then never triggers) | 0 or 1 |
| `RNG_CG` | 1 | 1: the lane generators share one gated clock and the selection generator has its own (`clk_gate`); 0: free-running clock with enable (v0 structure). Same traces either way | 0 or 1 |

Derived: `SEL_LAT` = cycles in state SEL (1 without SEL_PIPE; else 2 + popcount(SEL_ADD_CUT, low LOG2N bits) + popcount(SEL_WALK_CUT, low LOG2N-1 bits)), `LOG2N = clog2(N)`, `NSEG = ceil(NCON·NLEV / SEGW)` (v0: 1), `CW = clog2(SEGW+1) = 7` (count bits per
segment), `TW = clog2(NSEG·SEGW + 1)` (total count bits per row; v0: 7), `QSH = log2(NLEV)`.

Fixed widths:

| Quantity | Symbol | Bits | Format | Range check (why it is enough) |
|---|---|---|---|---|
| coupling | P_ij | 8 | signed int | D5c P ∈ 0…100; Max-Cut P = −2w |
| bias | d_i | 8 | signed int | D5c d ∈ 1…100; Max-Cut d = weighted degree ≤ 127 |
| constraint weight | w_ji | 6 | unsigned int | D5c w ∈ 1…50 |
| capacity, load | C_j, L_j | 16 | unsigned int | load ≤ N·63 |
| slack | s_j = C_j − L_j | 17 | signed int | |
| local field | h_i | 18 | signed int | \|h\| ≤ 127 + 127·(N−1) < 2^17 for N ≤ 1024 |
| gain | g_i = (1 − 2x_i)·h_i | 18 | signed int | same as h |
| objective | f | 32 | signed int | |
| gain shift | gsh | 3 | unsigned | 0 … 4 (energy scale 2^gsh) |
| penalty weight | Λ | 16 | unsigned int | |
| count per row | cnt | 7 | unsigned | 0 … NSEG·SEGW |
| offset | E_off | 24 | unsigned int, saturating | |
| offset step | ΔE | 16 | unsigned int | |
| temperature | T | 32 | unsigned UQ16.16 | |
| cooling factor | A | 32 | unsigned UQ0.32 (α = A/2^32) | |
| LUT entry | L[a] | 12 | unsigned UQ4.8, in nats | max L ≈ 7.62 at LAB = 10 |
| threshold | θ_i | 20 | unsigned int | (2^32·4095) >> 24 < 2^20 |
| acceptance sum | | 28 | signed int | magnitude < 2^26 |

**Energy unit.** All energies (gains after scaling, penalty, E_off, ΔE, θ, T) are integers in one "energy LSB"
(eLSB). One eLSB is 2^−gsh units of f. QUBO mode uses gsh = 0. Knapsack mode uses gsh = QSH, so that one eLSB is
1/Q of a gain unit and the D5c step dq = w_max/Q drops out (hw_prior_art §1.4).

## 4. Per-step timing (cycles)

States of `tim_ctrl`: IDLE, SEED, INIT, QENC, SADD, WADD, SREM, WREM, ACC, SEL, RD, UPD, DONE.

| State | Cycles | What happens (registers change at the end of the cycle) |
|---|---|---|
| IDLE | – | wait for `start` (one-cycle pulse) |
| SEED | 2(N+1) | splitmix64 fills the generator shift chain, one 64-bit word per cycle |
| INIT | 1 | x ← 0, h ← d, loads ← 0, counts ← 0, f ← 0, best ← 0, E_off ← 0, T ← T0, step ← 0 |
| QENC | 1 | knapsack only: query encoder registers the ADD and REM masks from the slacks |
| SADD | 1 | knapsack only: `s_valid` = 1 with the ADD mask, rows enabled = ¬x |
| WADD | SEARCH_LAT | wait for `s_done`; in the `s_done` cycle, latch every row's total count into cnt_add |
| SREM | 1 | `s_valid` = 1 with the REM mask, rows enabled = x |
| WREM | SEARCH_LAT | wait for `s_done`; latch counts into cnt_rem |
| ACC | 1 | every lane registers acc_i; every lane generator advances once |
| SEL | SEL_LAT | the count tree registers (valid, k, c) in the last SEL cycle; the selection generator advances once, in that cycle. With SEL_LAT > 1 the (acc, r16) inputs are held and the pipelined tree settles; the selected lane is the same as for SEL_LAT = 1 |
| RD | 1 | coupling memory and weight memory read word k (synchronous read) |
| UPD | 1 | apply the flip (if valid), update E_off, T, f, best, step; pulse `step_valid` next cycle |
| DONE | – | `done` = 1 until the next `start` |

Cycles per step:
- **QUBO mode: 3 + SEL_LAT** (4 at the default SEL_LAT = 1).
- **Knapsack mode: 6 + SEL_LAT + 2·SEARCH_LAT** (11 at the default SEARCH_LAT = 2, SEL_LAT = 1; 9 at SEARCH_LAT = 1).

Run length: 1 (start) + 2(N+1) + 1 + K·(cycles per step), K = number of steps. The top-level testbench checks the
cycles per step on every step.

At an assumed 100–200 MHz FPGA clock, QUBO mode is 20–40 ns per step and knapsack mode 55–110 ns. v0 is not
pipelined; overlapping QENC/SADD with the previous UPD would save about 2 cycles (§10).

## 5. Arithmetic and the exact rules

Notation: ⌊·⌋ is floor; `>>` is a logical right shift of a non-negative integer (floor division by a power of two).

### 5.1 Pricing (knapsack mode)

Each step starts from the current state (x, h, loads L_j).

1. Slack: s_j = C_j − L_j (signed).
2. Query masks, for constraint j and level k = 1 … Q (Q = NLEV):
   - ADD mask bit (j,k) = [ Q·s_j < k·w_max ]  (this is "k > ⌊Q·max(s_j,0)/w_max⌋")
   - REM mask bit (j,k) = [ k·w_max ≤ −Q·s_j ]  (this is "k ≤ ⌊Q·max(−s_j,0)/w_max⌋")
   - Column of (j,k) in the TCAM word: c = j·Q + (k − 1). Columns c ≥ NCON·Q have mask bit 0.
   - Search key: all zeros.
3. Stored row i (written once per instance by the host): cell (j,k) = 1 iff Wq_ij ≥ k, with
   Wq_ij = ⌊Q·w_ji / w_max⌋. Stored care = 1 on every cell.
4. TCAM count of row i for a search: Σ over segments of popcount((stored_bits XOR key) AND stored_care AND mask).
   - ADD search: rows enabled = ¬x. cnt_add_i = count if x_i = 0, else 0.
   - REM search: rows enabled = x. cnt_rem_i = count if x_i = 1, else 0.
   - Rows not enabled return 0 and are not counted as evaluated.
5. This gives exactly the D5c counts (proof in hw_prior_art §1.5 and checked in `selftest_golden.py`):
   cnt_add_i = Σ_j max(0, Wq_ij − ⌊Q·max(s_j,0)/w_max⌋) and cnt_rem_i = Σ_j min(Wq_ij, ⌊Q·max(−s_j,0)/w_max⌋).

In QUBO mode no search runs and cnt_add = cnt_rem = 0.

### 5.2 Acceptance (every lane, every step)

    g_i     = x_i ? −h_i : h_i                               (gain of flipping i, in units of f)
    geff_i  = (g_i << gsh) − Λ·cnt_add_i + Λ·cnt_rem_i       (eLSB)
    u_i     = next output of lane i's generator (32 bits)
    a_i     = u_i >> (32 − LAB)                               (top LAB bits)
    θ_i     = (T · L[a_i]) >> 24                              (T is UQ16.16, L is UQ4.8, so θ is in eLSB)
    acc_i   = [ geff_i + E_off + θ_i ≥ 0 ]

The LUT holds L[a] = min(4095, round(256 · (−ln((a + 0.5) / 2^LAB)))) for a = 0 … 2^LAB − 1. The host writes it
(the golden model generates it). This is the DA patent's threshold form T·f⁻¹(u): the float rule
"u < exp(min(0, (geff + E_off)/T))" is the same as "geff + E_off + T·(−ln u) ≥ 0" (up to a set of measure zero), and
the LUT replaces −ln u.

All terms are exact signed integers; the 28-bit sum cannot overflow at the widths of §3.

### 5.3 Selection (count-tree walk)

    v   = next output of the selection generator (32 bits); r16 = v >> 16
    c   = popcount(acc)
    if c > 0: r = (r16 · c) >> 16   (0 ≤ r < c);  k = index of the r-th set bit of acc, counting from lane 0, r = 0 first

The tree: leaves are acc_i; each node holds the popcount of its subtree. The walk starts at the root with r; at each
level it goes left if r < (left count), else it subtracts the left count and goes right. After log2(N) levels it
reaches leaf k. The pick is uniform up to the multiply-shift rounding: P(pick = r-th) = #{v16 : ⌊v16·c/2^16⌋ = r}/2^16,
which differs from 1/c by less than 1/2^16. The golden model's exact transition matrix uses this exact probability.

The selection generator advances once per step, also when c = 0. Each lane generator advances once per step.

### 5.4 Update

If c > 0 (a flip of lane k is applied):

    δ      = x_k ? −1 : +1
    f      ← f + g_k                     (g_k from before the flip, unscaled)
    x_k    ← 1 − x_k
    h_i    ← h_i + δ·P_ik   for all i    (one read of coupling word k, one add per lane)
    L_j    ← L_j + δ·w_jk   for all j    (knapsack mode only)
    E_off  ← 0
    feasible = all_j (L_j ≤ C_j)         (always true in QUBO mode)
    if feasible and f > best_f: best_f ← f, best_x ← x, best_step ← t

If c = 0:

    E_off ← min(E_off + ΔE, 2^24 − 1)

Then, in both cases, if the geometric schedule is on: T ← (T · A) >> 32. Otherwise T holds.

Start of a run: x = 0, h = d, L = 0, f = 0, best_f = 0, best_x = 0, best_step = 0, E_off = 0, T = T0. Steps are
numbered t = 1 … K.

### 5.5 Temperature schedule

One global T register. Geometric per step (`geom` = 1), matching qkp_nb (T *= α every step), or held constant
(`geom` = 0, used by the transition-matrix test). The (T_k, N_k) staircase table is left for later (§10).

### 5.6 Random numbers

- **xoshiro128\*\*** (Blackman and Vigna, version 1.1), 32-bit output, state s0…s3 of 32 bits:

      out = rotl(s1·5, 7)·9;  t = s1 << 9;
      s2 ^= s0; s3 ^= s1; s1 ^= s2; s0 ^= s3; s2 ^= t; s3 = rotl(s3, 11)

  All arithmetic is modulo 2^32. The output is a function of the current state; "advance" moves to the next state.
- **splitmix64**, 64-bit: `x += 0x9E3779B97F4A7C15; z = x; z = (z ^ (z>>30))·0xBF58476D1CE4E5B9;
  z = (z ^ (z>>27))·0x94D049BB133111EB; out = z ^ (z>>31)`, starting from x = seed.
- **Seeding order.** splitmix64 gives z_0, z_1, …, z_{2N+1}. Generator g (g = 0 … N−1 for lanes, g = N for the
  selection generator) gets s0 = low32(z_{2g}), s1 = high32(z_{2g}), s2 = low32(z_{2g+1}), s3 = high32(z_{2g+1}).
  In hardware the states form one shift chain {S_N, …, S_0}; in each SEED cycle the chain shifts right by 64 bits
  and z enters at the top. After 2(N+1) cycles z_t sits in 64-bit slot t.
- An all-zero state (probability 2^−128) is not guarded in v0; the golden model asserts it does not happen.

## 6. Problem loading

### 6.1 Host configuration bus

`cfg_we`, `cfg_addr[23:0]`, `cfg_wdata[31:0]`, write only, one write per cycle, only while the machine is IDLE or
DONE. Address = {region[23:20], offset[19:0]}.

| Region | Offset | Data | Meaning |
|---|---|---|---|
| 0 | 0 | bit 0 `knap`, bit 1 `geom` | mode |
| 0 | 1 | 32 bits | T0 (UQ16.16) |
| 0 | 2 | 32 bits | A (UQ0.32) |
| 0 | 3 | 16 bits | ΔE |
| 0 | 4 | 16 bits | Λ |
| 0 | 5 | 3 bits | gsh |
| 0 | 6 | 6 bits | w_max |
| 0 | 7 | 32 bits | seed, low half |
| 0 | 8 | 32 bits | seed, high half |
| 0 | 9 | 32 bits | K (number of steps) |
| 0 | 10 | 32 bits | restart stall window K_r (P3.02) |
| 0 | 11 | 2 bits | restart arm: 0 none (E_off held at 0), 1 da_offset (default, v0 machine), 2 mesa, 3 kc2 |
| 0 | 12 | 16 bits | kc2 kick size L (default 10; capped at enabled lanes - 1) |
| 0 | 13 | 1 bit | kc2 also resets T := T0 and E_off := 0 on restart (non-reference flag) |
| 0 | 14 | 5 bits | CiM ADC resolution (nominal bits; P3.03, build parameter CIM = 1) |
| 0 | 15 | 16 bits | CiM noise gain sg (0 = no noise) |
| 0 | 16 | 32 bits | CiM noise seed (xorshift32 column states) |
| 0 | 17 | bit 0 I10, bit 1 I7 | stall-gated power / adaptive ADC enables (P3.04) |
| 0 | 18 / 19 | 16 bits | K_g (ADC bias gating threshold) / K_p (I7 switch threshold) |
| 0 | 20 / 21 | 5 bits | I7 b_hi / b_lo |
| 0 | 22 | 1 bit | TCAM-lite enable (P3.07; only built with parameter TCL = 1; default 0) |
| 0 | 23 / 24 | 16 bits | TCAM-lite write period K_w (0 = never write) / lockout length L_lock (P3.07) |
| 0 | 25 | bit 0 I11, bit 1 I3, bit 2 I5 | H2 tweaks, all 0 after reset (= the v0 machine, bit-exact). I11 greedy + Kc2 kick: acc = geff >= 0, theta and E_off forced 0, no T / E_off writes, lane generators never advance (needs restart arm kc2 and I5 = 0). I3 ramped penalty (knapsack, hw rule). I5 held and grouped noise words |
| 0 | 26 | 16 bits | I3 lam_lo |
| 0 | 27 | 32 bits | I3 ramp_steps (>= 1) |
| 0 | 28 / 29 | 16 / 32 bits | I3 dq / dr: the host writes divmod(lam - lam_lo, ramp_steps) (division-free hardware). lam_t = lam_lo + floor((lam - lam_lo) * min(t, ramp_steps) / ramp_steps), t = 1, 2, ...; one update per step while t < ramp_steps (`lam_ramp`), then frozen at lam. Replaces the register of offset 4 in the acceptance when I3 = 1 |
| 0 | 30 | 16 bits | I5 hold (>= 1): a lane noise word is held this many steps (generators advance only after the last step of a window) |
| 0 | 31 | 4 bits | I5 group size 2^glog: the lanes of a group take the random word of the group leader (lane index with the low glog bits cleared); `lane_rnd_mux` |
| 0 | 32 | 16 bits | I7v2 ADC full scale (H6, build parameter CIM = 1): the ADC input range in counts; 0 = N rows (v1 rule). Set to the maximum column sum of the stored weights (`cim_field.max_column_sum`) |
| 1 | j·N + k | 10 bits signed | P_jk (lane j's memory, word k). The host writes all N² entries, or only the non-zero ones (the simulation model zero-initialises the array; P3.06). |
| 2 | j | 12 bits signed | d_j (P3.06; was 8 bits) |
| 3 | a | 12 bits | L[a] |
| 4 | j·N + k | 6 bits | w_jk (constraint j, item k) |
| 5 | j | 16 bits | C_j |
| 6 | j | 1 bit | lane enable of lane j (added P3.01, FIXES R1); all lanes on after reset. An off lane never accepts. |

Memories are not reset; the host must write every entry it uses. QUBO mode does not use regions 4–5 or the TCAM.

### 6.2 TCAM write port (host side)

`tw_en`, `tw_row[LOG2N-1:0]`, `tw_seg`, `tw_bits[63:0]`, `tw_care[63:0]`, `tw_busy`. A write is taken when
`tw_en` = 1 and `tw_busy` = 0; then `tw_busy` is 1 for WRITE_LAT cycles. Writes while busy are dropped and counted.

### 6.3 Max-Cut as a QUBO

cut(x) = Σ_{(i,j)∈E} w_ij (x_i + x_j − 2x_i x_j), so d_i = Σ_j w_ij and P_ij = −2w_ij; f = cut. With 12-bit signed d and
10-bit signed P (P3.06, FIXES R11; was 8 bit each) the weighted degree must be ≤ 2047 and |w| ≤ 255, and
|h| < 2^17 must hold for the 18-bit field (G-set: weighted degree ≤ 589, |P| = 2). The CiM array keeps 8 weight
planes (|P| ≤ 255 in CiM builds; the golden model asserts it).

## 7. Module list and ports

All modules are plain Verilog-2005, synthesizable, no initial blocks, no delays. Flattened buses: element i of a
bus of W-bit elements is bits [i·W +: W].

| Module | Ports (direction, width) | Notes |
|---|---|---|
| `xoshiro128ss` #(GATED) | in clk, ld, ld_state[128], adv; out out[32], state[128] | one generator; GATED = 1: `clk` is a gated clock that only pulses with ld or adv, no enable multiplexer |
| `clk_gate` | in clk, en; out gclk | gclk = clk & en sampled while clk is low (ICG model; the library cell is CLKGATETST_X1) |
| `splitmix64` | in clk, init, seed[64], next; out out[64] | seeding generator |
| `spin_reg` #(N) | in clk, clr, flip, flip_idx[LOG2N]; out x[N] | spin register file |
| `coupling_mem` #(N) | in clk, wr_p, wr_b, wr_col[LOG2N], wr_data[8], rd_en, rd_col[LOG2N]; out pk[8], bias[8] | one lane's row of P (N words × 8 bits) and its bias; word k read one cycle after rd_en. The machine's coupling memory is N of these |
| `field_unit` #(HW) | in clk, init, bias[8], upd, dir, pk[8]; out h[HW], ovf | one lane's field with incremental update; the local-field array is N of these |
| `accept_lut` #(LAB, LW) | in clk, wr, wr_addr[LAB], wr_data[LW], rd_addr[LAB]; out rd_data[LW] | one lane's copy of the host-written table (the host writes all copies at once) |
| `accept_unit` #(HW, TW, LW, EW) | in h[HW], x, cnt_add[TW], cnt_rem[TW], lam[16], gsh[3], eoff[EW], temp[32], lval[LW]; out gain[HW], acc | combinational, one per lane |
| `tim_lane` #(N, NSEG, …) | host writes for this lane; init, rd_en, rd_col, flip, dir, cnt_add_ld, cnt_rem_ld, seg_cnt[NSEG·CW], x, lam, gsh, eoff, temp, rnd[32]; out h, gain, acc, cnt_add, cnt_rem, ovf | one lane: coupling_mem + field_unit + seg_adder + count registers + accept_lut + accept_unit |
| `select_tree` #(N) | in acc[N], r16[16]; out valid, idx[LOG2N], count[LOG2N+1] | combinational count tree and walk (one procedural block) |
| `select_tree_pipe` #(N, ADD_CUT, WALK_CUT) | in clk, acc[N], r16[16]; out valid, idx[LOG2N], count[LOG2N+1] | same function, pipelined: registers after the chosen adder levels, always after the multiply, after the chosen walk steps; latency 2 + popcount(ADD_CUT) + popcount(WALK_CUT) cycles for held inputs |
| `lam_ramp` | in clk, init, step, lam_lo[16], ramp[32], dq[16], dr[32]; out lam_t[16] | I3 ramped penalty weight, division-free |
| `hold_ctl` | in clk, init, acc_ld, i11, i5, hold[16]; out lane_adv | I11 / I5 lane-generator advance gate |
| `lane_rnd_mux` #(LOG2N) | in cand[32(LOG2N+1)], glog, i5; out rnd[32] | I5 lane-group word sharing |
| `offset_unit` #(EW) | in clk, clr, upd, accepted, deoff[16]; out eoff[EW] | saturating |
| `temp_sched` | in clk, load, t0[32], step, geom, alpha[32]; out temp[32] | global T |
| `constraint_unit` #(N, NCON) | in clk, wr_w, wr_c, wr_con[4], wr_item[LOG2N], wr_data[16], clr, rd_en, rd_item[LOG2N], upd, dir, en; out load[NCON·16], slack[NCON·17], feas_next | W memory, C registers, load registers |
| `query_enc` #(NCON, NLEV, SEGW, NSEG) | in clk, ld, slack[NCON·17], wmax[6]; out add_mask[NSEG·SEGW], rem_mask[NSEG·SEGW] | registered thermometer masks |
| `tcam_stub` #(NROW, SEGW, NSEG, CW, SEARCH_LAT, WRITE_LAT, ERR_HOOK) | write: in wr_en, wr_row, wr_seg, wr_bits[SEGW], wr_care[SEGW]; out wr_busy. search: in s_valid, s_key[NSEG·SEGW], s_mask[NSEG·SEGW], s_row_en[NROW]; out s_done, r_cnt[NROW·NSEG·CW]. hooks: in err_en, err_thr[16]; out n_search[32], n_write[32], n_wdrop[32], n_rows_en[48], n_cells[48], n_err[32] | our behavioural TCAM, exact counts (§8) |
| `seg_adder` #(NROW, NSEG, CW, TW) | in r_cnt[NROW·NSEG·CW]; out tot[NROW·TW] | sums segment counts per row |
| `tim_ctrl` #(N, HW) | see source | FSM, step counter, f, best f and x, strobes |
| `tim_top` #(…) | cfg bus, TCAM write port, start, err_en, err_thr; out busy, done, step_valid and debug buses | top level |

## 8. The TCAM pricer interface and our stand-in

The interface is the boundary where the FeFET transistor-level array will later plug in (G4/G5). v0 puts our own
behavioural model behind it, `tcam_stub`, which:
- stores per row and segment 64 bits and a 64-bit care mask (ternary storage, so the visited-state control can reuse
  it later);
- answers a search with the exact count popcount((bits XOR key) AND care AND mask) per row and segment, for enabled
  rows only (disabled rows return 0);
- raises `s_done` exactly SEARCH_LAT cycles after the `s_valid` cycle; `r_cnt` changes only in that cycle and holds
  until the next result;
- counts events for the energy model: searches, writes, dropped writes, enabled rows, evaluated cells
  (enabled rows × mask-1 columns), injected errors;
- has an **error-injection hook** (`ERR_HOOK` = 1, input `err_en`, threshold `err_thr`): each row has its own
  xorshift32 that advances on every search; when `err_en` = 1 and the row is enabled, its count per segment becomes
  count ± 1 (clamped to 0 … SEGW) with probability err_thr/2^16. This is a placeholder: the SPICE runs (G4) will
  give a per-level error table, which will replace this rule through the same input. With `err_en` = 0 the counts
  are exact. The golden model does not model errors in v0.

The same stand-in is the plan's **C2 control** (digital-equivalent pricer): it is the TCAM function computed by
exact digital logic, behind the same interface.

## 9. Files: instance, host script, trace

### 9.1 Instance file (`.inst`, text)

Whitespace-separated tokens; `#` starts a comment to the end of the line. Keys in this order:

```
tim_inst v0
n <N>                      # spins; must equal the RTL parameter N
mode qubo | knap
geom 0 | 1                 # 1 = geometric schedule
t0 <uint>                  # T register start, UQ16.16
alpha <uint>               # A, UQ0.32
deoff <uint>               # ΔE
lambda <uint>              # Λ
gsh <uint>                 # gain shift
wmax <uint>                # w_max (knap); any value in QUBO mode
seed <uint, decimal or 0x hex>
steps <K>
lut <LAB> 8                # LUT address bits and fraction bits (entries follow the rule of §5.2)
bias <d_0> ... <d_{N-1}>
p                          # then N rows of N signed integers: row j is P_j0 ... P_j,N-1
<N lines>
m <m>                      # knap only (m ≤ NCON), then:
q <Q>                      # thermometer levels; must equal the RTL parameter NLEV (gsh must be log2 Q)
w                          # m rows of N integers: row j is w_j0 ... w_j,N-1
<m lines>
c <C_0> ... <C_{m-1}>
end
```

Example: `sim/data/ring8.inst` (an 8-spin ring, Max-Cut, optimum 8).

### 9.2 Host write script (`.cfg`, text, generated from the instance by `scripts/golden/tim_golden.py`)

One action per line, read by `rtl/tb/tb_top.v`:

```
w <addr hex> <data hex>                       # one cfg-bus write
t <row dec> <seg dec> <bits hex> <care hex>   # one TCAM row write (the testbench waits on tw_busy)
```

Unused constraints (m < NCON) are written as w = 0 and C = 65535, which makes them inert.

### 9.3 Trace (`.trace`, text)

One line per step, decimal, space separated:

    t k nacc acs f hcs eoff T lcs ccs

- t: step (1 … K); k: flipped lane or −1; nacc = popcount(acc); acs = Σ_i (i+1)·acc_i mod 2^32;
- f: objective after the step; hcs = Σ_i (i+1)·h_i mod 2^32 (h as 32-bit two's complement); eoff and T after the step;
- lcs = Σ_j (j+1)·L_j mod 2^32 over the NCON loads; ccs = Σ_i (i+1)·(cnt_add_i + 256·cnt_rem_i) mod 2^32 (counts used
  in this step).

Then one final line: `final <best_f> <best_step> <x hex> <best_x hex>` (bit i of the hex number is lane i).
The RTL testbench writes the same format, and `scripts/golden/compare_trace.py` compares the two files line by line.

## 10. Known differences from the float model (qkp_nb.py) and v0 limits

1. RNG: xoshiro128\*\* per lane instead of PCG64; the integer model is statistically, not bitwise, comparable.
2. Acceptance: u is quantised to 2^LAB bins; moves with (geff + E_off)/T < −L_max (−7.6 at LAB = 10) are never
   taken (their float probability is below 5·10^−4).
3. Selection: multiply-shift bias below 1/2^16.
4. Rounding of Λ, T0, ΔE and A to integers, and the floor in T ← (T·A) >> 32 (T decays at most 1 LSB per step
   faster than the float schedule).
5. E_off saturates at 2^24 − 1.
6. Not in v0: pipelining, the staircase schedule, the visited-state TCAM control (H4), per-segment λ weights,
   exact/adaptive digital hinge rules in RTL (C3; they exist in the golden model for the ranking check), the
   offset-on transition test, FPGA mapping.

## 11. Verification plan (what the tests check)

Run everything with `scripts/run_rtl_tests.sh` (add `--long` for the long runs). Results: `docs/rtl/STATUS.md`.

| Test | Checks |
|---|---|
| golden self-test | splitmix64 known values and equal to the reference software study; xoshiro scalar = vector; LUT; selection probabilities; pricer counts = qkp_nb float formula on D5c instances; D5c generator port = the reference software study; end-state invariants; file round trip; transition matrix rows |
| unit: `tb_rng` | splitmix64 and xoshiro128\*\* outputs equal golden vectors; shift-chain seeding order |
| unit: `tb_select` | 6 fixed patterns exhaustive over all 2^16 r16 values, plus random patterns, at N = 16 and 64: pick = r-th set bit |
| unit: `tb_accept` | random inputs and edge cases vs a 64-bit reference in the testbench |
| unit: `tb_field` | coupling rows + field units: 3000 random flips, every field = d + P x; overflow flag |
| unit: `tb_coupling` | write/read of every word, registered read holds |
| unit: `tb_offset_temp` | saturation, reset on accept, T·A >> 32 vs reference, hold |
| unit: `tb_tcam` | random ternary rows and searches vs reference popcount; latency 1 and 3; r_cnt stable before done; row enable; busy and dropped write; counters; error hook bounded and counted |
| unit: `tb_pricer` | query_enc + tcam + seg_adder at Q = 8 (1 segment) and Q = 16 (2 segments): counts = Σ max(0, Wq − flo) and Σ min(Wq, fov) by integer division |
| unit: `tb_constraint` | loads = W x, slacks, feas_next of the after-flip state, loads frozen in QUBO mode |
| elab: N = 16, 64, 256 | `tim_top` elaborates (warnings counted) |
| top: `ring8` | the example instance file `sim/data/ring8.inst`: bit-exact, best = 8 |
| top: `qubo64` | random QUBO, N = 64, 1500 steps: bit-exact |
| top: `maxcut16` | random graph, N = 16, optimum by brute force: bit-exact, best = optimum |
| top: `torus64` | 8×8 torus Max-Cut, N = 64, optimum 128: bit-exact, best = optimum |
| top: `knap16` | D5c generator instance, n = 16, m = 8, Q = 8: bit-exact through the TCAM, best feasible, best ≤ brute-force optimum (and reports whether equal) |
| top: `knap16_lat1`, `knap16_lat3` | same instance at SEARCH_LAT 1 and 3: same golden trace, cycle formula holds |
| top: `knap16_q16` | same instance at Q = 16 (two TCAM segments) |
| top: `knap64` | D5c generator instance, n = 64, m = 8: bit-exact |
| top: `trans8` | N = 8, fixed T, ΔE = 0, 40000 steps: bit-exact, and the RTL's transition frequencies match the exact DA transition matrix (chi-square, p ≥ 10^−3), while a wrong model (lowest-index pick) is rejected (p < 10^−6) |
| top: `qubo256` (long) | N = 256 runs a short bit-exact trace |

Every top-level run also checks: cycles per step on every step, no field overflow, TCAM counters (2 searches per
step and N·NSEG row writes in knapsack mode, none in QUBO mode, no dropped writes).

## 11. P3 additions (hw phase, 15 Nov 2026; golden counterparts in scripts/golden/)

- **Lane enable (P3.01, region 6).** An off lane never accepts; padding lanes carry zero coupling.
- **Restart unit (P3.02, `restart_unit.v`, controller state S_RST).** UPD can hand over to S_RST; the step's
  `step_valid` pulses after the restart, so the trace line shows the post-restart state. A restart flips spins one at a
  time through the ordinary read/update path: mesa flips x XOR best_x (ascending lanes; per flip R_ENC, R_CHK, R_RD, R_FL = 4 cycles, the lowest differing spin found in two registered
  stages) and resets T and E_off; kc2 draws L distinct enabled lanes from the selection generator (partial Fisher-Yates on a persistent permutation built during
  seeding in two registered stages, `pinit` held N + 1 cycles) and flips them (per kick R_DRAW, R_ADD, R_SWP1, R_SWAP, R_RD, R_FL = 6 cycles). Extra cycles are exported as `rs_cycles`.
- **CiM field unit (P3.03, `cim_field_unit.v`, build parameter CIM = 1, state S_CIM before ACC).** Duration
  CIMLAT + adc_bits cycles; `h` register doubles as the I10 field cache. Acceptance uses the CiM field, the objective
  f and the traced field checksum use the exact digital field.
- **Power control (P3.04, `power_ctl.v`).** Decides at the end of each step whether the next read is skipped (I10)
  and which ADC bits it uses (I7); exports arr_en, adc_en, adc_bits and 8 cumulative activity counters.
- **Widths (P3.06).** P 10 bit, d 12 bit signed (top parameters JW, BW).
