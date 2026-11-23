"""Checker for test 1e (retention: gate at 0 V for up to 10 years after the writes; and target C6,
the high-V_th state with +1.1 V on the gate for 1e5 s). Reads sim/out/t1e/t1e_read.csv (stage 2)
and the MW-deck reads for a restart check; tolerances in device/tb/TESTS.md."""
from checklib import OUT, Report, read_wrdata, write_csv
import fefet_decks as fd
import fefet_ref as fr
from make_fefet_mw import B_KEEP, C_KEEP, results
from make_t1e import C6_READ, READ, hold_times

I_CRIT = {"b": 1e-7, "c": 1e-7 * 200 / 100}
WAIT0 = 2.0  # the hold starts 2 s after the write


def offline_retention_c(times):
    """MW of set C after +-4 V / 10 us and a hold at 0 V, from the offline reduced model
    (quasi-static read; read disturb is below 1 mV for set C). times = seconds after the write."""
    p = fr.load_set("C")
    mos = fr.MosTable("c")

    def state(high):
        m = fr.FeFETReduced(p, mos, I_CRIT["c"])
        m.pulse(4.0, 1e-5)
        m.wait(WAIT0)
        m.pulse(-4.0, 1e-5)
        if not high:
            m.wait(WAIT0)
            m.pulse(4.0, 1e-5)
        return m

    lo, hi = state(False), state(True)
    out, t_prev = [], 0.0
    for t in times:
        lo.wait(t - t_prev)
        hi.wait(t - t_prev)
        t_prev = t
        out.append(hi.vth() - lo.vth())
    return out


def main():
    rep = Report()
    data = read_wrdata(OUT / "t1e" / "t1e_read.csv")
    t, win = data["time"], READ.windows()[0]

    def vth(name, crit):
        return fd.vth_from_ramp(t, data[f"v(g_{name})"], data[f"i(vd_{name})"], win, crit)

    v = {dev: [vth(f"{dev}{j}", I_CRIT[dev[0]]) for j in range(len(hold_times(dev)))] for dev in ("bl", "bh", "cl", "ch")}
    lb, hb = results("t1d", I_CRIT["b"])[B_KEEP]
    lc, hc = results("t1f", I_CRIT["c"])[C_KEEP]
    rep.info(f"restart check (state saved 1 us before the in-deck read, then a fresh read): set B "
             f"{1000*(v['bl'][0]-lb):+.1f} / {1000*(v['bh'][0]-hb):+.1f} mV, set C "
             f"{1000*(v['cl'][0]-lc):+.1f} / {1000*(v['ch'][0]-hc):+.1f} mV")
    rows = []
    k5 = hold_times("ch").index(1e5)
    for s in ("b", "c"):
        mw = [h - l for l, h in zip(v[s + "l"], v[s + "h"])]
        ratio = mw[k5] / mw[0]
        rep.check(f"t1e.set{s.upper()}_1e5s", ratio >= 0.90,
                  f"MW(2 s) {mw[0]:.3f} V -> MW(1e5 s) {mw[k5]:.3f} V ({100*ratio:.1f} %)", ">= 90 % of MW(2 s)")
        rep.info(f"set {s.upper()} V_th low/high (MW) after: " + "; ".join(
            f"{WAIT0+th:.3g} s {lo:.3f}/{hi:.3f} ({m:.3f})"
            for th, lo, hi, m in zip(hold_times(s + "l"), v[s + "l"], v[s + "h"], mw)))
        rows += [[s.upper(), WAIT0 + th, lo, hi, m] for th, lo, hi, m in zip(hold_times(s + "l"), v[s + "l"], v[s + "h"], mw)]
    off = offline_retention_c([2.0, 1e5 + 2, 1e6 + 2, 1e8, 3.15e8])
    k6 = hold_times("ch").index(1e6)
    rep.info("offline reduced model, set C MW after 2 s / 1e5 s / 1e6 s / 1e8 s / 3.15e8 s (10 years): "
             + " / ".join(f"{m:.3f}" for m in off) + f" V (ngspice at 1e6 s: {v['ch'][k6]-v['cl'][k6]:.3f} V)")
    cv = vth("cv0", I_CRIT["c"])
    shift = cv - v["ch"][k5]
    rep.check("t1e.setC_c6", abs(shift) <= 0.05, f"high V_th after 1e5 s at +1.1 V: {cv:.3f} V vs "
              f"{v['ch'][k5]:.3f} V held at 0 V (shift {1000*shift:+.1f} mV)", "|shift| <= 50 mV")
    rows.append(["C_c6", WAIT0 + C6_READ, float("nan"), cv, float("nan")])
    write_csv(OUT / "t1e" / "t1e_result.csv", ["set", "t_since_write_s", "vth_low", "vth_high", "MW"], rows)
    rep.finish()


if __name__ == "__main__":
    main()
