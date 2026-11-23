"""B2 HyCiM (Qian et al., DAC 2024, arXiv 2410.14111): filter-SA and the D-QUBO penalty baseline on QKP.

PROVENANCE (copied, not imported; never edit the source):
  sw_ref_wt/qkp_pricer/experiments/qkp_pricer/hycim_repro.py @ b72a607f (worktree HEAD 629e4023):
    Inst, dqubo_energy, _flip_field, _run, temps, feasible_random, t0_for, initial_state, run_one, seed_of,
    constants ALPHA/BETA/SCHEDULES/DQUBO_T0_S4/PSWAP_V3.
  sw_ref_wt/qkp_pricer/histmem/instances/external/qkp_soutif.py @ 629e4023: parse() (file reader).
Changes vs the source (P4.05, prereg/calib/P4.05.md), all additive:
  - _run also returns the H3 scorers: feasible profit of the FINAL state (-1 if infeasible) and the profit of the
    minimum-energy state seen if it is feasible (-1 otherwise). Best-seen scoring and the random streams are unchanged,
    so the best-seen value is bit-identical to the source kernel.
  - t0_for takes the D-QUBO S4 multiplier as an argument (H5); default = DQUBO_T0_S4 = 1e-4 as the source.
  - initial_state has the H4 "consistent" D-QUBO start (feasible_random x, y = e_{w.x}).
  - Inst.from_file reads with the copied parser (no histmem import).
"""
from __future__ import annotations

from pathlib import Path

import numba as nb
import numpy as np

ARMS = ("filter", "dqubo")
A_FILTER, A_DQUBO = 0, 1
ALPHA = BETA = 2.0
SCHEDULES = ("S1", "S2", "S3", "S4")
DQUBO_T0_S4 = 1e-4
PSWAP_V3 = 0.5
QKP_DIR = Path(__file__).resolve().parents[4] / "09_next_phase/benchmarks/qkp_billionnet_soutif"
OPTIMA = Path(__file__).resolve().parents[4] / "09_next_phase/items_work/09/optima.json"
INSTANCES = [f"jeu_100_{d}_{i}.txt" for d in (25, 50, 75, 100) for i in range(1, 11)]


def parse(text: str):
    lines = [ln.strip() for ln in text.splitlines()]
    name = lines[0]
    t = " ".join(lines[1:]).split()
    n = int(t[0])
    pos = 1
    p = np.array(t[pos:pos + n], dtype=np.float64); pos += n
    P = np.zeros((n, n))
    for i in range(n - 1):
        P[i, i + 1:] = np.array(t[pos:pos + n - 1 - i], dtype=np.float64); pos += n - 1 - i
    ctype, C = int(t[pos]), float(t[pos + 1]); pos += 2
    w = np.array(t[pos:pos + n], dtype=np.float64)
    if ctype != 0 or len(w) != n:
        raise ValueError("QKP: expected constraint type 0 and n weights")
    return name, n, p, P, C, w


class Inst:
    """Dense symmetric profit matrix Ps (diagonal = linear profits), integer weights w, capacity C."""

    def __init__(self, name, p, P_upper, w, C):
        self.name = name
        self.n = len(p)
        self.Ps = np.asarray(P_upper, np.float64) + np.asarray(P_upper, np.float64).T
        np.fill_diagonal(self.Ps, p)
        self.p = np.asarray(p, np.float64)
        self.off = self.Ps - np.diag(self.p)
        self.w = np.asarray(w, np.int64)
        self.C = int(C)

    @classmethod
    def from_file(cls, path):
        nm, n, p, P, C, w = parse(Path(path).read_text(encoding="utf-8", errors="replace"))
        return cls(nm, p, np.triu(P, 1), w, C)

    def profit(self, x):
        x = np.asarray(x, np.float64)
        return float(self.p @ x + 0.5 * x @ self.off @ x)


def load(name: str) -> Inst:
    return Inst.from_file(QKP_DIR / name)


def dqubo_energy(inst: Inst, x, y, alpha=ALPHA, beta=BETA):
    x = np.asarray(x, np.float64)
    k = np.arange(1, inst.C + 1)
    S = inst.w @ x - k @ np.asarray(y, np.float64)
    return -inst.profit(x) + alpha * (1.0 - np.sum(y)) ** 2 + beta * S ** 2


@nb.njit(cache=True)
def _flip_field(off, x, h, i, s):
    x[i] += s
    for j in range(h.shape[0]):
        h[j] += s * off[j, i]


@nb.njit(cache=True)
def _run(arm, p, off, w, C, temps, x, y, rng_u, rng_i, rng_j, rng_m, pswap, alpha, beta):
    """One SA run in place from (x, y). Returns (best feasible profit seen, filter rejections, final-state feasible
    profit, profit of the min-energy state seen if feasible); -1 marks 'no feasible value'."""
    n = p.shape[0]
    h = np.zeros(n)
    for j in range(n):
        if x[j]:
            for l in range(n):
                h[l] += off[l, j]
    W = 0
    prof = 0.0
    for j in range(n):
        if x[j]:
            W += w[j]
            prof += p[j] + 0.5 * h[j]
    nv = n + (C if arm == A_DQUBO else 0)
    S = 0.0
    Y = 0.0
    if arm == A_DQUBO:
        S = W
        for k in range(C):
            if y[k]:
                S -= k + 1
                Y += 1.0
    best = prof if W <= C else -1.0
    # energy tracking for the H3 min-energy scorer (D-QUBO energy; filter energy = -profit if feasible else 0)
    if arm == A_DQUBO:
        E = -prof + alpha * (1.0 - Y) ** 2 + beta * S * S
    else:
        E = -prof if W <= C else 0.0
    Emin = E
    minE_prof = prof if W <= C else -1.0
    rej = 0
    L = temps.shape[0]
    for t in range(L):
        T = temps[t]
        v = rng_i[t] % nv
        if arm == A_FILTER and rng_m[t] < pswap:
            i = v
            j = rng_j[t] % n
            if x[i] == x[j]:
                continue
            if x[i] == 0:
                i, j = j, i
            Wn = W - w[i] + w[j]
            if Wn > C:
                rej += 1
                continue
            dprof = -(p[i] + h[i]) + (p[j] + h[j] - off[j, i])
            dE = -dprof if W <= C else -(prof + dprof)
            if dE <= 0.0 or rng_u[t] < np.exp(-dE / T):
                _flip_field(off, x, h, i, -1)
                _flip_field(off, x, h, j, 1)
                W = Wn
                prof += dprof
                E += dE
                if W <= C and prof > best:
                    best = prof
                if E < Emin:
                    Emin = E
                    minE_prof = prof if W <= C else -1.0
            continue
        if v < n:
            s = 1 - 2 * x[v]
            Wn = W + s * w[v]
            dprof = s * (p[v] + h[v])
            if arm == A_FILTER:
                if Wn > C:
                    rej += 1
                    continue
                dE = -dprof if W <= C else -(prof + dprof)
            else:
                Sn = S + s * w[v]
                dE = -dprof + beta * (Sn * Sn - S * S)
            if dE <= 0.0 or rng_u[t] < np.exp(-dE / T):
                _flip_field(off, x, h, v, s)
                W = Wn
                prof += dprof
                E += dE
                if arm == A_DQUBO:
                    S += s * w[v]
                if W <= C and prof > best:
                    best = prof
                if E < Emin:
                    Emin = E
                    minE_prof = prof if W <= C else -1.0
        else:
            k = v - n
            s = 1 - 2 * y[k]
            Sn = S - s * (k + 1)
            Yn = Y + s
            dE = beta * (Sn * Sn - S * S) + alpha * ((1.0 - Yn) ** 2 - (1.0 - Y) ** 2)
            if dE <= 0.0 or rng_u[t] < np.exp(-dE / T):
                y[k] += s
                S = Sn
                Y = Yn
                E += dE
                if E < Emin:
                    Emin = E
                    minE_prof = prof if W <= C else -1.0
    final = prof if W <= C else -1.0
    return best, rej, final, minE_prof


def temps(schedule: str, T0: float, L: int = 1000):
    if schedule in ("S1", "S2", "S4"):
        Te = T0 / 1000.0
    elif schedule == "S3":
        Te = T0 / 30.0
    else:
        raise ValueError(schedule)
    if schedule == "S2":
        return np.linspace(T0, Te, L)
    return T0 * (Te / T0) ** (np.arange(L) / (L - 1))


def feasible_random(inst: Inst, rng):
    x = (rng.random(inst.n) < 0.5).astype(np.int64)
    on = list(rng.permutation(np.flatnonzero(x)))
    while inst.w @ x > inst.C:
        x[on.pop()] = 0
    return x


def t0_for(inst: Inst, arm: str, schedule: str, seed, samples: int = 1000, alpha=ALPHA, beta=BETA,
           dqubo_mult: float = DQUBO_T0_S4):
    if schedule == "S4":
        base = t0_for(inst, arm, "S1", seed, samples, alpha, beta)
        return dqubo_mult * base if arm == "dqubo" else base
    if schedule == "S3":
        return 10.0 * float(np.mean(np.abs(inst.p)))
    rng = np.random.default_rng(seed)
    m = 0.0
    k = np.arange(1, inst.C + 1)
    for _ in range(samples):
        if arm == "filter":
            x = feasible_random(inst, rng)
            i = rng.integers(inst.n)
            x2 = x.copy(); x2[i] ^= 1
            if inst.w @ x2 > inst.C:
                continue
            m = max(m, abs(inst.profit(x2) - inst.profit(x)))
        else:
            x = (rng.random(inst.n) < 0.5).astype(np.int64)
            y = (rng.random(inst.C) < 0.5).astype(np.int64)
            v = rng.integers(inst.n + inst.C)
            S = inst.w @ x - k @ y
            Y = y.sum()
            if v < inst.n:
                s = 1 - 2 * x[v]
                dprof = s * (inst.p[v] + inst.off[v] @ x)
                dE = -dprof + beta * ((S + s * inst.w[v]) ** 2 - S ** 2)
            else:
                kk = v - inst.n
                s = 1 - 2 * y[kk]
                dE = beta * ((S - s * (kk + 1)) ** 2 - S ** 2) + alpha * ((1 - Y - s) ** 2 - (1 - Y) ** 2)
            m = max(m, abs(dE))
    return m


def initial_state(inst: Inst, arm: str, seed, init: str = "bernoulli"):
    rng = np.random.default_rng(seed)
    if arm == "filter":
        return feasible_random(inst, rng), np.zeros(1, np.int64)
    if init == "consistent":
        x = feasible_random(inst, rng)
        y = np.zeros(inst.C, np.int64)
        wx = int(inst.w @ x)
        if 1 <= wx <= inst.C:
            y[wx - 1] = 1
        return x, y
    x = (rng.random(inst.n) < 0.5).astype(np.int64)
    y = (rng.random(inst.C) < 0.5).astype(np.int64)
    return x, y


def run_one(inst: Inst, arm: str, T: np.ndarray, x0, y0, seed, pswap=0.0, alpha=ALPHA, beta=BETA):
    rng = np.random.default_rng(seed)
    nv = inst.n + (inst.C if arm == "dqubo" else 0)
    rng_i = rng.integers(0, nv, size=T.shape[0]).astype(np.int64)
    rng_u = rng.random(T.shape[0])
    rng_j = rng.integers(0, inst.n, size=T.shape[0]).astype(np.int64)
    rng_m = rng.random(T.shape[0])
    x, y = x0.copy(), y0.copy()
    return _run(A_FILTER if arm == "filter" else A_DQUBO, inst.p, inst.off, inst.w, inst.C, T, x, y,
                rng_u, rng_i, rng_j, rng_m, float(pswap), float(alpha), float(beta))


def seed_of(*parts) -> list:
    return [20261113, *parts]
