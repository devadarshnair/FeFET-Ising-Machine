"""Checker for test 1d (set B FeFET memory window vs Ni 2018 Fig. 6(d), table T4, and the
I_D-V_G numbers of T5). Reads sim/out/t1d/t1d_wNN.csv; tolerances in device/tb/TESTS.md."""
import numpy as np

from checklib import OUT, Report, read_wrdata, write_csv
import data_ni2018 as d
from make_fefet_mw import B_AMPS, B_KEEP, B_WIDTHS, PROT_B, deck_name, results

W_UM = 1.0
I_CRIT = 1e-7 * W_UM


def iv_numbers(data, k, window):
    """V_G at 1e-9 and 1e-8 A/um and I_D at V_G = 0.5 V during one read ramp."""
    t = data["time"]
    m = (t >= window[0]) & (t <= window[1])
    vg, idd = data[f"v(g{k})"][m], np.maximum(-data[f"i(vd{k})"][m], 1e-30) / W_UM
    li = np.log10(idd)
    j9, j8 = np.argmax(li >= -9), np.argmax(li >= -8)
    return vg[j9], vg[j8], 10 ** np.interp(0.5, vg, li)


def main():
    rep = Report()
    res = results("t1d", I_CRIT)
    mw = np.array([[res[(v, pw)][1] - res[(v, pw)][0] for v in B_AMPS] for pw in B_WIDTHS])
    err = mw - d.T4_MW
    lo, hi = res[B_KEEP]
    rep.check("t1d.mw_4p5V", abs((hi - lo) - 0.735) <= 0.05, f"MW = {hi-lo:.3f} V at +-4.5 V / 10 us",
              "0.735 +- 0.05 V")
    rms = float(np.sqrt(np.mean(err ** 2)))
    rms_p1 = float(np.sqrt(np.mean((d.T4_MW_P1SIM - d.T4_MW) ** 2)))
    rep.check("t1d.mw_table", rms <= 0.10, f"RMS = {rms:.3f} V over 72 points (P1's own model: {rms_p1:.3f} V)",
              "<= 0.10 V")
    ok = abs(lo - d.T5_VTH_LOW) <= 0.10 and abs(hi - d.T5_VTH_HIGH) <= 0.10
    rep.check("t1d.vth", ok, f"V_th low {lo:+.3f} V, high {hi:+.3f} V (1e-7 A/um, V_DS 50 mV)",
              f"{d.T5_VTH_LOW:+.2f} / {d.T5_VTH_HIGH:+.2f} +- 0.10 V")
    data = read_wrdata(OUT / "t1d" / f"{deck_name('t1d', B_WIDTHS.index(B_KEEP[1]))}.csv")
    k = B_AMPS.index(B_KEEP[0])
    w_hi, w_lo = PROT_B.windows()
    l9, l8, l05 = iv_numbers(data, k, w_lo)
    h9, h8, h05 = iv_numbers(data, k, w_hi)
    rep.info(f"T5: V_G at 1e-9 A/um low/high {l9:+.2f}/{h9:+.2f} V (exp -0.43/+0.20); at 1e-8 A/um "
             f"{l8:+.2f}/{h8:+.2f} V (exp -0.24/+0.42)")
    rep.info(f"T5: I_D at V_G = 0.5 V low/high {l05:.2e}/{h05:.2e} A/um, ratio {l05/h05:.1f} (exp 41, P1 sim 7.5); "
             f"SS(1e-9 -> 1e-8 A/um) {1000*(l8-l9):.0f} mV/dec (exp about 185)")
    for j, v in enumerate(B_AMPS):
        rep.info(f"MW at {v:.1f} V, PW 5e-8 ... 1e-2 s: " + " ".join(f"{x:+.2f}" for x in mw[:, j])
                 + "  | exp: " + " ".join(f"{x:+.2f}" for x in d.T4_MW[:, j]))
    rows = [[v, pw, d.T4_MW[i, j], d.T4_MW_P1SIM[i, j], mw[i, j], res[(v, pw)][0], res[(v, pw)][1]]
            for j, v in enumerate(B_AMPS) for i, pw in enumerate(B_WIDTHS)]
    write_csv(OUT / "t1d" / "t1d_result.csv", ["V", "PW_s", "MW_exp", "MW_P1sim", "MW_sim", "vth_low", "vth_high"],
              rows)
    rep.finish()


if __name__ == "__main__":
    main()
