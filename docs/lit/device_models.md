# FeFET compact-model notes for this project (v0 model input)

Written 31 Oct 2026 (IST). Notes only; no model code here. Every number carries its source.
Tags: **[paper]** = stated in the paper text/table; **[fig-vector]** = we read it from the figure's vector
data (exact to about 0.5% of the axis span, method in §2.0); **[fig-raster]** = read by eye from a raster figure
(about ±10% of axis span); **[derived]** = our own calculation from the above (formula given);
**uncertain** = could not confirm.

Contents: §1 summary and v0 recipe · §2 the three chosen papers · §3 open-source models · §4 FeFET TCAM
targets · §5 MOSFET model choice · §6 simulator / Verilog-A toolchain · §7 open questions and risks.

Source keys: **P1** = Ni, Jerry, Smith, Datta, VLSI Tech. 2018 (FeFET compact model); **P2** = Chow,
Sheikholeslami, Cross, Masui, VLSI Circuits 2004 (VDST); **P3** = Alessandri, Pandey, Abusleme, Seabaugh,
IEEE TED 66(8) 2019 (Monte Carlo NLS). Full citations in §2.

## 1. One-page summary and v0 recipe

### 1.1 Summary

- **P1** gives the FeFET framework: a ferroelectric element in series with a BSIM4 MOSFET, sharing one
  charge (Q_FE = Q_MOS, V_G = V_FE + V_MOS). It uses a tanh saturation loop, minor loops scaled between
  turning points, and the P2 delay unit. It also gives good calibration data (we extracted it to about 0.5%
  of axis span from the vector figures, §2.1 T1-T6). **It prints no parameter values.**
- **P2** is the origin of P1's delay unit. A delayed "effective voltage" drives a static Preisach model,
  with τ = τ_∞·exp[(V_0/V_pulse)^m]. **It also prints no parameter values.**
- **P3** gives a complete, physically grounded parameter set for HZO switching kinetics (Table I):
  nucleation-limited switching with a GB2 distribution of activation fields. It also gives a history
  variable and grain-count variability. Its deterministic limit is a **multi-domain Preisach model whose
  hysterons switch with NLS kinetics**.
- The Ni 2019 TCAM Supplementary Information (§4.1) describes P1's model as exactly that: independent
  domains with rectangular hysterons, a distribution of coercive fields, and nucleation-limited switching.
- **Toolchain fact that decides the design (§6).** ngspice 45 takes Verilog-A only as OSDI objects from
  OpenVAF(-reloaded). OpenVAF cannot parse `@(cross())`, and it most likely (uncertain) does not keep variables
  between time steps. A turning-point stack held in variables (P1/P2 style) is therefore not portable,
  and B-sources cannot hold a stack at all. **All history must live in node voltages.**
- **Recommended v0:** an N-domain kinetic Preisach FE (one state node per domain, P3 kinetics), in series
  with a built-in BSIM4 MOSFET through an internal gate node (MFMIS-style lumping, as in P1). The same
  equations can be written two ways: Verilog-A using only `ddt`, or an ngspice-native subcircuit of
  B-sources and 1 F state capacitors.
- **MOSFET (§5):** PTM 45 nm BSIM4. It is the node used by the Yin/Qian FeFET-TCAM simulation papers (Ni 2019
  used 45 nm wire parasitics; card unnamed). It is two short plain-text cards, and ngspice runs it
  natively. Its weak point is that it has no explicit licence.
- **Closest open reference (§3.A):** Heracles (MIT, Groningen/TUM). It is a single-state kinetic HfO2
  FeCap in Verilog-A that ships OSDI binaries for ngspice and is tested in series with built-in BSIM4.
  It is not Preisach and not an FeFET, but it shows that the node-state, `ddt`-only pattern compiles with
  OpenVAF and runs in ngspice.

### 1.2 v0 recipe (equations for the model writer)

Terminals g, d, s, b. Internal node m (MOSFET gate = bottom of the FE). Internal state nodes x_1 … x_N
(dimensionless domain polarization in [−1, +1], each stored as a voltage on a 1 F capacitor). Default
N = 16.

    (R1) V_FE = V(g) − V(m);   E = (V_FE + V_imp) / t_FE
         [P3 convention: V_FE = V_A + V_OS, V_OS = +80 mV]
    (R2) τ_i(E) = τ_∞ · exp[ (E_a,i / |E|)^α ]          [P3 eq. (4)]
         r_i = 1/τ_i for |E| > E_floor, else 0         (exponent capped at ~200; smooth, because
                                                        exp(−(E_a/E)^α) and all its derivatives → 0 as E → 0)
    (R3a) β = 1 form (robust default):
         dx_i/dt = r_i · [ (1 − x_i)·H(E) − (1 + x_i)·H(−E) ]      (H = unit step)
    (R3b) β ≠ 1 form (reproduces P3 eq. (2)/(5) exactly for reversal from a saturated state under any
          one-sign field). For E > 0 let s = (1 + x_i)/2:
         ds/dt = β · r_i · (1 − s) · [ −ln(1 − s) + h0 ]^((β−1)/β),   h0 ≈ 1e-6 (seed)
         dx_i/dt = +2·ds/dt.  For E < 0, mirror with s = (1 − x_i)/2 and dx_i/dt = −2·ds/dt.
          Derivation: s = 1 − exp(−h^β) with dh/dt = r_i gives ds/dt = β·r_i·(1 − s)·h^(β−1) and
          h = [−ln(1 − s)]^(1/β). The h-history is therefore tied to the switched fraction, which sits
          between P3's "reset" and "no reset" rules (risk R10).
    (R4) P = P_S · Σ_i w_i · x_i,   w_i = 1/N  (bins at equal-probability quantiles of g(E'_a))
    (R5) Q_FE = A_FE · [ P + ε0·εr·E ];   I(g→m) = dQ_FE/dt   (+ optional V_FE/R_leak)
    (R6) MOSFET: BSIM4 instance (d, m, s, b), W, L; A_FE = W·L·r_A (r_A = 1 is the MFIS-equivalent of P1;
         r_A < 1 is a true MFMIS area ratio)
    (R7) Initial state: x_i = +1 or −1 via .ic. Node m via .ic plus R_m ≥ 1e15 Ω to s (Heracles ngspice testbench uses 10 TΩ to ground)
         (time constant ≫ simulated time); transient with uic.
    (R8) Variation: per-instance E_a,i sampled outside the model from g(E'_a), with
         N_grains ≈ FE area / grain area. Monte Carlo is a netlist-generation step (OpenVAF has no $random).
    (R9) Optional v1: P2/P1 delay node V_eff (dV_eff/dt = (V_FE − V_eff)/τ_d(V_FE)) feeding (R1) instead of
         V_FE, only if P1's exact delay behaviour is needed. P1's tanh/turning-point form can be kept as a
         post-processing reference (Python/offline), not as the SPICE model.

Approximate bins for Set A, N = 10 [derived]. These use a log-normal stand-in for P3's GB2, with median
1.82 MV/cm and σ_ln = 0.21 (§2.3 (iv)). E'_a,i in MV/cm: 1.29, 1.46, 1.58, 1.68, 1.77, 1.87, 1.97, 2.10,
2.26, 2.57. Replace these with exact GB2 quantiles: x = b·[z/(1−z)]^(1/a), where z is the inverse
regularized incomplete beta I⁻¹(u; p, q) at u = (i − 0.5)/N.

### 1.3 Starting parameter table

| Parameter | Set A: P3 film (8.3 nm Hf0.5Zr0.5O2) | Set B: P1 FeFET film (10 nm Hf0.4Zr0.6O2) | Set C: 28 nm-class TCAM FeFET (Ni 2019 / Yin 2024) |
|---|---|---|---|
| t_FE | 8.3 nm [P3 p. 3529] | 10 nm [P1] | 8 nm doped HfO2 [Ni 2019 SI p. 2; Yin 2024 Methods] |
| Interlayer | — (MFM) | 2 nm SiO2 [P1 Fig. 1(a)] | 1 nm SiO2, TiN 2 nm gate [Yin 2024 Methods] |
| P_S | 22.9 µC/cm² [P3 Table I, row "P_R"] | ≈ 25 µC/cm² [derived, P1 Fig. 3(c)/4(c)]; published fit to the same P1 data: P_s = 19, P_r = 18.5 µC/cm², V_c = 1.2 V [Chatterjee 2023 Table 1, §3.B] | no value; start 22.9 (uncertain) |
| εr | not reported; start 30 (uncertain) | ≈ 30-45 [derived from loop slope, uncertain]; 40 [Chatterjee 2023 Table 1] | start 30 (uncertain) |
| τ_∞ | 387 ns [P3 Table I] | ≈ 2.5 µs [derived from P1 Fig. 4(c) t50; may include set-up RC] | fit to Ni 2019 SI Fig. 1 |
| α | 4.11 [P3 Table I] | ≈ 2.4 [derived] | ≈ 2 (SI uses τ ∝ exp((V0/V)²), gate-referenced) |
| β | 2.07 [P3 Table I] (or 1 with refit) | 1 (start) | 1 (start) |
| E_a distribution | g(E'_a) = GB2(a = 12.1, b = 1.79 MV/cm, p = 0.691, q = 0.633) [P3 Table I]; median ≈ 1.82 MV/cm, σ_ln ≈ 0.21 [derived] | log-normal, median ≈ 1.9 MV/cm, σ_ln ≈ 0.2 (start) [derived] | fit; gate-referenced V0 ≈ 10.6 V (MW 0.2 V) to 16.0 V (MW 1.0 V) [SI Fig. 1, fig-vector] |
| Imprint V_imp | +0.08 V (V_OS) [P3] | ≈ +0.17 V [derived] | 0 (unknown) |
| N domains | 16 (deterministic); 20-500 for MC variation [P3 Fig. 7] | 16 | 16; MC for σ(V_th) |
| MOSFET | — | PTM 45 nm nmos BSIM4 with toxe/toxp/toxm → 2 nm and vth0 refit (stand-in) | PTM 45 nm nmos BSIM4 with toxe → ≈ 1 nm and vth0 refit (stand-in) |
| W × L | — | per-µm data; use 1 µm × 1 µm | 450 × 450 nm (GF test devices, Kazemi 2022; uncertain) |
| Write | — | ±2 … ±4.5 V, 50 ns-10 ms [P1 Fig. 6(d)] | ±4 V, 1-10 µs [Ni 2019 SI Fig. 5; Yin 2024] |
| Targets | §4.3 C1 | §4.3 C2-C5 | §4.3 C4-C8 |

### 1.4 Calibration and acceptance tests (in order)

1. Implementation check (Set A): FE capacitor alone, reversal from −P_S with constant V. This must match
   the analytic NLS eq. (5) with Table I within 1% (computed offline), for V = 0.6-1.8 V and t = 200 ns-1 ms
   (P3 Fig. 1(b)/2).
2. Set B kinetics: refit τ_∞, α, E_a median/spread and P_S against P1 Fig. 4(c) (table T3). Check the
   quasi-static loop at ≈ 50 V/ms against T1, and minor-loop return-point memory with the T2 waveforms.
3. FeFET (Set B): MW vs PW/V table T4, including the 2 s wait before the read. Then the I_D-V_G points T5:
   V_th(1e-7 A/µm) ≈ −0.01/+0.73 V, MW 0.735 V at ±4.5 V/10 µs.
4. Set C: MW ≈ 1.0 V at ±4 V/10 µs; V_th means 0.65/1.68 V; the SI Fig. 1 iso-MW write points; σ(V_th)
   0.10/0.15 V via domain-count Monte Carlo.
5. Disturb and retention: |V_G| ≤ 1-1.5 V for long times gives no V_th shift. At V_G = 0, check drift
   (risk R3).
6. TCAM cell sanity: ML mismatch discharge in < 1 ns; ≈ 0.35-0.40 fJ/bit at 45 nm.

Top risks (detail in §7): R2 history portability; R1 no P1 parameters from the authors (only a third-party fit, §3.B); R3
depolarization-driven drift/retention in kinetic models; R4 the two films' kinetics disagree by ~10×;
R6/R7 floating gate node and stiff time constants.

---

## 2. The three chosen papers

### 2.0 How figure numbers were read

The Ni 2018 paper (P1) has vector figures. We read the plot data with `mutool draw -F trace` (to stdout, no
files written), mapped each path to the axes using the axis tick marks drawn in the same figure, and matched
colours to legend entries. These numbers are tagged [fig-vector]. The VDST paper (P2) is a scanned page and
the Monte Carlo paper (P3) has raster figures; numbers from those are [fig-raster] and approximate.

---

### 2.1 P1: Ni, Jerry, Smith, Datta, "A Circuit Compatible Accurate Compact Model for Ferroelectric-FETs"

**Citation.** K. Ni\*, M. Jerry\*, J. A. Smith, S. Datta (\*equal contribution), "A Circuit Compatible Accurate
Compact Model for Ferroelectric-FETs," *2018 IEEE Symposium on VLSI Technology*, Digest of Technical Papers,
pp. 131-132, 2018. doi:10.1109/VLSIT.2018.8510622 (DOI as cited in P3 ref. [9]). University of Notre Dame.
2 pages; all equations are inside figures (Fig. 3(a), Fig. 4(a), Fig. 5(a)); there are no numbered text equations.

**Device structure.**
- FeFET (Fig. 1(a), Fig. 2(a), p. 132): n-channel, p-Si(100) / 2 nm SiO2 / 10 nm Hf0.4Zr0.6O2 (HZO) / W gate;
  n+ source/drain. This is an **MFIS** stack. Channel W, L not stated (SEM in Fig. 2(a) has a 5 µm scale bar;
  currents are given per µm of width). **[paper]**
- Calibration capacitor: W / 10 nm Hf0.4Zr0.6O2 / W **MFM** capacitor (Fig. 3(c) inset, Fig. 5). Area not stated.
- Note: abstract says "Hf0.4Zr0.6O2"; Fig. 3 caption typo "H0.4Z0.6O2". Same film.

**Model structure (Fig. 1(b)-(c), text p. 131).**
- MOSFET = BSIM4 [ref 6 of P1], no model card or node given. Ferroelectric = "dynamic Preisach model".
- Coupling: the FE and the MOSFET gate are treated as two series elements sharing one charge:
  `Q_FE(V_FE) = Q_MOS(V_MOS)` and `V_G = V_FE + V_MOS` (text p. 131, "Modeling Framework").
  So although the device is MFIS, the model is MFMIS-like (a lumped internal node between FE and MOS gate).
- Solve order (Fig. 1(c) flowchart): for each V_GS, guess V_MOS → BSIM4 gives Q_MOS → find V_FE from
  Q_MOS = Q_FE(V_FE) by Newton (`V_FE,new = V_FE − Q_FE/Q'_FE`, stop when |Q_MOS − Q_FE(V_FE)| < ε) →
  check |V_GS − (V_FE + V_MOS)| < ε, else update V_MOS ("implemented by solver"). Inside Q_FE: first
  "Ferroelectric History (2)", then "FE Switching Dynamics Unit (3)", then "Static Preisach Model (1)/(2)".
- No depolarization term beyond what the series charge balance gives; no charge trapping; no leakage.

**Equations (exact, as printed in the figures).**

(1) Saturation loop, Fig. 3(a) eq. (1):

    F(V_eff) = Q_o · tanh[ a · (V_eff ± V_C) ]

Sign convention (our reading; the figure only prints "±"): ascending branch F↑ uses (V_eff − V_C), descending
branch F↓ uses (V_eff + V_C), so the ascending branch crosses zero at +V_C. Q_o, a, V_C are fit parameters.
**No values are given in the paper.**

(2) History and minor loops, Fig. 5(a) eqs. (1)-(4):

    (1) Q_FE(V_eff) = P_FE(V_eff) + ε_FE · V_FE / t_FE
    (2) P_FE(V_eff) = m↑/↓ · F(V_eff) + b↑/↓
    (3) m↑/↓ = [P_FE(V_A) − P_FE(V_B)] / [F↑/↓(V_A) − F↑/↓(V_B)]
    (4) b↑/↓ = [P_FE(V_B)·F↑/↓(V_A) − P_FE(V_A)·F↑/↓(V_B)] / [F↑/↓(V_A) − F↑/↓(V_B)]

V_A and V_B are the two most recent turning points; the current branch (↑ when V_eff is increasing, ↓ when
decreasing) is the saturated branch F↑/↓ scaled linearly so that it passes through (V_A, P_FE(V_A)) and
(V_B, P_FE(V_B)) (Fig. 5(b) sketch). Turning-point tracking follows Jiang et al., VLSI Tech. 1997 [P1 ref 7]
(see §3.C for the stack algorithm). Note that P depends on the delayed voltage V_eff but the linear dielectric
term uses the actual V_FE. ε_FE and t_FE: t_FE = 10 nm; **ε_FE value not given.**

(3) Switching dynamics, Fig. 4(a) eqs. (1)-(2) ("RC type delay", following Chow et al. 2004 = P2):

    (1) dV_eff(t)/dt = [ V_IN − V_eff(t) ] / τ(V_IN, V_eff(t))        "Delay Eqn."
    (2) τ = τ_∞ · exp[ (V_0 / V_IN)^m ]                                "Time Constant"

V_IN is the voltage across the ferroelectric; the static model is evaluated at V_FE = V_eff (Fig. 4(b) label
"V_FE = V_eff"). Eq. (2) as printed depends only on V_IN, although eq. (1) writes τ(V_IN, V_eff); the
V_eff-dependence is presumably P2's V_pulse form (§2.2) but this is **uncertain**. Use |V_IN| in practice
(the printed form is undefined for V_IN < 0 with non-integer m). **No values of τ_∞, V_0, m are given.**

**Fitted parameter values.** None are printed (not Q_o, a, V_C, ε_FE, τ_∞, V_0, m, BSIM4 card). The values
below are our estimates from the vector data, for starting fits only.

| Quantity | Value | Source |
|---|---|---|
| t_FE | 10 nm | [paper] |
| Q_o (tanh amplitude) | ≈ 25 µC/cm² | [derived] from Fig. 3(c) loop after removing a linear slope of ≈ 4 µC/cm²/V; agrees with the pulse-data plateau ±24-25 µC/cm² of Fig. 4(c) |
| V_C (descending / ascending) | ≈ 0.70 V / ≈ 1.05 V (zero crossings of P after removing the slope); mean ≈ 0.88 V | [derived] |
| a | ≈ 1.1 V⁻¹ (descending), ≈ 1.6 V⁻¹ (ascending); 1.3 V⁻¹ as a symmetric start | [derived] slope at P = 0 divided by Q_o |
| ε_FE/t_FE | ≈ 4 µC/cm²/V (slope of Q between 2 and 3 V) → εr ≈ 45 for 10 nm | [derived], uncertain: part of that slope is the tanh tail; 30-45 is a reasonable start |
| Imprint | ≈ +0.17 V (mid-point of the two coercive voltages) | [derived] |
| τ (Fig. 4(b) illustration only) | V_IN trapezoid 1.5 V, 1 µs rise, 1 µs flat, 1 µs fall; V_eff reaches 0.87 V at end of rise and ≈ 1.45 V at end of flat → τ(1.5 V) ≈ 0.4 µs | [fig-vector] + [derived]. This is inconsistent with Fig. 4(c), where 1.5 V needs ~10 µs to switch half, so Fig. 4(b) is probably illustrative |

**Validation data (calibration targets) from P1.**

T1. MFM saturated P-V loop, Fig. 3(b)-(c) [fig-vector]. Triangular V_FE ±3 V; turning points at t = 0, 0.119,
… ms in Fig. 5 (same set-up) → sweep rate ≈ 6 V / 0.119 ms ≈ 50 V/ms (Fig. 3(b) itself spans 0-1.2 ms;
period not printed, uncertain). Charge Q (includes dielectric part), µC/cm²:

| V (V) | −3.0 | −2.5 | −2.0 | −1.5 | −1.0 | −0.5 | 0.0 | 0.5 | 1.0 | 1.5 | 2.0 | 2.5 | 3.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| descending, exp | −36.8 (min) | −34.3 | −31.5 | −26.7 | −11.9 | 3.9 | 17.8 | 25.0 | 28.7 | 31.3 | 33.5 | 35.5 | 37.3 (max) |
| descending, P1 sim | −36.8 | −34.4 | −31.6 | −27.0 | −12.4 | 3.7 | 17.5 | 25.0 | 28.6 | 31.2 | 33.5 | 35.4 | 36.9 |
| ascending, exp | −36.8 | −35.5 | −33.8 | −31.9 | −29.5 | −26.6 | −21.8 | −14.4 | 0.5 | 23.1 | 31.7 | 34.8 | 37.3 |
| ascending, P1 sim | — | −35.5 | −33.8 | −31.9 | −29.6 | −26.7 | −22.0 | −14.5 | 0.3 | 22.9 | 31.6 | 34.7 | 37.2 |

Zero crossings: exp Q = 0 at −0.68 V (descending) and +0.99 V (ascending); Q(V=0) = +17.3 / −21.6 µC/cm².

T2. Minor loops, Fig. 5(c)-(k) [fig-vector]. Triangular V_FE waveforms, all starting at A = +3 V:
- (c): +3.0 → −3.0 (t = 0.119 ms) → +1.2 → −1.2 → +1.2 → −3.0 → +3.0 (t = 0.504 ms).
- (d): +3.0 → −3.0 → +2.0 → −1.0 → +1.0 → −2.0 → +3.0 (0.48 ms).
- (e): +3.0 → −3.0 → +2.0 → −1.5 → 0.0 → −2.0 → +1.5 → 0.0 → +3.0 (0.50 ms).
Measured (f)-(h) and simulated (i)-(k) loops are shown for each; numbers on the inner loops were not
extracted (they can be read from the same vector data if needed).

T3. MFM switched polarization vs pulse width and amplitude, Fig. 4(c) [fig-vector]. Start state ≈ −24.8
µC/cm², one pulse of amplitude V and width t, then remanent P read. Pulse widths in the data are
{3, 5, 7, 9, 10} × 10^k s, k = −8 … −4 (30 ns to 1 ms). Experimental points, P_r in µC/cm²:

| t (s) | 0.5 V | 1 V | 1.5 V | 2 V | 2.5 V | 3 V |
|---|---|---|---|---|---|---|
| 1e-7 | −24.9 | −24.8 | −24.3 | −25.1 | −24.7 | −24.7 |
| 3e-7 | −24.8 | −24.5 | −23.9 | −24.4 | −23.8 | −23.5 |
| 5e-7 | −24.7 | −24.3 | −23.5 | −23.7 | −22.8 | −22.1 |
| 1e-6 | −24.6 | −23.7 | −22.1 | −21.4 | −19.5 | −18.1 |
| 3e-6 | −24.2 | −21.7 | −16.6 | −11.1 | −6.1 | −3.6 |
| 5e-6 | −24.0 | −20.0 | −11.4 | −2.1 | 5.9 | 9.7 |
| 7e-6 | −23.8 | −18.6 | −6.8 | 5.4 | 15.3 | 20.0 |
| 1e-5 | −23.7 | −16.6 | −0.8 | 14.1 | 21.6 | 22.4 |
| 3e-5 | −23.3 | −9.4 | 16.1 | 21.8 | 23.3 | 23.8 |
| 1e-4 | −22.9 | −2.5 | 19.4 | 22.3 | 23.7 | 24.1 |
| 3e-4 | −22.6 | 0.9 | 20.3 | 22.6 | 24.0 | 24.4 |
| 1e-3 | −22.2 | 3.3 | 20.9 | 22.8 | 24.2 | 24.9 |

P1's simulated curves on the same plot (sampled from the vector lines), P_r in µC/cm²:

| log10 t | −7.0 | −6.5 | −6.0 | −5.5 | −5.25 | −5.0 | −4.75 | −4.5 | −4.0 | −3.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.5 V | −24.8 | −24.8 | −24.7 | −24.6 | −24.4 | −24.2 | −23.8 | −23.4 | −22.5 | −21.8 |
| 1 V | −24.8 | −24.7 | −24.4 | −23.1 | −21.4 | −18.2 | −13.6 | −9.6 | −4.5 | −1.9 |
| 1.5 V | −24.7 | −24.6 | −23.9 | −20.4 | −14.4 | −2.6 | 9.1 | 14.5 | 18.0 | 19.0 |
| 2 V | −24.7 | −24.4 | −23.4 | −16.1 | −3.1 | 13.9 | 21.2 | 22.6 | 23.2 | 23.4 |
| 2.5 V | −24.7 | −24.3 | −22.7 | −10.1 | 8.7 | 21.2 | 23.5 | 23.7 | 23.8 | 23.9 |
| 3 V | −24.7 | −24.2 | −21.9 | −2.7 | 16.8 | 23.2 | 23.8 | 23.9 | 23.9 | 23.9 |

Half-switching times from the experimental data [derived, linear interpolation in log t]:
t50 ≈ 2.5e-4 s (1 V), 1.05e-5 s (1.5 V), 5.4e-6 s (2 V), 4.0e-6 s (2.5 V), 3.5e-6 s (3 V); 0.5 V switches
only ≈ 5% in 1 ms. A single Merz/NLS law fits these t50 values with τ_∞ ≈ 2.5 µs, V_0 ≈ 1.9 V, m ≈ 2.4
(t50 = τ_∞·exp[(V_0/V)^m]; check: 2 V → 6.0 µs, 3 V → 3.5 µs, 1.5 V → 14 µs) [derived, uncertain]. The
saturation of t50 near 3-4 µs at high voltage may be partly the measurement set-up (P1 does not state its
set-up time constant).

T4. FeFET memory window vs program/erase pulse, Fig. 6(d) [fig-vector]. Symmetric ±V pulses of width PW,
MW read from I_D-V_G (criterion not stated; Fig. 6(b) MW = 735 mV matches the 1e-7 A/µm constant-current
criterion, see T5). Experimental MW in volts:

| PW (s) | 2 V | 2.5 V | 3 V | 3.5 V | 4 V | 4.5 V |
|---|---|---|---|---|---|---|
| 5e-8 | −0.01 | −0.02 | −0.02 | −0.01 | 0.07 | 0.21 |
| 1e-7 | −0.01 | −0.02 | −0.02 | 0.02 | 0.18 | 0.36 |
| 5e-7 | −0.02 | −0.02 | 0.02 | 0.15 | 0.40 | 0.65 |
| 1e-6 | −0.02 | −0.03 | 0.06 | 0.24 | 0.47 | 0.69 |
| 5e-6 | −0.03 | 0.01 | 0.20 | 0.42 | 0.62 | 0.74 |
| 1e-5 | −0.04 | 0.03 | 0.26 | 0.49 | 0.62 | 0.74 |
| 5e-5 | −0.03 | 0.12 | 0.37 | 0.55 | 0.58 | 0.74 |
| 1e-4 | −0.02 | 0.17 | 0.45 | 0.56 | 0.62 | 0.73 |
| 5e-4 | 0.01 | 0.26 | 0.49 | 0.54 | 0.63 | 0.67 |
| 1e-3 | 0.02 | 0.29 | 0.47 | 0.57 | 0.63 | 0.67 |
| 5e-3 | 0.08 | 0.31 | 0.50 | 0.59 | 0.62 | 0.64 |
| 1e-2 | 0.10 | 0.32 | 0.53 | 0.57 | 0.62 | 0.66 |

P1 simulated MW (same PW columns as rows above, in order 5e-8 … 1e-2):
2 V: 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.01 0.01 0.02 0.05 0.07;
2.5 V: 0.00 0.00 0.00 0.01 0.03 0.05 0.12 0.16 0.22 0.25 0.29 0.31;
3 V: 0.00 0.00 0.04 0.09 0.23 0.29 0.37 0.39 0.43 0.45 0.48 0.48;
3.5 V: 0.01 0.03 0.23 0.33 0.45 0.48 0.53 0.54 0.57 0.58 0.60 0.60;
4 V: 0.03 0.16 0.45 0.51 0.59 0.60 0.64 0.64 0.66 0.67 0.68 0.69;
4.5 V: 0.15 0.36 0.59 0.62 0.67 0.69 0.71 0.72 0.73 0.74 0.75 0.75.
Note: measured MW falls at long PW for ≥ 4 V (0.74 → 0.64-0.67 V); P1's Fig. 2(b) labels that corner
"Charge Trapping". The model has no trapping and keeps rising. Fig. 2(b) is a colour map (PW 1e-7-1e-2 s,
V_PRG/−V_ERS 1.0-4.5 V, MW scale −0.8…+0.8 V); not extracted (raster).

T5. FeFET I_D-V_G after ±4.5 V, 10 µs (Fig. 6(b) exp, 6(c) sim) [fig-vector]. Currents in A/µm; V_DS not
stated for this figure (Fig. 7 uses 50 mV; uncertain).

| Quantity | Program (+4.5 V) exp | Erase (−4.5 V) exp | Program sim | Erase sim |
|---|---|---|---|---|
| V_G at 1e-9 A/µm | −0.43 V | +0.20 V | −0.50 V | +0.24 V |
| V_G at 1e-8 A/µm | −0.24 V | +0.42 V | −0.42 V | +0.32 V |
| V_G at 1e-7 A/µm | −0.01 V | +0.73 V | −0.26 V | +0.47 V |
| MW at 1e-7 A/µm | 0.74 V (paper label: 735 mV) | | 0.73 V (label: 740 mV) | |
| I_D at V_G = 0.5 V (read) | 7.9e-7 | 1.9e-8 | 9.1e-7 | 1.2e-7 |
| I_D at V_G = 1.0 V | 1.5e-6 | 3.7e-7 | 1.5e-6 | 6.5e-7 |
| SS (1e-9→1e-8) | ≈ 185 mV/dec | ≈ 220 mV/dec | ≈ 80 mV/dec | ≈ 80 mV/dec |

So the paper's sim matches MW but not the subthreshold slope or the read-current ratio (exp ≈ 41×, sim
≈ 7.5× at 0.5 V). Protocol (Fig. 6(a)): erase pulse (0-20 µs window), wait 2 s, read sweep, program pulse at
2 s + 50 µs, wait, read at 4 s.

T6. Analog (partial switching), Fig. 7 [fig-vector, labels uncertain]. Pulse scheme: increasing amplitude
V_{i+1} > V_i (Fig. 7(a)). Fig. 7(b) exp family: V_ERS −2.9 to −4.8 V in 0.1 V steps; Fig. 7(c) sim: −1 to
−4 V in 0.1 V steps (different voltages from experiment; not explained). G_DS at V_GS,read = 0.5 V,
V_DS = 50 mV: exp rises from ≈ 8 µS to ≈ 850 µS over ≈ 33 pulses then falls to ≈ 43 µS by pulse ≈ 60;
sim rises to ≈ 770 µS over 31 pulses then falls.

**Stated limitations (P1).** Only implicit: L-K models criticised as single-domain (p. 131). The model has
no charge trapping (visible in Fig. 2(b)/6(d)), no variation, no stochasticity, no leakage, no
temperature. No implementation language is stated ("circuit compatible"; the flowchart shows an iterative
solver). No timestep or convergence notes.

---

### 2.2 P2: Chow, Sheikholeslami, Cross, Masui, "A Voltage-Dependent Switching-Time (VDST) Model of Ferroelectric Capacitors for Low-Voltage FeRAM Circuits"

**Citation.** J. Chow, A. Sheikholeslami (Univ. of Toronto), J. S. Cross, S. Masui (Fujitsu Laboratories),
"A Voltage-Dependent Switching-Time (VDST) Model of Ferroelectric Capacitors for Low-Voltage FeRAM
Circuits," *2004 Symposium on VLSI Circuits, Digest of Technical Papers*, paper 26.3, pp. 448-449, 2004.
IEEE doi not printed on the page (P1 cites it as "J. Chow et al., VLSI Circuits Dig. Tech. Pap., 2004").

**Device.** PZT ferroelectric capacitors, not HfO2. Two technologies: 0.5 µm PZT (V_dd = 5 V) and 0.35 µm
PZT (V_dd = 3 V), switching data from Stolichnov et al., APL 83, 3362 (2003) [P2 ref 6]; circuit validation on
a 0.35 µm CMOS/PZT FeRAM test chip (differential capacitance read scheme, DCRS, Eslami et al. VLSI Circuits
2002 [ref 7]; 1T1C and 2T2C arrays, Fig. 5). No thicknesses or areas given.

**Model (Fig. 2, eqs. (1)-(4), p. 448).** A dynamic part delays V_in through n parallel first-order
sections with voltage-dependent time constants; a static part (the Preisach-type model of Jiang et al., VLSI
Tech. 1997 [P2 ref 1]) maps the weighted effective voltage to charge Q(V_eff):

    (1) V_eff(t) = μ1·V_eff1(t) + μ2·V_eff2(t) + … + μn·V_effn(t),   μ1 + μ2 + … + μn = 1
    (2) dV_effi(t)/dt = ( V_in(t) − V_effi(t) ) / τ_i
    (3) τ_i(V_pulse,i) = τ_∞ · exp( (V_0 / V_pulse,i)^m )
    (4) V_pulse,i(V_effi) = V_in − c_i − k_i·(V_effi − c_i)^x,   k_i = (V_in − c_i)^−(x−1)

c_i = V_effi at the last change of V_in, so that V_pulse,i(c_i) = V_in − c_i and V_pulse,i(V_in) = 0
(boundary conditions stated in the text). As V_effi → V_in, V_pulse,i → 0 and τ_i → ∞, which gives the slow
(log-time-like) tail of switching. x sets how fast τ_i grows: x = 1 gives V_pulse = V_in − V_eff (the model
of Kuhn et al. 2000 [ref 3]) and fits the slower 0.5 µm PZT; x = 2 keeps τ_i small longer and fits the faster
0.35 µm PZT (Fig. 3, Fig. 4(b)-(c)). Fig. 2 draws each section as a resistor of value τ_i into a 1 F
capacitor, and the static part as a controlled source Σμ_i·V_effi driving the hysteretic C_static.

Implementation notes for us:
- Whether τ_∞, V_0, m differ between the n sections is **not stated** (uncertain). With identical parameters
  all sections would be identical, so in practice they must differ (or n = 1).
- c_i requires detecting "a change of V_in" (an event); for a continuous V_in this is ill-defined. In
  SPICE, use a piecewise-defined drive or drop c_i (x = 1 needs no c_i). Use |V_pulse| and sign handling
  for negative steps (eq. (4) with non-integer x is undefined for negative bases).
- Guard V_pulse → 0 (τ → ∞) with a floor, e.g. τ = τ_∞·exp(min((V_0/max(|V_pulse|,ε))^m, 80)).

**Parameter values.** None printed: τ_∞, V_0, m, n, μ_i are not given; only x = 1 (0.5 µm PZT) and x = 2
(0.35 µm PZT). Static-model parameters are in Jiang 1997 (not in P2).

**Validation data.** All figures are from a scanned page; numbers are [fig-raster], ±10%.
- Fig. 1: 1T1C cell at V_dd = 3 V, 1.8 V plate-line step; with zero switching time the bit line settles in
  < 50 ns (text); with switching time it stays well below its final value over the 0-300 ns window.
- Fig. 4: circuit of Fig. 4(a) (P1 sets the state, P2 of amplitude v2 and width t2 reverses, P3 reads).
  Switched polarization vs t2 = 1e-8 … 1e-2 s for v2 = 1.5, 2, 3 V. (b) 0.5 µm PZT, x = 1: at 3 V about
  25 µC/cm² at 10 ns rising to about 31 at 10 ms; at 2 V about 10 → 27; at 1.5 V about 2 → 22. (c) 0.35 µm
  PZT, x = 2: 3 V about 31 → 35; 2 V about 20 → 33; 1.5 V about 3 at 10 ns, about 28 by 10 µs, about 33 at
  10 ms. All approximate.
- Fig. 6: test chip at V_dd reduced to 1.8 V; bit-line voltages BL1 ≈ 0.6-0.7 V and BL0 ≈ 0.4 V develop
  gradually from 1 ns to 100 µs.
- Fig. 7-8: reference capacitor of four series FE capacitors sees only V_BLref/2, switches slowly; the
  VDST model reproduces the measured failure (V_BLref > V_BL0 and V_BL1, chip always outputs '1'); BL traces
  0-3 V over 0-30 ns.

**Implementation statement.** "Eq. (1)-(4) are implemented in Verilog-A and integrated into Spectre"; same
accuracy as a circuit-element implementation with a 20-fold reduction in simulation time (p. 448).

**Limitations.** Not discussed beyond the need to calibrate x per technology. Phenomenological; no
physical link of V_0, m to material constants; no variation.

---

### 2.3 P3: Alessandri, Pandey, Abusleme, Seabaugh, "Monte Carlo Simulation of Switching Dynamics in Polycrystalline Ferroelectric Capacitors"

**Citation.** C. Alessandri, P. Pandey, A. Abusleme, A. Seabaugh, "Monte Carlo Simulation of Switching
Dynamics in Polycrystalline Ferroelectric Capacitors," *IEEE Transactions on Electron Devices*, vol. 66,
no. 8, pp. 3527-3534, Aug. 2019. doi:10.1109/TED.2019.2922268. Univ. of Notre Dame and Pontificia Univ.
Católica de Chile. Short version: IEDM 2018, 16.2 [P3 ref 18]. Parameter-extraction method: Alessandri et al.,
IEEE EDL 39(11), 1780-1783, 2018 [ref 15].

**Device.** MFM capacitor with Hf0.5Zr0.5O2, T_FE = 8.3 nm (p. 3529; fabrication in ref [18]). Electrodes and
area not stated in this paper. Offset voltage V_OS = 80 mV measured from P-V loops: V_FE = V_A + V_OS;
E_FE = V_FE/T_FE (p. 3529). Measurement set-up time constant < 10 ns; pulses ≥ 200 ns used (p. 3529).

**Ferroelectric model: field-dependent nucleation-limited switching (NLS) generalised to arbitrary
waveforms by per-grain Monte Carlo.**

    (1) P(t_S < t | τ) = 1 − exp(−t/τ)                      (Poisson, original NLS)
    (2) P(t_S < t | τ, β) = 1 − exp[ −(t/τ)^β ]             (Weibull, used here)
    (3) r(t) = (β/τ)·(t/τ)^(β−1)                            (switching rate)
    (4) τ(E_a, E) = τ_∞ · exp[ (E_a/E)^α ]                   (Merz-type law)
    (5) P(E_FE, t) = −P_S + 2·P_S ∫_0^∞ P(t_S < t | τ(E_a, η·E_FE), β) f(η) dη
    (6) GB2(η | a, b, p, q) = (|a|/b)·(η/b)^(a·p−1) / { B(p,q)·[1 + (η/b)^a]^(p+q) }
    (7) g(E'_a) = (η²/E_a)·f(η),  with E'_a = E_a/η   (equivalent distribution of effective activation fields)

Monte Carlo (Algorithms 1-3, pp. 3529-3532): N grains, each with E_a^(i) sampled from g(E'_a), state
s^(i) = ±1, and a history variable h^(i):

    (8)  P^(i)(t_S < t+Δt | t_S > t) = 1 − exp[ (t/τ^(i))^β − ((t+Δt)/τ^(i))^β ]      (constant field)
    (9)  P_FE(t) = (P_S/N)·Σ_i s^(i)(t)
    (10) h^(i)(t) = ∫_{t_o}^{t} dt' / τ(E_FE(t'), E_a^(i))                            (arbitrary field)
    (11) r^(i)(t) = β/τ^(i)(t) · (h^(i)(t))^(β−1)
    (12) P^(i)(t_S < t+Δt | t_S > t) = 1 − exp[ (h^(i)(t))^β − (h^(i)(t+Δt))^β ]
    (13) Q_FE(t) = P_FE(t) + ε_FE·E(t)
    (14) h^(i) ← h^(i)·γ(t_OFF)          (relaxation during off-time between pulses)

Algorithm 2: a grain is updated only if s^(i)·E(t) < 0 (field opposes it); τ^(i) = τ_∞·exp[(E_a^(i)/|E(t)|)^α];
h ← h + Δt/τ; Bernoulli trial with probability from (12); on success flip s and apply the h-relaxation rule.
Algorithm 3 adds: on switch h ← h_S; when s·E ≥ 0, "relax h" (functional form not determined).

History rules tested (pp. 3530-3531): reset h = 0 on switching matches loops with 10 s hold (Fig. 3(b));
not resetting matches 1 ms hold (Fig. 3(c)) and the minor-loop sequence (Fig. 4); h ← γ·h with γ = 0.55
for t_OFF = 1 µs and γ = 0.3 for t_OFF = 10 µs matches pulse trains (Fig. 5). Text says the short hold was
"10 ms" but Fig. 3(c) is labelled "T_H = 1 ms" (inconsistency in the paper).

**Fitted parameters, Table I (p. 3529) [paper], 8.3 nm HZO:**

| Parameter | f(η) column | g(E'_a) column (used in simulations) |
|---|---|---|
| E_a | 1.77 MV/cm | — |
| a | 12.1 | 12.1 |
| b | 0.99 | 1.79 MV/cm |
| p | 0.633 | 0.691 |
| q | 0.691 | 0.633 |
| P_R (row label as printed; used as P_S in eqs.) | 22.9 µC/cm² | 22.9 µC/cm² |
| τ_∞ | 387 ns | 387 ns |
| α | 4.11 | 4.11 |
| β | 2.07 | 2.07 |

Consistency checks [derived]: (i) If η ~ GB2(a, b, p, q) then E_a/η ~ GB2(a, E_a/b, q, p) = GB2(12.1,
1.788 MV/cm, 0.691, 0.633), matching the g column. (ii) Fig. 1(b) ΔP saturates near 45 µC/cm² ≈ 2 × 22.9.
(iii) Mode of g = b·[(a·p − 1)/(a·q + 1)]^(1/a) = 1.766 MV/cm (Fig. 1(c) peaks near 1.8 MV/cm).
(iv) ln E'_a has mean ln b + [ψ(p) − ψ(q)]/a → geometric mean ≈ 1.82 MV/cm, and standard deviation
sqrt[ψ1(p) + ψ1(q)]/a ≈ 0.21 (ψ, ψ1 = digamma, trigamma). So a log-normal with median 1.82 MV/cm and
σ_ln ≈ 0.21 is a usable first approximation (GB2 tails are heavier; compute exact GB2 quantiles for the
final model). In volts at 8.3 nm: median activation voltage ≈ 1.51 V. (v) Example time constants:
τ(E'_a = 1.77 MV/cm, V_FE = 1.5 V) ≈ 0.97 µs; at 1.0 V ≈ 50 µs; at 0.7 V (0.84 MV/cm) ≈ 7.5e2 s.
ε_FE is used in eq. (13) but **its value is not reported**.

**Validation data.**
- Fig. 1 [fig-raster]: protocol: conditioning triangle ±V_R = 2.5 V (3 ms), write pulse V_P/t_P, read by
  double triangles (4 ms); t_P from 200 ns to 1 ms in ×1.5 steps; V_P = 0.6-1.8 V in 0.1 V steps (Fig. 1
  caption and legend). ΔP vs log t_P: dots = data, lines = NLS fit with Table I. ΔP rises from ~0 to ≈ 45
  µC/cm²; 1.8 V half-switches near 1 µs, 1.0 V near 10-30 µs, 0.6 V only a few µC/cm² by 1 ms (approximate).
- Fig. 2: normalised polarization vs log t_P at V_P = 0.6, 1.0, 1.4, 1.8 V: NLS = Monte Carlo with 5000
  grains (indistinguishable); 100 grains: 10 runs show spread.
- Fig. 3: P-V loops (double triangles, ±2.5 V; 5 ms segments per Fig. 3(a)), ≈ ±22 µC/cm² plateaus;
  measured vs simulated for hold 10 s and 1 ms.
- Fig. 4: triangle waveform of varying amplitude (±2 V max, 30 ms record), Q_FE ±30 µC/cm²; minor loops
  entering/exiting, drift of minor loops with cycling reproduced (with no h-reset).
- Fig. 5: single pulse of width 1-20 µs vs train of 1 µs pulses with t_OFF = 1 or 10 µs, amplitudes 1, 1.25,
  1.5 V; normalised P after 20 µs total: about 0.7-0.75 (1.5 V), about 0.2-0.3 (1.25 V), about −0.6 to −0.7
  (1 V) (approximate); PWM ends higher than trains.
- Fig. 6: FE-DE stacks with C_DE/C_FE = 5, 2.5, 1 (triangle 4 ms period, 3 V): series dielectric lowers the
  switching onset but does not make it abrupt (unlike L-K); smaller C_DE → less switched P. Square waves 3
  and 4 V, 2 and 5 µs period.
- Fig. 7: device-to-device variation, 200 devices each with N = 500, 100, 20 grains, 20 µs-period square
  wave. FE alone: at 1.5 V, 500 grains give ≈ 2P_S window; 20 grains lose ≈ 50%; at 1.25 V, 20 grains lose
  the window. FE-DE with C_DE = 5·C_FE: 1.5 V gives ≈ P_S window with 500 grains and ≈ 0 with 20 grains;
  needs 2 V to match the FE at 1.5 V (p. 3533 text).
- Fig. 8: 3 grains with E_a = 1, 1.8, 2.6 MV/cm and area fractions 0.45, 0.35, 0.2, train of 2 V / 100 ns
  pulses; stochastic switching after different pulse counts (stair-like P), five repeats.

**Stated limitations (p. 3533).** Nucleation-limited regime only; domain-growth transient assumed
negligible, which "does not necessarily hold for highly scaled FE, especially when there is a large series
capacitance". Constant ε_FE (measured C-V is butterfly-shaped, p. 3531). Relaxation rule for h not
determined. Monte Carlo time stepping, not a SPICE element.

---

### 2.4 How the three papers fit together (for the model writer)

- P1 is the FeFET framework (series FE + BSIM4, tanh Preisach with turning-point history, VDST-style delay).
  It gives the FeFET calibration targets but no parameter values.
- P2 is the origin of P1's delay unit. It adds the V_pulse/x refinement and n parallel sections, no values.
- P3 gives a complete, physically meaningful parameter set (Table I) for switching kinetics with a
  distribution of activation fields, plus variation with grain count. Its deterministic limit (eq. (5)) is a
  multi-domain Preisach model whose hysterons have NLS kinetics. That limit needs no turning-point stack:
  each domain's state is the memory.

---

## 3. Open-source models survey

Rows marked **checked** were re-read by us at the source; the rest come from a web-research pass, and the
URL is given so they can be re-checked. We read source on the web only; nothing was downloaded, cloned or run.

### 3.A Models with code

| Model | URL | Licence | Physics | History | Time dependence | Transistor coupling | OpenVAF |
|---|---|---|---|---|---|---|---|
| **Heracles** (Univ. Groningen / TUM), Fehlings et al., IEEE TED 72(11), 6009-6014 (2025), doi:10.1109/TED.2025.3615577, arXiv:2410.07791 — **checked** (README + `heracles.va` lines) | https://github.com/ncas-tum/heracles ; testbenches https://github.com/ncas-tum/heracles-testbenches | MIT | HfO2 FeCap; two-state kinetic ("non-equilibrium thermodynamics") model; plus interface layer, depletion, TAT/FN leakage, thermal, MC parameters | One state p on an internal node: `p = V(polarization); I(polarization) <+ ddt(p); I(polarization) <+ k_minus*p - k_plus*(1 - p);` No turning points; minor loops only through kinetics | Arrhenius-type rates `k± = (k·T/h)·limexp(−(w_b ∓ w_e)·q/(k·T))`, `w_e = (e_fe − e_off)·d_e` | FeCap only ("Dedicated FeFET … extensions are in development"). ngspice testbench `fefet.sp`: FeCap in series with built-in BSIM4 (`level=54 version=4.8.2`), internal gate node with `R2 gate gnd 10T`; options `reltol=0.001 abstol=1e-12 gmin=1e-12` (web pass) | **Yes**: OSDI binary shipped with each release (README); built with `openvaf-r heracles.va -o heracles.osdi` (web pass) |
| **pfecap** (A. Leushin, 2019) | https://github.com/supadupaplex/pfecap ; annotated fork https://github.com/DavidTobar456/pfecapRevision | GPL-2 | Jiang 1997 / Ni 2018 tanh Preisach: F = Qs·tanh(a(V − dir·Ec·tFE)); P = m·F + b; Q = P + εr·ε0·V/tFE; delay `V(pos,neg) <+ tFE*rho*ddt(q)` | Static `real` arrays of minima/maxima (NUM_PTS = 1000); push on sign change of (V_fe − V_prev) beyond 1e-4 V; pop pairs on wipe-out; ±saturation points found in `@(initial_step)` | ρ (resistive) delay | Charge-driven: needs a modified FET exporting gate charge on a pin (nanoHUB NCFET method); in-model Newton `while` loop with `$random` damping | Unknown; probably fails (module arrays, `$random`); state updated on every Newton iteration (hidden state) |
| **Scalable-FeFET** (implements Deng et al., VLSI 2020; authorship of repo uncertain) | https://github.com/boltma/Scalable-FeFET | none stated (no LICENSE file) | Multi-domain Monte Carlo NLS: τ_i = τ0·exp[(Ea_i/max(|V_sw,i|, V_lim,i))^α], h_i += Δt/τ_i, p = 1 − exp(h_prev^β − h^β) vs `$rdist_uniform`; P = Pr·ΣS_i/ndom + ε·ε0·V/t_fe | Per-domain arrays + `$abstime` forward Euler (hidden state) | NLS | In-file charge-sheet MOS model, MFIS balance by 50-step bisection; gate currents 0 | Will not compile stock (`$rdist_*` unsupported) |
| **nanoHUB NCFET** (Wahab & Alam, Purdue) | https://nanohub.org/publications/95/ (v1.1.3, doi:10.4231/D3QZ22K3Z) | "NEEDS Modified CMC License" | Single-domain L-K: V_FE = 2α·t·Q + 4β·t·Q³ + 6γ·t·Q⁵ + ρ·t·dQ/dt (manual Eq. 5); defaults α = −1.8e11 cm/F, β = 5.8e22 cm⁵/(F·C²), ρ = 9 cm·s/F, t_FE = 10e-7 cm | None beyond the L-K S-curve | ρ·dQ/dt | Modified MVS/BSIM4 source exports gate charge as a voltage; not usable with ngspice's built-in BSIM4 | Unknown |

Default values in these models are not calibrations except where stated. Values in Scalable-FeFET's
`FeFET.va` (cm units): t_fe 8 nm, t_il 1 nm, Pr 25 µC/cm², τ0 1.9e-8 s, α 3.0, β 2, Ea ~ N(2.3 V, 0.4 V),
εr 28, ndom 20; `MFM.va`: Pr 18, τ0 1e-7 s, α 3.2975, εr 50, ndom 2000 (web pass). Heracles defaults:
p_s = 0.27 C/m², t_fe = 9.8 nm, eps_fe = 70, w_b = 1.05 eV, d_e = 7.5e-9 m, e_off = 0 (**checked**).

Verilog-A models described in papers, no public code:
- Chatterjee, Kumar, Gaidhane, Dabhi, Chauhan, Amrouch, "Ferroelectric FDSOI FET modeling for memory and
  logic applications," *Solid-State Electronics* 200, 108554 (2023), doi:10.1016/j.sse.2022.108554 —
  **checked**. Preisach FeCap + BSIM-IMG, MFMIS-style balance (Q_mos = P_FE·W·L, V_total = V_fe + V_mos).
  It stores only two turning points (u, l), detected by comparing V_aux with an RC-delayed copy V_del, not
  by derivatives. Values in §3.B. PDF: https://in4.iue.tuwien.ac.at/pdfs/sispad2022/Ferroelectric-FDSOI-FET-modeling-for-memory-and-logi_2023_Solid-State-Electr.pdf
- Gaidhane et al., Fe-FinFET with BSIM-CMG (IEEE TCAD 2023), same method (web pass).
- Lederer et al. (Fraunhofer IPMS), *Solid-State Electronics* 199, 108501 (2023): Jiles-Atherton FeCap in
  Verilog-A (Spectre). P = (1−c)·P_irr + c·P_anh; P_anh = P_S·L(D_eff/γ), D_eff = D − α·P0,
  L(x) = coth x − 1/x; dP_irr/dt = (P_anh − P0)/(sign(dD/dt)·k − α(P_anh − P0))·dD/dt; fit P_S = 47.2 µC/cm²,
  α = 0.70, k = 2.04e-5 C/cm², γ = 1.74e-5 C/cm², c = 0.04, ε0εr = 9.90e-15 F/m (web pass).
  https://in4.iue.tuwien.ac.at/pdfs/sispad2022/SPICE-compatible-semi-empirical-compact-model-for-ferr_2023_Solid-State-Elec.pdf
- Guo et al., SISPAD 2025 (BJUT): Ni 2018 Preisach + RC delay + NMP trapping + BSIM-BULK 106.2, HSPICE.
  https://in4.iue.tuwien.ac.at/pdfs/sispad2025/SISPAD2025_097.pdf (web pass)
- Penn State Aziz et al. EDL 2016 L-K SPICE model: no public code found.

**Takeaway.** Heracles is the only open, licence-clean model confirmed to compile with OpenVAF and run in
ngspice. It is a single-state FeCap, not Preisach and not FeFET, but its pattern matches our v0: state on an
internal node, `ddt` only, `limexp`, clamped τ, series with built-in BSIM4 through a 10 TΩ-grounded internal
gate node. No open model implements a multi-domain NLS-Preisach FeFET without hidden state, so we write our
own.

### 3.B Published parameter values for the P1 (Ni 2018) model

- **Chatterjee et al. 2023, Table 1 — checked**, "validation of the Fe-Cap model against experimental data
  from [6]" (= P1), Fig. 3: **P_r = 18.5 µC/cm², P_s = 19 µC/cm², V_c = 1.2 V, t_fe = 10 nm, ε_fe = 40,
  τ_v = 1.5 µs** (constant delay). Equations as printed:
      (1) V_aux = V_in − τ_v·dV_aux/dt
      (2) P_aux = m·P_s·tanh(w(V_aux ± V_c)) + P_off
      (3) w = (t_fe/(2V_c))·ln((P_s + P_r)/(P_s − P_r))
      (4) m↑,↓ = (P_aux,u − P_aux,l) / {P_s·[tanh(w(V_aux,u ± V_c)) − tanh(w(V_aux,l ± V_c))]}
      (5) P_off↑,↓ = P_aux,u/l − m↑,↓·P_s·tanh(w(V_aux,u/l ± V_c))
  "For the main loop, m = 1 and P_off = 0." Eq. (3) as printed has units m/V unless the tanh argument is a
  field; in voltage form w = ln(75)/(2·1.2 V) = 1.80 V⁻¹ [derived; unit ambiguity uncertain]. Their FeFET
  (100 nm wide) shows MW = 1.186 V (Fig. 4). Compare our fit from P1's vector data (§2.1): Q_o ≈ 25,
  a ≈ 1.1-1.6 V⁻¹, V_C ≈ 0.70/1.05 V, εr ≈ 30-45. Their larger V_c and smaller P_s use a constant τ_v
  delay, which shifts the apparent coercive voltage.
- **Guo et al., SISPAD 2025** (web pass): P1 model re-calibrated to Yin et al. TCAS-II 2019 data: T_FE =
  10 nm HfO2, T_IL = 3 nm SiO2, W = L = 10 µm, **P_r = 18.5 µC/cm², E_c = 1.2 MV/cm**, ±4 V/10 µs → MW 0.84 V
  (sim) vs 0.86 V (meas). No τ given.
- **Ni et al. 2019 SI — checked**: m = 2 in τ ∝ exp((V_o/V_APP)²); no V_o printed (our fitted line values
  are in §4.1).
- Not obtained: Yin et al. TCAS-II 66(9):1577 (2019) (paywalled); Jerry et al., J. Phys. D 2018; Jerry/Yin
  PhD theses. Kazemi et al. (Sci. Rep. 2022 Methods, web pass) say the Ni Preisach model "is not scalable and
  only supports 200 nm × 100 nm (W × L)" (uncertain).

### 3.C Preisach-style FE capacitor models and the turning-point algorithm

**Miller et al. 1990** (S. L. Miller, R. D. Nasby, J. R. Schwank, M. S. Rodgers, P. V. Dressendorfer,
"Device modeling of ferroelectric capacitors," J. Appl. Phys. 68, 6463 (1990); paywalled, form confirmed
via secondary sources: Pešić et al. arXiv:1709.06983 Eq. 4; Toprasertpong et al. arXiv:2211.01584 Eq. 5):

    P⁺_sat(E) = P_s · tanh[ (E − E_c) / (2δ) ],   δ = E_c · [ ln( (1 + P_r/P_s) / (1 − P_r/P_s) ) ]⁻¹
    P⁻_sat(E) = −P⁺_sat(−E)
    (equivalently P_s·tanh[ (1/(2E_c))·ln((P_s + P_r)/(P_s − P_r))·(E ∓ E_c) ]; check: P⁺_sat(0) = −P_r)

**Miller et al. 1991** (S. L. Miller, J. R. Schwank, R. D. Nasby, M. S. Rodgers, J. Appl. Phys. 70, 2849
(1991)): dP_d/dE = Γ·dP_sat/dE with ξ = +1 (rising) / −1 (falling). The often-quoted
Γ = 1 − tanh{[(P_d − P_sat)/(ξ·P_s − P_d)]^½} is **unverified** (secondary snippets only). Jiang 1997 states
that earlier models "either do not … or incorrectly account for the history dependence", citing Miller 1991.

**Jiang et al. 1997** (B. Jiang, P. Zurcher, R. E. Jones, S. J. Gillespie, J. C. Lee, "Computationally
efficient ferroelectric capacitor model for circuit simulation," Symp. VLSI Technology 1997, pp. 141-142;
full text via https://consensus.app/papers/details/9416878e33aa53bb801ae3b513c67dc9/, web pass):
- Eq. 1: Q(t) = ∬_{α≥β} μ(α,β)·γ_αβ[V(t)] dα dβ (Preisach integral; OCR uncertain).
- Eq. 2: F↑↓(V) = Q_s·tanh[a(V − V_c±)], separate V_c+ and V_c−.
- Memory rule: turning points are where dV/dt changes sign, tagged + (local max) / − (local min). "Only the
  alternating series of dominant input voltage extrema are important." The saturation points (+∞, +Q_s) and
  (−∞, −Q_s) are permanent first entries (OCR garbled; uncertain). Wipe-out (Table 1): points "are erased in
  pairs. Each new local maxima erases the previous local maxima of equal or lesser value and its following
  local minima; each new local minima erases the previous local minima of equal or greater value and its
  following local maxima."
- Branches: "as the voltage is increased (decreased), the Q-V curve always passes through previous +(−)
  turning points." Eq. 3: f_i(V) = m_i·F(V) + b_i, through (v_i, q_i) and (v_{i+1}, q_{i+1}); Eq. 4:
  m_i = (q_i − q_{i+1})/(F(v_i) − F(v_{i+1})), always in [0, 1]. Linear part = parallel capacitor C_l;
  relaxation neglected; implemented in SABER.

**Dragosits PhD thesis**, TU Wien 2000, "Modeling and simulation of ferroelectric devices"
(https://repositum.tuwien.at/bitstream/20.500.12708/20709/1/Dragosits%20Klaus%20-%202000%20-%20Modeling%20and%20simulation%20of%20ferroelectric%20devices.pdf,
web pass): (4.5) P = k·P_sat·tanh(w(E ± E_c)) + P_off; (4.12) k = (P_old − P_turn)/{P_sat·[tanh(w(E_old ± E_c))
− tanh(w(E_turn ± E_c))]}; (4.13) P_off = P_turn − k·P_sat·tanh(w(E_turn ± E_c)). Stack (§6.3.1): "If the
direction changes, the values of the previous operating point are pushed to the stack… The value of the
electric field is compared to its precursor on the stack, and if the new value is higher, the old value is
removed." Transient (5.2): E = E_stat + τ_Ef·dE/dt plus a polarization relaxation term τ_P.

**Turning-point stack in pseudo-code** (synthesis of Jiang Table 1 and Dragosits §6.3.1; for an offline
reference implementation, not for SPICE):

    stack = [(+inf, +Q_s), (−inf, −Q_s)]          # permanent
    on each accepted time point with new V:
      if direction reversed: push (V_prev, P_prev)
      while rising and len(stack) > 2 and V >= stack[-2].V: pop 2   # wipe-out: new max beats old max
      while falling and len(stack) > 2 and V <= stack[-2].V: pop 2   # new min beats old min
      branch = F↑ if rising else F↓
      (V_A, P_A) = stack[-1];  (V_B, P_B) = stack[-2]   # current loop ends at the previous opposite turning point
      m = (P_A − P_B)/(F(V_A) − F(V_B));  b = (P_B·F(V_A) − P_A·F(V_B))/(F(V_A) − F(V_B))
      P = m·F(V) + b

### 3.D Verilog-A practice for hysteresis memory

- Wang & Roychowdhury, "Well-posed models of memristive devices," arXiv:1605.04897, §III-IV
  (https://arxiv.org/abs/1605.04897, web pass). Do not keep state in `real` variables or `idt()`, and do not
  integrate inside the model with `$abstime`/`@(initial_step)`/`$bound_step` (that is forward Euler: it
  breaks DC/AC/HB and truncation-error control). Put the state on an internal node:
  `s = V(ns,n); I(ns_br1) <+ f(V,s); I(ns_br2) <+ ddt(-tau*s);`. Scale unknowns to ~1. Replace if/else
  with smooth switches/clips and safe exponentials. Bound the state with clip terms.
- Best-practice summary (McAndrew et al., "Best practices for compact modeling in Verilog-A," IEEE J-EDS 3,
  383 (2015); Coram), as summarised in https://tianshiwang.github.io/talks/2017-Purdue-review-tianshi-v1.pdf
  slide 6: "DO NOT use memory states… event control statements… idt… random number generators."
- Kundert, "Hidden state in Verilog-A" (https://designers-guide.org/analysis/hidden-state.pdf): hidden
  state is invisible to the simulator; recompute or move it to nodes.
- OpenVAF-specific (web pass, not re-checked):
  - The dwarning/VA-Models README lists `$abstime()`, `@cross()`, Laplace filters, indirect contributions
    and paramset as unsupported. This conflicts with the compiler-source reading in §6, which does not list
    `$abstime`, so treat `$abstime` as unsafe.
  - OpenVAF-Reloaded PR #41 (open) would run cross/above/timer bodies "on every evaluation".
  - Issue #44 "Hidden state not fully implemented" is reported closed in Oct 2026 with no fix shown.
  - One claim says ngspice-46 passes the same OSDI state slot as prev and next (uncertain; not about
    ngspice 45).
- Chatterjee/Gaidhane store two turning points and detect them with an RC-delayed copy. That still needs
  stored values. A node-only alternative is a smooth track/hold node per stored point (untested idea from
  the web pass). Our v0 avoids both by using hysteron-ensemble states.
- Clamp τ: P1's τ_∞·exp[(V_0/V)^m] diverges at V → 0. Deng's implementation caps τ at 1e9 s; Heracles
  clamps a τ to [1e-15, 1e6] s.

---

## 4. FeFET TCAM / CAM / Ising device targets

Legend: (meas) measured, (sim) simulation. "n.r." = not reported in what we could read. Rows marked
"checked" were verified by us against the source; the others come from a web-research pass with the URL
given and were not re-read by us (treat single numbers as uncertain until re-checked).

### 4.1 Ni et al. 2019, the reference 2FeFET TCAM

K. Ni, X. Yin, A. F. Laguna, S. Joshi, S. Dünkel, M. Trentzsch, J. Müller, S. Beyer, M. Niemier, X. S. Hu,
S. Datta, "Ferroelectric ternary content-addressable memory for one-shot learning," *Nature Electronics*
2, 521-529 (2019), doi:10.1038/s41928-019-0321-3. Main text paywalled (not read). Supplementary
Information (SI) read by us (checked):
https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41928-019-0321-3/MediaObjects/41928_2019_321_MOESM1_ESM.pdf

- Device: "8nm HfO2 FeFET" (SI p. 2, p. 17). Co-authors are GlobalFoundries Dresden; 28 nm HKMG is likely
  but not stated in the SI (uncertain). Gate leakage "on the order of pA at 1V", gate resistance ~1e12 Ω
  (SI p. 17).
- Write (SI Fig. 5 caption): "Erase pulse of 4 V, for 10 μs and a program pulse of -4V, for 10 μs".
  Naming: here program = −4 V = high V_th. (P1 used +4.5 V = "PRG" = low V_th. Naming differs between
  papers; physically a positive gate pulse gives low V_th on an n-FeFET in all sources.)
- V_th distributions, 40 devices, first program/erase cycle (SI Fig. 5(b)) [fig-vector, from the fitted
  Gaussian curves]: erase (+4 V) **V_th ≈ 0.65 V, σ ≈ 0.10 V**; program (−4 V) **V_th ≈ 1.68 V, σ ≈
  0.15 V**; so **MW ≈ 1.03 V** between means. 50 cycles per device also measured (Fig. 5(a); not
  extracted). V_th criterion not stated in the SI.
- Switching kinetics (SI p. 2, Fig. 1): "τ∝exp((Vo/VAPP)²)" (nucleation-limited), V_APP = gate pulse
  amplitude. Fig. 1 plots pulse width vs 1/V_APP² for constant MW = 0.2 … 1.0 V [fig-vector]. Fitted lines
  log10(t) = log10(τ0) + V0²/(ln10·V_APP²): MW 0.2 V: V0 ≈ 10.6 V, τ0 ≈ 10^-11.7 s; 0.4 V: 11.7 V,
  10^-12.2 s; 0.6 V: 12.7 V, 10^-12.6 s; 0.8 V: 13.5 V, 10^-12.6 s; 1.0 V: 16.0 V, 10^-13.8 s (intercepts
  uncertain ±0.1 decade). Data points for MW = 1.0 V: 4.0 V at 50-230 ns, 3.86 V at 0.5 µs, 3.77 V at 1 µs,
  3.66 V at 10 µs, 3.30 V at 100 µs. For MW = 0.2 V: 3.38 V at 50 ns, 2.82 V at 1 µs, 2.60 V at 10 µs,
  2.50 V at 1 ms, 2.18 V at 10 ms. These are the cleanest write-time targets for a 28 nm-class FeFET.
- Cell operation (SI pp. 3-4, 7, 10): 2 FeFETs per cell, gates on SL and SL̄, drains on the match line
  (ML), sources on ScL. Stored '0' = left FeFET low-V_th, right high-V_th. Search '1': SL high, SL̄ low;
  mismatch discharges the precharged ML through the low-V_th FeFET. Don't care: write both FeFETs high-V_th,
  or search with 0 V (or negative) on both SL and SL̄. ML precharged by a PMOS in simulation; the 1×6
  measured array used a passive resistor. During write, ML and ScL grounded. Measured waveforms on a ~110 ms
  axis (instrument-limited); SPICE search < 1 ns (SI Fig. 4).
- Simulation model (SI p. 6): Spectre with the P1 model described as "multi-domain Preisach model … each
  domain is described by a single retangular hysteron … a distribution of the coercive field … adopts the
  nucleation limited domain switching dynamics model"; "parasitic capacitances on the metal lines (45nm node)
  are included". No parameter values. (This description is a hysteron-ensemble with NLS kinetics, i.e. the
  same structure we recommend for v0, not the tanh turning-point form printed in P1.)
- Degree-of-match (Hamming) sensing up to 8 mismatches in a 1×64 word (sim, SI Fig. 8); 3.2 Ω line
  resistance between cells (SI p. 17). System-level: 2.4× lower energy than a 16T CMOS TCAM (SI Fig. 13).

### 4.2 Other targets

| Work | Node / stack | MW | Write V / width | Read / search V | I_on/I_off | σ(V_th) | Endurance | Retention | E / delay per bit | Cell area | Source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Yin et al., Nat. Commun. 15, 2419 (2024), FeFET CiM annealer, 32×32 1FeFET1R array (meas) — **checked** | GF 28 nm HKMG; poly-Si/TiN 2 nm/doped HfO2 8 nm/SiO2 1 nm/p-Si (Methods) | n.r. as a number | ±4 V, 1 µs gate pulses; V_W/3 inhibit (Fig. S5a) | "V_write/V_read = 4/1 V" (Intro) | > 1000 with 1 MΩ series resistor (Fig. 2h-i) | variation "significant"; suppressed by the resistor | n.r. | CiM result stable to 1e5 s (Fig. S5c) | n.r. | n.r. | https://pmc.ncbi.nlm.nih.gov/articles/PMC10948773/ |
| Qian et al., DATE 2021, 2FeFET-1T / 2FeFET-2T TCAM (sim) — **checked** | 45 nm PTM + Ni Preisach model | ≈ 1 V after ±4 V, 1 µs (Fig. 1b) | V_W = 4 V, V_W/2 inhibit | V_S = 1 V | — | — | — | — | 0.195 fJ, 252.8 ps (1T); 0.073 fJ, 1.43 ns (2T) | 0.36 / 0.44 µm² (16T CMOS 1.12 µm²) | https://past.date-conference.com/proceedings-archive/2021/pdf/1478.pdf |
| Re-simulations of the Ni 2019 2FeFET cell (sim) — Qian value **checked** (their Table I: 16T CMOS 1.12 µm², 582.4 ps, 0.59 fJ) | 45 nm PTM, Spectre | — | — | — | — | — | — | — | 0.35 fJ / 340.8 ps [Qian 2021 Tab. I]; 0.40 fJ / 360 ps [Shou 2023 Tab. II] | 0.15 µm² at 45 nm | DATE 2021 link above; https://arxiv.org/abs/2310.04940 |
| Yin et al., FeCAM, IEEE TED 2020 (sim, MFM data measured) | 45 nm PTM; 10 nm HZO MFM | multi-level | 2-4 V in 50 mV steps; ±2 V inhibit | V_SL 0-1 V; ML threshold 0.5 V | — | — | — | — | 0.182 fJ digital, 0.069 fJ analog [Shou Tab. II] | 0.05 µm² | https://arxiv.org/abs/2004.01866 |
| Kazemi et al., DATE 2021 / Sci. Rep. 2022, multi-bit CAM on GF AND arrays (meas, 2-bit array) | GF 28 nm HKMG MFIS, W/L 450/450 nm | 8 levels (3 bit) single cell, V_t 0.1-1.15 V in 150 mV steps | erase −5 V/500 ns; program 1-4.5 V, 200 ns; write-verify 1.25-5.5 V, 100 ns, 40 mV steps | ML 0.1 V; data line −0.5 to 1.1 V | n.r. | most cells within 100 mV of target; sim σ up to 80 mV | n.r. | n.r. | n.r. | n.r. | https://arxiv.org/abs/2011.07095 ; https://par.nsf.gov/servlets/purl/10423723 |
| Mallick et al., Sci. Rep. 2023, latch Ising with FeFET couplers | GF 28 nm HKMG, doped HfO2 on SiO2 IL | 1.3 V at W/L 0.5/0.5 µm (Fig. 4b) | −4 V / +4 V, 1 µs; array sim ±3 V, V_W/2 | V_DS 50 mV; couplers at V_GS 1.5 V | ≈ 100× at V_GS = 1 V | n.r. | n.r. | n.r. | latches settle < 100 ns (sim) | — | https://par.nsf.gov/servlets/purl/10434161 |
| Mattar et al., TCAS-I 2026, 3×3 2FeFET CAM, time-domain macro (meas) | GF 28SLPe; FeFET W = L = 90 nm | multi-level via body bias | WL +4 V → LVT, −4 V → HVT; −2 V inhibit | V_WL 0.6 V, V_BL 0.8 V, V_DD 0.85 V | n.r. | calibrated to ≤ 100 ps delay steps | stable to ~1e3 cycles, drift by several 1e3 | 1e5 s at RT, negligible drift | 550 ps delay step | macro 17.6 × 30.7 µm² | https://arxiv.org/abs/2504.03925 |
| Tan et al., EDL 41, 240 (2020), Berkeley FeFET CAM (meas, cell + 2-bit word) | thin SOI; ~1 nm SiO2/1.3 nm HfO2/4.2 nm HZO; W/L 1/1 µm | n.r. | ±5 V (retention test −5.5 V/35 ns, +5.5 V/25 ns) | V_G(read) 0.3 V; search on drains 0/50 mV | ML 10.9-13.1 nA (match) vs 2.79-3.21 pA (miss) | n.r. | n.r. (optimised SiNx-IL device: > 1e10) | 85 °C: I_on/I_off −30% after 24 h | n.r. | — | https://www2.eecs.berkeley.edu/Pubs/TechRpts/2022/EECS-2022-17.pdf |
| Trentzsch et al., IEDM 2016 | GF 28 nm SLP HKMG, 2 extra masks, 64 kbit | n.r. (abstract) | n.r. | n.r. | n.r. | n.r. | 1e5 | high-temperature retention to 250 °C | — | — | https://fis.tu-dresden.de/portal/en/publications/a-28nm-hkmg-super-low-power-embedded-nvm-technology-based-on-ferroelectric-fets(07d5b1f3-b4f1-4c3c-ba75-5d7aa0497146).html |
| Dünkel et al., IEDM 2017 | GF 22 nm FDSOI | ≈ 1.5 V | n.r. | n.r. | n.r. | n.r. | up to 1e5 | n.r. | — | cells down to 0.025 µm² | https://fis.tu-dresden.de/portal/en/publications/a-fefet-based-superlowpower-ultrafast-embedded-nvm-technology-for-22nm-fdsoi-and-beyond(2fd89f5b-2391-4fc3-8000-4440811bf3bc).html |
| Beyer et al., IMW 2020 | GF 28 nm HKMG | 1.4 V | n.r. | n.r. | n.r. | "approaching 6σ" separation | n.r. | n.r. | — | — | https://fis.tu-dresden.de/portal/en/publications/fefet(c584785b-c492-4a75-a362-68cdf7709e8d).html |
| Qian et al., arXiv 2025, BEOL Ising, 32×256 (meas) | 180 nm CMOS + TiN/10 nm HZO/TiN MFM on M4 (MFMIS) | Fig. 2h (64 devices) | ±4 V, 1 µs | n.r. | n.r. | n.r. | n.r. | n.r. | converges within 900 ns | n.r. | https://arxiv.org/abs/2512.17165 |

Not found: any measured FeFET-TCAM-based Ising or SAT solver chip (the closest are Yin 2024's QUBO
VMV array and Mallick 2023's FeFET couplers). Kioxia/SK hynix/Samsung FeFET CAM data not found.

### 4.3 Calibration targets for our model (ordered by priority)

C1 (FE kinetics, capacitor): reproduce P1 Fig. 4(c) table (§2.1 T3) within ±3 µC/cm² for 1-3 V and
 30 ns-1 ms, and P3 Fig. 1/2 via the analytic NLS eq. (5) with Table I (implementation check).
C2 (quasi-static loop): P1 Fig. 3(c) loop (§2.1 T1): Q(±3 V) ≈ ±37 µC/cm², Q(0) ≈ +17.5/−21.8 µC/cm²,
 crossings −0.68/+0.99 V at ≈ 50 V/ms.
C3 (minor loops): P1 Fig. 5 waveforms (§2.1 T2): return-point memory (re-entering at C closes the loop).
C4 (FeFET MW vs write): P1 Fig. 6(d) table (§2.1 T4), including MW = 0.735 V at ±4.5 V/10 µs and the
 2 s read delay; then the 28 nm-class targets of §4.1: MW ≈ 1.0 V at ±4 V/10 µs, and the SI Fig. 1
 iso-MW points (e.g. MW 1.0 V needs 3.66 V at 10 µs, 4.0 V at 50-100 ns).
C5 (I_D-V_G): P1 Fig. 6(b) (§2.1 T5): V_th(1e-7 A/µm) ≈ −0.01 V (LVT) and 0.73 V (HVT); read ratio ≈ 40×
 at V_G = 0.5 V; for the 28 nm-class TCAM device: V_th ≈ 0.65 V (LVT) and 1.68 V (HVT).
C6 (disturb): no measurable switching at |V_G| ≤ 1-1.5 V for 1e5 s-equivalent stress (supports V_W/2 or
 V_W/3 inhibit at 4 V writes; read at ≈ 1 V).
C7 (variation): σ(V_th) ≈ 0.10 V (LVT) and 0.15 V (HVT) device-to-device (§4.1); multi-level write-verify
 errors ≲ 100 mV.
C8 (TCAM cell, sim sanity): mismatch discharge of a precharged ML in < 1 ns; ≈ 0.35-0.40 fJ/bit and
 ≈ 340-360 ps per search at 45 nm (Qian 2021, Shou 2023 re-simulations of the Ni cell).
C9 (reliability, not modelled in v0): endurance 1e5 cycles (GF 28/22 nm); retention 1e5 s stable at RT
 (Yin 2024, Mattar 2026), 10 years claimed for GF 28 nm (Trentzsch 2016, secondary).

---

## 5. MOSFET model choice

### 5.1 What ngspice 45 has built in

- Built-in MOS levels accepted by the ngspice parser: 1-6, 8-10, 14, 49, 54-58, 60, 68, 73 (source:
  `src/spicelib/parser/inpdomod.c`, mirror https://github.com/danchitnis/ngspice-sf-mirror/blob/master/src/spicelib/parser/inpdomod.c).
  BSIM4 is level 14 or 54. **BSIM-CMG (level 72) is not built in**; it needs an OSDI shared object.
- BSIM4 implementation is chosen by `version`: 4.0-4.5 → BSIM4v5 code, 4.6 → v6, 4.7 → v7, 4.8/default →
  current BSIM4 (same source). ngspice-45 updated BSIM4 to 4.8.3 (https://ngspice.sourceforge.io/news.html).
- Local check (31 Oct 2026, `ls`/`grep` only): the installed Debian package is `ngspice 45.2+ds-1`. Its
  `/usr/share/ngspice/scripts/spinit` contains `unset osdi_enabled` and, under `if $?osdi_enabled`, `osdi`
  lines for `/usr/lib/x86_64-linux-gnu/ngspice/{asmhemt, bjt504t, BSIMBULK107, BSIMCMG, HICUMl0-2.0,
  psp103_nqs, r2_cmc, vbic_4T_et_cf}.osdi`, but **none of those .osdi files are present** in that directory
  (only XSPICE `.cm` code models are). The binary contains the strings `pre_osdi` and `osdi_enabled`, so
  OSDI loading is compiled in. Debian's `debian/rules` reportedly has `--enable-osdi`
  (https://sources.debian.org/src/ngspice/45.2%2Bds-1/debian/rules; page not loaded by us, so uncertain).

### 5.2 Candidates

| Model set | URL | Licence / terms | Model, level | ngspice 45 | Plain pasteable card? | Notes |
|---|---|---|---|---|---|---|
| PTM bulk 45/32/22 nm HP and LP | https://mec.umn.edu/ptm (moved from ptm.asu.edu) | No terms of use on the page; only "© Regents of the University of Minnesota. All rights reserved." Redistribution rights unclear | BSIM4 (PTM `.pm` cards use level 54; header `version = 4.0`, uncertain for current files) | Built in (BSIM4v5 path) | Yes: one short nmos + one pmos `.model` each, no bins/corners | 45 nm HP: nominal V_dd 1.0 V, toxe 1.25 nm (n) / 1.3 nm (p) (via a tuned copy, https://github.com/iveney/cts/blob/master/tuned_45nm_HP.pm; original vth0 uncertain). Files are Google-Drive links |
| PTM-MG FinFET 7-20 nm | same | same | BSIM-CMG, level 72 | OSDI only | Plain text | Not usable without an OSDI BSIM-CMG |
| SkyWater SKY130 | https://github.com/google/skywater-pdk | Apache-2.0 | BSIM4 level 54, version 4.5, binunit 2; toxe 4.148 nm; bin-0 vth0 0.519 V (`sky130_fd_pr__nfet_01v8__tt.pm3.spice`) | Built in | No: 63 bins for nfet_01v8, ~1.1 MB per corner, corner/mismatch `.param` files; needs `.spiceinit` with `set ngbehavior=hsa`, `set ng_nomodcheck` | 1.8 V device, V_th 0.54-0.74 V by W/L |
| GF180MCU | https://github.com/google/gf180mcu-pdk (archived, read-only) | Apache-2.0 | BSIM4 (uncertain) | Built in (uncertain) | No (binned library, uncertain) | 3.3/6 V process |
| FreePDK45 (NCSU) | https://eda.ncsu.edu/freepdk45/ | Apache-2.0 for the kit (SVRF decks have a separate click-through EULA) | HSPICE NMOS_VTL/PMOS_VTL cards "based on 45nm PTM", nominal/FF/SS | Built in (assumed BSIM4, uncertain) | Mostly yes | V_dd ≈ 1.1 V (uncertain) |
| ASAP7 | https://github.com/The-OpenROAD-Project/asap7_pdk_r1p7 (`models/hspice`) | BSD-3-Clause | BSIM-CMG level 72, version 107; eot 0.75 nm | OSDI only | Yes, ~41 kB per corner | V_dd 0.7 V (uncertain) |

BSIM-CMG Verilog-A with a prebuilt .osdi for ngspice: https://github.com/dwarning/VA-Models (bsim-cmg
111.2.1, Educational Community License 2.0). Not needed for v0.

### 5.3 What the FeFET papers paired with

- P1 (Ni 2018): "BSIM 4" only; card and node not stated (p. 131).
- Ni et al., Nature Electronics 2019 TCAM, Supplementary Information: Cadence Spectre with the Ni 2018
  multi-domain Preisach model; "parasitic capacitances on the metal lines (45nm node) are included"; MOSFET
  card not named (https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41928-019-0321-3/MediaObjects/41928_2019_321_MOESM1_ESM.pdf; uncertain whether PTM).
- Yin group: DATE 2017 TCAM used "45 nm predictive technology models"
  (https://past.date-conference.com/proceedings-archive/2017/pdf/0615.pdf); FeCAM (TED 2020) used Ni's
  calibrated model with capacitances "extracted from PTM 45-nm technology model" (https://arxiv.org/abs/2004.01866);
  Qian, Yin et al., DATE 2021: "The 45nm PTM model is adopted for all MOSFET devices"
  (https://past.date-conference.com/proceedings-archive/2021/pdf/1478.pdf).

### 5.4 Recommendation for the first FeFET model

**PTM 45 nm bulk (HP first; LP as a variant), BSIM4, built-in ngspice level 54.** Reasons: it is the node
the Yin/Qian FeFET-TCAM simulation papers used (Ni 2019: 45 nm wiring, card unnamed), so our circuit
numbers are comparable; two short plain-text
cards; no bins/corners; runs on ngspice's built-in BSIM4 with no OSDI. Weak point: no explicit licence. Per
the project README, each card is approved before it is added; we suggest downloading the
cards and keeps the citation (Zhao & Cao, IEEE TED 2006, PTM) next to them. If a clean licence is required,
the FreePDK45 PTM-derived cards (Apache-2.0) are the fallback. For the FeFET's own channel we will need a
separate card anyway, because P1's FeFET has a 2 nm SiO2 interlayer under 10 nm HZO (thick-gate device);
reuse the PTM 45 nm nmos card with TOXE/TOXP/TOXM raised to the interlayer EOT (≈ 1-2 nm) and V_th0
adjusted, and treat that as a fitted stand-in, not a real process.

---

## 6. Simulator and Verilog-A toolchain facts

**OSDI / OpenVAF.**
- "Since version 39 ngspice contains the OSDI interface" (https://ngspice.sourceforge.io/osdi.html). ADMS
  is "deprecated and no longer part of the ngspice project" (same page). NEWS: ngspice-39 declared ADMS
  deprecated; ngspice-43 made OSDI a standard configure option and added `NGSPICE_OSDI_DIR`; ngspice-45
  `showmod` lists Verilog-A models (https://github.com/danchitnis/ngspice-sf-mirror/blob/master/NEWS).
- So **ngspice 45 loads Verilog-A only as compiled OSDI objects**; it has no built-in Verilog-A compiler.
  Load with `pre_osdi file.osdi` in the netlist (or `osdi` in `.spiceinit`/`spinit`); instances start with
  `N`; `.model` type = Verilog-A module name.
- Original OpenVAF (https://github.com/pascalkuthe/OpenVAF, GPL-3.0): unmaintained since end of 2023 (per
  the fork's README).
- **OpenVAF-reloaded** (https://github.com/arpadbuermen/OpenVAF, GPL-3.0), started by Árpád Bűrmen in
  early 2024; binaries for 64-bit Linux and Windows from https://fides.fe.uni-lj.si/openvaf/download;
  `openvaf-r` (master) emits OSDI 0.4; README: "Ngspice >=44: 0.3 & 0.4, uses only 0.3 features";
  changes include "$bound_step() fixed", loops no longer crash, `limexp()` made a stateless builtin.
  (README fetched 31 Oct 2026.) No numbered release.
- **Limits that matter for a hysteresis model** (OpenVAF docs, https://openvaf.semimod.de/docs/details/verilog-a-standard/):
  "Syntax for events other than `initial_step` and `final_step` can't be parsed" → **no `@(cross())`,
  no `@(timer())`**; `initial_step`/`final_step` "are executed on every iteration and time step".
  The compiler source marks `transition`, `slew`, `laplace_*`, `zi_*`, `last_crossing`, file I/O and
  `$random`/`$dist_*` as unsupported (https://github.com/arpadbuermen/OpenVAF/blob/master/openvaf/hir_def/src/builtin.rs).
  `ddt`, `idt`, `absdelay`, `$abstime`, `$bound_step`, `$limit`, `analysis()` are not on that list
  (whether `idt`/`absdelay` behave correctly in ngspice: uncertain).
- **Hidden state**: OpenVAF documentation does not say. The OSDI instance data only reserves state slots for
  `$limit` (https://github.com/arpadbuermen/OpenVAF/blob/master/internals.md), so ordinary variables are
  most likely **not** kept between time steps (inference, uncertain). Independently of OpenVAF, hidden
  state in Verilog-A is bad practice: variables updated inside the analog block are re-evaluated on every
  Newton iteration and on rejected time steps, and simulators cannot see them (Kundert, "Hidden state in
  Verilog-A", https://designers-guide.org/analysis/hidden-state.pdf; Cadence forum thread on avoiding hidden
  state, https://community.cadence.com/cadence_technology_forums/f/rf-design/26712/how-to-avoid-hidden-state-in-veriloga-model-for-spectrerf).
  Web-pass reports (not re-checked): OpenVAF-Reloaded issue #44 "Hidden state not fully implemented" was
  closed in Oct 2026 with no fix shown; PR #41 (open) proposes event-body semantics. The dwarning/VA-Models
  README lists `$abstime()` and `@cross()` as unsupported.
  **Consequence: a turning-point stack held in Verilog-A variables (P1's history algorithm) is not portable
  to OpenVAF/ngspice. All memory must live in internal nodes.** Heracles (§3.A) shows that this pattern
  compiles with `openvaf-r` and runs in ngspice in series with built-in BSIM4.
- Not installed locally: no `openvaf`/`openvaf-r` binary on PATH (checked with `which`). Installing one needs
  approval (this project README: "an ngspice-native version for use until a Verilog-A compiler is
  approved").

**Alternatives without OpenVAF.**
- ngspice B-sources support `ddt()` since ngspice-39 (NEWS). The standard memory trick: a B-source current
  into a 1 F capacitor so that the node voltage *is* the state variable, as in the Pershin threshold
  memristor model in ngspice (https://knowm.org/the-pershin-voltage-threshold-memristor-model-in-ngspice/).
  This is exactly what an N-domain polarization ODE needs: one capacitor node per domain.
- XSPICE code models already in the installed package (`analog.cm`, `xtradev.cm`, etc.): `hyst` (single
  hysteresis block) and `core` (magnetic core, PWL or hysteresis mode; a single hysteron, not Preisach)
  (https://github.com/danchitnis/ngspice-sf-mirror/blob/master/src/xspice/icm/xtradev/core/ifspec.ifs).
  Not useful for multi-domain FE.
- Custom XSPICE code models in C via `cmpp` (https://ngspice.sourceforge.io/xspicehowto.html): possible but
  needs a C build step and approval.
- Xyce (alternative simulator): Verilog-A via ADMS `buildxyceplugin`; no events except `@(initial_step)`;
  `idt`, `absdelay`, `transition`, `slew`, `last_crossing` unsupported; `$bound_step`, `$abstime` supported
  (https://xyce.sandia.gov/?p=121). Stricter than OpenVAF.

**Practical rule for our model:** write the FeFET as ODEs on internal nodes, using only `ddt` (or B-source
`ddt`), smooth functions, `limexp`-style guards and `$bound_step` at most; no events, no variables that must
survive between time steps. The same equations then run as (a) Verilog-A compiled by OpenVAF-reloaded and
loaded with `pre_osdi`, and (b) an ngspice-native subcircuit of B-sources and 1 F state capacitors.

---

## 7. Open questions and risks

R1. **No parameter values from the P1 authors.** P1 prints the equations but not Q_o, a, V_C, ε_FE,
τ_∞, V_0, m or the BSIM4 card. Ni 2019 SI gives only m = 2. The only published values fitted to P1's data
are third-party (Chatterjee 2023: P_s 19, P_r 18.5 µC/cm², V_c 1.2 V, ε 40, constant τ_v 1.5 µs, §3.B),
and they use a constant delay, not P1's τ(V). Our values in §2.1 are fits to vector-extracted data. All of
these are starting points to be re-fitted against the T1-T5 tables.

R2. **History in variables is not portable.** P1/P2's turning-point stack lives in model variables. OpenVAF
cannot parse `@(cross())` and most likely does not keep variables between time steps (§6); B-sources cannot
hold a stack at all. The v0 recipe therefore stores history only in N domain-state nodes. Cost: N extra
nodes per FeFET (N = 10-20), so a 64-word × 32-bit TCAM (4096 FeFETs) gets 40k-80k extra nodes.

R3. **Depolarization-driven drift / retention.** In any kinetic model (P1's delay with τ(V_IN) finite for
V_IN ≠ 0, or the NLS domains), the depolarizing V_FE at V_G = 0 slowly back-switches domains. Example with
P3 Table I: a median domain at 0.84 MV/cm has τ ≈ 7.5e2 s (§2.3 (v)); low-E_a tail domains go faster. P1
reads 2 s after each write (Fig. 6(a)), so the measured MW already includes some back-switching. Real
28 nm FeFETs claim 10-year retention (§4), so the model may over-predict retention loss. Test: hold at
V_G = 0 for 1e0 … 1e8 s (in log-spaced transient) and check MW drift; if too large, raise α or the low tail
of the E_a distribution, or add a compensating trapped-charge term.

R4. **Different films, different kinetics.** P3 (8.3 nm Hf0.5Zr0.5O2, τ_∞ = 387 ns, α = 4.11) and P1
(10 nm Hf0.4Zr0.6O2, t50 ≈ 3.5 µs even at 3 V) disagree by about 10× at high field and in field
dependence. P1's capacitor data may be set-up limited (no set-up time constant given) while its FeFET
switches in < 1 µs at 4.5 V. Do not mix the two parameter sets; calibrate kinetics (set B) to P1 Fig. 4(c)
and check against P1 Fig. 6(d).

R5. **Charge trapping not modelled.** P1's MW drops at long/high pulses (Fig. 2(b), 6(d)); real FeFET
endurance (10^4-10^5 cycles typical for MFIS HfO2) is limited by trapping and interlayer breakdown. The
v0 model will be optimistic on MW at long pulses and silent on endurance.

R6. **Floating internal node.** The FE-MOS series node M has no DC path. Need: `.ic` on M and on the
domain nodes, or a very large resistor (≥ 1e15 Ω·µm²-scaled) with time constant ≫ the simulated time; and
`uic`/initial conditions for every transient. A resistor that is too small acts as gate leakage and erases
the state.

R7. **Stiffness and timestep.** τ spans 1e-7 … 1e+10 s across the field range; exp((E_a/E)^α) overflows
for small E. Guard the exponent (cap at ~200), set the rate to exactly 0 below a small |E| (the function is
flat there, so this is smooth), and consider `$bound_step` during writes. With β > 1 the Weibull ODE has a
non-Lipschitz start (rate = 0 at zero switched fraction); seed it (u ≥ 1e-6) or use β = 1.

R8. **Model card for the FeFET channel.** PTM 45 nm is a thin-oxide logic card; P1's FeFET has a 2 nm
SiO2 interlayer under 10 nm HZO, and GF 28 nm FeFETs have their own stack. A modified PTM card is a
stand-in, so absolute V_th, SS and I_on are not predictive; only the MW and relative behaviour are
calibrated.

R9. **Variation.** Domain count per device sets device-to-device spread (P3 Fig. 7: 20 grains halve the
window at 1.5 V). For TCAM sensing margins we need σ(V_th) per state from measured arrays (§4) and a way to
map it to N and the E_a distribution. Deterministic bins (equal-probability quantiles) give zero variation;
Monte Carlo needs per-instance sampled E_a values (instance parameters), which ngspice/OSDI can pass as
parameters but random sampling must happen outside the model (OpenVAF does not support `$random`).

R10. **β and the history (h) rule.** P3 shows the h-reset rule depends on hold time (10 s vs 1 ms) and fits
γ = 0.55/0.3 for 1/10 µs gaps. The v0 one-state-per-domain form cannot represent that; it behaves like
"h tied to the switched fraction". Acceptable for binary TCAM writes with long gaps; revisit for
pulse-train (multi-level) writes.

Open questions:
- Q1. Approve installing OpenVAF-reloaded (GPL-3.0, prebuilt Linux binary) so the Verilog-A version can be
  compiled, or stay with the B-source version for now?
- Q2. Approve PTM 45 nm cards (no explicit licence) or prefer FreePDK45 (Apache-2.0, PTM-derived)?
- Q3. Which device do we target: P1's lab FeFET (10 nm HZO, 2 nm SiO2, large device) for calibration, then
  the GF 28 nm HKMG FeFET numbers of Ni 2019 (§4) for the TCAM?
