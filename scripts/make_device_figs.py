"""Make the small PNG figures of docs/device/CALIBRATION_v0.md from the checker CSVs in sim/out/.
Run after scripts/run_spice_tests.sh:  scripts/run_guarded.sh <python> scripts/make_device_figs.py
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "sim" / "out"
FIG = REPO / "docs" / "device" / "fig"
sys.path.insert(0, str(REPO / "device" / "py"))
import data_ni2018 as d  # noqa: E402

plt.rcParams.update({"figure.dpi": 110, "font.size": 8, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})
COLORS = plt.rcParams["axes.prop_cycle"].by_key()["color"]


def rows(path):
    with open(path) as f:
        r = list(csv.DictReader(f))
    return r


def col(rs, key, cond=None):
    return np.array([float(x[key]) for x in rs if cond is None or cond(x)])


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name)
    plt.close(fig)
    print("wrote", name)


def fig_t1a():
    rs = rows(OUT / "t1a" / "t1a_result.csv")
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    for k, v in enumerate(sorted({float(x["V_A"]) for x in rs})):
        c = (lambda x, v=v: float(x["V_A"]) == v)
        t = col(rs, "t_s", c)
        ax.semilogx(t, col(rs, "P_ref_eq5", c), "-", color=COLORS[k], lw=1, label=f"{v} V eq.(5)")
        ax.semilogx(t, col(rs, "P_sim_16dom", c), "o", color=COLORS[k], ms=2.5)
        ax.semilogx(t, col(rs, "P_sim_1dom", c), "x", color=COLORS[k], ms=3)
    ax.set_xlabel("time at constant V (s)")
    ax.set_ylabel("P / P_S")
    ax.set_title("1a set A: lines eq.(5), o = 16 domains, x = 1 domain", fontsize=8)
    ax.legend(fontsize=6, ncol=2)
    save(fig, "t1a_setA_nls.png")


def fig_t1b():
    rs = rows(OUT / "t1b" / "t1b_result.csv")
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.6))
    ax = axs[0]
    for curve, style, lab in (("major_asc", "-", "model 50 V/ms"), ("major_desc", "-", None),
                              ("major_0p5Vms", ":", "model 0.5 V/ms")):
        c = (lambda x, cv=curve: x["curve"] == cv)
        ax.plot(col(rs, "V", c), col(rs, "Q_uC_per_cm2", c), style, color=COLORS[0], lw=1, label=lab)
    ax.plot(d.T1_V, d.T1_Q_ASC, "o", color=COLORS[1], ms=3, label="Ni 2018 exp")
    ax.plot(d.T1_V, d.T1_Q_DESC, "o", color=COLORS[1], ms=3)
    ax.set_xlabel("V_FE (V)")
    ax.set_ylabel("Q (uC/cm^2)")
    ax.set_title("1b set B loop", fontsize=8)
    ax.legend(fontsize=6)
    ax = axs[1]
    for k, w in enumerate("cde"):
        c = (lambda x, w=w: x["curve"] == f"minor_{w}")
        ax.plot(col(rs, "V", c), col(rs, "Q_uC_per_cm2", c), lw=0.8, color=COLORS[k], label=f"Fig. 5({w})")
    ax.set_xlabel("V_FE (V)")
    ax.set_title("1b minor-loop waveforms (50 V/ms)", fontsize=8)
    ax.legend(fontsize=6)
    save(fig, "t1b_setB_loops.png")


def fig_t1c():
    rs = rows(OUT / "t1c" / "t1c_result.csv")
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    for k, v in enumerate(d.T3_V):
        c = (lambda x, v=v: abs(float(x["V"]) - v) < 1e-9)
        t = col(rs, "t_pulse_s", c)
        ax.semilogx(t, col(rs, "P_exp", c), "o", color=COLORS[k], ms=3)
        ax.semilogx(t, col(rs, "P_sim", c), "-", color=COLORS[k], lw=1, label=f"{v} V")
    ax.set_xlabel("pulse width (s)")
    ax.set_ylabel("remanent P (uC/cm^2)")
    ax.set_title("1c set B pulses: o = Ni 2018 Fig. 4(c), lines = model", fontsize=8)
    ax.legend(fontsize=6, ncol=2)
    save(fig, "t1c_setB_pulses.png")


def fig_t1d():
    rs = rows(OUT / "t1d" / "t1d_result.csv")
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    for k, v in enumerate(d.T4_V):
        c = (lambda x, v=v: abs(float(x["V"]) - v) < 1e-9)
        t = col(rs, "PW_s", c)
        ax.semilogx(t, col(rs, "MW_exp", c), "o", color=COLORS[k], ms=3)
        ax.semilogx(t, col(rs, "MW_sim", c), "-", color=COLORS[k], lw=1, label=f"+-{v} V")
        ax.semilogx(t, col(rs, "MW_P1sim", c), ":", color=COLORS[k], lw=0.8)
    ax.set_xlabel("write pulse width (s)")
    ax.set_ylabel("memory window (V)")
    ax.set_title("1d set B FeFET: o = exp, lines = model, dotted = P1 model", fontsize=8)
    ax.legend(fontsize=6, ncol=2)
    save(fig, "t1d_setB_mw.png")


def fig_t1f():
    rs = rows(OUT / "t1f" / "t1f_result.csv")
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    for k, w in enumerate(sorted({float(x["PW_s"]) for x in rs})):
        c = (lambda x, w=w: float(x["PW_s"]) == w)
        ax.plot(col(rs, "V", c), col(rs, "MW_sim", c), "-", color=COLORS[k], lw=1, label=f"{w:.0e} s")
    iso = [(3.77, 1e-6, 1.0), (3.66, 1e-5, 1.0), (3.30, 1e-4, 1.0), (2.82, 1e-6, 0.2), (2.60, 1e-5, 0.2),
           (2.50, 1e-3, 0.2)]
    widths = sorted({float(x["PW_s"]) for x in rs})
    for v, w, mw in iso:
        ax.plot(v, mw, "o", color=COLORS[widths.index(w)], ms=4)
    ax.plot(4.0, 1.03, "k*", ms=6, label="Ni 2019 +-4 V/10 us")
    ax.set_xlabel("write amplitude (V)")
    ax.set_ylabel("memory window (V)")
    ax.set_title("1f set C: lines = model, o = Ni 2019 iso-MW points", fontsize=8)
    ax.legend(fontsize=6)
    save(fig, "t1f_setC_mw.png")


def fig_t1e():
    rs = rows(OUT / "t1e" / "t1e_result.csv")
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    for k, s in enumerate(("B", "C")):
        c = (lambda x, s=s: x["set"] == s)
        t = col(rs, "t_since_write_s", c)
        ax.semilogx(t, col(rs, "vth_low", c), "-o", color=COLORS[k], ms=2.5, lw=1, label=f"set {s} low/high")
        ax.semilogx(t, col(rs, "vth_high", c), "-o", color=COLORS[k], ms=2.5, lw=1)
    c = (lambda x: x["set"] == "C_c6")
    ax.semilogx(col(rs, "t_since_write_s", c), col(rs, "vth_high", c), "s", color=COLORS[1], ms=4,
                label="set C high, gate at +1.1 V")
    ax.axvline(1e5, color="k", lw=0.5)
    ax.axvline(3.15e8, color="k", lw=0.5, ls=":")
    ax.set_xlabel("time after write (s)")
    ax.set_ylabel("V_th (V)")
    ax.set_title("1e retention (gate 0 V unless noted)", fontsize=8)
    ax.legend(fontsize=6)
    save(fig, "t1e_retention.png")


def fig_t3():
    rs = rows(OUT / "t3b" / "t3b_result.csv")
    w8 = [x for x in rs if x["word"] == "word8" and x["case"].startswith("count")]
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.6))
    m = col(w8, "count")
    td = col(w8, "t_discharge_ps")
    axs[0].plot(m[m > 0], td[m > 0], "o-", ms=3, lw=1, label="nominal")
    p = OUT / "t3d" / "t3d_result.csv"
    if p.exists():
        mc = [x for x in rows(p) if int(x["count"]) > 0]
        axs[0].errorbar(col(mc, "count"), col(mc, "t_mean_ps"), yerr=col(mc, "t_sigma_ps"), fmt="s", ms=3,
                        capsize=2, label="Monte Carlo mean +- 1 sigma")
    axs[0].set_xlabel("mismatch count (8-cell word)")
    axs[0].set_ylabel("discharge time (ps)")
    axs[0].legend(fontsize=6)
    axs[1].plot(m, col(w8, "E_vdd_fJ"), "o-", ms=3, lw=1, label="VDD (precharge + SA)")
    axs[1].plot(m, col(w8, "E_sl_fJ"), "s-", ms=3, lw=1, label="search lines")
    axs[1].plot(m, col(w8, "E_total_fJ"), "k^-", ms=3, lw=1, label="total")
    axs[1].set_xlabel("mismatch count")
    axs[1].set_ylabel("energy per search (fJ, one word)")
    axs[1].legend(fontsize=6)
    save(fig, "t3_word8.png")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    for f in (fig_t1a, fig_t1b, fig_t1c, fig_t1d, fig_t1f, fig_t1e, fig_t3):
        try:
            f()
        except (OSError, KeyError, ValueError) as e:
            print(f"skipped {f.__name__}: {e}")


if __name__ == "__main__":
    main()
