"""B2 HyCiM on the shared device models (P4.06, prereg/calib/P4.06.md).

Filter = 1FeFET1R matchline comparator against a replica array: 16 x 100 weight array, 5-level cells (cim_cell_v1
levels 0-4), replica = C units + half-unit reference. Multi-level cells use per-cell write-verify (costed), as fixed
in the prereg. SA behaviour: the P4.05 kernel (hycim.py, copied from qkp_pricer@b72a607f), label "post-hoc v3".
Energy/time: filter rows from P1.10 (cim_cell_v1.csv) and P1.11 (adc_energy.csv); ΔE array/ADC, RNG and digital
rows from the shared table via cost_model.CostModel (same as ours and B1). Label "literature-parameterised".

CLI: `python -I scripts/baselines/hycim_b2.py [--smoke]` -> A2 error rates + A3 v3 re-run, RESULT line, JSON in
sim/out/hw/P4.06/.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts" / "golden"))

import hycim as hc  # noqa: E402
from cost_model import CostModel, adc_conv_fj, adc_curve_points  # noqa: E402

CELL_CSV = ROOT / "circuit" / "cim" / "cim_cell_v1.csv"
ADC_CSV = ROOT / "circuit" / "adc" / "adc_energy.csv"
OUT = ROOT / "sim" / "out" / "hw" / "P4.06"
ROWS, COLS, LEVELS, MAXD = 16, 100, 5, 4
WV_TOL = 0.05                      # t4a acceptance band = write-verify residual
T_VERIFY_US = 0.020                # one 20 ns verify read
CMP_BITS = 3
PROFIT_BITS = 7                    # Billionnet-Soutif profits 0..100
A3_INST = ["jeu_100_100_7.txt", "jeu_100_25_3.txt", "jeu_100_75_8.txt", "jeu_100_50_6.txt", "jeu_100_75_5.txt"]
A3_V3 = {"jeu_100_100_7.txt": 0.897, "jeu_100_25_3.txt": 0.924, "jeu_100_75_8.txt": 0.978,
         "jeu_100_50_6.txt": 0.989, "jeu_100_75_5.txt": 0.989}
A3_TOL_PP = 5.0


def load_cell(path: Path = CELL_CSV) -> list[dict]:
    with open(path, newline="") as fh:
        rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(fh)]
    return rows[:LEVELS]


def comparator_fj(path: Path = ADC_CSV) -> float:
    with open(path, newline="") as fh:
        r = next(r for r in csv.DictReader(fh) if int(r["bits"]) == CMP_BITS)
    return float(r["e_cmp_fJ"]) / CMP_BITS


def digits(value: int, ncells: int) -> np.ndarray:
    """Unary-in-4 encoding: floor(value/4) cells at level 4, one at value mod 4, rest 0."""
    assert 0 <= value <= MAXD * ncells, (value, ncells)
    d = np.zeros(ncells, np.int64)
    q, r = divmod(int(value), MAXD)
    d[:q] = MAXD
    if r:
        d[q] = r
    return d


@dataclass
class Filter:
    weight_levels: np.ndarray   # ROWS x n
    replica_levels: np.ndarray  # ROWS*COLS
    cell: list

    @classmethod
    def build(cls, inst: hc.Inst, cell=None):
        assert inst.n <= COLS
        W = np.stack([digits(w, ROWS) for w in inst.w], axis=1)
        return cls(W, digits(inst.C, ROWS * COLS), cell or load_cell())

    def currents(self, mode: str, rng=None):
        """Per-cell currents (nA): mode 'ideal' (k * I_u), 'wv' (write-verify), 'open' (open-loop char sigma)."""
        iu = self.cell[1]["i_target_nA"]

        def draw(levels):
            ideal = levels * iu
            if mode == "ideal":
                return ideal.astype(float)
            mu = np.array([c["i_read_nA"] for c in self.cell])[levels]
            sg = np.array([c["i_sigma_nA"] for c in self.cell])[levels]
            open_ = np.maximum(0.0, mu + sg * rng.standard_normal(levels.shape))
            if mode == "open":
                return open_
            if mode == "wv_l0ideal":        # post-hoc attribution diagnostic: level-0 cells ideal (0 nA)
                return np.where(levels == 0, 0.0, ideal * (1.0 + WV_TOL * rng.uniform(-1.0, 1.0, levels.shape)))
            wv = ideal * (1.0 + WV_TOL * rng.uniform(-1.0, 1.0, levels.shape))
            return np.where(levels == 0, open_, wv)
        return draw(self.weight_levels), draw(self.replica_levels), iu

    def decide(self, X: np.ndarray, mode: str = "ideal", rng=None) -> np.ndarray:
        """Accept (True) iff I_ML < I_rep for each state row of X."""
        Iw, Ir, iu = self.currents(mode, rng)
        i_ml = X @ Iw.sum(axis=0)
        return i_ml < Ir.sum() + 0.5 * iu


def state_sets(inst: hc.Inst, n_states: int, seed) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    bern = (rng.random((n_states, inst.n)) < 0.5).astype(np.int64)
    prop = np.empty_like(bern)
    for s in range(n_states):
        x = hc.feasible_random(inst, rng)
        x[rng.integers(inst.n)] ^= 1
        prop[s] = x
    return {"S_bern": bern, "S_prop": prop}


def error_rate(inst: hc.Inst, mode: str, n_states=10_000, draws=20, seed=0) -> float:
    f = Filter.build(inst)
    X = state_sets(inst, n_states, hc.seed_of(406, seed))["S_prop"]
    exact = X @ inst.w <= inst.C
    rng = np.random.default_rng(hc.seed_of(406, seed, 1))
    return float(np.mean([np.mean(f.decide(X, mode, rng) != exact) for _ in range(draws)]))


def wv_attempts(cell=None) -> list[float]:
    """Expected write-verify attempts per level: 1 / P(|N(0, sigma/mu)| < tol); level 0 is not verified."""
    cell = cell or load_cell()
    out = [1.0]
    for c in cell[1:]:
        p_in = math.erf(WV_TOL / (c["sigma_over_mu"] * math.sqrt(2.0)))
        out.append(1.0 / p_in)
    return out


def program_cost(inst: hc.Inst, level0_verify: bool = False, cost: CostModel | None = None) -> dict[str, float]:
    """One-time cell-by-cell programming (P1.07 fallback) of weight + replica arrays with write-verify.

    level0_verify (ruling R7, provisional): level 0 is also verified (deep-erase window, 3-bit window attempts and
    E/t from the canonical table, char_v1). False = as measured (level 0 written once, unverified)."""
    f, cell, att = Filter.build(inst), load_cell(), wv_attempts()
    if level0_verify:
        v = (cost or CostModel()).v
        att[0] = v("n_l0_attempts_3bit")
    levels = np.concatenate([f.weight_levels.ravel(), f.replica_levels])
    e = t = 0.0
    for k in range(LEVELS):
        nk = int((levels == k).sum())
        verified = k > 0 or level0_verify
        e += nk * att[k] * (cell[k]["e_write_fJ"] + (cell[k]["e_read_fJ"] if verified else 0.0))
        t += nk * att[k] * (cell[k]["t_write_us"] + (T_VERIFY_US if verified else 0.0))
    # P1.07 disturb: HVT level-0 shift -156.7 mV per 255 x 10 us at +2 V; stress here = row-neighbour write time
    stress_us = t / ROWS
    return {"e_program_fJ": e, "t_program_us": t, "cells": int(levels.size),
            "disturb_stress_ratio": stress_us / (255 * 10.0)}


def filter_energy_fj(inst: hc.Inst, x: np.ndarray) -> float:
    """One filter decision: selected columns read at their levels, unselected columns pay the shared WL gate charge,
    replica fully read, one comparator decision."""
    f, cell = Filter.build(inst), load_cell()
    e_rd = np.array([c["e_read_fJ"] for c in cell])
    e_wl = np.array([c["e_read_wl_fJ"] for c in cell])
    sel = np.asarray(x, bool)
    w = f.weight_levels
    return float(e_rd[w[:, sel]].sum() + e_wl[w[:, ~sel]].sum() + e_rd[f.replica_levels].sum() + comparator_fj())


def adc_energy_fj(proposals: int, tiles: int, cost: CostModel) -> float:
    """ADC block of B2 under the one tiling rule (like cost_model.tiled_counts): the profit-matrix read converts PROFIT_BITS bits
    per step; every extra column tile adds one 1-bit comparator conversion per step."""
    if not cost.adc_curve:
        return proposals * (PROFIT_BITS + (tiles - 1)) * cost.v("e_adc_conv_bit")
    e8 = 8 * cost.v("e_adc_conv_bit")
    pts = adc_curve_points()
    return proposals * (adc_conv_fj(PROFIT_BITS, e8, pts) + (tiles - 1) * adc_conv_fj(1, e8, pts))


def leakage_fj(proposals: int, cost: CostModel) -> float:
    """B2 leakage under the one rule: logic gates over the run time plus the ADC comparator bias on every step (B2 never gates a step)."""
    return cost.leak_fj(cost.v("g_b2_logic"), proposals * cost.v("t_clk")) + proposals * cost.v("e_adc_bias_step")


def run_energy(inst: hc.Inst, proposals: int, x_typ: np.ndarray, cost: CostModel | None = None) -> dict[str, float]:
    """Energy (fJ) per SA run of `proposals` steps, blocks named as cost_model.CostModel.energy."""
    cost = cost or CostModel()
    v, n = cost.v, inst.n
    return {
        "array": proposals * n * PROFIT_BITS * v("e_array_cell_read"),       # ΔE row read (profit matrix)
        "adc": adc_energy_fj(proposals, math.ceil(n / COLS), cost),
        "digital": proposals * (2 * v("e_add") + v("e_reg_write")),
        "rng": proposals * 4 * v("e_rng_draw"),                              # u, i, j, move type
        "filter": proposals * filter_energy_fj(inst, x_typ),
        "restart": 0.0,
        "leakage": leakage_fj(proposals, cost),
    }


def a3_rerun(names, n_init=100, n_runs=10, L=100_000) -> dict[str, float]:
    opt = json.loads(hc.OPTIMA.read_text())["instances"]
    ai, si = hc.ARMS.index("filter"), hc.SCHEDULES.index("S4")
    out = {}
    for nm in names:
        inst, idx = hc.load(nm), hc.INSTANCES.index(nm)
        T = hc.temps("S4", hc.t0_for(inst, "filter", "S4", hc.seed_of(idx, ai, si, 99)), L)
        ok = []
        for k in range(n_init):
            x0, y0 = hc.initial_state(inst, "filter", hc.seed_of(idx, ai, 0, k))
            for r in range(n_runs):
                b = hc.run_one(inst, "filter", T, x0, y0, hc.seed_of(idx, ai, si, k, r, L), hc.PSWAP_V3)[0]
                ok.append(b >= 0.95 * opt[nm]["value"])
        out[nm] = float(np.mean(ok))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    names = A3_INST[:2] if a.smoke else A3_INST
    n_states, draws = (500, 2) if a.smoke else (10_000, 20)
    err = {nm: {m: error_rate(hc.load(nm), m, n_states, draws) for m in ("wv", "open", "wv_l0ideal")} for nm in names}
    prog = {nm: program_cost(hc.load(nm)) for nm in names}
    inst0 = hc.load(names[0])
    x_typ = hc.feasible_random(inst0, np.random.default_rng(hc.seed_of(406, 9)))
    L = 1000 if a.smoke else 100_000
    energy = run_energy(inst0, L, x_typ)
    rates = a3_rerun(names, *((5, 2, 1000) if a.smoke else (100, 10, 100_000)))
    dev = {nm: 100 * abs(rates[nm] - A3_V3[nm]) for nm in names}
    ok = all(d <= A3_TOL_PP for d in dev.values())
    res = {"smoke": a.smoke, "error_rate": err, "program": prog, "wv_attempts": wv_attempts(),
           "energy_per_run_fJ": {"instance": names[0], "proposals": L, **energy},
           "e_filter_decision_fJ": filter_energy_fj(inst0, x_typ),
           "a3_rate": rates, "a3_v3": {nm: A3_V3[nm] for nm in names}, "a3_dev_pp": dev, "pass": ok}
    (OUT / ("smoke.json" if a.smoke else "result.json")).write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    if not a.smoke:
        print(f"RESULT P4.06 {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
