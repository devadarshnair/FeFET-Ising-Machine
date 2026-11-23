"""Checker for tests 3b (8-cell word) and 3c (64-cell word): search function, discharge time and
energy per search. Reads sim/out/t3b/t3b_word8.csv and sim/out/t3c/t3c_word64_mNN.csv;
tolerances in device/tb/TESTS.md."""
import numpy as np

import tcam_build as tb
from checklib import OUT, Report, read_wrdata, write_csv
from make_tcam import COUNTS64, PATTERN, T64, T8, key_with, word8_cases


def measure(d, w, timing):
    """Discharge time (s, SA 'miss' output crossing VDD/2 after the search-line edge; inf if it
    never does), ML 50 % time, SA state at the end of the window, and energy (J) of cycle 2."""
    t = d["time"]
    t_sl = timing.sl_mid(1)
    t_stop = t_sl + timing.t_eval
    k = (t >= t_sl) & (t <= t_stop)
    miss, ml = d[f"v(miss{w})"][k], d[f"v(ml{w}_0)"][k]
    tt = t[k]

    def first_cross(y, level, rising):
        idx = np.where(y >= level)[0] if rising else np.where(y <= level)[0]
        if len(idx) == 0 or idx[0] == 0:
            return float("inf")
        j = idx[0]
        return tt[j - 1] + (level - y[j - 1]) * (tt[j] - tt[j - 1]) / (y[j] - y[j - 1]) - t_sl

    td = first_cross(miss, tb.VDD / 2, True)
    tml = first_cross(ml, tb.VDD / 2, False)
    flipped = float(np.interp(t_stop - 50e-12, t, d[f"v(miss{w})"])) > tb.VDD / 2
    c0, c1 = timing.start(1), timing.start(1) + timing.period
    kk = (t >= c0) & (t <= c1)
    e_vdd = -np.trapezoid(tb.VDD * d[f"i(vdd{w})"][kk], t[kk])
    e_vs = -np.trapezoid(tb.VS * d[f"i(vs{w})"][kk], t[kk])
    return td, tml, flipped, e_vdd, e_vs


def main():
    rep = Report()
    d = read_wrdata(OUT / "t3b" / "t3b_word8.csv")
    rows, ok_fn, tds = [], True, {}
    for w, (name, stored, key) in enumerate(word8_cases()):
        m = tb.mismatches(stored, key)
        td, tml, flipped, ev, es = measure(d, w, T8)
        ok_fn &= flipped == (m >= 1)
        if name.startswith("count"):
            tds[m] = td
        rows.append(["word8", name, "".join(stored), "".join(key), m, td * 1e12, tml * 1e12, int(flipped),
                     ev * 1e15, es * 1e15, (ev + es) * 1e15])
        rep.info(f"8-cell {name:18s} m = {m}: t_discharge {td*1e12:8.1f} ps, ML 50 % {tml*1e12:8.1f} ps, "
                 f"E = {ev*1e15:.2f} (VDD) + {es*1e15:.2f} (SL) = {(ev+es)*1e15:.2f} fJ")
    pf = OUT / "t3b" / "t3b_word8_frozen.csv"
    if pf.exists():
        dfz = read_wrdata(pf)
        dt_max, de_max = 0.0, 0.0
        for w, (name, stored, key) in enumerate(word8_cases()):
            td0, _, f0, ev0, es0 = measure(d, w, T8)
            td1, _, f1, ev1, es1 = measure(dfz, w, T8)
            if np.isfinite(td0) and np.isfinite(td1):
                dt_max = max(dt_max, abs(td1 - td0) / td0)
            de_max = max(de_max, abs((ev1 + es1) - (ev0 + es0)) / (ev0 + es0))
        rep.check("t3b.frozen_equiv", dt_max <= 0.01 and de_max <= 0.01,
                  f"frozen-domain cells vs full model, 14 cases: max |dt|/t {100*dt_max:.3f} %, max |dE|/E "
                  f"{100*de_max:.3f} %", "each <= 1 %")
    rep.check("t3b.function", ok_fn, "SA output correct for all 14 cases" if ok_fn else "SA output WRONG in some case",
              "mismatch flagged iff count >= 1")
    seq = [tds[m] for m in range(1, 9)]
    mono = all(a > b for a, b in zip(seq, seq[1:]))
    rep.check("t3b.monotonic", mono, "t(1..8) = " + " ".join(f"{x*1e12:.0f}" for x in seq) + " ps",
              "strictly decreasing")
    rep.check("t3b.t1", tds[1] < 1e-9, f"t(1 mismatch) = {tds[1]*1e12:.0f} ps", "< 1000 ps")
    e1 = [r for r in rows if r[1] == "count 1"][0][10] / 8
    rep.check("t3b.energy", 0.19 <= e1 <= 0.75, f"{e1:.3f} fJ per cell per search at 1 mismatch "
              "(VDD + search lines, one row)", "0.19-0.75 fJ (factor 2 of 0.375)")
    ok64, parts = True, []
    for m in COUNTS64:
        p = OUT / "t3c" / f"t3c_word64_m{m:02d}.csv"
        if not p.exists():
            ok64 = False
            parts.append(f"m={m}: not run")
            continue
        d64 = read_wrdata(p)
        td, tml, flipped, ev, es = measure(d64, 0, T64)
        ok64 &= flipped == (m >= 1)
        parts.append(f"m={m}: {td*1e12:.0f} ps")
        rows.append(["word64", f"count {m}", "".join(PATTERN) + " x8", "key_with", m, td * 1e12, tml * 1e12,
                     int(flipped), ev * 1e15, es * 1e15, (ev + es) * 1e15])
        rep.info(f"64-cell m = {m:2d}: t_discharge {td*1e12:8.1f} ps, E = {ev*1e15:.2f} + {es*1e15:.2f} = "
                 f"{(ev+es)*1e15:.2f} fJ ({(ev+es)*1e15/64:.3f} fJ/cell)")
    rep.check("t3c.function", ok64, "; ".join(parts), "mismatch flagged iff count >= 1")
    write_csv(OUT / "t3b" / "t3b_result.csv", ["word", "case", "stored", "key", "count", "t_discharge_ps",
              "t_ml50_ps", "sa_miss", "E_vdd_fJ", "E_sl_fJ", "E_total_fJ"], rows)
    rep.finish()


if __name__ == "__main__":
    main()
