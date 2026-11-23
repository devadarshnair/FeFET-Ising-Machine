# FeFET model v0: calibration report

31 Oct 2026 (IST). Model: N = 16-domain kinetic Preisach ferroelectric with NLS switching, in
series with a BSIM4 channel through an internal node (MFMIS lumping); see `DECISIONS.md` and
`MODEL_EQUIVALENCE.md`. All numbers below come from ngspice runs of the generated library
`device/ngspice/fefet_preisach.lib` (final run of `scripts/run_spice_tests.sh`), unless marked
"offline" (Python reference). Tolerances were fixed in `device/tb/TESTS.md` before the comparisons;
the two tests added later are marked there.

Targets and data tables: `docs/lit/device_models.md` (T1-T5 from Ni 2018 = P1; §4.1 from the
Ni 2019 SI; Table I of Alessandri 2019 = P3).

## Parameter sets

| Parameter | Set A (P3 film, check only) | Set B (Ni 2018 film) | Set C (TCAM-class FeFET) |
|---|---|---|---|
| t_FE | 8.3 nm | 10 nm | 8 nm |
| P_S (µC/cm²) | 22.9 [P3] | **23.97** [fit T3] | **1.72** [fit; effective switchable polarization] |
| ε_r | 30 (not used) | **42.9** [T1 slope, +2 → +3 V descending] | 30 [fixed] |
| τ_∞ | 387 ns [P3] | **3.65 µs** [fit T3] | **5.65 ns** [fit] |
| α | 4.11 [P3] | **2.94** [fit T3] | **3.76** [fit] |
| β | 2.07 [P3] | **1.64** [fit T3] | 1 [fixed] |
| E_a distribution | GB2(12.1, 1.79 MV/cm, 0.691, 0.633) [P3] | log-normal, median **1.393 MV/cm**, σ_ln **0.341** [fit T3] | log-normal, median **2.44 MV/cm**, σ_ln **0.050** [fit; at its lower bound] |
| V_imp | +0.08 V [P3] | −0.155 V [T1 crossings] | 0 [fixed] |
| N domains | 16 | 16 | 16 |
| Channel card | – | nfefet_b: toxe 2 nm, vth0 **0.139 V** [fit], u0 0.03 | nfefet_c: toxe 1 nm, vth0 **0.813 V** [fit], u0 0.022, cit 0.012 |
| Device | – | W = L = 1 µm | W/L = 200/100 nm |

The 16 activation fields of each set are listed in the header of the generated library.

How the fits were done:
- **Set B kinetics** (`device/py/fit_setB.py`): least squares over all 72 points of T3 (MFM capacitor,
  one pulse from −P_S, 0.5-3 V, 100 ns-1 ms), offline with the same equations (pulse edges ignored;
  ngspice with 5 ns edges differs by ≤ 0.12 µC/cm²). β = 1 was tried first: RMS 2.0 µC/cm², 8 of 60
  points at 1-3 V outside ±3; with β free: RMS 1.05, 1 of 60 outside.
- **Set B channel**: vth0 only, so that the mean of the two thresholds after ±4.5 V / 10 µs equals the
  mean of T5. Everything else in 1d is a prediction.
- **Set C** (`device/py/fit_fefet.py`): offline reduced FeFET model (node m eliminated by charge
  conservation, MOS gate charge and drain current tabulated from ngspice), with the same protocol and
  the same read ramps as the SPICE decks. Free: τ_∞, α, median E_a, σ_ln, P_S; then vth0 for the mean
  threshold. Residuals: the 10 iso-MW points of Ni 2019 SI Fig. 1, MW(±4 V, 10 µs) = 1.03 V (weight 5),
  and C6 (high-V_th shift after 1e5 s at +1.1 V, weight 2 per volt).
  History (the raw fit logs were in `sim/out/scratch` and were deleted in the disk trim; the numbers
  below were copied from them before that, and the ledger has the related slips): (1) a first fit with P_S
  fixed at 22.9 µC/cm² could not bring the 0.2 V iso-line below about 0.7 V; (2) with P_S free it gave
  α = 1.63, τ_∞ = 3.4 ps, which in ngspice showed strong read disturb and a wrong offline model (missing
  fringing charge, quasi-static read) — finding 5 below; (3) with read ramps and C6 (weight of the main
  point 2) it gave MW 1.136 V, outside the 1.03 ± 0.05 V target; (4) the final fit raises the main
  point's weight to 5 and lowers the P_S bound to 0.5 µC/cm². The weights are a calibration choice
  (the ±4 V / 10 µs states are what the TCAM uses); no tolerance was changed.

## Results against targets

| Test | Wanted (tolerance) | Achieved | |
|---|---|---|---|
| 1a single domain vs analytic NLS (set A) | ≤ 1 % of 2P_S | 0.16 % | PASS |
| 1a 16 domains vs the same 16-term sum | ≤ 1 % | 0.04 % | PASS |
| 1a 16 domains vs P3 eq. (5), continuous GB2 | ≤ 1 % | 2.3 % (N = 32 would give 0.93 %, offline) | **FAIL** |
| 1a charge from the source vs area·ΔP | ≤ 1 % | 0.12 % | PASS |
| 1b loop at 50 V/ms vs T1, RMS | ≤ 3 µC/cm² | 9.8 µC/cm² | **FAIL** |
| 1b Q = 0 crossings | −0.68 / +0.99 V ± 0.15 | −1.26 / +1.54 V (at 0.5 V/ms: −0.69 / +0.98 V) | **FAIL** |
| 1b Q(0) | +17.3 / −21.6 ± 3 µC/cm² | +24.0 / −24.0 | **FAIL** |
| 1b Q(±3 V) | ±37.0 ± 3 | +34.8 / −35.3 | PASS |
| 1b minor loops: return-point memory, return to major loop | ≤ 1.0 µC/cm² | 0.21 / 0.05 | PASS |
| 1c T3 pulse table, 60 points at 1-3 V | every point ± 3 µC/cm² | 59 of 60; worst 3.5 at 1.5 V / 30 µs (RMS of all 72: 1.04) | **FAIL** (one point) |
| 1d MW at ±4.5 V / 10 µs (set B FeFET) | 0.735 ± 0.05 V | 0.592 V | **FAIL** |
| 1d MW table T4, 72 points | RMS ≤ 0.10 V | 0.162 V (P1's own model: 0.041 V) | **FAIL** |
| 1d V_th after ±4.5 V / 10 µs | −0.01 / +0.73 ± 0.10 V | +0.064 / +0.656 V | PASS |
| 1f V_th low (set C, +4 V / 10 µs) | 0.65 ± 0.05 V | 0.643 V | PASS |
| 1f V_th high (−4 V / 10 µs) | 1.68 ± 0.05 V | 1.678 V | PASS |
| 1f MW | 1.03 ± 0.05 V | 1.035 V | PASS |
| 1f iso-MW write amplitudes (6 points) | each ± 0.15 V | MW 1.0 V: 3.92 / 3.67 / 3.51 V at 1 µs / 10 µs / 100 µs (exp 3.77 / 3.66 / 3.30); MW 0.2 V: 2.80 / 2.61 / 2.38 V at 1 µs / 10 µs / 1 ms (exp 2.82 / 2.60 / 2.50). 4 of 6 inside; worst 0.21 V | **FAIL** |
| 1f ngspice vs offline model | ≤ 20 mV | 3.6 mV | PASS |
| 1e set B retention, MW(1e5 s) / MW(2 s), gate at 0 V | ≥ 90 % | 84.3 % (0.592 → 0.499 V; 0.485 V at 1e6 s; about −20 mV per decade) | **FAIL** |
| 1e set C retention, same | ≥ 90 % | 100 % (1.035 V from 2 s to 1e6 s in ngspice; offline estimate 1.035 V at 10 years) | PASS |
| 1e set C, C6: high state at +1.1 V for 1e5 s | ≤ 50 mV | +0.6 mV | PASS |
| 1e restart from a saved state (information) | – | 0.0 mV for both sets and states | – |

T1-T5 points with both measured and P1-model values, and our per-point results, are in the checker
CSVs (`sim/out/t1*/t1*_result.csv`); the figures below plot them.

## Findings worth knowing

1. **The implementation is right; 16 bins are too coarse for P3's distribution.** One domain matches
   the analytic NLS law to 0.16 % and 16 domains match their own 16-term sum to 0.04 %, but 16
   equal-probability bins of P3's heavy-tailed GB2 distribution miss the continuous eq. (5) by 2.3 %
   of 2P_S (mostly the low-field tail at 0.6 V and the middle at 1.4 V). Offline, N = 32 gives 0.93 %
   and N = 64 gives 0.52 %. N stays 16 by decision; it is a generator parameter.
2. **Ni 2018's loop (T1) and pulse table (T3) do not agree under NLS kinetics.** With kinetics fitted
   to the pulses, the loop at the stated 50 V/ms is far too wide (coercive points −1.26 / +1.54 V).
   The same parameters give T1's crossings (−0.69 / +0.98 V) at 0.5 V/ms, 100 times slower. The time
   axis was checked in the P1 PDF (Fig. 5 is in ms), so the sweep rate is as read. P1's own model can
   match both because its static loop and its delay are separate; in NLS the coercive voltage *is*
   the kinetics. Q(0) is also too high (±24 vs +17 / −22 µC/cm²): the NLS model has no back-switching
   at 0 V, while the measured loop loses about 6 µC/cm² on the way to 0 V.
3. **Set B kinetics are too slow for the FeFET at short pulses** (risk R4). τ_∞ = 3.65 µs (forced by
   the capacitor data, which may include set-up delay) means nothing switches in 50-100 ns, while
   P1's FeFET opens 0.2-0.36 V at ±4.5 V / 50-100 ns. At long pulses the model window saturates at
   0.59 V (measured 0.62-0.74 V) and rises too early at low voltage (2-2.5 V). Read current ratio at
   0.5 V is far larger than measured (5.8e3 vs 41) because the stand-in channel has a steep 69 mV/dec
   slope (measured 185 mV/dec).
4. **Set C wants a small, narrow switchable polarization.** The fit to the Ni 2019 points gives an
   effective P_S of 1.7 µC/cm² and an almost single activation field (σ_ln at its 0.05 bound). The
   1 V window is then nearly the full switching of this small charge, which is what makes the window
   saturate between 3.66 and 4 V as in the data. Read P_S as "what the MFIS stack can switch and keep",
   not as the film's remanent polarization.
5. **Two checks caught real errors in the offline model, not in the SPICE model.** (a) BSIM4's
   reported `qg`/`cgg` leave out the fringing and overlap gate charge (about 0.09 fF here); the
   charge balance on node m was off by 1.1e-16 C until the table was built from the integrated gate
   current. (b) The first set-C fit (α = 1.6) switched its weakest domains in about 1 µs at the
   0.86 V that sits across the ferroelectric during a read ramp, so the measured high V_th was 0.12 V
   below the quasi-static value. The offline model now simulates the same read ramp, and target C6
   was added to the fit; the final set C has α = 3.76 and no measurable read disturb.
6. **Read ramps that go past V_th disturb set B.** A read ramp to 1.8 V lowers a set-B high state by
   64 mV after the crossing. Saved states are therefore taken 1 µs before each read.
7. **Negative gate stress erases low-V_th set-C cells.** −2 V (V_W/2 inhibit) for 2.55 ms raises a
   low V_th by 0.72 V; −1.33 V (V_W/3) still by 78 mV. Positive stress and stress on the high state
   are harmless (≤ 10 mV). Searches only put 0 or +1.1 V on gates, so search disturb is not the issue;
   the write inhibit is. Whether real devices are this asymmetric is not known from our data.
8. **Restarting from a saved state is exact** (1e: 0.0 mV between a restarted read and the in-deck read).
9. **Retention (risk R3) depends entirely on the activation-field spread.** Set B (σ_ln 0.34) loses
   about 20 mV of window per decade of time at 0 V (84 % left at 1e5 s): its low-field domains
   back-switch under the depolarizing field. Set C (σ_ln 0.05) loses nothing in 10 years because no
   domain is weak enough. Neither number is validated: v0 has no retention data to fit, and the
   set-C result is only as good as the narrow distribution the fit chose.
10. **Long holds are stiff in ngspice.** Holds at 0 V took steps of about 5e-4·t and did not reach
   3.2e8 s in 15 minutes; they now stop at 1.1e6 s (the 10-year value is offline).

## What is not modelled

- **Charge trapping.** P1's measured MW falls at long, high pulses (Fig. 6(d), "charge trapping"); the
  model keeps rising. Endurance (wake-up, fatigue, breakdown) is not modelled at all.
- **Variation.** The deterministic 16 bins give zero device-to-device spread. TCAM Monte Carlo applies
  σ(V_th) from Ni 2019 directly as a gate-referred shift; domain-count variation (P3 §IV) is not used.
- **History details.** One state per domain ties the NLS history to the switched fraction (risk R10):
  no relaxation between pulses, no dependence on hold time.
- **Leakage, temperature, depolarization beyond the series charge balance**, quantum and
  poly effects of the internal MOS: none.
- **MOSFETs are hand-written stand-ins**, so absolute V_th, subthreshold slope and currents of the
  FeFET channel are not predictive; only the window and the relative behaviour are calibrated.

## Figures

PNG files in `docs/device/fig/`, made by `scripts/make_device_figs.py` from the checker CSVs:
`t1a_setA_nls.png`, `t1b_setB_loops.png`, `t1c_setB_pulses.png`, `t1d_setB_mw.png`,
`t1f_setC_mw.png`, `t1e_retention.png`, `t3_word8.png`.
