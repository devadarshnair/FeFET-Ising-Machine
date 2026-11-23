"""P4.08 (P4_CHECK M2): level-0 spread (cim_cell_v1 level 0, sigma 4.86 nA) applied to EVERY CiM design.

Analytic (CLT normal sums of independent cells) per-column error probabilities; two level-0 models:
'gauss' N(mu0, sigma0) and 'rect' max(0, N(mu0, sigma0)) (the P4.06 stand-in, biased positive).
Our design / B1 bit-slice: binary cells (levels 0/7, unit I7 - I0), ADC LSB = 1 cell (full resolution), column error
iff |sum error| > 0.5 cell. Sign flip: single differential plane with true field +1 cell (c+ = 1, c- = 0, all other
active cells level 0) -> P(code+ - code- <= 0). B1 3-bit: Yin 32-row tile column, levels 0..7, step 14.16 nA, error iff
|sum error| > half a step; levels 1-6 either write-verified (uniform target +-5 %) or open-loop (cim_cell_v1 sigma);
level 0 open-loop or 'verified' (same +-5 %-of-step window applied around 0). Output: docs/hw/results/P4_level0_variation.csv
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CELL = REPO / "circuit" / "cim" / "cim_cell_v1.csv"
OUT = REPO / "docs" / "hw" / "results" / "P4_level0_variation.csv"
VERIFY_TOL = 0.05                                  # write-verify window, fraction of the target / step


def _phi(z): return math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
def _Phi(z): return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def load(path=CELL) -> list[dict]:
    with open(path, newline="") as fh:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(fh)]


def level0_moments(c: list[dict], model: str) -> tuple[float, float]:
    """(bias, variance) of one level-0 cell current in nA, relative to the intended 0."""
    mu, s = c[0]["i_read_nA"], c[0]["i_sigma_nA"]
    if model == "gauss":
        return mu, s * s
    z = mu / s
    m1 = mu * _Phi(z) + s * _phi(z)
    m2 = (mu * mu + s * s) * _Phi(z) + mu * s * _phi(z)
    return m1, m2 - m1 * m1


def p_out(bias: float, var: float, half: float) -> float:
    sd = math.sqrt(var)
    if sd == 0:
        return float(abs(bias) > half)
    return 1 - (_Phi((half - bias) / sd) - _Phi((-half - bias) / sd))


def binary_rows(c, model):
    """Our design (and B1 bit-sliced, L = 32): per-column error and sign flip vs active zero cells L."""
    unit = c[7]["i_read_nA"] - c[0]["i_read_nA"]
    if model == "verified":                 # level 0 verified to |I| < VERIFY_TOL * unit (uniform), costed in the .md
        b0, v0 = 0.0, (VERIFY_TOL * unit) ** 2 / 3
    else:
        b0, v0 = level0_moments(c, model)
        b0 -= c[0]["i_read_nA"]             # trim only the nominal mean; the rect excess bias depends on L (untrimmable)
    rows = []
    for L in (16, 32, 64, 128, 256, 512, 1024):
        p_col = p_out(L * b0, L * v0, unit / 2)
        # sign flip at h = +1: column + has 1 at level 7 and L-1 zeros, column - has L zeros; flip iff round
        # error difference <= -1 cell, i.e. e+ - e- < -0.5 cell (normal difference, biases nearly cancel)
        var_d = (2 * L - 1) * v0 + c[7]["i_sigma_nA"] ** 2
        p_sign = _Phi((-unit / 2 - (-b0)) / math.sqrt(var_d))
        rows.append(dict(design="ours (binary 0/7, differential, full-res ADC)", model=model, L_active_zero=L,
                         p_column_code_error=p_col, p_field_sign_flip_h1=p_sign))
    return rows


def b1_multilevel_rows(c, model):
    step = c[1]["i_target_nA"] - c[0]["i_target_nA"]
    out = []
    for lv_mode in ("write-verify 1-6", "open-loop 1-6"):
        for l0_mode in ("open-loop", "verified"):
            for f0 in (0.125, 0.5, 0.875):
                L, n0 = 32, round(32 * f0)
                n_other = 32 - n0                      # spread evenly over levels 1..7
                bias, var = 0.0, 0.0
                if l0_mode == "open-loop":
                    b0, v0 = level0_moments(c, model)
                else:                                  # uniform +-VERIFY_TOL*step around 0 (P4_CHECK: ill-defined target)
                    b0, v0 = 0.0, (VERIFY_TOL * step) ** 2 / 3
                bias, var = n0 * b0, n0 * v0
                for lv in range(1, 8):
                    k = n_other / 7
                    if lv == 7 or lv_mode.startswith("open"):
                        s = c[lv]["i_sigma_nA"] if lv < 7 else c[7]["i_sigma_nA"]
                        var += k * s * s
                    else:
                        var += k * (VERIFY_TOL * c[lv]["i_target_nA"]) ** 2 / 3
                out.append(dict(design=f"B1 3-bit, {lv_mode}, level 0 {l0_mode}", model=model, L_active_zero=n0,
                                p_column_code_error=p_out(bias, var, step / 2), p_field_sign_flip_h1=float("nan")))
    return out


def main():
    c = load()
    rows = []
    for model in ("gauss", "rect"):
        rows += binary_rows(c, model) + b1_multilevel_rows(c, model)
    rows += binary_rows(c, "verified")
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.3e}" if isinstance(v, float) else v) for k, v in r.items()})
    for r in rows:
        print(r["design"][:42].ljust(42), r["model"], r["L_active_zero"],
              f"{r['p_column_code_error']:.2e}", f"{r['p_field_sign_flip_h1']:.2e}")


if __name__ == "__main__":
    main()
