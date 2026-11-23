"""Checker for test 1f (set C, the TCAM-class FeFET, vs the Ni 2019 targets). Reads
sim/out/t1f/t1f_wNN.csv; tolerances in device/tb/TESTS.md. The offline cross-check needs
sim/out/mos/mos_table.txt made from the current library (device/tb/mos_table.cir)."""
from checklib import OUT, Report, write_csv
import fefet_ref as fr
from make_fefet_mw import C_AMPS, C_KEEP, C_WIDTHS, results

VTH_LOW, VTH_HIGH = 0.65, 1.68
ISO_TARGETS = [(1.0, 1e-6, 3.77), (1.0, 1e-5, 3.66), (1.0, 1e-4, 3.30),
               (0.2, 1e-6, 2.82), (0.2, 1e-5, 2.60), (0.2, 1e-3, 2.50)]


def i_crit(p):
    f = p["fefet"]
    return 1e-7 * f["W_m"] / f["L_m"]


def amp_for_mw(amps, mws, target):
    """Smallest amplitude where MW(amp) rises through target (linear interpolation)."""
    if mws[0] >= target:
        return float("-inf")       # already above target at the lowest amplitude
    for k in range(1, len(amps)):
        if mws[k - 1] < target <= mws[k]:
            return amps[k - 1] + (target - mws[k - 1]) * (amps[k] - amps[k - 1]) / (mws[k] - mws[k - 1])
    return float("inf")            # never reached


def main():
    rep = Report()
    p = fr.load_set("C")
    res = results("t1f", i_crit(p))
    lo, hi = res[C_KEEP]
    rep.check("t1f.vth_low", abs(lo - VTH_LOW) <= 0.05, f"V_th = {lo:.3f} V after +4 V / 10 us", "0.65 +- 0.05 V")
    rep.check("t1f.vth_high", abs(hi - VTH_HIGH) <= 0.05, f"V_th = {hi:.3f} V after -4 V / 10 us", "1.68 +- 0.05 V")
    rep.check("t1f.mw", abs((hi - lo) - 1.03) <= 0.05, f"MW = {hi-lo:.3f} V", "1.03 +- 0.05 V")
    mw = {w: [res[(a, w)][1] - res[(a, w)][0] for a in C_AMPS] for w in C_WIDTHS}
    worst, parts = 0.0, []
    for target, width, v_exp in ISO_TARGETS:
        v = amp_for_mw(C_AMPS, mw[width], target)
        worst = max(worst, abs(v - v_exp))
        parts.append(f"MW {target} V at {width:.0e} s: {v:.2f} V (exp {v_exp:.2f})")
    rep.check("t1f.iso_mw", worst <= 0.15, "; ".join(parts), "each within +-0.15 V")
    for w in C_WIDTHS:
        rep.info(f"MW at {w:.0e} s for 2.0 ... 4.4 V: " + " ".join(f"{x:.2f}" for x in mw[w]))
    mos = fr.MosTable("c")
    lo_r, hi_r = fr.mw_protocol(lambda: fr.FeFETReduced(p, mos, i_crit(p)), 4.0, 1e-5, read=(-0.2, 2.4))
    dmax = max(abs(lo_r - lo), abs(hi_r - hi))
    rep.check("t1f.ref_agree", dmax <= 0.020,
              f"offline reduced model (same read ramp): V_th {lo_r:.3f} / {hi_r:.3f} V; max difference "
              f"{1000*dmax:.1f} mV", "each within 20 mV")
    lo_q, hi_q = fr.mw_protocol(lambda: fr.FeFETReduced(p, mos, i_crit(p)), 4.0, 1e-5)
    rep.info(f"offline quasi-static thresholds (no switching during the read): {lo_q:.3f} / {hi_q:.3f} V; "
             f"read disturb of the 26 us ramp = {1000*(lo_r-lo_q):+.1f} / {1000*(hi_r-hi_q):+.1f} mV")
    rows = [[a, w, mw[w][C_AMPS.index(a)], res[(a, w)][0], res[(a, w)][1]] for w in C_WIDTHS for a in C_AMPS]
    write_csv(OUT / "t1f" / "t1f_result.csv", ["V", "PW_s", "MW_sim", "vth_low", "vth_high"], rows)
    rep.finish()


if __name__ == "__main__":
    main()
