"""Checker for test 3d (Monte Carlo of the 8-cell word under V_th variation) and writer of the
characterisation table circuit/tcam/char_v0.csv (format: docs/device/CHAR_FORMAT.md).

Reading rule (fixed before the run): the count is read from the discharge time t_d of the SA
output. Count 0 = no SA flip inside the evaluation window. Between counts m and m+1 (m >= 1) the
boundary is placed on ln(t_d) where the two fitted Gaussians are the same number of standard
deviations away (b = (mu_m*s_m1 + mu_m1*s_m)/(s_m + s_m1)). Error rates are given two ways: the
empirical fraction of misread samples and a Gaussian estimate from the fitted mean and sigma.
A level counts as resolved when both are <= 1 %.
"""
import json
import sys
import math

import numpy as np

import tcam_build as tb
from checklib import OUT, Report, write_csv
from make_tcam import T8

TCAM_DIR = tb.TCAM
P_MAX = 0.01


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def collect(folder):
    """Discharge times and energies per count from the ngspice logs of the measure-only MC decks
    (sim/out/<folder>/t3d_mcNNN.log). No waveform files are written for the Monte Carlo."""
    meta = json.loads((OUT / folder / "t3d_mc_meta.json").read_text())
    t_d = {m: [] for m in range(9)}
    energy = {m: [] for m in range(9)}
    for d, info in enumerate(meta["decks"]):
        path = OUT / folder / f"t3d_mc{d:03d}.log"
        if not path.exists():
            continue
        for item, (td, _flip, ev, es) in zip(info, tb.meas_from_log(path, len(info), T8)):
            t_d[item["count"]].append(td)
            energy[item["count"]].append(ev + es)
    return meta, {m: np.array(v) for m, v in t_d.items()}, {m: np.array(v) for m, v in energy.items()}


def main():
    rep = Report()
    folder = sys.argv[1] if len(sys.argv) > 1 else "t3d"
    meta, t_d, energy = collect(folder)
    n = len(t_d[1])
    rep.info(f"{n} samples per count (seed {meta['seed']}, sigma {meta['sigma_low']} / {meta['sigma_high']} V)")
    t_win = T8.t_eval
    fit = {}
    for m in range(1, 9):
        x = t_d[m][np.isfinite(t_d[m])]
        lx = np.log(x)
        fit[m] = (lx.mean(), lx.std(ddof=1), len(x))
    bounds = {0: math.log(t_win)}           # t_d >= window (or no flip) -> read as 0
    for m in range(1, 8):
        mu0, s0, _ = fit[m]
        mu1, s1, _ = fit[m + 1]
        bounds[m] = (mu0 * s1 + mu1 * s0) / (s0 + s1)   # between m+1 (faster, below) and m (above)
        bounds[m] = min(bounds[m], bounds[m - 1] - 1e-9)  # keep the reading intervals ordered
    edges = [-math.inf] + [bounds[m] for m in range(7, 0, -1)] + [bounds[0], math.inf]
    levels = list(range(8, 0, -1)) + [0]      # level for each interval of ln(t_d), fastest first

    def read(td):
        lt = math.log(td) if np.isfinite(td) else math.inf
        for k in range(len(levels)):
            if edges[k] <= lt < edges[k + 1]:
                return levels[k]
        return 0

    rows, resolved, confusion = [], [], np.zeros((9, 9), int)
    for m in range(9):
        reads = np.array([read(td) for td in t_d[m]])
        for r in reads:
            confusion[m, r] += 1
        p_emp = float(np.mean(reads != m))
        p_lo, p_hi = float(np.mean(reads < m)), float(np.mean(reads > m))
        if m == 0:
            n_flip = int(np.sum(np.isfinite(t_d[0])))
            p_gauss = p_emp
            row_t = (float("inf"), float("nan"), float("nan"), float("nan"))
        else:
            mu, s, _ = fit[m]
            hi_edge = bounds[m - 1] if m >= 1 else math.inf      # slower than this -> read lower
            lo_edge = bounds[m] if m <= 7 else -math.inf          # faster than this -> read higher
            p_gauss = (1 - phi((hi_edge - mu) / s)) + (phi((lo_edge - mu) / s) if m <= 7 else 0.0)
            x = t_d[m][np.isfinite(t_d[m])]
            row_t = (float(np.mean(x)), float(np.std(x, ddof=1)), float(np.percentile(x, 1)),
                     float(np.percentile(x, 99)))
        ok = p_emp <= P_MAX and p_gauss <= P_MAX
        resolved.append(ok)
        e = energy[m]
        lo_b = math.exp(bounds[m]) if m <= 7 and m >= 1 else (0.0 if m == 8 else float("nan"))
        hi_b = math.exp(bounds[m - 1]) if m >= 1 else float("inf")
        rows.append([m, len(t_d[m]), row_t[0] * 1e12, row_t[1] * 1e12, row_t[2] * 1e12, row_t[3] * 1e12,
                     float(np.mean(e)) * 1e15, float(np.std(e, ddof=1)) * 1e15, p_emp, p_gauss, p_lo, p_hi,
                     (lo_b if m >= 1 else math.exp(bounds[0])) * 1e12, hi_b * 1e12])
        rep.info(f"count {m}: t_d mean {row_t[0]*1e12:8.1f} ps sigma {row_t[1]*1e12:7.1f} ps; E {np.mean(e)*1e15:.2f} fJ; "
                 f"P(misread) empirical {p_emp:.3f} (low {p_lo:.3f}, high {p_hi:.3f}), Gaussian {p_gauss:.2e}"
                 + (f"; {n_flip} false flips" if m == 0 else ""))
    n_levels = 0
    while n_levels < 9 and resolved[n_levels]:
        n_levels += 1
    summary = (f"{n_levels} consecutive levels (0..{n_levels-1}) read with error <= 1 %; resolved set: "
               + ",".join(str(m) for m in range(9) if resolved[m]))
    if folder == "t3d":
        rep.check("t3d.levels", all(resolved), summary, "all 9 levels (0..8) with error <= 1 %")
    else:   # extra runs at other sigma are information only
        rep.info(f"{folder} (sigma {meta['sigma_low']:.3f} / {meta['sigma_high']:.3f} V): {summary}")
    rep.info("confusion matrix (row = true count, column = read count): " +
             " | ".join(" ".join(str(v) for v in confusion[m]) for m in range(9)))
    header = ["count", "n_mc", "t_mean_ps", "t_sigma_ps", "t_p01_ps", "t_p99_ps", "e_mean_fJ", "e_sigma_fJ",
              "p_err_emp", "p_err_gauss", "p_read_low", "p_read_high", "t_bound_fast_ps", "t_bound_slow_ps"]
    write_csv(OUT / folder / "t3d_result.csv", header, rows)
    if folder == "t3d":
        write_csv(TCAM_DIR / "char_v0.csv", header, rows)
    rep.finish()


if __name__ == "__main__":
    main()
