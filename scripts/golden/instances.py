"""Instance generators for TIM v0 tests: random QUBO, Max-Cut graphs, and the D5c knapsack generator (port).

d5c_make_instance is a line-by-line port of make_instance in
sw_ref/experiments/d5c_qhinge/qkp_nb.py (the reference software study, MIT licence, same author); selftest_golden.py checks that it
gives the same arrays as the original.
"""
from __future__ import annotations

import math

import numpy as np

from tim_golden import MASK64, Instance, objective, splitmix64_stream

TWO16 = 1 << 16
TWO32 = 1 << 32


# ------------------------------------------------------------------------------------------------ schedule helpers
def temp_reg(temp_elsb: float) -> int:
    """T register value (UQ16.16) for a temperature in energy LSB."""
    return int(round(temp_elsb * TWO16))


def alpha_reg(t_start: float, t_end: float, steps: int) -> int:
    """A register (UQ0.32) for a geometric schedule from t_start to t_end over `steps` steps (as qkp_nb.run)."""
    alpha = (t_end / t_start) ** (1.0 / max(steps - 1, 1))
    return min(int(round(alpha * TWO32)), TWO32 - 1)


def mix_seed(*parts: int) -> int:
    """A 64-bit machine seed from small integers (deterministic)."""
    v = 0
    for p in parts:
        v = splitmix64_stream((v ^ (p & MASK64)) & MASK64, 1)[0]
    return v


# ------------------------------------------------------------------------------------------------ QUBO and Max-Cut
def random_qubo(n: int, seed: int, pmax: int, dmax: int, density: float = 0.5):
    """(d, P): integer QUBO with d in [-dmax, dmax], symmetric P in [-pmax, pmax] with the given density."""
    rng = np.random.default_rng([20261031, n, seed])
    P = rng.integers(-pmax, pmax + 1, size=(n, n)) * (rng.random((n, n)) < density)
    P = np.triu(P, 1)
    P = (P + P.T).astype(np.int64)
    d = rng.integers(-dmax, dmax + 1, size=n).astype(np.int64)
    return d, P


def maxcut_qubo(n: int, edges: list[tuple[int, int, int]]):
    """(d, P) with f(x) = cut(x): d_i = sum_j w_ij, P_ij = -2 w_ij (spec 6.3)."""
    d = np.zeros(n, dtype=np.int64)
    P = np.zeros((n, n), dtype=np.int64)
    for i, j, w in edges:
        d[i] += w
        d[j] += w
        P[i, j] -= 2 * w
        P[j, i] -= 2 * w
    return d, P


def random_graph(n: int, p: float, seed: int) -> list[tuple[int, int, int]]:
    rng = np.random.default_rng([20261031, 7, n, seed])
    return [(i, j, 1) for i in range(n) for j in range(i + 1, n) if rng.random() < p]


def torus_graph(rows: int, cols: int) -> list[tuple[int, int, int]]:
    edges = []
    for r in range(rows):
        for c in range(cols):
            v = r * cols + c
            edges.append((v, r * cols + (c + 1) % cols, 1))
            edges.append((v, ((r + 1) % rows) * cols + c, 1))
    return [(min(a, b), max(a, b), w) for a, b, w in edges]


def ring_graph(n: int) -> list[tuple[int, int, int]]:
    return [(i, (i + 1) % n, 1) for i in range(n)]


def qubo_instance(d, P, *, seed: int, steps: int, t_start: float, t_end: float | None, deoff: int,
                  lab: int = 10) -> Instance:
    """QUBO-mode instance; t_end = None holds T at t_start (geom = 0)."""
    geom = t_end is not None
    return Instance(n=len(d), mode="qubo", geom=int(geom), t0=temp_reg(t_start),
                    alpha=alpha_reg(t_start, t_end, steps) if geom else 0, deoff=deoff, lam=0, gsh=0, wmax=1,
                    seed=seed, steps=steps, lab=lab, d=np.asarray(d, dtype=np.int64), P=np.asarray(P, dtype=np.int64))


# ------------------------------------------------------------------------------------------------ D5c knapsack
def d5c_make_instance(n: int, m: int, seed: int, density: float = 0.5, tight: float = 0.25) -> dict:
    """Port of qkp_nb.make_instance (same RNG calls in the same order), returned as integer arrays."""
    rng = np.random.default_rng([20261021, n, m, seed])
    P = rng.integers(1, 101, size=(n, n)).astype(np.float64)
    mask = rng.random((n, n)) < density
    P = np.where(mask, P, 0.0)
    P = np.triu(P, 1)
    P = P + P.T
    diag = rng.integers(1, 101, size=n).astype(np.float64)
    W = rng.integers(1, 51, size=(m, n)).astype(np.int64)
    C = np.floor(tight * W.sum(axis=1)).astype(np.int64)
    return dict(n=n, m=m, seed=seed, P=P.astype(np.int64), d=diag.astype(np.int64), W=W, C=C)


def d5c_to_tim(raw: dict, *, rule: str, T0: float, T_min: float, budget: int, seed: int, lam: float,
               dE_off: float, Q: int = 8, w_max: int = 50, gsh: int | None = None, lab: int = 10) -> Instance:
    """Integer machine registers for a qkp_nb.run configuration (hw_prior_art 1.4).

    Energies are scaled by 2^gsh (gsh = log2 Q for the TCAM rule). Float model: T = T0*unit, dE = dE_off*unit,
    geff = gain - lam*unit*dq*S with dq = w_max/Q. Integer: T, dE and Lambda are rounded once here."""
    unit = float(np.abs(raw["d"]).mean())
    if gsh is None:
        gsh = int(round(math.log2(Q)))
    scale = 1 << gsh
    if rule == "hw":
        lam_reg = int(round(lam * unit * w_max / Q * scale))
    elif rule == "penalty":
        lam_reg = int(round(lam * unit * scale))
    else:
        lam_reg = 0
    return Instance(n=raw["n"], mode="knap", geom=1, t0=temp_reg(T0 * unit * scale),
                    alpha=alpha_reg(T0, T_min, budget), deoff=int(round(dE_off * unit * scale)), lam=lam_reg,
                    gsh=gsh, wmax=w_max, seed=mix_seed(seed, raw["n"], raw["m"], raw["seed"]), steps=budget,
                    lab=lab, d=raw["d"].copy(), P=raw["P"].copy(), W=raw["W"].copy(), C=raw["C"].copy(), q=Q,
                    rule=rule)


# ------------------------------------------------------------------------------------------------ brute force
def brute_force_best(inst: Instance) -> tuple[int, np.ndarray]:
    """Best feasible objective over all 2^n states (n <= 20)."""
    n = inst.n
    assert n <= 20
    best, best_x = None, None
    chunk = 1 << min(n, 14)
    for start in range(0, 1 << n, chunk):
        codes = np.arange(start, start + chunk, dtype=np.int64)
        X = ((codes[:, None] >> np.arange(n)[None, :]) & 1).astype(np.int64)
        f = X @ inst.d + ((X @ inst.P) * X).sum(axis=1) // 2
        if inst.mode == "knap":
            ok = (X @ inst.W.T <= inst.C[None, :]).all(axis=1)
            f = np.where(ok, f, np.iinfo(np.int64).min)
        i = int(np.argmax(f))
        if best is None or f[i] > best:
            best, best_x = int(f[i]), X[i].copy()
    assert objective(inst, best_x) == best
    return best, best_x
