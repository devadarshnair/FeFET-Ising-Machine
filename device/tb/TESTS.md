# v0 device and circuit tests: what each test checks and its tolerance

Written 31 Oct 2026 (IST) **before** any checker compared a simulation with a target. The tolerances
below are fixed. If a test fails, the failure is reported; the tolerance is not changed to make it pass.
Targets come from `docs/lit/device_models.md` (tables T1-T5, §4.1, §4.3) unless stated.

Every checker prints `RESULT <id> PASS|FAIL <achieved> | target: <wanted>` and writes a CSV to `sim/out/`.
`scripts/run_spice_tests.sh` runs all of them.

Common conventions:
- Threshold voltage V_th = gate voltage at a constant drain current, read with a fast gate ramp
  (transient; a DC sweep would lose the stored state). Set B: 1e-7 A per µm of width at V_DS = 50 mV
  (the P1 criterion). Set C: 1e-7 A × W/L at V_DS = 50 mV (Ni 2019 does not state its criterion).
- Memory window MW = V_th(after the negative write) − V_th(after the positive write).
- FeFET protocol for MW (P1 Fig. 6(a) style), from the neutral start state (all domains x = 0, all nodes
  0 V): +V pulse, wait, −V pulse, wait, read (high V_th), +V pulse, wait, read (low V_th). The wait is
  **2 s** for both sets (P1 states 2 s; Ni 2019 states none, so 2 s is our assumption). Pulse edges 5 ns.
- Units: polarization in µC/cm². "1 % of 2P_S" means 0.01 × 2P_S.

## 1. Model checks

| ID | What | Tolerance (PASS if) |
|---|---|---|
| t1a.single | Set A, one domain at the distribution median, constant V_A = 0.6/1.0/1.4/1.8 V from −P_S, t = 200 ns-1 ms, ngspice vs the analytic NLS law 1 − exp(−(t/τ)^β) (P3 eq. 2, no seed) | max \|ΔP\| ≤ 1 % of 2P_S |
| t1a.ensemble_discrete | Same, 16 domains, ngspice vs the analytic sum over the same 16 domains | max \|ΔP\| ≤ 1 % of 2P_S |
| t1a.ensemble_eq5 | Same, 16 domains, ngspice vs P3 eq. (5) with the continuous GB2 distribution (tests the N = 16 discretisation) | max \|ΔP\| ≤ 1 % of 2P_S |
| t1a.charge | Charge delivered by the source vs area × ΔP (checks that the polarization current matches the domain states) | relative error ≤ 1 % (cases with \|ΔP\| > 10 % of 2P_S) |
| t1b.loop_rms | Set B MFM loop, triangle ±3 V at 50 V/ms, Q = P + ε0·εr·V/t_FE vs T1 (experimental, both branches) | RMS error ≤ 3 µC/cm² |
| t1b.crossings | Q = 0 crossings of the same loop | each within ±0.15 V of −0.68 V (descending) and +0.99 V (ascending) |
| t1b.q0 | Q at V = 0 on each branch | within ±3 µC/cm² of +17.3 (descending) and −21.6 (ascending) |
| t1b.qmax | Q at ±3 V | within ±3 µC/cm² of ±37.0 |
| t1b.rpm | Minor loops, P1 Fig. 5 waveforms (c), (d), (e) at 50 V/ms: return-point memory, \|P(2nd visit of +1.2 V) − P(1st visit)\| in (c); and each waveform's end at +3 V back on the major loop | each ≤ 1.0 µC/cm² |
| t1c.pulse_1to3V | Set B MFM, one pulse from −P_S, remanent P vs T3 (experimental), all 60 points at 1-3 V, 100 ns-1 ms | every point within ±3 µC/cm² (C1) |
| t1d.mw_4p5V | Set B FeFET, MW at ±4.5 V / 10 µs | 0.735 ± 0.05 V |
| t1d.mw_table | Set B FeFET, MW over the 72 points of T4 (±2-4.5 V, 50 ns-10 ms) | RMS error ≤ 0.10 V |
| t1d.vth | Set B FeFET after ±4.5 V / 10 µs (T5, 1e-7 A/µm) | V_th(low) −0.01 ± 0.10 V and V_th(high) 0.73 ± 0.10 V |
| t1e.setC_1e5s | Set C FeFET, gate at 0 V after the writes; MW at 1e5 s vs MW at 2 s | MW(1e5 s) ≥ 0.90 × MW(2 s) (C9: stable to 1e5 s at room temperature) |
| t1e.setB_1e5s | Same for set B | MW(1e5 s) ≥ 0.90 × MW(2 s) |
| (info) | MW and both V_th at 1e2 … 1e6 s for both sets in ngspice, and the 10-year (3.15e8 s) MW of set C from the offline reduced model. **Changed 31 Oct 2026, 05:50 IST:** the ngspice hold was first planned to 3.2e8 s, but those runs did not finish in 15 min (steps of about 5e-4·t), so ngspice now stops at 1.1e6 s; the 1e5 s pass/fail point is unchanged | reported, no pass/fail |
| t1f.vth_low | Set C FeFET (W/L = 200/100 nm) after +4 V / 10 µs | 0.65 ± 0.05 V |
| t1f.vth_high | after −4 V / 10 µs | 1.68 ± 0.05 V |
| t1f.mw | MW at ±4 V / 10 µs | 1.03 ± 0.05 V |
| t1f.iso_mw | Write amplitude that gives MW = 1.0 V at 1 µs / 10 µs / 100 µs (Ni 2019 SI Fig. 1: 3.77 / 3.66 / 3.30 V) and MW = 0.2 V at 1 µs / 10 µs / 1 ms (2.82 / 2.60 / 2.50 V) | each within ±0.15 V |
| t1f.ref_agree | Set C V_th from ngspice vs the Python reduced model (device/py/fefet_ref.py) | each within 20 mV (implementation cross-check) |
| t1e.setC_c6 | **Added 31 Oct 2026, 04:45 IST**, after the first set-C fit showed strong read disturb (see docs/device/CALIBRATION_v0.md). Target C6 of device_models.md §4.3 at the search level: set-C high-V_th state with +1.1 V on the gate for 1e5 s, vs the same state held at 0 V | \|V_th shift\| ≤ 50 mV |

Note on t1f.ref_agree: from 04:45 IST the offline model reads V_th with the same gate ramp as the
SPICE decks (switching during the read included). The first version used a quasi-static read and
also missed BSIM4's fringing/overlap gate charge; both are described in CALIBRATION_v0.md. The
20 mV tolerance is unchanged.

## 3. TCAM circuits (set-C FeFET, stand-in 45 nm MOSFETs, VDD = 1.0 V)

| ID | What | Tolerance (PASS if) |
|---|---|---|
| t3a.write | 2-FeFET cells written with the program/erase scheme: every FeFET of the selected word ends in the intended state | each V_th within ±0.10 V of the single-device value from t1f |
| t3a.inhibit | Unselected word in the same columns during that write | every V_th shift ≤ 50 mV |
| t3a.disturb255 | One FeFET, LVT and HVT state, at the inhibit voltage ±V_W/2 = ±2 V for 255 × 10 µs (a 256-row array written once) | every V_th shift ≤ 50 mV |
| t3b.function | 8-cell word, keys with 0…8 mismatches, binary and {0, X} queries, stored X cells: SA reports "mismatch" iff the count ≥ 1 | all cases correct |
| t3b.monotonic | discharge time strictly decreases with the mismatch count 1 → 8 | true |
| t3b.t1 | discharge time at 1 mismatch (C8) | < 1 ns |
| t3b.energy | search energy per cell at 1 mismatch (C8: 0.35-0.40 fJ/bit at 45 nm) | within a factor 2 of 0.375 fJ (0.19-0.75 fJ) |
| t3b.frozen_equiv | **Added 31 Oct 2026, 04:52 IST** (to make the Monte Carlo affordable): the 14 cases of t3b with frozen-domain FeFETs (`fefet_c16_frozen`) vs the full model | discharge time and energy each within 1 % |
| t3c.function | 64-cell word: match/mismatch correct for counts 0, 1, 2, 8, 64 | all correct |
| t3d.levels | Monte Carlo, 200 samples per count, σ(V_th) = 0.10 V (low-V_th FeFETs) and 0.15 V (high-V_th FeFETs) (Ni 2019 SI Fig. 5); count read from the discharge time with fixed thresholds | target: all 9 levels (0…8) read with error ≤ 1 % each (Ni 2019 measured 8 levels in a 1×8 word). The number of levels that meet this is reported either way |

Error probability in t3d is reported two ways: the empirical fraction of misread samples (resolution
1/200), and a Gaussian estimate from the fitted mean and σ of ln(discharge time).
