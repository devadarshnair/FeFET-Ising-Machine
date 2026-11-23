"""Checker for test 1c (set B pulse switching vs Ni 2018 Fig. 4(c), table T3). Reads
sim/out/t1c/t1c.csv from device/tb/t1c_pulse_setB.cir; tolerances in device/tb/TESTS.md."""
import numpy as np

from checklib import OUT, Report, read_wrdata, write_csv
import data_ni2018 as d
import fefet_ref as fr
from fit_setB import p_after_pulse


def main():
    rep = Report()
    p = fr.load_set("B")
    s = read_wrdata(OUT / "t1c" / "t1c.csv")
    ps = 100 * p["P_S_C_per_m2"]
    sim = np.zeros_like(d.T3_P)
    rows = []
    for j, v in enumerate(d.T3_V):
        ref = p_after_pulse(p, v, d.T3_T)
        for k, tw in enumerate(d.T3_T):
            sim[k, j] = ps * s[f"v(xp{j+1:02d}{k+1:02d}.xfe.xs)"][-1]
            rows.append([v, tw, d.T3_P[k, j], sim[k, j], ref[k]])
    err = sim - d.T3_P
    e13 = err[:, 1:]
    n_out = int(np.sum(np.abs(e13) > 3.0))
    worst = np.unravel_index(np.argmax(np.abs(e13)), e13.shape)
    rep.check("t1c.pulse_1to3V", n_out == 0,
              f"{n_out} of {e13.size} points outside +-3 uC/cm^2; max |err| {np.abs(e13).max():.2f} at "
              f"{d.T3_V[1:][worst[1]]:.1f} V, {d.T3_T[worst[0]]:.0e} s", "every point within +-3 uC/cm^2")
    rep.info(f"RMS error, all 72 points (incl. 0.5 V) = {np.sqrt(np.mean(err**2)):.2f} uC/cm^2")
    ref_all = np.array([r[4] for r in rows]).reshape(len(d.T3_V), -1).T
    rep.info(f"ngspice vs offline fit model (no pulse edges): max |dP| = {np.abs(sim - ref_all).max():.2f} uC/cm^2")
    write_csv(OUT / "t1c" / "t1c_result.csv", ["V", "t_pulse_s", "P_exp", "P_sim", "P_offline"], rows)
    rep.finish()


if __name__ == "__main__":
    main()
