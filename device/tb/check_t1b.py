"""Checker for test 1b (set B loop and minor loops at 50 V/ms). Reads sim/out/t1b/t1b.csv
(and t1b_slow.csv for an INFO line); tolerances in device/tb/TESTS.md."""
import numpy as np

from checklib import OUT, Report, read_wrdata, write_csv
import data_ni2018 as d
import fefet_ref as fr


def charge(p, v, xs):
    """Q in uC/cm^2: polarization plus linear dielectric part (eps0*eps_r*V/t_FE)."""
    return 100 * (p["P_S_C_per_m2"] * xs + fr.EPS0 * p["eps_r"] * v / p["t_fe_m"])


def branch(t, v, q, t0, t1):
    k = (t >= t0) & (t <= t1)
    return v[k], q[k]


def crossing(v, q):
    k = np.where(np.diff(np.sign(q)) != 0)[0][0]
    return v[k] - q[k] * (v[k + 1] - v[k]) / (q[k + 1] - q[k])


def on_branch(v, q, vq):
    order = np.argsort(v)
    return np.interp(vq, v[order], q[order])


def loop_numbers(t, v, q, t_asc, t_desc):
    va, qa = branch(t, v, q, *t_asc)
    vd, qd = branch(t, v, q, *t_desc)
    return va, qa, vd, qd, crossing(va, qa), crossing(vd, qd)


def main():
    rep = Report()
    p = fr.load_set("B")
    s = read_wrdata(OUT / "t1b" / "t1b.csv")
    t = s["time"]
    q_maj = charge(p, s["v(nmaj)"], s["v(xmaj.xfe.xs)"])
    va, qa, vd, qd, xa, xd = loop_numbers(t, s["v(nmaj)"], q_maj, (0.30e-3, 0.42e-3), (0.42e-3, 0.54e-3))
    qa_t1 = on_branch(va, qa, d.T1_V)
    qd_t1 = on_branch(vd, qd, d.T1_V)
    err = np.concatenate([qa_t1 - d.T1_Q_ASC, qd_t1 - d.T1_Q_DESC])
    rms = float(np.sqrt(np.mean(err ** 2)))
    rep.check("t1b.loop_rms", rms <= 3.0, f"RMS = {rms:.2f} uC/cm^2 over 26 T1 points", "<= 3 uC/cm^2")
    ok = abs(xd - d.T1_CROSS_DESC) <= 0.15 and abs(xa - d.T1_CROSS_ASC) <= 0.15
    rep.check("t1b.crossings", ok, f"descending {xd:+.2f} V, ascending {xa:+.2f} V",
              f"{d.T1_CROSS_DESC:+.2f} / {d.T1_CROSS_ASC:+.2f} V +- 0.15 V")
    q0d, q0a = on_branch(vd, qd, 0.0), on_branch(va, qa, 0.0)
    ok = abs(q0d - d.T1_Q0_DESC) <= 3 and abs(q0a - d.T1_Q0_ASC) <= 3
    rep.check("t1b.q0", ok, f"Q(0) descending {q0d:+.1f}, ascending {q0a:+.1f} uC/cm^2",
              f"{d.T1_Q0_DESC:+.1f} / {d.T1_Q0_ASC:+.1f} +- 3")
    qp, qm = on_branch(vd, qd, 3.0), on_branch(va, qa, -3.0)
    ok = abs(qp - 37.0) <= 3 and abs(qm + 37.0) <= 3
    rep.check("t1b.qmax", ok, f"Q(+3 V) {qp:+.1f}, Q(-3 V) {qm:+.1f} uC/cm^2", "+-37.0 +- 3")

    # minor loops: return-point memory and return to the major loop
    ps = 100 * p["P_S_C_per_m2"]
    xc = s["v(xc.xfe.xs)"]
    p_first = ps * np.interp(0.264e-3, t, xc)
    p_second = ps * np.interp(0.360e-3, t, xc)
    p_sat = ps * np.interp(0.42e-3, t, s["v(xmaj.xfe.xs)"])
    ends = {w: ps * np.interp(te, t, s[f"v(x{w}.xfe.xs)"]) for w, te in
            (("c", 0.564e-3), ("d", 0.54e-3), ("e", 0.58e-3))}
    worst_end = max(abs(e - p_sat) for e in ends.values())
    rpm = abs(p_second - p_first)
    ok = rpm <= 1.0 and worst_end <= 1.0
    rep.check("t1b.rpm", ok, f"(c) |P(2nd +1.2 V) - P(1st)| = {rpm:.2f}; worst end-of-waveform offset "
              f"from the major loop at +3 V = {worst_end:.2f} uC/cm^2", "each <= 1.0 uC/cm^2")
    rep.info(f"minor loop (c): P at 1st +1.2 V = {p_first:+.2f}, 2nd = {p_second:+.2f}; min P inside the "
             f"inner loop = {ps*np.min(xc[(t > 0.264e-3) & (t < 0.36e-3)]):+.2f} uC/cm^2")

    rows = [["major_asc", vv, qq] for vv, qq in zip(va, qa)] + [["major_desc", vv, qq] for vv, qq in zip(vd, qd)]
    for w in "cde":
        q_w = charge(p, s[f"v(nw{w})"], s[f"v(x{w}.xfe.xs)"])
        k = t >= 0.06e-3
        rows += [[f"minor_{w}", vv, qq] for vv, qq in zip(s[f"v(nw{w})"][k], q_w[k])]
    try:
        sl = read_wrdata(OUT / "t1b" / "t1b_slow.csv")
        q_sl = charge(p, sl["v(nmaj)"], sl["v(xmaj.xfe.xs)"])
        *_, xa_s, xd_s = loop_numbers(sl["time"], sl["v(nmaj)"], q_sl, (30e-3, 42e-3), (42e-3, 54e-3))
        rep.info(f"same loop at 0.5 V/ms (100x slower): crossings {xd_s:+.2f} / {xa_s:+.2f} V")
        k = (sl["time"] >= 30e-3)
        rows += [["major_0p5Vms", vv, qq] for vv, qq in zip(sl["v(nmaj)"][k], q_sl[k])]
    except OSError:
        rep.info("slow-loop diagnostic not run")
    write_csv(OUT / "t1b" / "t1b_result.csv", ["curve", "V", "Q_uC_per_cm2"], rows)
    rep.finish()


if __name__ == "__main__":
    main()
