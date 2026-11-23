"""Checker for test 3a (TCAM write scheme, inhibit of an unselected word, write disturb).
Reads sim/out/t3a/t3a_read.csv; tolerances in device/tb/TESTS.md."""
import tcam_build as tb  # noqa: F401  (sets the import path)
from checklib import OUT, Report, read_wrdata, write_csv
import fefet_decks as fd
from make_fefet_mw import C_KEEP, results
from make_tcam import DISTURB, ROW0_TARGET, ROW1_START

I_CRIT = 1e-7 * 200 / 100


def main():
    rep = Report()
    d = read_wrdata(OUT / "t3a" / "t3a_read.csv")
    win = fd.ReadOnly(-0.2, 2.4).windows()[0]

    def vth(name):
        return fd.vth_from_ramp(d["time"], d[f"v(g_{name})"], d[f"i(vd_{name})"], win, I_CRIT)

    ref = dict(zip(("low", "high"), results("t1f", I_CRIT)[C_KEEP]))
    aged = {"low": vth("dl0"), "high": vth("dh0")}
    rows, worst_w, worst_i = [], 0.0, 0.0
    for r, pattern in ((0, ROW0_TARGET), (1, ROW1_START)):
        for j, bit in enumerate(pattern):
            for side, state in zip("lr", tb.fefet_states(bit)):
                v = vth(f"r{r}c{j}{side}")
                if r == 0:
                    worst_w = max(worst_w, abs(v - ref[state]))
                else:
                    worst_i = max(worst_i, abs(v - aged[state]))
                rows.append([r, j, side, bit, state, v])
    rep.check("t3a.write", worst_w <= 0.10, f"row 0 written to {''.join(ROW0_TARGET)}: worst |V_th - single device| "
              f"= {1000*worst_w:.1f} mV (single device {ref['low']:.3f} / {ref['high']:.3f} V)", "<= 100 mV")
    rep.check("t3a.inhibit", worst_i <= 0.05, f"row 1 ({''.join(ROW1_START)}, +-2 V inhibit): worst V_th shift "
              f"{1000*worst_i:.1f} mV vs unstressed devices of the same age", "<= 50 mV")
    shifts = []
    for name, state, v in DISTURB[:4]:
        s = vth(f"d{name}") - aged[state]
        shifts.append(s)
        rows.append(["disturb", name, "", "", state, vth(f"d{name}")])
        rep.info(f"disturb {state} V_th at {v:+.0f} V for 2.55 ms: shift {1000*s:+.1f} mV")
    for name, state, v in DISTURB[6:]:
        s = vth(f"d{name}") - aged[state]
        rows.append(["disturb", name, "", "", state, vth(f"d{name}")])
        rep.info(f"V_W/3 case (information): {state} V_th at {v:+.2f} V for 2.55 ms: shift {1000*s:+.1f} mV")
    worst_d = max(abs(s) for s in shifts)
    rep.check("t3a.disturb255", worst_d <= 0.05, f"worst V_th shift after 255 x 10 us at +-2 V: {1000*worst_d:.1f} mV",
              "<= 50 mV")
    write_csv(OUT / "t3a" / "t3a_result.csv", ["row", "cell", "side", "bit", "state", "vth"], rows)
    rep.finish()


if __name__ == "__main__":
    main()
