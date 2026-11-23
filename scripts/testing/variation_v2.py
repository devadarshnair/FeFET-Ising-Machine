"""VARIATION_V2: physically grounded device-variation model, mitigations under one rule for every machine, and the stress harness.

Why a second model (docs/hw/results/VARIATION_V2.md, "Root cause"): the H5/H7-V model (machines.PerturbedCim, "v1") has three
magnitude/structure defects for this cell (1FeFET1R, R_S = 1 MOhm, read WL 1.2 V, char_v1 / P1.10 t4e):
  1. it applies the +-5 % multi-level write-verify band to the binary ON (level-7) cells, whose open-loop spread is 0.15 % (the
     series resistor saturates the ON current) -> a 19x too large per-cell sigma on every ON cell of ours and of B1;
  2. it adds the static cell error to the field AFTER the ADC (continuous, x 2^plane), so the integer column ADC never rounds
     a sub-half-LSB column error away: the error immunity of a binary bit-plane column with LSB = 1 cell is lost;
  3. it treats the level-0 (erased) error as zero-mean Gaussian (2.9 nA "verified" window), while the char_v1 Monte Carlo shows
     a one-sided, heavy (exponential-in-Vth) leakage tail: median 0.06 nA, mean 1.32 nA, sigma 4.86 nA, p99 33 nA.
V2 replaces the per-cell statistics by the SPICE transfer curves I_k(dVth) of every level (200 Monte Carlo samples per level of
P1.10 t4e, re-extracted to docs/hw/char/t4e_mc_samples.csv) and injects every error where it physically occurs: in the cell
current, summed per column, converted by that column's own ADC (rounding, clipping), shift-added digitally.

Error terms of one run (all drawn once per run from the run's seed, except read noise, drawn per conversion):
  D2D   static Vth shift per cell, sigma_k * sqrt(1 - C2C_SHARE) * dev        (sigma_k = 0.15 - 0.05 k/7 V, Ni 2019 SI Fig. 5)
  C2C   per-programming-attempt Vth shift, sigma_k * sqrt(C2C_SHARE) * write (redrawn on every write-verify attempt)
  read  Johnson noise of R_S per conducting cell, sqrt(4kT BW / R_S) * read   (BW = 1/(2 x 20 ns read))
  ADC   static per-column offset, N(0, MISMATCH_OFFSET_LSB * mismatch) LSB   (P1.11, 7.4 mV; same as v1)
  gain  supply x (1 + TEMPCO_GAIN (T - 25 C))                                    (parametric, same as v1)
  drift retention MW loss drift_v_dec x DRIFT_DECADES V, split +-1/2 between LVT (level 7) and HVT (level 0), linear in k
        between (parametric: the retention fit k is 0 in char_v1, so this is a sweep axis, not a prediction)

Mitigations (one rule for every CiM machine; B3 is digital and has nothing to mitigate):
  wv     write-verify. Multi-level cells: ISPP reaches the target despite D2D/C2C (one coarse pulse per ISPP_STEP_V of the
         cell's |dVth| offset, then ceil(log2(ISPP_STEP_V / window width in V)) fine pulses), residual uniform in
         |I/I_target - 1| < wv_window (the t4a / P4.06 band). Level 0: re-erase
         attempts redraw only the C2C part until I < wv_window x unit current (a full erase cannot compensate D2D). Level 7: one
         verify read. Every pulse and verify read is charged (char_v1 per-level write energy, 2.02 us + 20 ns).
  diff   complementary 2-cell coding: every cell gets a partner holding (kmax - level); the column pair is converted
         differentially and the count recovered as (D + kmax L_active)/2 (L_active known digitally). Common-mode leakage becomes
         a gain error, the error threshold doubles. Cost: 2x cells (area, read energy, programming), +1 ADC bit per conversion.
  calib  one-time per-column ADC offset/gain calibration at deployment (x = 0 and x = all-ones patterns, N_CAL reads each,
         offset trim step 1/8 LSB, gain trim step GAIN_TRIM_STEP). Does not track drift or temperature after calibration.
  binary binary cells instead of multi-level: B1 -> B1 bit-sliced (3 binary planes, its existing b1bs pricing), B2 -> unary
         binary filter cells (4x rows); ours is binary already (no-op).
  reads  R redundant conversions per column per read, median (= majority) of the R codes. Dynamic noise only. Cost: R x array and
         ADC energy and read cycles, (R-1) compare-adds per conversion, R-1 code registers per column.
Model "v1" (no Mitigation, or Mitigation(model="v1")) is the unchanged H5 PerturbedCim: bit-exact to all earlier results.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "golden"))
sys.path.insert(0, str(HERE.parent / "baselines"))
import plan as pl  # noqa: E402

if __name__ == "__main__":      # one module object: machines.py imports `variation_v2`; module state (_C2C) must be shared
    sys.modules.setdefault("variation_v2", sys.modules[__name__])

REPO = HERE.parents[1]
MC_CSV = REPO / "docs" / "hw" / "char" / "t4e_mc_samples.csv"
CELL_CSV = REPO / "circuit" / "cim" / "cim_cell_v1.csv"

# ---------------------------------------------------------------------------------------------------------- constants
N_LEVELS = 8
I_SAT_CAP_NA = 99.5             # R_S-limited ceiling (V_BL / R_S = 100 nA; max MC sample 99.37 nA)
C2C_SHARE = 0.5                 # [ASSUMPTION] share of the Ni 2019 sigma(Vth)^2 that is cycle-to-cycle (redrawn per write)
_C2C = [C2C_SHARE]              # active value (the stress harness sweeps it: c2c_share())


class c2c_share:
    """Context manager: run with a different C2C share of the sigma(Vth)^2 (sensitivity sweep)."""

    def __init__(self, share: float):
        assert 0.0 <= share <= 1.0
        self.share = share

    def __enter__(self):
        self.prev = _C2C[0]
        _C2C[0] = self.share

    def __exit__(self, *exc):
        _C2C[0] = self.prev
ISPP_STEP_V = 0.05              # [ASSUMPTION] ISPP amplitude step expressed as a Vth step (typical 25-100 mV)
WV_MAX_ATTEMPTS = 32            # verify attempts cap per cell (best attempt kept)
WV_WINDOW = 0.05                # default verify window: the t4a / P4.06 +-5 % band
K_B, T_ROOM_K, R_SERIES, T_READ_S = 1.380649e-23, 300.0, 1.0e6, 20e-9
I_THERMAL_NA = math.sqrt(4 * K_B * T_ROOM_K * (1 / (2 * T_READ_S)) / R_SERIES) * 1e9   # 0.64 nA rms per conducting cell
N_CAL = 64                      # calibration reads per pattern
OFFSET_TRIM_LSB = 1.0 / 8       # offset trim DAC step (4 bit, +-1 LSB range)
GAIN_TRIM_STEP = 0.25 / 256     # gain trim: 8-bit reference DAC over +-12.5 %
DFF_NAND2_EQ = 6.0              # [ASSUMPTION] NAND2-eq of one DFF (OSU gscl45nm DFFPOSX1 / NAND2X1 area ratio ~ 5.5-6)
CDAC_UM2_PER_UNIT = 0.5         # 1 fF unit cap / 2 fF/um2 (the a_adc_col build-up in energy_table_v1_p309.csv)


def sigma_vth(k: int) -> float:
    """Gate-referred sigma(Vth) of level k (P1.10 t4e, Ni 2019 SI Fig. 5: 0.15 V HVT, 0.10 V LVT, linear in between)."""
    return 0.15 - 0.05 * k / 7


# ---------------------------------------------------------------------------------------------------------- cell physics
class Transfer:
    """I_k(dvg): read current of a level-k cell vs its gate-referred Vth shift (positive dvg = higher Vth = less current), from the
    200 SPICE Monte Carlo samples per level (monotone, log-interpolated, log-linear extrapolation outside the sampled range, capped
    at the series-resistor limit)."""

    def __init__(self, mc_csv: Path = MC_CSV, cell_csv: Path = CELL_CSV):
        d = np.genfromtxt(mc_csv, delimiter=",", names=True)
        with open(cell_csv, newline="") as fh:
            self.cell = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(fh)]
        self.unit_bin = self.cell[7]["i_read_nA"]           # binary ON current (one cell of a binary column = 1 count)
        self.unit_ml = self.cell[1]["i_target_nA"]          # multi-level step (one count of a native column)
        self.curves = []
        for k in range(N_LEVELS):
            s = d[d["level"] == k]
            o = np.argsort(s["dvg_V"])
            g = s["dvg_V"][o]
            li = np.minimum.accumulate(np.log(np.maximum(s["i_read_nA"][o], 1e-9)))
            n = 20
            lo = np.polyfit(g[:n], li[:n], 1)[0]
            hi = np.polyfit(g[-n:], li[-n:], 1)[0]
            self.curves.append((g, li, min(lo, 0.0), min(hi, 0.0)))

    def current(self, k: int, dvg) -> np.ndarray:
        g, li, a, b = self.curves[k]
        dvg = np.asarray(dvg, float)
        y = np.interp(dvg, g, li)
        y = np.where(dvg < g[0], li[0] + a * (dvg - g[0]), y)
        y = np.where(dvg > g[-1], li[-1] + b * (dvg - g[-1]), y)
        return np.minimum(np.exp(y), I_SAT_CAP_NA)

    def dvg_at(self, k: int, i_na) -> np.ndarray:
        """Inverse of current(k, .) on a dense grid (monotone decreasing): the dvg giving read current i_na."""
        if not hasattr(self, "_inv"):
            self._inv = {}
        if k not in self._inv:
            g = np.linspace(-1.0, 1.0, 8001)
            li = np.log(self.current(k, g))
            keep = np.concatenate([[True], np.diff(li) < 0])
            self._inv[k] = (li[keep][::-1], g[keep][::-1])
        li, g = self._inv[k]
        return np.interp(np.log(np.asarray(i_na, float)), li, g)

    def target(self, k: int, binary: bool) -> float:
        if binary:
            return self.unit_bin if k else 0.0
        return k * self.unit_ml


_TRANSFER: Transfer | None = None


def transfer() -> Transfer:
    global _TRANSFER
    if _TRANSFER is None:
        _TRANSFER = Transfer()
    return _TRANSFER


@dataclass(frozen=True)
class Mitigation:
    model: str = "v1"            # v1 = legacy H5 model (bit-exact), v2 = this module's physical model
    wv: bool = False
    wv_window: float = WV_WINDOW
    diff: bool = False
    calib: bool = False
    binary: bool = False
    reads: int = 1
    ref: bool = False             # R9: one all-level-0 reference column per tile; its mean leakage per row times the column's active level-0 count is subtracted
    cal2: int = 0                 # R11: operating-point calibration, cal2 random half-density states fit a per-column leakage slope (needs cal)
    dith: bool = False            # R10: uniform +-LSB/2 dither before every conversion
    scr: float = 0.0              # leaky-zero screening (default off): level-0 cells above scr nA are retired to spares (fresh cells), up to SCR_TRIES
    lcor: int = 0                 # sparse digital leakage correction (default off): top-lcor leakiest level-0 cells per tile column measured once
                                  # (calibration time) and their excess current subtracted digitally when their row is active

    def __post_init__(self):
        assert self.model in ("v1", "v2"), self.model
        assert self.reads >= 1 and self.reads % 2 == 1, "redundant reads: odd R (median = majority)"
        if self.model == "v1":
            assert not (self.wv or self.diff or self.calib or self.binary or self.reads > 1 or self.ref or self.cal2 or self.dith), \
                "mitigations need model v2"
        assert self.cal2 == 0 or self.calib, "R11 operating-point calibration extends cal"

    @property
    def label(self) -> str:
        if self.model == "v1":
            return "v1"
        parts = [p for p, on in (("wv", self.wv), ("diff", self.diff), ("cal", self.calib), ("bin", self.binary)) if on]
        if self.wv and self.wv_window != WV_WINDOW:
            parts[0] = f"wv{self.wv_window:g}"
        if self.reads > 1:
            parts.append(f"r{self.reads}")
        parts += [p for p, on in (("ref", self.ref), (f"cal2x{self.cal2}", self.cal2), ("dith", self.dith), (f"scr{self.scr:g}", self.scr),
                                  (f"lcor{self.lcor}", self.lcor)) if on]
        return "+".join(parts) or "none"

    @classmethod
    def parse(cls, label: str) -> "Mitigation":
        if label == "v1":
            return cls()
        kw: dict = {"model": "v2"}
        for p in ([] if label == "none" else label.split("+")):
            if p.startswith("wv"):
                kw["wv"] = True
                if len(p) > 2:
                    kw["wv_window"] = float(p[2:])
            elif p == "diff":
                kw["diff"] = True
            elif p == "cal":
                kw["calib"] = True
            elif p == "bin":
                kw["binary"] = True
            elif p == "ref":
                kw["ref"] = True
            elif p.startswith("cal2x"):
                kw["cal2"] = int(p[5:])
            elif p == "dith":
                kw["dith"] = True
            elif p.startswith("scr"):
                kw["scr"] = float(p[3:])
            elif p.startswith("lcor"):
                kw["lcor"] = int(p[4:])
            elif p.startswith("r"):
                kw["reads"] = int(p[1:])
            else:
                raise ValueError(p)
        return cls(**kw)


def drift_shift(k: int, pert: pl.Perturb) -> float:
    """dVth of a level-k cell after retention loss: MW closes by drift_v_dec x DRIFT_DECADES, HVT (k=0) down, LVT (k=7) up."""
    dmw = pert.drift_v_dec * pl.DRIFT_DECADES
    return 0.5 * dmw * (2.0 * k / 7.0 - 1.0)


def program_cells(levels: np.ndarray, binary: bool, pert: pl.Perturb, mit: Mitigation, rng) -> dict:
    """Program cells holding `levels` (0..7 physical levels; binary columns use 0/7) under the D2D/C2C model and (optionally)
    write-verify. Returns analog currents (nA) at calibration time (no drift) and in operation (drift applied), plus the programming
    pulses / verify reads per level for the cost model. Ideal (pert.ideal) gives the exact target currents."""
    tr = transfer()
    levels = np.asarray(levels)
    shape = levels.shape
    lv = levels.ravel()
    i0 = np.empty(lv.size)
    i1 = np.empty(lv.size)
    pulses = np.zeros(N_LEVELS)
    verifies = np.zeros(N_LEVELS)
    counts = np.bincount(lv, minlength=N_LEVELS).astype(float)
    for k in range(N_LEVELS):
        idx = np.flatnonzero(lv == k)
        if idx.size == 0:
            continue
        tgt = tr.target(k, binary)
        if pert.ideal:
            i0[idx] = i1[idx] = tgt
            pulses[k] += idx.size
            continue
        s_d2d = sigma_vth(k) * math.sqrt(1.0 - _C2C[0]) * pert.dev
        s_c2c = sigma_vth(k) * math.sqrt(_C2C[0]) * pert.write
        d2d = s_d2d * rng.standard_normal(idx.size)
        if not mit.wv or k == 7:
            dvg = d2d + s_c2c * rng.standard_normal(idx.size)
            pulses[k] += idx.size
            verifies[k] += idx.size if (mit.wv and k == 7) else 0
        elif k == 0:                                 # re-erase: only C2C redrawn; keep the lowest-current attempt
            thr = mit.wv_window * (tr.unit_bin if binary else tr.unit_ml)
            att = s_c2c * rng.standard_normal((WV_MAX_ATTEMPTS, idx.size))
            cur = tr.current(0, d2d[None, :] + att)
            ok = cur < thr
            first = np.where(ok.any(axis=0), ok.argmax(axis=0), WV_MAX_ATTEMPTS - 1)
            best = np.where(ok.any(axis=0), first, cur.argmin(axis=0))
            dvg = d2d + att[best, np.arange(idx.size)]
            pulses[k] += float((first + 1).sum())
            verifies[k] += float((first + 1).sum())
        else:                                        # ISPP: coarse steps over |D2D + C2C|, then fine (bisection) steps
            off = d2d + s_c2c * rng.standard_normal(idx.size)
            lo, hi = tr.dvg_at(k, tgt * (1 + mit.wv_window)), tr.dvg_at(k, tgt * (1 - mit.wv_window))
            fine = max(0, math.ceil(math.log2(max(ISPP_STEP_V / max(hi - lo, 1e-6), 1.0))))
            n = 1 + np.ceil(np.abs(off) / ISPP_STEP_V) + fine
            i_res = tgt * (1 + mit.wv_window * rng.uniform(-1.0, 1.0, idx.size))     # verified: uniform in the window
            dvg = tr.dvg_at(k, i_res)
            pulses[k] += float(n.sum())
            verifies[k] += float(n.sum())
        i0[idx] = tr.current(k, dvg)
        i1[idx] = tr.current(k, dvg + drift_shift(k, pert)) if pert.drift_v_dec else i0[idx]
    return {"i_cal": i0.reshape(shape), "i_op": i1.reshape(shape), "pulses": pulses, "verifies": verifies, "counts": counts}


def program_cost(prog_stats: list[dict], verified: bool) -> dict:
    """One-time programming energy/time of all programmed cells (char_v1 per-level write energy and 2.02 us pulse, verify read =
    the level's read energy and 20 ns), serial cell-by-cell (upper bound, P1.07 fallback)."""
    tr = transfer()
    e = t = cells = 0.0
    pulses = np.zeros(N_LEVELS)
    ver = np.zeros(N_LEVELS)
    for s in prog_stats:
        pulses += s["pulses"]
        ver += s["verifies"]
        cells += s["counts"].sum()
    for k in range(N_LEVELS):
        c = tr.cell[k]
        e += pulses[k] * c["e_write_fJ"] + ver[k] * c["e_read_fJ"]
        t += pulses[k] * c["t_write_us"] + ver[k] * 0.02
    return {"e_program_fJ": e, "t_program_us": t, "cells": int(cells), "pulses_per_cell": float(pulses.sum() / max(cells, 1)),
            "pulses_by_level": [float(p) for p in pulses], "verified": verified}


# ---------------------------------------------------------------------------------------------------------- column engine
class ColumnField:
    """Analog column model of a (tiled) differential CiM array under V2 physics.

    cells: integer count-levels per (polarity, plane, lane, row): planes coding = bits (0/1, physical levels 0/7, weight 2^plane),
    native coding = |P| level 0..kmax in ONE cell (weight 1). Rows are tiled by `tile`; each (pol, plane, lane, tile) column has its
    own ADC (lsb, top) from `adc(r)`. Field h_i = sum_tiles sum_planes weight_p (code_pos - code_neg)."""

    def __init__(self, counts: np.ndarray, binary: bool, tile: int, weights: np.ndarray, pert: pl.Perturb, mit: Mitigation,
                 rng, adc, sparse: bool = False):
        tr = transfer()
        self.mit, self.pert = mit, pert
        two, npl, nl, nr = counts.shape
        self.nb = max(1, math.ceil(nr / tile))
        self.tile, self.nr, self.nl, self.npl = tile, nr, nl, npl
        pad = self.nb * tile - nr
        counts = np.pad(counts, ((0, 0), (0, 0), (0, 0), (0, pad)))
        self.kmax = 1 if binary else 7
        self.binary = binary
        unit = tr.unit_bin if binary else tr.unit_ml
        phys = counts * 7 if binary else counts
        stats = []
        p = program_cells(phys, binary, pert, mit, rng)
        stats.append(p)
        self.A_cal, self.A = p["i_cal"] / unit, p["i_op"] / unit
        self.V = counts.astype(float)
        if pad:      # padding rows hold no cells
            self.A_cal[..., nr:] = self.A[..., nr:] = 0.0
        if sparse:   # T-2: level-0 cells are not stored, so they carry no current
            self.A_cal[counts == 0] = 0.0
            self.A[counts == 0] = 0.0
        if mit.diff:
            q = program_cells(7 - phys, binary, pert, mit, rng)       # complement cell: level 7 - k (binary: ON <-> OFF)
            stats.append(q)
            self.B_cal, self.B = q["i_cal"] / unit, q["i_op"] / unit
            if pad:
                self.B_cal[..., nr:] = self.B[..., nr:] = 0.0
        self.spares = 0
        self._spare_stats = []
        self.zero_cells = int(((phys == 0) & (np.arange(counts.shape[-1]) < nr)).sum())
        if mit.scr or mit.lcor:                 # leaky-zero screening and sparse per-cell correction act on the level-0 cells of A (and B)
            self.r0 = tr.target(0, binary) / unit
            real = np.zeros(counts.shape, bool)
            real[..., :nr] = True
            self._fix_zeros("A", (phys == 0) & real, binary, pert, mit, rng, unit)
            if mit.diff:
                self._fix_zeros("B", ((7 - phys) == 0) & real, binary, pert, mit, rng, unit)
        self.K0 = (counts == self.kmax).astype(float) if mit.diff else None       # cells whose diff partner sits at level 0
        if mit.ref:                                     # R9: one level-0 reference column per tile (programmed like any cell)
            r = program_cells(np.zeros(self.nb * tile, np.int64), binary, pert, mit, rng)
            stats.append(r)
            self.R_cal, self.R = r["i_cal"] / unit, r["i_op"] / unit
            self.R_cal[nr:] = self.R[nr:] = 0.0
            self.r0 = tr.target(0, binary) / unit       # nominal level-0 current: what the ideal column already carries
        self.prog_stats = stats + self._spare_stats            # spare cells are programmed too (priced by program_cost)
        self.weights = weights.astype(np.int64)
        self.adc = adc                                   # adc(r) -> (lsb, top) for tile r (live: I7 may change it)
        self.cols = (2, npl, nl, self.nb)
        ideal = pert.ideal
        self.sig_th = 0.0 if ideal else pert.read * I_THERMAL_NA / unit
        lsb0 = np.array([adc(r)[0] for r in range(self.nb)], float)
        self.off = (0.0 if ideal else 1.0) * pert.mismatch * pl.MISMATCH_OFFSET_LSB * rng.standard_normal(self.cols) * lsb0
        self.g_cal = pert.supply
        self.g_op = pert.supply * (1.0 + pl.TEMPCO_GAIN * (pert.temp_c - 25.0))
        self.rng_read = np.random.default_rng(rng.integers(1 << 62))
        self.reset_sums()
        self.off_hat = np.zeros(self.cols)
        self.gain_hat = np.ones(self.cols)
        self.leak_hat = np.zeros(self.cols)
        if mit.calib:
            self._calibrate(lsb0)
        if mit.cal2:
            self._calibrate_oppoint(mit.cal2, rng)

    # -- sums
    def _tile_sum(self, M, x):
        return (M.reshape(*M.shape[:3], self.nb, self.tile) * x.reshape(self.nb, self.tile)).sum(-1)

    def reset_sums(self):
        self.xprev = np.zeros(self.nb * self.tile, np.int64)
        z = np.zeros(self.cols)
        self.SA, self.SB, self.S, self.NZ = z.copy(), z.copy(), z.copy(), z.copy()
        self.NK = z.copy()
        self.L = np.zeros(self.nb)
        self.SR = np.zeros(self.nb)

    def _update(self, x):
        j = np.flatnonzero(x != self.xprev)
        if j.size == 0:
            return
        if j.size > 16:
            xf = x.astype(float)
            self.SA = self._tile_sum(self.A, xf)
            self.S = self._tile_sum(self.V, xf)
            self.NZ = self._tile_sum((self.V > 0).astype(float), xf)
            if self.mit.diff:
                self.SB = self._tile_sum(self.B, xf)
                self.NK = self._tile_sum(self.K0, xf)
            if self.mit.ref:
                self.SR = (self.R * xf).reshape(self.nb, self.tile).sum(-1)
            self.L = x.reshape(self.nb, self.tile).sum(-1).astype(float)
        else:
            for jj in j:
                dx = float(x[jj] - self.xprev[jj])
                r = jj // self.tile
                self.SA[..., r] += self.A[..., jj] * dx
                self.S[..., r] += self.V[..., jj] * dx
                self.NZ[..., r] += (self.V[..., jj] > 0) * dx
                if self.mit.diff:
                    self.SB[..., r] += self.B[..., jj] * dx
                    self.NK[..., r] += self.K0[..., jj] * dx
                if self.mit.ref:
                    self.SR[r] += self.R[jj] * dx
                self.L[r] += dx
        self.xprev = x.copy()

    def _fix_zeros(self, name: str, zmask, binary, pert, mit, rng, unit) -> None:
        cal, op = getattr(self, f"{name}_cal"), getattr(self, name)
        if mit.scr:                                       # retire to a spare (a different physical cell: fresh D2D + C2C draw)
            cut = mit.scr / unit
            for _ in range(SCR_TRIES):
                bad = zmask & (cal > cut)
                nb = int(bad.sum())
                if nb == 0:
                    break
                self.spares += nb
                r = program_cells(np.zeros(nb, np.int64), binary, pert, mit, rng)
                self._spare_stats.append(r)
                cal[bad], op[bad] = r["i_cal"] / unit, r["i_op"] / unit
        if mit.lcor:                                      # measure once; subtract the excess of the top-k level-0 cells of every tile column
            ex = np.where(zmask, cal - self.r0, -np.inf).reshape(*cal.shape[:3], self.nb, self.tile)
            k = min(mit.lcor, self.tile)
            idx = np.argpartition(-ex, k - 1, axis=-1)[..., :k]
            sel = np.zeros(ex.shape, bool)
            np.put_along_axis(sel, idx, True, axis=-1)
            sel &= np.isfinite(ex) & (ex > 0)
            corr = np.where(sel, ex, 0.0).reshape(cal.shape)
            cal -= corr
            op -= corr

    def _zeff(self, NZ, NK, L):
        """Active level-0 cells of the positive column minus those of its diff partner (leakage that does not cancel)."""
        z = L - NZ
        return z - NK if self.mit.diff else z

    def _analog(self, SA, SB, NZ, L, g, R, NK=None, SR=None):
        """Analog column value(s) before calibration correction, R independent read-noise draws (shape (R,) + cols)."""
        y = g * (SA - SB) if self.mit.diff else g * SA
        if self.mit.ref and SR is not None:             # R9: subtract the reference's excess leakage per active level-0 cell
            zeff = self._zeff(NZ, NK, L)
            with np.errstate(divide="ignore", invalid="ignore"):
                excess = np.where(L > 0, SR / np.maximum(L, 1.0), 0.0) - self.r0
            y = y - g * zeff * excess
        y = y + self.off
        cond = L[None, None, None, :] * np.ones(self.cols) if self.mit.diff else NZ
        if self.sig_th > 0:
            sd = self.sig_th * np.sqrt(np.maximum(cond, 0.0) * (2.0 if self.mit.diff and not self.binary else 1.0))
            return y[None] + sd[None] * self.rng_read.standard_normal((R,) + self.cols)
        return np.broadcast_to(y, (R,) + self.cols)

    def _calibrate(self, lsb0):
        """Deployment calibration: x = 0 (offset) and x = all rows (gain), N_CAL reads each, at calibration-time cells (no drift)
        and 25 C; trims quantised to OFFSET_TRIM_LSB / GAIN_TRIM_STEP."""
        ones = np.zeros(self.nb * self.tile)
        ones[:self.nr] = 1.0
        z = np.zeros(self.cols)
        L1 = ones.reshape(self.nb, self.tile).sum(-1)
        y0 = self._analog(z, z, z, np.zeros(self.nb), self.g_cal, N_CAL, z, np.zeros(self.nb)).mean(0)
        self.off_hat = np.round(y0 / (OFFSET_TRIM_LSB * lsb0)) * (OFFSET_TRIM_LSB * lsb0)
        SA1 = self._tile_sum(self.A_cal, ones)
        SB1 = self._tile_sum(self.B_cal, ones) if self.mit.diff else z
        NZ1 = self._tile_sum((self.V > 0).astype(float), ones)
        NK1 = self._tile_sum(self.K0, ones) if self.mit.diff else z
        SR1 = (self.R_cal * ones).reshape(self.nb, self.tile).sum(-1) if self.mit.ref else None
        y1 = self._analog(SA1, SB1, NZ1, L1, self.g_cal, N_CAL, NK1, SR1).mean(0) - self.off_hat
        S1 = self._tile_sum(self.V, ones)
        expect = 2 * S1 - self.kmax * L1[None, None, None, :] if self.mit.diff else S1
        with np.errstate(divide="ignore", invalid="ignore"):
            g = np.where(np.abs(expect) > 0, y1 / expect, 1.0)
        g = np.clip(g, 0.875, 1.125)
        self.gain_hat = 1.0 + np.round((g - 1.0) / GAIN_TRIM_STEP) * GAIN_TRIM_STEP

    def _calibrate_oppoint(self, M: int, rng):
        """R11: M random half-density states at calibration-time cells, N_CAL reads each; per column, least squares (through 0) of
        the residual after offset/gain trims on the active level-0 count; slope quantised to OFFSET_TRIM_LSB / 64 per cell."""
        num, den = np.zeros(self.cols), np.zeros(self.cols)
        z = np.zeros(self.cols)
        for _ in range(M):
            x = np.zeros(self.nb * self.tile)
            x[:self.nr] = rng.integers(0, 2, self.nr)
            L = x.reshape(self.nb, self.tile).sum(-1)
            SA = self._tile_sum(self.A_cal, x)
            SB = self._tile_sum(self.B_cal, x) if self.mit.diff else z
            NZ = self._tile_sum((self.V > 0).astype(float), x)
            NK = self._tile_sum(self.K0, x) if self.mit.diff else z
            SR = (self.R_cal * x).reshape(self.nb, self.tile).sum(-1) if self.mit.ref else None
            y = (self._analog(SA, SB, NZ, L, self.g_cal, N_CAL, NK, SR).mean(0) - self.off_hat) / self.gain_hat
            S = self._tile_sum(self.V, x)
            expect = 2 * S - self.kmax * L[None, None, None, :] if self.mit.diff else S
            ze = self._zeff(NZ, NK, L[None, None, None, :])
            num += (y - expect) * ze
            den += ze * ze
        q = OFFSET_TRIM_LSB / 64.0
        self.leak_hat = np.round(np.where(den > 0, num / np.maximum(den, 1e-12), 0.0) / q) * q

    def column_codes(self, x) -> np.ndarray:
        """Counts recovered by every column ADC for state x (rows), shape cols."""
        xr = np.zeros(self.nb * self.tile, np.int64)
        xr[:self.nr] = x[:self.nr]
        self._update(xr)
        R = self.mit.reads
        y = self._analog(self.SA, self.SB, self.NZ, self.L, self.g_op, R, self.NK, self.SR)
        y = (y - self.off_hat) / self.gain_hat
        if self.mit.cal2:
            y = y - self.leak_hat * self._zeff(self.NZ, self.NK, self.L[None, None, None, :])
        if self.mit.diff:
            y = (y + self.kmax * self.L[None, None, None, None, :]) / 2.0
        codes = np.empty_like(y)
        for r in range(self.nb):
            lsb, top = self.adc(r)
            yr = y[..., r] / lsb
            if self.mit.dith:                               # R10: subtractive-free uniform dither of +-LSB/2
                yr = yr + self.rng_read.uniform(-0.5, 0.5, yr.shape)
            codes[..., r] = np.clip(np.floor(yr + 0.5), 0, top) * lsb
        return np.median(codes, axis=0) if R > 1 else codes[0]

    def field_delta(self, x) -> np.ndarray:
        c = self.column_codes(x)
        return np.einsum("p,pir->i", self.weights, c[0] - c[1])


SCR_TRIES = 3                       # leaky-zero screening: spare remaps per cell before the cell is accepted as is
OURS_TILE_ROWS: int | None = None   # R13: None = legacy one-column ours sim (H8); 256 = tiled as priced (pricing.TILE_ROWS)


class PerturbedCimV2:
    """Drop-in replacement of machines.PerturbedCim for model v2: same interface (field, last_eta, delegation), field from
    ColumnField. ours: one tile of n_pad rows (its own ADC lsb/top, live for I7), bit planes. B1: 32-row tiles, native 3-bit cells,
    or bit planes when mit.binary (B1 bit-sliced)."""

    def __init__(self, inner, machine, pert: pl.Perturb, seed_parts: tuple, n_act: int, w_bits: int, mit: Mitigation, kind: str,
                 incremental: bool = False, sparse: bool = False, refresh: int = 0):
        """incremental (T-1, ours): fields are accumulated digitally from a 1-bit sense of each cell of the flipped column (threshold at
        half the ON current; diff: A > B), so the field equals the exact field of the SENSED array: errors only where a cell's
        programmed current crosses the threshold. sparse (T-2, ours): level-0 cells are not stored (no leakage); needs no diff."""
        self.inner, self.m, self.n_act = inner, machine, n_act
        self.incremental, self.sparse = incremental and kind == "ours", sparse and kind == "ours"
        assert not (self.sparse and mit.diff), "sparse storage keeps only the 1-cells: no complement partner"
        self.last_eta = 0.0
        self.kind = kind
        P = np.asarray(machine.inst.P, np.int64)[:n_act, :n_act]
        rng = np.random.default_rng([*seed_parts, 56])
        pos, neg = np.maximum(P, 0), np.maximum(-P, 0)
        if kind == "ours" or (kind in ("b1", "b1bs") and mit.binary) or kind == "b1bs":
            planes = np.arange(w_bits)
            counts = np.stack([((pos[None] >> planes[:, None, None]) & 1), ((neg[None] >> planes[:, None, None]) & 1)])
            weights = 1 << planes
            binary = True
        else:
            counts = np.stack([pos[None], neg[None]])
            weights = np.array([1])
            binary = False
        if kind == "ours" and OURS_TILE_ROWS and n_act > OURS_TILE_ROWS:
            # R13 (B-3 / A8): the priced machine, row tiles of OURS_TILE_ROWS, each column of each tile with its own LSB-1 ADC
            # (own offset, own leakage sum, own calibration) at the worst-tile full-scale bits; partial sums added digitally.
            assert getattr(machine, "power", None) is None and getattr(inner, "lsb", 1) == 1, "tiled ours sim: LSB-1 modes only (no I7)"
            tile = OURS_TILE_ROWS
            fs_t = max(1, max(int(c.sum(-1).max(initial=0)) for r in range(0, n_act, tile) for c in counts[..., r:r + tile]))
            top_t = (1 << fs_t.bit_length()) - 1
            adc = lambda r: (1, top_t)                       # noqa: E731
        elif kind == "ours":
            tile = n_act
            adc = lambda r: (inner.lsb, inner.top)          # noqa: E731  (live: I7 switches bits)
        else:
            import yin_mesa as b1
            tile = b1.TILE
            tiles = inner.tiles
            if binary:
                adc = lambda r: (tiles[r].lsb, tiles[r].top)   # noqa: E731
            else:
                fsn = [max(1, int(pos[:, r * tile:(r + 1) * tile].sum(1).max(initial=0)),
                           int(neg[:, r * tile:(r + 1) * tile].sum(1).max(initial=0))) for r in range(math.ceil(n_act / tile))]
                fs_mode = bool(getattr(tiles[0].cfg, "fs", 0))
                tops = [((1 << f.bit_length()) - 1) if fs_mode else (1 << inner.adc_bits) - 1 for f in fsn]
                adc = lambda r: (1, tops[r])                 # noqa: E731
        self.cf = ColumnField(counts, binary, tile, weights, pert, mit, rng, adc, sparse=self.sparse)
        self.binary = binary
        self.P_sensed = None
        if self.incremental:
            cf = self.cf
            on = (cf.A > 0.5 * cf.kmax) if not mit.diff else (cf.A > cf.B)
            bits = on[..., :cf.nr].astype(np.int64)                     # (pol, plane, lane, row)
            self.P_sensed = np.einsum("p,pir->ir", cf.weights, bits[0] - bits[1])
        self.refresh = int(refresh) if self.incremental else 0
        if self.refresh:                 # register-accumulated field: per-update 1-bit sense with read noise; full column read every `refresh` reads
            self.h_reg = None
            self.x_reg = None
            self.n_reads = 0
            self.refreshes = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def _sense_cols(self, js) -> np.ndarray:
        """1-bit sense of the cells of rows js (fresh thermal read noise each time): weighted signed bits, shape (lanes, len(js))."""
        cf = self.cf
        A = cf.A[..., js]
        noise = cf.sig_th * cf.rng_read.standard_normal(A.shape) if cf.sig_th > 0 else 0.0
        on = (A + noise > 0.5 * cf.kmax) if not cf.mit.diff else (A + noise > cf.B[..., js])
        b = on.astype(np.int64)
        return np.einsum("p,pij->ij", cf.weights, b[0] - b[1])

    def _field_reg(self, x) -> np.ndarray:
        self.n_reads += 1
        if self.h_reg is None or self.n_reads % self.refresh == 0:     # full refresh through the column ADC path (exact up to its own error)
            self.h_reg = np.rint(self.cf.field_delta(x)).astype(np.int64)
            self.x_reg = x.copy()
            self.refreshes += 1
            return self.h_reg
        js = np.flatnonzero(x != self.x_reg)
        if js.size:
            sgn = np.where(x[js] == 1, 1, -1)
            self.h_reg = self.h_reg + self._sense_cols(js) @ sgn
            self.x_reg = x.copy()
        return self.h_reg

    def field(self, x):
        out = self.inner.d.copy() if self.kind != "ours" else np.asarray(self.inner.d, np.int64).copy()
        out = out.astype(np.int64)
        if self.refresh:
            out[:self.n_act] = out[:self.n_act] + self._field_reg(np.asarray(x, np.int64)[:self.n_act])
        elif self.P_sensed is not None:
            out[:self.n_act] = out[:self.n_act] + self.P_sensed @ np.asarray(x, np.int64)[:self.n_act]
        else:
            out[:self.n_act] = out[:self.n_act] + np.rint(self.cf.field_delta(np.asarray(x)[:self.n_act])).astype(np.int64)
        e = out - self.m.h
        self.last_eta = float(np.asarray(x) @ e) / 2.0
        return out

    @property
    def prog_stats(self):
        return self.cf.prog_stats


# ---------------------------------------------------------------------------------------------------------- B2 (HyCiM filter)
QKP_REL = Path("09_next_phase/benchmarks/qkp_billionnet_soutif")
OPTIMA_REL = Path("09_next_phase/items_work/09/optima.json")


def _qkp_roots() -> list[Path]:
    """Candidate project roots holding 09_next_phase: $HW_PROJECT_ROOT, the ancestors of this checkout, and the ancestors of
    the main repository (git common dir), so a detached worktree anywhere on disk finds the shared benchmark data."""
    roots = [Path(os.environ["HW_PROJECT_ROOT"])] if os.environ.get("HW_PROJECT_ROOT") else []
    roots += list(REPO.parents)
    try:
        import subprocess
        common = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        if common:
            roots += list(Path(common).parents)
    except (OSError, subprocess.SubprocessError):
        pass
    return roots


def hycim():
    """hycim with QKP_DIR / OPTIMA resolved independently of where this checkout lives ($HW_QKP_DIR / $HW_QKP_OPTIMA
    override). Returns the module; qkp_available() tells whether the data were found."""
    import hycim as hc
    if os.environ.get("HW_QKP_DIR"):
        hc.QKP_DIR = Path(os.environ["HW_QKP_DIR"])
    if os.environ.get("HW_QKP_OPTIMA"):
        hc.OPTIMA = Path(os.environ["HW_QKP_OPTIMA"])
    if not (hc.QKP_DIR.is_dir() and hc.OPTIMA.is_file()):
        for r in _qkp_roots():
            if (r / QKP_REL).is_dir() and (r / OPTIMA_REL).is_file():
                hc.QKP_DIR, hc.OPTIMA = r / QKP_REL, r / OPTIMA_REL
                break
    return hc


def qkp_available() -> bool:
    hc = hycim()
    return hc.QKP_DIR.is_dir() and hc.OPTIMA.is_file()
def b2_filter_v2(inst, pert: pl.Perturb, mit: Mitigation, rng, x_typ) -> dict:
    """V2 HyCiM filter: per-cell currents of the weight array (ROWS x n) and the replica (ROWS x COLS) under the same physics and
    mitigations, collapsed to effective weights / capacity in count units (accept iff x.w_eff < cref + noise, ideal: x.w <= C).
    binary: unary binary cells (weight w = w ON cells of 4 x ROWS rows; capacity C = C ON replica cells). diff: complementary partner
    cells, recovered as (sum(A - B) + kmax rows)/2 with the kmax-rows term supplied by a digital-count current DAC (ideal)."""
    import hycim_b2 as hb2
    tr = transfer()
    if mit.binary:
        rows = hb2.ROWS * hb2.MAXD
        wl = np.stack([(np.arange(rows) < w).astype(np.int64) for w in inst.w], axis=1)
        rl = (np.arange(rows * hb2.COLS) < inst.C).astype(np.int64)
        phys_w, phys_r, unit, kmax = wl * 7, rl * 7, tr.unit_bin, 1
    else:
        f = hb2.Filter.build(inst)
        wl, rl = f.weight_levels, f.replica_levels
        phys_w, phys_r, unit, kmax = wl, rl, tr.unit_ml, 7
    stats = []
    pw, pr_ = program_cells(phys_w, mit.binary, pert, mit, rng), program_cells(phys_r, mit.binary, pert, mit, rng)
    stats += [pw, pr_]
    wcol = pw["i_op"].sum(axis=0) / unit
    cref = pr_["i_op"].sum() / unit
    if mit.diff:
        qw, qr = program_cells(7 - phys_w, mit.binary, pert, mit, rng), program_cells(7 - phys_r, mit.binary, pert, mit, rng)
        stats += [qw, qr]
        wcol = (wcol - qw["i_op"].sum(axis=0) / unit + kmax * wl.shape[0]) / 2.0
        cref = (cref - qr["i_op"].sum() / unit + kmax * rl.size) / 2.0
    sel = np.asarray(x_typ, bool)
    cond = float((wl[:, sel] > 0).sum() + (rl > 0).sum()) * (2.0 if mit.diff else 1.0)
    sig = 0.0 if pert.ideal else pert.read * I_THERMAL_NA / unit * math.sqrt(cond)
    off = 0.0 if pert.ideal else pert.mismatch * pl.MISMATCH_OFFSET_LSB * float(rng.standard_normal())
    if mit.calib:                                    # comparator offset trim at deployment (1/8-unit step)
        off -= round(off / OFFSET_TRIM_LSB) * OFFSET_TRIM_LSB
    return {"w_eff": wcol, "cref": cref + 0.5 + off, "sigma": sig / (2.0 if mit.diff else 1.0), "stats": stats}


def run_b2_v2(spec: pl.Spec, mit: Mitigation, cost=None) -> dict:
    """drive_b2 with the V2 filter (unchanged hycim kernel stepped per proposal; the R redundant comparisons are the majority
    decision = threshold at the median of R noisy thresholds). Reports the best TRULY feasible profit and false accepts."""
    hc = hycim()
    import machines as mc
    import pricing as prc
    from cost_model import CostModel
    cost = cost or CostModel()
    cfgd = spec.cfg
    inst = hc.load(spec.instance)
    idx = hc.INSTANCES.index(spec.instance)
    sch = pl.B2_SCHEDULES.index(cfgd["sched"])
    L = spec.proposals
    t0 = time.time()
    T = hc.temps(cfgd["sched"], hc.t0_for(inst, "filter", cfgd["sched"], hc.seed_of(idx, 0, sch, 99)), L)
    x0, y0 = hc.initial_state(inst, "filter", hc.seed_of(idx, 0, 0, spec.r))
    seed = hc.seed_of(idx, 0, sch, spec.r, L)
    pswap = hc.PSWAP_V3 if cfgd["pswap"] else 0.0
    pert = pl.Perturb(**spec.pert)
    rng_p = np.random.default_rng([pl.BASE_SEED, 4, idx, spec.r, 78])
    x_typ = hc.feasible_random(inst, np.random.default_rng(hc.seed_of(406, 9)))
    flt = b2_filter_v2(inst, pert, mit, rng_p, x_typ)
    w_eff = np.rint(flt["w_eff"] * mc.B2_UNIT).astype(inst.w.dtype)
    rng = np.random.default_rng(seed)
    rng_i = rng.integers(0, inst.n, size=L).astype(np.int64)
    rng_u = rng.random(L)
    rng_j = rng.integers(0, inst.n, size=L).astype(np.int64)
    rng_m = rng.random(L)
    noise = flt["sigma"] * rng_p.standard_normal((mit.reads, L))
    noise = np.median(noise, axis=0) if mit.reads > 1 else noise[0]
    x, y = x0.copy(), y0.copy()
    best = float(inst.profit(x)) if int(inst.w @ x) <= inst.C else -1.0
    rej, bad, prev = 0, 0, x.tobytes()
    for t in range(L):
        c_eff = int(math.floor((flt["cref"] + noise[t]) * mc.B2_UNIT - 1e-9))
        _, r, _, _ = hc._run(hc.A_FILTER, inst.p, inst.off, w_eff, c_eff, T[t:t + 1], x, y, rng_u[t:t + 1], rng_i[t:t + 1],
                             rng_j[t:t + 1], rng_m[t:t + 1], float(pswap), hc.ALPHA, hc.BETA)
        rej += int(r)
        key = x.tobytes()
        if key == prev:
            continue
        prev = key
        if int(inst.w @ x) <= inst.C:
            best = max(best, float(inst.profit(x)))
        else:
            bad += 1
    pb = prc.price_b2(spec.instance, L, [int(v) for v in x_typ], mit.wv, cost)
    opt = json.loads(hc.OPTIMA.read_text())["instances"][spec.instance]["value"]
    return {"desc": {"kind": "b2", "n_act": inst.n, "x_typ": [int(v) for v in x_typ]}, "steps": L, "best_profit": best,
            "opt": opt, "success": best >= pl.QKP_TARGET_FRAC * opt, "rejected": rej, "false_accept_states": bad,
            "wall_s": round(time.time() - t0, 2), "price": {k: pb[k] for k in ("e_total", "blocks", "time_ns", "a_total", "area")},
            "prog_v2": program_cost(flt["stats"], mit.wv), "mit": mit.label}


# ---------------------------------------------------------------------------------------------------------- cost of mitigations
def b2_filter_energy_binary(inst, x_typ, cost) -> float:
    """One B2 filter decision with unary binary cells (4 x ROWS rows, levels 0/7): read energies of char_v1 levels 0/7."""
    import hycim_b2 as hb2
    tr = transfer()
    rows = hb2.ROWS * hb2.MAXD
    e = {k: tr.cell[k]["e_read_fJ"] for k in (0, 7)}
    e_wl = {k: tr.cell[k]["e_read_wl_fJ"] for k in (0, 7)}
    sel = np.asarray(x_typ, bool)
    on = np.array([min(int(w), rows) for w in inst.w])
    e_sel = float((on[sel] * e[7] + (rows - on[sel]) * e[0]).sum())
    e_uns = float((on[~sel] * e_wl[7] + (rows - on[~sel]) * e_wl[0]).sum())
    rep_on = int(inst.C)
    e_rep = rep_on * e[7] + (rows * hb2.COLS - rep_on) * e[0]
    return e_sel + e_uns + e_rep + hb2.comparator_fj()


def calib_cost(cost, cols: float, bits: int, conversions: float, cells_per_col: float) -> dict:
    """ONE calibration rule for every analog converter (ours/B1 column ADCs, B2 filter comparators): per converter a 4-bit
    offset trim DAC + 8-bit reference trim DAC (12 DFF, 16 + 256 unit caps); deployment = 2 patterns x N_CAL conversions per
    converter (conversions run in parallel across converters), the all-ones pattern reads every cell of the converter's input;
    runtime = reference-DAC switching of about one conversion-bit per conversion."""
    v = cost.v
    return {"run_fJ": conversions * v("e_adc_conv_bit"),
            "area_um2": cols * ((4 + 8) * DFF_NAND2_EQ * v("a_nand2") + (16 + 256) * CDAC_UM2_PER_UNIT),
            "once_fJ": cols * (2 * N_CAL * bits * v("e_adc_conv_bit") + N_CAL * cells_per_col * v("e_array_cell_read")),
            "once_us": 2 * N_CAL * (1 + bits) * v("t_clk") / 1000.0}


def mitigation_cost(rec: dict, mit: Mitigation, cost) -> dict:
    """Runtime and one-time overheads of `mit` for one priced record, ONE rule for every machine (blocks/area from the record's own
    price, so each machine pays its own array/ADC energies). Returns dict(e_run_fJ, d_run_fJ, t_run_ns, d_area_um2, e_once_fJ,
    t_once_us, items). B3 has no analog array: zero overhead."""
    v = cost.v
    pr_ = rec["price"]
    blk, area = pr_["blocks"], pr_["area"]
    kind = rec["desc"]["kind"]
    out = {"d_run_fJ": 0.0, "d_time_ns": 0.0, "d_area_um2": 0.0, "e_once_fJ": 0.0, "t_once_us": 0.0, "items": {}}
    prog = rec.get("prog_v2")
    if prog:
        out["e_once_fJ"] += prog["e_program_fJ"]
        out["t_once_us"] += prog["t_program_us"]
        out["items"]["program_fJ"] = prog["e_program_fJ"]
    if kind == "b3":
        pass
    elif kind == "b2":
        hc = hycim()
        import hycim_b2 as hb2
        inst = hc.load(rec["spec"]["instance"])
        L = rec["steps"]
        x_typ = rec["desc"]["x_typ"]
        f_base = blk["filter"]
        f = f_base
        if mit.binary:
            f = L * b2_filter_energy_binary(inst, x_typ, cost)
            out["d_area_um2"] += (hb2.MAXD - 1) * (inst.n * hb2.ROWS + hb2.ROWS * hb2.COLS) * v("a_array_cell")
        if mit.diff:
            out["d_area_um2"] += (hb2.MAXD if mit.binary else 1) * (inst.n * hb2.ROWS + hb2.ROWS * hb2.COLS) * v("a_array_cell")
            f = 2 * f
        f *= mit.reads
        out["items"]["filter_fJ"] = f - f_base
        out["d_run_fJ"] += f - f_base
        if mit.reads > 1:
            out["d_time_ns"] += (mit.reads - 1) * L * v("t_clk")
        if mit.calib:                                  # same rule as ours/B1: one trimmed converter per filter tile
            tiles = math.ceil(inst.n / hb2.COLS)
            cells = inst.n * hb2.ROWS * (hb2.MAXD if mit.binary else 1) + hb2.ROWS * hb2.COLS * (hb2.MAXD if mit.binary else 1)
            cc = calib_cost(cost, cols=tiles, bits=hb2.CMP_BITS, conversions=mit.reads * L * tiles, cells_per_col=cells)
            out["d_run_fJ"] += cc["run_fJ"]
            out["e_once_fJ"] += cc["once_fJ"]
            out["t_once_us"] += cc["once_us"]
            out["d_area_um2"] += cc["area_um2"]
            out["items"]["calib_fJ"] = cc["run_fJ"]
    else:
        c = rec.get("counters", {})
        reads = c.get("array_reads", 0)
        bits = rec["desc"].get("adc_bits_fs", rec["desc"].get("adc_bits", 8))
        e_arr, e_adc = blk["array"], blk["adc"]
        conv = e_adc / (v("e_adc_conv_bit") * max(bits, 1))
        cols = area["adc"] / v("a_adc_col")
        R = mit.reads
        d = 0.0
        if mit.diff:
            d += e_arr * R + e_adc * R / max(bits, 1)              # partner cell read, +1 SAR bit per conversion
            out["d_area_um2"] += area["array"] + 0.3 * area["adc"]     # 2x cells; C-DAC doubles (128 of 430 um2 per column ADC)
            out["d_time_ns"] += R * reads * v("t_clk")
        d += (R - 1) * (e_arr + e_adc) + (R - 1) * conv * v("e_add")
        out["d_time_ns"] += (R - 1) * reads * (1 + bits) * v("t_clk")
        if R > 1:
            out["d_area_um2"] += cols * (R - 1) * bits * DFF_NAND2_EQ * v("a_nand2")
        if mit.calib:
            rows = 32 if kind in ("b1", "b1bs") else rec["desc"].get("n_act", 0)    # rows per converted column (tile height)
            cc = calib_cost(cost, cols=cols, bits=bits, conversions=R * conv, cells_per_col=rows * (2 if mit.diff else 1))
            d += cc["run_fJ"]
            out["d_area_um2"] += cc["area_um2"]
            out["e_once_fJ"] += cc["once_fJ"]
            out["t_once_us"] += cc["once_us"]
        tiles = max(1, int(pr_.get("tiles", 1)))
        if mit.ref:                                    # R9: +1 reference column per tile (cells + ADC), one multiply-add per conversion
            f_ref = tiles / max(cols, 1.0)
            d += R * f_ref * (e_arr + e_adc) + R * conv * v("e_add")
            out["d_area_um2"] += f_ref * (area["array"] + area["adc"])
            out["items"]["ref_fJ"] = R * f_ref * (e_arr + e_adc) + R * conv * v("e_add")
        if mit.cal2:                                   # R11: per-column slope register + one multiply-add per conversion; M x N_CAL reads once
            d += R * conv * v("e_add")
            out["d_area_um2"] += cols * 8 * DFF_NAND2_EQ * v("a_nand2")
            per_read = (e_arr + e_adc) / max(reads, 1)
            out["e_once_fJ"] += mit.cal2 * N_CAL * per_read
            out["t_once_us"] += mit.cal2 * N_CAL * (1 + bits) * v("t_clk") * 1e-3
            out["items"]["cal2_once_fJ"] = mit.cal2 * N_CAL * per_read
        if mit.scr:                                    # screening: one verify read per level-0 cell once; spares (programming priced in prog_v2)
            zc = float(rec.get("zero_cells", 0))
            sp = float(rec.get("spares", 0))
            cells_all = area["array"] / v("a_array_cell") if area.get("array") else 0.0
            out["e_once_fJ"] += zc * v("e_array_cell_read")
            out["t_once_us"] += zc * v("t_clk") * 1e-3 / max(cols, 1.0)
            spare_rows = 0.02 * cells_all                                       # 2 % spare cells provisioned (review: 1-3 %)
            idx = max(1, math.ceil(math.log2(max(cells_all, 2))))
            out["d_area_um2"] += spare_rows * v("a_array_cell") + sp * idx * DFF_NAND2_EQ * v("a_nand2")   # spares + remap table (estimate)
            out["items"]["scr_once_fJ"] = zc * v("e_array_cell_read")
            out["items"]["spares"] = sp
        if mit.lcor:                                   # sparse correction: k (index, 8-bit value) entries per column; k/2 active adds per conversion
            rows_t = 32 if kind in ("b1", "b1bs") else min(rec["desc"].get("n_act", 1), rec["desc"].get("sim_tile_rows") or 10**9)
            bits_e = math.ceil(math.log2(max(rows_t, 2))) + 8
            out["d_area_um2"] += cols * mit.lcor * bits_e * DFF_NAND2_EQ * v("a_nand2")
            d += R * conv * 0.5 * mit.lcor * 0.5 * v("e_add")
            out["items"]["lcor_fJ"] = R * conv * 0.5 * mit.lcor * 0.5 * v("e_add")
        if mit.dith:                                   # R10: one RNG bit per conversion (32-bit draws) + one C-DAC LSB cap per ADC
            d += R * conv * v("e_rng_draw") / 32.0
            out["d_area_um2"] += 0.02 * area["adc"]
            out["items"]["dith_fJ"] = R * conv * v("e_rng_draw") / 32.0
        out["items"]["runtime_fJ"] = d
        out["d_run_fJ"] += d
    tot = pr_["time_ns"]
    leak_rate = blk.get("leakage", 0.0) / tot if tot else 0.0
    out["d_run_fJ"] += leak_rate * out["d_time_ns"]
    out["e_run_fJ"] = pr_["e_total"] + out["d_run_fJ"]
    out["overhead_pct"] = 100.0 * out["d_run_fJ"] / pr_["e_total"] if pr_["e_total"] else 0.0
    return out


# ---------------------------------------------------------------------------------------------------------- stress harness
SMOKE_OUT = REPO / "sim" / "out" / "hw" / "variation_v2"
RESULTS = REPO / "docs" / "hw" / "results" / "variation_v2"
REF_JSON = REPO / "docs" / "hw" / "char" / "vmc_reference.json"
SEED_TAG = 8                                 # Spec.tag: stream disjoint from Stages 2-4 (0, 6, 7)
SWEEPS = 150
SMOKE_INST = {"col3p": "501", "p3n240": "801", "vmc120": "1", "vmc240": "1"}
QKP_INST = ("jeu_100_25_1.txt", "jeu_100_50_1.txt")
B2_PROPOSALS = 10_000
MACHINE_ARMS = {"ours": ("ours.kc2.fs.i11", "ours.kc2.i10.i11"), "b1": ("b1.none.fs", "b1.none"), "b3": ("b3.b3", "b3.b3"),
                "ours_i7v2": ("ours.kc2.i7v2.i11", "ours.kc2.i10.i11")}     # I7v2: same algorithm config, ADC b_hi/b_lo switching
K_GRID = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)
FULL_COMBOS = ("v1", "none", "wv", "diff", "cal", "r3", "wv+diff", "wv+cal", "diff+cal", "wv+diff+cal", "wv+diff+cal+r3")
CURVE_COMBOS = ("v1", "none", "wv", "wv+diff+cal", "wv+diff+cal+r3")
BIN_COMBOS = ("bin", "wv+bin", "wv+diff+cal+bin")      # B1 / B2 only (ours is binary already)
DRIFT_GRID = (0.005, 0.01, 0.02, 0.05)
DRIFT_COMBOS = ("none", "wv+diff+cal")
TERM_POINTS = {"t_d2d": dict(write=0.0, read=0.0, mismatch=0.0), "t_c2c": dict(dev=0.0, read=0.0, mismatch=0.0),
               "t_read": dict(dev=0.0, write=0.0, mismatch=0.0), "t_mism": dict(dev=0.0, write=0.0, read=0.0)}
TERM_COMBOS = ("v1", "none", "wv")
SMOKE_SEEDS = 5


def vx(k: float) -> pl.Perturb:
    """All stochastic terms (D2D, C2C, read, ADC offset) at k x nominal; k = 0 is the ideal device."""
    return pl.Perturb(f"vx{k:g}", dev=k, write=k, read=k, mismatch=k, ideal=k == 0)


def point(pid: str) -> pl.Perturb:
    if pid.startswith("vx"):
        return vx(float(pid[2:]))
    if pid.startswith("drift"):
        return pl.Perturb(pid, drift_v_dec=float(pid[5:]))
    if pid in TERM_POINTS:
        return pl.Perturb(pid, **TERM_POINTS[pid])
    raise ValueError(pid)


def grid(machine: str, seeds: int = SMOKE_SEEDS) -> list[dict]:
    """Every (family, point, mitigation, seed) cell of the smoke for one machine. B3: one ideal-equivalent run per instance/seed
    (no analog array; variation and mitigations do not apply)."""
    jobs = []
    fams = list(QKP_INST) if machine == "b2" else list(SMOKE_INST)
    for fam in fams:
        cells = []
        if machine == "b3":
            cells = [("vx0", "none")]
        else:
            extra = BIN_COMBOS if machine in ("b1", "b2") else ()
            for k in K_GRID:
                if k == 0:
                    cells.append(("vx0", "none"))
                elif k == 1:
                    cells += [("vx1", m) for m in FULL_COMBOS + extra]
                else:
                    cells += [(f"vx{k:g}", m) for m in CURVE_COMBOS + extra[-1:]]
            cells += [(f"drift{d:g}", m) for d in DRIFT_GRID for m in DRIFT_COMBOS]
            if fam in ("p3n240", "vmc240", QKP_INST[0]):
                cells += [(t, m) for t in TERM_POINTS for m in TERM_COMBOS]
        for pid, m in cells:
            for r in range(seeds):
                jobs.append({"machine": machine, "family": fam, "point": pid, "mit": m, "r": r})
    return jobs


def job_key(j: dict) -> str:
    k = f"{j['machine']}|{j['family']}|{j['point']}|{j['mit']}|{j['r']}"
    if "inst" in j:
        k += f"|i{j['inst']}"
    if j.get("c2c", C2C_SHARE) != C2C_SHARE:
        k += f"|c2c{j['c2c']:g}"
    return k


# ---------------------------------------------------------------------------------------------------------- statistical grid
# Review fix list (VARIATION_V2.md "Internal review verdict"): decision points k = 1 and k = 3 at >= 20 seeds x 3 instances per
# family (Wilson CIs, Newcombe non-inferiority selection), B2 at 1e5 proposals, C2C-share sensitivity, I7v2 arm.
STAT_OUT = REPO / "sim" / "out" / "hw" / "variation_v2b"
STAT_RESULTS = REPO / "docs" / "hw" / "results" / "variation_v2b"
STAT_INST = {"col3p": ("501", "502", "503"), "p3n240": ("801", "802", "803"), "vmc120": ("1", "2", "3"), "vmc240": ("1", "2", "3")}
STAT_QKP = ("jeu_100_25_1.txt", "jeu_100_50_1.txt", "jeu_100_75_1.txt")
STAT_B2_PROPOSALS = 100_000
DEC_SEEDS, CURVE_SEEDS, C2C_SEEDS, B2_SEEDS = 20, 5, 10, 10
DEC_K3 = ("wv+diff+cal", "wv+diff+cal+r3")
C2C_GRID = (0.0, 0.25, 0.5, 0.75)
C2C_COMBOS = ("wv", "wv+diff+cal")
C2C_FAMILIES = ("p3n240", "vmc240")


def grid_stat(machine: str) -> list[dict]:
    """Statistical grid. CiM machines (ours, b1): ideal + every combination at k = 1 and the full-mitigation combinations at
    k = 3, 20 seeds x 3 instances per family; success curves at k = 0.5/1.5/2 (5 seeds); C2C-share sweep (10 seeds, two 240-spin
    families). ours_i7v2: none and wv+diff+cal over the whole k grid (k = 1 at 20 seeds). B2: 1e5 proposals, 3 QKP instances,
    10 seeds. B3: ideal-equivalent, 20 seeds x 3 instances."""
    cells = []                                                   # (family, inst, point, mit, seeds, c2c)

    def add(fams, insts, pids, mits, seeds, c2c=C2C_SHARE):
        for f in fams:
            for i in insts(f):
                for pid in pids:
                    for m in mits:
                        cells.append((f, i, pid, m, seeds, c2c))
    if machine == "b2":
        fams, insts = ["qkp"], (lambda f: STAT_QKP)
    else:
        fams, insts = list(STAT_INST), (lambda f: STAT_INST[f])
    extra = BIN_COMBOS if machine in ("b1", "b2") else ()
    if machine == "b3":
        add(fams, insts, ["vx0"], ["none"], DEC_SEEDS)
    elif machine == "ours_i7v2":
        add(fams, insts, ["vx0"], ["none"], DEC_SEEDS)
        add(fams, insts, ["vx1"], ["none", "wv+diff+cal"], DEC_SEEDS)
        add(fams, insts, [f"vx{k:g}" for k in K_GRID if k not in (0, 1)], ["none", "wv+diff+cal"], CURVE_SEEDS)
    elif machine == "b2":
        add(fams, insts, ["vx0"], ["none"], B2_SEEDS)
        add(fams, insts, ["vx1"], FULL_COMBOS + extra, B2_SEEDS)
        add(fams, insts, ["vx2"], ("v1", "none", "wv", "wv+cal"), B2_SEEDS)
        add(fams, insts, ["vx3"], DEC_K3 + extra[-1:], B2_SEEDS)
        for c in C2C_GRID:
            add(fams, insts, ["vx1", "vx2"], C2C_COMBOS, B2_SEEDS, c)
    else:
        add(fams, insts, ["vx0"], ["none"], DEC_SEEDS)
        add(fams, insts, ["vx1"], FULL_COMBOS + extra, DEC_SEEDS)
        add(fams, insts, ["vx3"], DEC_K3 + extra[-1:], DEC_SEEDS)
        add(fams, insts, ["vx0.5", "vx1.5", "vx2"], CURVE_COMBOS + extra[-1:], CURVE_SEEDS)
        for c in C2C_GRID:
            add(C2C_FAMILIES, insts, ["vx1", "vx2"], C2C_COMBOS, C2C_SEEDS, c)
    jobs, seen = [], set()
    for f, i, pid, m, seeds, c2c in cells:
        for r in range(seeds):
            j = {"machine": machine, "family": f, "inst": i, "point": pid, "mit": m, "r": r, "c2c": c2c}
            if machine == "b2":
                j["proposals"] = STAT_B2_PROPOSALS
            k = job_key(j)
            if k not in seen:
                seen.add(k)
                jobs.append(j)
    return jobs


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95 % interval of a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def newcombe_diff(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """p1 - p2 with the Newcombe (1998, method 10) hybrid-score 95 % interval from the two Wilson intervals."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def _tuned():
    return json.loads((REPO / "docs" / "hw" / "results" / "stage2_eval" / "tuned.json").read_text())["tuned"]


def vmc_reference(family: str, key: str) -> int:
    """Reference cut of a small smoke Max-Cut (cached): best of dwave-samplers SA, 200 reads x 20000 sweeps (>130x the machines'
    budget). Success = cut >= MAXCUT_TARGET_FRAC x reference (H2 rule)."""
    ref = json.loads(REF_JSON.read_text()) if REF_JSON.exists() else {}
    k = f"{family}/{key}"
    if k not in ref:
        import machines as mc
        from dwave.samplers import SimulatedAnnealingSampler
        mq = mc.mapped(family, key)
        Q = {}
        n = mq.spins
        P = np.asarray(mq.P, float)
        d = np.asarray(mq.d, float)
        for i in range(n):
            Q[(i, i)] = d[i]
            for j in range(i + 1, n):
                if P[i, j]:
                    Q[(i, j)] = P[i, j]
        ss = SimulatedAnnealingSampler().sample_qubo(Q, num_reads=200, num_sweeps=20000, seed=11)
        best = min(float(mq.energy(np.array([ss.first.sample[i] for i in range(n)]))), float(ss.first.energy + mq.offset))
        ref[k] = int(round(-best))
        REF_JSON.write_text(json.dumps(ref, indent=1, sort_keys=True) + "\n")
    return ref[k]


def run_job(j: dict, cost=None) -> dict:
    from cost_model import CostModel
    cost = cost or CostModel()
    with c2c_share(j.get("c2c", C2C_SHARE)):
        return _run_job(j, cost)


def _run_job(j: dict, cost) -> dict:
    import machines as mc
    mit = Mitigation.parse(j["mit"])
    pert = point(j["point"])
    if j["machine"] == "b2":
        props = j.get("proposals", B2_PROPOSALS)
        cfg = _tuned()["qkp"][f"b2.b2@{props}"]
        qinst = j.get("inst", j["family"])
        sp = pl.Spec(study="var2", phase="smoke", family="qkp", instance=qinst, r=j["r"], arm="b2.b2", cfg=cfg, sweeps=0,
                     pert=pert.as_dict(), proposals=props, tag=SEED_TAG)
        if mit.model == "v1":
            rec = mc.drive_b2(sp, cost)
            rec["spec"] = dataclasses.asdict(sp)
            hc = hycim()
            opt = json.loads(hc.OPTIMA.read_text())["instances"][qinst]["value"]
            rec.update(opt=opt, success=rec["best_profit"] >= pl.QKP_TARGET_FRAC * opt, mit="v1")
        else:
            rec = run_b2_v2(sp, mit, cost)
            rec["spec"] = dataclasses.asdict(sp)
        quality = rec["best_profit"] / rec["opt"]
    else:
        fam = j["family"]
        key = j.get("inst", SMOKE_INST.get(fam))
        arm, tkey = MACHINE_ARMS[j["machine"]]
        if j["machine"] == "b1" and mit.binary:
            arm = "b1bs.none.fs"
        tuned = _tuned()["maxcut" if fam.startswith("vmc") else "colouring"]
        sp = pl.Spec(study="var2", phase="smoke", family=fam, instance=key, r=j["r"], arm=arm, cfg=tuned[tkey], sweeps=SWEEPS,
                     pert=pert.as_dict(), tag=SEED_TAG,
                     inst_index=400 + list(SMOKE_INST).index(fam) + (10 * (int(key) % 100) if "inst" in j else 0))
        rec = mc.execute(sp, cost, mit if j["machine"] != "b3" else None)
        if fam.startswith("vmc"):
            ref = vmc_reference(fam, key)
            cut = -rec["best_E"]
            rec.update(ref=ref, success=cut >= pl.MAXCUT_TARGET_FRAC * ref)
            quality = cut / ref
        else:
            rec.update(success=rec["best_E"] == 0)
            quality = -rec["best_E"]          # colouring: minus the number of end conflicts
    mc_ = mitigation_cost(rec, mit, cost)
    slim = {"key": job_key(j), **j, "success": bool(rec["success"]), "quality": float(quality),
            "best": rec.get("best_E", rec.get("best_profit")), "e_total_fJ": rec["price"]["e_total"], "time_ns": rec["price"]["time_ns"],
            "a_total_um2": rec["price"]["a_total"], "cost": mc_, "prog_v2": rec.get("prog_v2"), "wall_s": rec.get("wall_s"),
            "false_stall": rec.get("false_stall"), "false_accept_states": rec.get("false_accept_states")}
    return slim


def run_grid(jobs: list[dict], out: Path, chunk: tuple[int, int] = (0, 1)) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(line)["key"] for line in out.read_text().splitlines() if line.strip()}
    mine = [j for i, j in enumerate(jobs) if i % chunk[1] == chunk[0] and job_key(j) not in done]
    print(f"VAR2 {len(mine)} jobs to run ({len(done)} already in {out})", flush=True)
    from cost_model import CostModel
    cost = CostModel()
    with open(out, "a") as fh:
        for i, j in enumerate(mine):
            t0 = time.time()
            r = run_job(j, cost)
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"VAR2 {i + 1}/{len(mine)} {r['key']} success={r['success']} q={r['quality']:.3f} {time.time() - t0:.1f}s", flush=True)
    return 0


def summarize(paths: list[Path], out_dir: Path = RESULTS) -> list[dict]:
    """Per (machine, family, point, mitigation): success rate, mean quality, mean run energy incl. mitigation overhead, overhead %,
    one-time energy/time, area overhead; CSV + a markdown table of the nominal (vx1) cells."""
    rows = {}
    for p in paths:
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            k = (r["machine"], r["family"], r["point"], r["mit"])
            rows.setdefault(k, []).append(r)
    table = []
    for (m, f, pid, mit), rs in sorted(rows.items()):
        table.append({"machine": m, "family": f, "point": pid, "mit": mit, "n": len(rs),
                      "success": float(np.mean([r["success"] for r in rs])), "quality": float(np.mean([r["quality"] for r in rs])),
                      "e_run_fJ": float(np.mean([r["cost"]["e_run_fJ"] for r in rs])),
                      "e_base_fJ": float(np.mean([r["e_total_fJ"] for r in rs])),
                      "overhead_pct": float(np.mean([r["cost"]["overhead_pct"] for r in rs])),
                      "e_once_fJ": float(np.mean([r["cost"]["e_once_fJ"] for r in rs])),
                      "t_once_us": float(np.mean([r["cost"]["t_once_us"] for r in rs])),
                      "d_area_um2": float(np.mean([r["cost"]["d_area_um2"] for r in rs])),
                      "a_base_um2": float(np.mean([r["a_total_um2"] for r in rs])),
                      "pulses_per_cell": float(np.mean([(r.get("prog_v2") or {}).get("pulses_per_cell", 1.0) for r in rs]))})
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "smoke_var_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    return table


def report_md(table: list[dict], out: Path = RESULTS / "smoke_var_report.md") -> str:
    """Markdown tables from the summary rows: nominal mitigation table, success-vs-k curves, drift sweep, term decomposition,
    and per machine the cheapest combination that restores success at nominal (>= ideal success - 10 pp on every family)."""
    by = {(r["machine"], r["family"], r["point"], r["mit"]): r for r in table}
    machines = [m for m in ("ours", "b1", "b2", "b3") if any(r["machine"] == m for r in table)]
    L = ["# VARIATION_V2 smoke-var report (generated by variation_v2.py --summarize)", "",
         "success = share of seeds reaching the target (colouring: 0 conflicts; Max-Cut: cut >= 0.99 x reference; QKP: profit >= "
         "0.99 x optimum). q = mean quality (colouring: -conflicts; Max-Cut: cut/ref; QKP: profit/opt). ovh = runtime energy "
         "overhead of the mitigation in % of the machine's own run energy; once = one-time programming + calibration energy (nJ); "
         "dA = area overhead in % of the machine's area.", ""]
    fams = lambda m: sorted({r["family"] for r in table if r["machine"] == m})            # noqa: E731
    for m in machines:
        L += [f"## {m}: nominal variation (vx1) per mitigation", "",
              "| mitigation | " + " | ".join(f"{f} success / q" for f in fams(m)) + " | ovh % | once nJ | dA % | pulses/cell |",
              "|---|" + "---|" * (len(fams(m)) + 4)]
        mits = [k for k in dict.fromkeys(r["mit"] for r in table if r["machine"] == m and r["point"] in ("vx1", "vx0"))]
        for mit in mits:
            pid = "vx0" if m == "b3" else "vx1"
            cells = [by.get((m, f, pid, mit)) for f in fams(m)]
            if not any(cells):
                continue
            ok = [c for c in cells if c]
            L.append(f"| {mit} | " + " | ".join(f"{c['success']:.2f} / {c['quality']:.3g}" if c else "-" for c in cells)
                     + f" | {np.mean([c['overhead_pct'] for c in ok]):.1f} | {np.mean([c['e_once_fJ'] for c in ok]) / 1e6:.3g}"
                     + f" | {100 * np.mean([c['d_area_um2'] / c['a_base_um2'] for c in ok]):.1f}"
                     + f" | {np.mean([c['pulses_per_cell'] for c in ok]):.2f} |")
        ideal = [by.get((m, f, "vx0", "none")) for f in fams(m)]
        if all(ideal):
            L.append("| ideal device (vx0) | " + " | ".join(f"{c['success']:.2f} / {c['quality']:.3g}" for c in ideal) + " | | | | |")
        L.append("")
        if m == "b3":
            continue
        ks = sorted({float(r["point"][2:]) for r in table if r["machine"] == m and r["point"].startswith("vx")})
        L += [f"### {m}: success vs variation multiplier k (mean over families)", "",
              "| mitigation | " + " | ".join(f"k={k:g}" for k in ks) + " |", "|---|" + "---|" * len(ks)]
        for mit in mits:
            vals = []
            for k in ks:
                pid = f"vx{k:g}"
                c = [by.get((m, f, pid, mit)) or (by.get((m, f, pid, "none")) if k == 0 else None) for f in fams(m)]
                vals.append(f"{np.mean([x['success'] for x in c]):.2f}" if all(c) else "-")
            L.append(f"| {mit} | " + " | ".join(vals) + " |")
        L.append("")
        drifts = sorted({r["point"] for r in table if r["machine"] == m and r["point"].startswith("drift")}, key=lambda p: float(p[5:]))
        if drifts:
            L += [f"### {m}: retention drift sweep (k = 1; V per decade x {pl.DRIFT_DECADES} decades)", "",
                  "| mitigation | vx1 | " + " | ".join(drifts) + " |", "|---|---|" + "---|" * len(drifts)]
            for mit in DRIFT_COMBOS:
                vals = [np.mean([by[(m, f, p, mit)]["success"] for f in fams(m) if (m, f, p, mit) in by] or [np.nan])
                        for p in ["vx1"] + drifts]
                L.append(f"| {mit} | " + " | ".join(f"{x:.2f}" for x in vals) + " |")
            L.append("")
        terms = [(f, t) for f in fams(m) for t in TERM_POINTS if (m, f, t, "none") in by]
        if terms:
            L += [f"### {m}: one term at a time (nominal magnitude, all others 0)", "",
                  "| family | term | v1 success / q | v2 none success / q | v2 wv success / q |", "|---|---|---|---|---|"]
            for f, t in terms:
                L.append(f"| {f} | {t} | " + " | ".join(f"{by[(m, f, t, x)]['success']:.2f} / {by[(m, f, t, x)]['quality']:.3g}"
                                                       if (m, f, t, x) in by else "-" for x in TERM_COMBOS) + " |")
            L.append("")
        best = None
        for mit in mits:
            cs = [by.get((m, f, "vx1", mit)) for f in fams(m)]
            if not all(cs) or mit == "v1":
                continue
            if all(c["success"] >= by[(m, c["family"], "vx0", "none")]["success"] - 0.10 for c in cs):
                o = float(np.mean([c["overhead_pct"] for c in cs]))
                if best is None or o < best[1]:
                    best = (mit, o)
        L += [f"**{m}: cheapest combination restoring success at nominal (>= ideal - 10 pp on every family): "
              + (f"`{best[0]}` (runtime overhead {best[1]:.1f} %)**" if best else "none in the grid**"), ""]
    txt = "\n".join(L) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt)
    return txt


def summarize_stat(paths: list[Path], out_dir: Path = STAT_RESULTS) -> list[dict]:
    """Pool instances and seeds per (machine, family, point, mitigation, c2c): successes, Wilson 95 % CI, mean quality and costs."""
    groups: dict = {}
    for p in paths:
        for line in p.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                groups.setdefault((r["machine"], r["family"], r["point"], r["mit"], r.get("c2c", C2C_SHARE)), []).append(r)
    table = []
    for (m, f, pid, mit, c2c), rs in sorted(groups.items(), key=lambda kv: tuple(map(str, kv[0]))):
        n, k = len(rs), int(sum(r["success"] for r in rs))
        lo, hi = wilson(k, n)
        table.append({"machine": m, "family": f, "point": pid, "mit": mit, "c2c": c2c, "n": n, "k": k, "success": k / n,
                      "ci_lo": lo, "ci_hi": hi, "instances": len({r.get("inst") for r in rs}),
                      "quality": float(np.mean([r["quality"] for r in rs])),
                      "e_base_fJ": float(np.mean([r["e_total_fJ"] for r in rs])),
                      "e_run_fJ": float(np.mean([r["cost"]["e_run_fJ"] for r in rs])),
                      "overhead_pct": float(np.mean([r["cost"]["overhead_pct"] for r in rs])),
                      "e_once_fJ": float(np.mean([r["cost"]["e_once_fJ"] for r in rs])),
                      "d_area_pct": float(np.mean([100 * r["cost"]["d_area_um2"] / r["a_total_um2"] for r in rs])),
                      "pulses_per_cell": float(np.mean([(r.get("prog_v2") or {}).get("pulses_per_cell", 1.0) for r in rs]))})
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "stat_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    return table


NONINF_MARGIN = 0.10


def restoring(table: list[dict], machine: str, pid: str = "vx1") -> list[dict]:
    """Combinations that restore the ideal device's success at point pid: (a) pooled over families, Newcombe 95 % lower bound of
    (p_combo - p_ideal) > -NONINF_MARGIN (non-inferiority), and (b) no family significantly worse than ideal (per-family Newcombe
    upper bound >= 0). A per-family 10 pp non-inferiority test is unresolvable at 60 runs per family (identical counts at p ~ 0.6
    give a lower bound of about -0.17), so the margin is tested on the pooled 240 runs. Sorted by runtime energy overhead (then
    one-time energy): the first is the pick."""
    by = {(r["family"], r["point"], r["mit"]): r for r in table if r["machine"] == machine and r["c2c"] == C2C_SHARE}
    fams = sorted({f for f, p, m in by if p == "vx0"})
    out = []
    for mit in sorted({m for f, p, m in by if p == pid}):
        if mit == "v1":
            continue
        rows, ideal, fam_ok = [], [], True
        for f in fams:
            c, i = by.get((f, pid, mit)), by.get((f, "vx0", "none"))
            if c is None or i is None:
                break
            rows.append(c)
            ideal.append(i)
            fam_ok &= newcombe_diff(c["k"], c["n"], i["k"], i["n"])[2] >= 0
        else:
            d, lo, hi = newcombe_diff(sum(r["k"] for r in rows), sum(r["n"] for r in rows),
                                      sum(r["k"] for r in ideal), sum(r["n"] for r in ideal))
            if fam_ok and lo > -NONINF_MARGIN:
                out.append({"mit": mit, "worst_lo": lo, "diff": d, "overhead_pct": float(np.mean([r["overhead_pct"] for r in rows])),
                            "e_once_fJ": float(np.mean([r["e_once_fJ"] for r in rows])),
                            "d_area_pct": float(np.mean([r["d_area_pct"] for r in rows]))})
    return sorted(out, key=lambda r: (round(r["overhead_pct"], 6), r["e_once_fJ"]))


def report_stat(table: list[dict], out: Path = STAT_RESULTS / "stat_report.md") -> str:
    fmt = lambda r: f"{r['k']}/{r['n']} = {r['success']:.2f} [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]"     # noqa: E731
    L = ["# VARIATION_V2 statistical grid report (variation_v2.py --summarize-stat)", "",
         f"Cells pool instances x seeds; success with Wilson 95 % CI. Restoring = pooled over families, Newcombe 95 % lower bound of "
         f"(p - p_ideal) > -{NONINF_MARGIN:g}, and no family significantly worse than ideal; the pick is the restoring combination "
         f"with the lowest runtime energy overhead.", ""]
    machines = [m for m in ("ours", "ours_i7v2", "b1", "b2", "b3") if any(r["machine"] == m for r in table)]
    for m in machines:
        rows = [r for r in table if r["machine"] == m]
        fams = sorted({r["family"] for r in rows})
        by = {(r["family"], r["point"], r["mit"], r["c2c"]): r for r in rows}
        for pid in ("vx1", "vx3"):
            mits = [x for x in dict.fromkeys(r["mit"] for r in rows if r["point"] == pid and r["c2c"] == C2C_SHARE)]
            if not mits:
                continue
            L += [f"## {m}: k = {pid[2:]} (success, Wilson 95 % CI)", "",
                  "| mitigation | " + " | ".join(fams) + " | runtime ovh % | once nJ | area % | pulses/cell |", "|---|" + "---|" * (len(fams) + 4)]
            for mit in ["(ideal vx0)"] + mits:
                cs = [by.get((f, "vx0", "none", C2C_SHARE)) if mit == "(ideal vx0)" else by.get((f, pid, mit, C2C_SHARE)) for f in fams]
                ok = [c for c in cs if c]
                L.append(f"| {mit} | " + " | ".join(fmt(c) if c else "-" for c in cs)
                         + (" | | | | |" if mit == "(ideal vx0)" else
                            f" | {np.mean([c['overhead_pct'] for c in ok]):.1f} | {np.mean([c['e_once_fJ'] for c in ok]) / 1e6:.3g}"
                            f" | {np.mean([c['d_area_pct'] for c in ok]):.1f} | {np.mean([c['pulses_per_cell'] for c in ok]):.2f} |"))
            L.append("")
            if m != "b3":
                res = restoring(table, m, pid)
                L.append(f"**{m} restoring at k = {pid[2:]}:** " + (", ".join(f"`{r['mit']}` (+{r['overhead_pct']:.1f} %, pooled diff "
                                                                              f"{r['diff']:+.2f}, lower bound {r['worst_lo']:+.2f})" for r in res) or "none")
                         + (f". **Pick: `{res[0]['mit']}`.**" if res else ""))
                L.append("")
        curve_p = sorted({r["point"] for r in rows if r["point"].startswith("vx")}, key=lambda p: float(p[2:]))
        cm = [x for x in dict.fromkeys(r["mit"] for r in rows if r["point"] in ("vx0.5", "vx2") and r["c2c"] == C2C_SHARE)]
        if cm:
            L += [f"### {m}: success vs k (pooled over families)", "", "| mitigation | " + " | ".join(curve_p) + " |",
                  "|---|" + "---|" * len(curve_p)]
            for mit in cm:
                vals = []
                for pid in curve_p:
                    cs = [by.get((f, pid, "none" if pid == "vx0" else mit, C2C_SHARE)) for f in fams]
                    cs = [c for c in cs if c]
                    vals.append(f"{sum(c['k'] for c in cs) / sum(c['n'] for c in cs):.2f}" if cs else "-")
                L.append(f"| {mit} | " + " | ".join(vals) + " |")
            L.append("")
        c2 = sorted({(r["point"], r["mit"]) for r in rows if r["c2c"] != C2C_SHARE})
        if c2:
            shares = sorted({r["c2c"] for r in rows if (r["point"], r["mit"]) in c2} | {C2C_SHARE})
            L += [f"### {m}: C2C-share sensitivity (success pooled over {', '.join(sorted({r['family'] for r in rows if r['c2c'] != C2C_SHARE}))})", "",
                  "| point | mitigation | " + " | ".join(f"C2C {c:g}" for c in shares) + " |", "|---|---|" + "---|" * len(shares)]
            for pid, mit in c2:
                vals = []
                for c in shares:
                    cs = [r for r in rows if r["point"] == pid and r["mit"] == mit and r["c2c"] == c
                          and r["family"] in ({"qkp"} if m == "b2" else set(C2C_FAMILIES))]
                    k, n = sum(x["k"] for x in cs), sum(x["n"] for x in cs)
                    lo, hi = wilson(k, n)
                    vals.append(f"{k}/{n} [{lo:.2f}, {hi:.2f}]" if n else "-")
                L.append(f"| {pid} | {mit} | " + " | ".join(vals) + " |")
            L.append("")
    txt = "\n".join(L) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt)
    return txt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--smoke-var", action="store_true", help="run the variation stress grid")
    ap.add_argument("--machine", choices=("ours", "ours_i7v2", "b1", "b2", "b3"), action="append")
    ap.add_argument("--chunk", default="0/1", help="i/N: run every N-th job starting at i")
    ap.add_argument("--seeds", type=int, default=SMOKE_SEEDS)
    ap.add_argument("--out", type=Path, default=SMOKE_OUT)
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--stat", action="store_true", help="statistical grid (grid_stat) instead of the first smoke")
    ap.add_argument("--summarize-stat", action="store_true")
    ap.add_argument("--skip-keys", type=Path, help="file of job keys already done elsewhere: removed BEFORE chunking")
    ap.add_argument("--prefix", default="", help="output file name prefix (e.g. cloud_), so offloaded chunks never clobber local ones")
    ap.add_argument("--list", action="store_true", help="print the number of jobs this invocation would run and exit")
    ap.add_argument("--max-jobs", type=int, default=0, help="debug: stop after this many jobs")
    a = ap.parse_args(argv)
    machines = a.machine or ["ours", "b1", "b2", "b3"]
    if a.summarize_stat:
        report_stat(summarize_stat(sorted(STAT_OUT.glob("*.jsonl"))))
        return 0
    if a.summarize:
        report_md(summarize(sorted(a.out.glob("*.jsonl"))))
        return 0
    if a.smoke_var:
        i, n = (int(x) for x in a.chunk.split("/"))
        for m in machines:
            jobs = grid_stat(m) if a.stat else grid(m, a.seeds)
            if a.skip_keys:
                skip = set(a.skip_keys.read_text().split())
                jobs = [j for j in jobs if job_key(j) not in skip]
            if a.max_jobs:
                jobs = jobs[:a.max_jobs]
            if a.list:
                print(m, len([j for k, j in enumerate(jobs) if k % n == i]))
                continue
            run_grid(jobs, (STAT_OUT if a.stat else a.out) / f"{a.prefix}{m}_{i}of{n}.jsonl", (i, n))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
