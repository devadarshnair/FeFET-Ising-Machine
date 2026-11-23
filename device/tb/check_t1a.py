"""Checker for test 1a (set A implementation check). Reads sim/out/t1a/t1a.csv from
device/tb/t1a_nls_setA.cir; tolerances in device/tb/TESTS.md."""
import numpy as np

from checklib import OUT, Report, at_times, read_wrdata, write_csv
import fefet_ref as fr

TOL = 0.01          # 1 % of 2 P_S
VOLTS = [0.6, 1.0, 1.4, 1.8]
TAGS = ["06", "10", "14", "18"]
AREA = 1e-10


def main():
    rep = Report()
    p = fr.load_set("A")
    d = read_wrdata(OUT / "t1a" / "t1a.csv")
    t = d["time"]
    tq = 10 ** (-7 + np.arange(33) / 8)
    tq = tq[tq >= 2e-7 - 1e-12]
    va1 = fr.activation_fields(p, 1) * p["t_fe_m"]
    rows, err1, err16d, err16c, qerr = [], [], [], [], []
    for v, tag in zip(VOLTS, TAGS):
        x1 = at_times(t, d[f"v(x1a{tag}.xfe.x1)"], tq)
        x16 = at_times(t, d[f"v(x16a{tag}.xfe.xs)"], tq)
        ref1 = -1 + 2 * fr.switched_fraction_weibull(v, tq, va1[0], p)
        ref16d = fr.p_ensemble_const(v, tq, p)
        ref16c = fr.p_eq5_continuous(v, tq, p)
        # errors in units of 2 P_S (P/P_S spans 2)
        err1.append(np.max(np.abs(x1 - ref1)) / 2)
        err16d.append(np.max(np.abs(x16 - ref16d)) / 2)
        err16c.append(np.max(np.abs(x16 - ref16c)) / 2)
        # charge check over [t_a, 1 ms]: source current vs area * P_S * d(mean x)
        k0 = np.searchsorted(t, 1e-9)
        cur = -d[f"i(v16a{tag})"][k0:]
        q_src = np.trapezoid(cur, t[k0:])
        dp = AREA * p["P_S_C_per_m2"] * (d[f"v(x16a{tag}.xfe.xs)"][-1] - d[f"v(x16a{tag}.xfe.xs)"][k0])
        if abs(dp) > 0.1 * 2 * AREA * p["P_S_C_per_m2"]:
            qerr.append(abs(q_src - dp) / abs(dp))
        for k, tk in enumerate(tq):
            rows.append([v, tk, x1[k], ref1[k], x16[k], ref16d[k], ref16c[k]])
        rep.info(f"V_A = {v} V: max|dP| single {err1[-1]*100:.3f} %, 16-domain vs discrete "
                 f"{err16d[-1]*100:.3f} %, vs eq.(5) {err16c[-1]*100:.3f} % of 2P_S")
    write_csv(OUT / "t1a" / "t1a_result.csv",
              ["V_A", "t_s", "P_sim_1dom", "P_ref_1dom", "P_sim_16dom", "P_ref_16dom_discrete",
               "P_ref_eq5"], rows)
    # Offline only (no SPICE): how the N-bin discretisation error falls with N.
    for n in (16, 32, 64, 128):
        e = max(np.max(np.abs(fr.p_ensemble_const(v, tq, p, n) - fr.p_eq5_continuous(v, tq, p))) / 2
                for v in VOLTS)
        rep.info(f"offline: N = {n:3d} equal-probability bins vs eq.(5): max|dP| = {e*100:.3f} % of 2P_S")
    e1, e16d, e16c = max(err1), max(err16d), max(err16c)
    rep.check("t1a.single", e1 <= TOL, f"max|dP| = {e1*100:.3f} % of 2P_S", "<= 1 %")
    rep.check("t1a.ensemble_discrete", e16d <= TOL, f"max|dP| = {e16d*100:.3f} % of 2P_S", "<= 1 %")
    rep.check("t1a.ensemble_eq5", e16c <= TOL, f"max|dP| = {e16c*100:.3f} % of 2P_S", "<= 1 %")
    qe = max(qerr) if qerr else float("nan")
    rep.check("t1a.charge", qe <= 0.01, f"max relative charge error {qe*100:.3f} % ({len(qerr)} cases)",
              "<= 1 %")
    rep.finish()


if __name__ == "__main__":
    main()
