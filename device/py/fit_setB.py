"""Fit parameter set B (Ni 2018 film) and write device/params/setB.json.

Step 1 (kinetics): least-squares fit of P_S, tau_inf, alpha, beta, and the median and sigma_ln
of a log-normal E_a distribution to the pulse-switching table T3 (MFM, Fig. 4(c), all 72
points), with the imprint fixed from the loop: V_imp = -(crossing_asc + crossing_desc)/2.
beta = 1 was tried first (RMS 2.0 uC/cm^2, 8 of 60 points at 1-3 V outside +-3); the data rise
more steeply in log(t) than one exponential, so beta is fitted (recipe form R3b).
Step 2 (dielectric): eps_r from the descending-branch slope of T1 between +2 and +3 V, where the
NLS model has no switching (all domains are already up).
The FeFET channel (vth0) is fitted separately in fit_fefet.py.

Run: scripts/run_guarded.sh <python> device/py/fit_setB.py [--write]
"""
import argparse

import numpy as np
from scipy.optimize import least_squares

import data_ni2018 as d
import fefet_ref as fr


def p_after_pulse(p, v, t):
    """P (uC/cm^2) after one pulse of v volts and width t from -P_S (edges ignored)."""
    return 100 * p["P_S_C_per_m2"] * fr.p_ensemble_const(v, t, p)


def unpack(theta, base):
    p = dict(base)
    p["dist"] = dict(base["dist"])
    p["P_S_C_per_m2"] = theta[0] / 100
    p["tau_inf_s"] = 10 ** theta[1]
    p["alpha"] = theta[2]
    p["dist"]["median_MV_per_cm"] = theta[3]
    p["dist"]["sigma_ln"] = theta[4]
    p["beta"] = theta[5]
    return p


def residuals(theta, base):
    p = unpack(theta, base)
    return np.concatenate([p_after_pulse(p, v, d.T3_T) - d.T3_P[:, j] for j, v in enumerate(d.T3_V)])


def fit(base):
    best = None
    for la in (2.0, 3.0, 4.0):
        for lt in (-8.0, -6.0):
            for b in (1.5, 2.0, 3.0):
                r = least_squares(residuals, [24.8, lt, la, 1.5, 0.3, b], args=(base,),
                                  bounds=([20, -12, 1.0, 0.3, 0.02, 1.0], [30, -3, 10, 20, 0.8, 6.0]))
                if best is None or r.cost < best.cost:
                    best = r
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the fitted values to setB.json")
    args = ap.parse_args()
    base = fr.load_set("B")
    base["V_imp_V"] = -(d.T1_CROSS_ASC + d.T1_CROSS_DESC) / 2
    slope = (d.T1_Q_DESC[-1] - d.T1_Q_DESC[-3]) / (d.T1_V[-1] - d.T1_V[-3])   # uC/cm^2 per V
    base["eps_r"] = round(slope * 1e-2 * base["t_fe_m"] / fr.EPS0, 1)
    best = fit(base)
    p = unpack(best.x, base)
    res = residuals(best.x, base).reshape(len(d.T3_V), -1).T
    print(f"V_imp = {p['V_imp_V']:.3f} V, eps_r = {p['eps_r']} (T1 slope {slope:.2f} uC/cm^2/V)")
    print(f"P_S = {p['P_S_C_per_m2']*100:.2f} uC/cm^2, tau_inf = {p['tau_inf_s']:.3e} s, "
          f"alpha = {p['alpha']:.3f}, beta = {p['beta']:.3f}, "
          f"E_a median = {p['dist']['median_MV_per_cm']:.3f} MV/cm, sigma_ln = {p['dist']['sigma_ln']:.3f}")
    print(f"T3 RMS error (all 72) = {np.sqrt(np.mean(res**2)):.2f} uC/cm^2; "
          f"1-3 V max |err| = {np.max(np.abs(res[:, 1:])):.2f}; "
          f"points at 1-3 V outside +-3: {int(np.sum(np.abs(res[:, 1:]) > 3))} of {res[:, 1:].size}")
    for j, v in enumerate(d.T3_V):
        print(f"  {v:.1f} V residuals: " + " ".join(f"{e:+.1f}" for e in res[:, j]))
    if args.write:
        out = fr.load_set("B")
        out["V_imp_V"] = round(float(p["V_imp_V"]), 4)
        out["eps_r"] = float(p["eps_r"])
        out["P_S_C_per_m2"] = round(float(p["P_S_C_per_m2"]), 5)
        out["tau_inf_s"] = float(f"{p['tau_inf_s']:.5g}")
        out["alpha"] = round(float(p["alpha"]), 4)
        out["beta"] = round(float(p["beta"]), 4)
        out["dist"]["median_MV_per_cm"] = round(float(p["dist"]["median_MV_per_cm"]), 4)
        out["dist"]["sigma_ln"] = round(float(p["dist"]["sigma_ln"]), 4)
        out["what"] = ("P1 film: 10 nm Hf0.4Zr0.6O2 on 2 nm SiO2 (Ni, Jerry, Smith, Datta, VLSI 2018). "
                       "Kinetics fitted to T3 by device/py/fit_setB.py; eps_r from the T1 slope; "
                       "channel vth0 by device/py/fit_fefet.py.")
        fr.save_set(out)
        print("wrote device/params/setB.json")


if __name__ == "__main__":
    main()
