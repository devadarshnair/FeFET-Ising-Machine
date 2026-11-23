"""Round 4: fit OpenRAM (FreePDK45, ngspice, TT 1.0 V 25 C) macro characterisations into an energy / leakage / area model of a 1rw SRAM bank,
and write docs/hw/energy_table_measured_v4_r4.csv.

Per macro (word size w, words n) OpenRAM gives the average read power over one cycle at its minimum period (lib internal_power / datasheet
"Read", mW), the leakage (mW) and the layout area (um2, netlist_only = False). Read energy per access = P_read x t_min.
Model (least squares over the characterised points; the fitted ranges are reported, extrapolation beyond 256 words is stated):
  E_access(w, n) = alpha + beta*w + gamma*w*n            fJ   (word-line / decoder; per bit; bit-line length)
  P_leak(w, n)   = lam0 + lam1*w*n                       nW
  A(w, n)        = a0 + a1*w*n                           um2
  openram_fit_r4.py WORKDIR [OUT.csv]"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CACTI = [   # CACTI 7 cross-check (run by hand, outputs ~/tools/cacti/r4_*.out): 32-bit words
    ("r4_cacti_lstp_leak_bit_nw", 4.6901e-05 * 1e6 / (2048 * 8), "nW per bit, itrs-lstp cells, 2 KB bank (32 x 512)"),
    ("r4_cacti_hp_leak_bit_nw", 1.17664 * 1e6 / (2048 * 8), "nW per bit, itrs-hp cells, 2 KB bank"),
    ("r4_cacti_lstp_e_bit_n512_fj", 0.00223182 * 1e6 / 32, "fJ per bit read, lstp, 32 x 512"),
    ("r4_cacti_hp_e_bit_n512_fj", 0.00196774 * 1e6 / 32, "fJ per bit read, hp, 32 x 512"),
    ("r4_cacti_hp_e_bit_n1024_fj", 0.00254055 * 1e6 / 32, "fJ per bit read, hp, 32 x 1024"),
    # wide word = B3's actual row read (480 couplings x 16 b = 7680 b), 480 rows x 960 B (CACTI ram, ~/tools/cacti/r4_wide_*.cfg)
    ("r4_cacti_wide_lstp_e_bit_n512_fj", 8.15434 * 1e6 / 7680, "fJ per bit read, lstp, 7680-bit row of a 480-row array (incl. H-tree / output drivers)"),
    ("r4_cacti_wide_hp_e_bit_n512_fj", 6.41024 * 1e6 / 7680, "fJ per bit read, hp, 7680-bit row (incl. H-tree / output drivers)"),
    ("r4_array_lb_e_bit_n512_fj", 0.112402 * 1e6 / 7680, "fJ per bit, ARRAY-ONLY LOWER BOUND (decoder + wordline + bit-line precharge + bit lines + sense amps, no H-tree / output drivers), lstp, 7680-bit row"),
]


def points(work: Path) -> list[dict]:
    out = []
    for d in sorted(work.glob("out_r4_w*_n*")):
        ds = d / "datasheet.info"
        lib = next(d.glob("*.lib"), None)
        if not ds.exists() or lib is None:
            continue
        f = ds.read_text().split(",")
        w, n = int(re.search(r"_w(\d+)_n(\d+)", d.name).group(1)), int(re.search(r"_n(\d+)", d.name).group(1))
        t_min = float(f[10])
        p_read = float(f[f.index("Read") + 1])
        p_leak = float(f[f.index("leak") + 2])
        area = float(re.search(r"area : ([0-9.]+)", lib.read_text()).group(1))
        out.append({"w": w, "n": n, "t_min_ns": t_min, "e_read_fj": p_read * 1e-3 * t_min * 1e-9 * 1e15, "leak_nw": p_leak * 1e6, "area_um2": area})
    return out


def fit(pts):
    w = np.array([p["w"] for p in pts], float)
    n = np.array([p["n"] for p in pts], float)
    E = np.array([p["e_read_fj"] for p in pts])
    X = np.c_[np.ones_like(w), w, w * n]
    (alpha, beta, gamma), *_ = np.linalg.lstsq(X, E, rcond=None)
    Y = np.c_[np.ones_like(w), w * n]
    (lam0, lam1), *_ = np.linalg.lstsq(Y, np.array([p["leak_nw"] for p in pts]), rcond=None)
    (a0, a1), *_ = np.linalg.lstsq(Y, np.array([p["area_um2"] for p in pts]), rcond=None)
    return dict(alpha=alpha, beta=beta, gamma=gamma, lam0=lam0, lam1=lam1, a0=a0, a1=a1)


def main(argv):
    work = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else REPO / "docs" / "hw" / "energy_table_measured_v4_r4.csv"
    pts = points(work)
    assert len(pts) >= 4, f"need >= 4 characterised macros, have {len(pts)}"
    p = fit(pts)
    src = (f"Round 4 OpenRAM {open(Path.home() / 'tools/openram/VERSION').read().strip()} FreePDK45 1rw, ngspice TT 1.0 V 25 C, layout area (no DRC/LVS); "
           f"points (w x n): {', '.join(str(q['w']) + 'x' + str(q['n']) for q in pts)}; fitted by scripts/hw_timing/openram_fit_r4.py")
    rows = [["key", "block", "kind", "unit", "value", "band_lo_x", "band_hi_x", "source", "placeholder"]]
    units = {"alpha": "fJ per access", "beta": "fJ per bit per access", "gamma": "fJ per bit per word of bit-line", "lam0": "nW per macro",
             "lam1": "nW per bit", "a0": "um2 per macro", "a1": "um2 per bit"}
    for k, v in p.items():
        rows.append([f"r4_sram_{k}", "sram", "measured-fit", units[k], f"{v:.6g}", 0.5, 2.0, src, 0])
    bank = next(q for q in pts if q["w"] == 32 and q["n"] == 64)       # the bank B3 / the table are built from (no extrapolation)
    rows.append(["r4_bank_e_read_fj", "sram", "measured", "fJ per 32-bit access of a 32x64 bank", f"{bank['e_read_fj']:.6g}", 0.5, 2.0, src, 0])
    rows.append(["r4_bank_area_um2", "sram", "measured", "um2 per 32x64 bank (layout incl. periphery)", f"{bank['area_um2']:.6g}", 0.8, 1.3, src, 0])
    rows.append(["r4_bank_bits", "sram", "def", "bits per bank", "2048", 1, 1, src, 0])
    rows.append(["r4_leak_bit_openram_nw", "sram", "measured", "nW per bit (FreePDK45 PTM nominal-Vt, OpenRAM 32x64)", f"{bank['leak_nw'] / 2048:.6g}", 1, 1, src, 0])
    for k, v, u in CACTI:
        rows.append([k, "sram", "cacti", u, f"{v:.6g}", 1, 1, "CACTI 7 (HewlettPackard/cacti master), 45 nm, ram, 32-bit block, 1 rw port, 300 K; ~/tools/cacti/r4_*.cfg", 0])
    for q in pts:
        rows.append([f"r4_pt_w{q['w']}_n{q['n']}", "sram", "measured", "e_read_fj|leak_nw|area_um2|t_min_ns",
                     f"{q['e_read_fj']:.6g}|{q['leak_nw']:.6g}|{q['area_um2']:.6g}|{q['t_min_ns']:.4g}", 1, 1, src, 0])
    with open(out, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    for q in pts:
        pred = p["alpha"] + p["beta"] * q["w"] + p["gamma"] * q["w"] * q["n"]
        print(q, f"fit E {pred:.4g}")
    print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
