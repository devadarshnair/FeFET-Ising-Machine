"""Max-Cut loaders (P5.01): Stanford G-set files (data only) and small the reference software study-style generators, plus the
Max-Cut -> QUBO map and a degree/weight table (feeds P3.06).

QUBO convention: minimise f(x) = sum_{i<j} Q_ij x_i x_j + sum_i c_i x_i with x in {0,1}^n, so that
f(x) = -cut(x) for every partition x (cut = sum over edges w_ij (x_i + x_j - 2 x_i x_j)).
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
BENCH = REPO.parents[1] / "05_external_tools/open_source_implementations/benchmarks_and_eval_tools/gset"
GSET_DIR = BENCH / "stanford_yyye_Gset"
BKS_CSV = BENCH / "gset_best_known_cuts_2026-10-17.csv"


class MaxCut:
    def __init__(self, name, n, edges, weights, best_known=None):
        self.name, self.n = name, int(n)
        self.edges = np.asarray(edges, np.int64).reshape(-1, 2)  # 0-based, i < j
        self.weights = np.asarray(weights, np.float64)
        self.best_known = best_known  # reference only, never a target

    @property
    def m(self):
        return len(self.edges)

    def cut(self, x):
        x = np.asarray(x, np.int64)
        d = x[self.edges[:, 0]] != x[self.edges[:, 1]]
        return float(self.weights[d].sum())

    def to_qubo(self):
        """-> (Q dense upper-triangular (n, n), c (n,), c0 = 0)."""
        Q = np.zeros((self.n, self.n))
        c = np.zeros(self.n)
        i, j = self.edges[:, 0], self.edges[:, 1]
        np.add.at(Q, (i, j), 2.0 * self.weights)
        np.add.at(c, i, -self.weights)
        np.add.at(c, j, -self.weights)
        return Q, c, 0.0

    def energy(self, x):
        Q, c, c0 = self.to_qubo()
        x = np.asarray(x, np.float64)
        return float(x @ Q @ x + c @ x + c0)

    def degree_stats(self):
        deg = np.zeros(self.n, np.int64)
        np.add.at(deg, self.edges[:, 0], 1)
        np.add.at(deg, self.edges[:, 1], 1)
        absw = np.zeros(self.n)
        np.add.at(absw, self.edges[:, 0], np.abs(self.weights))
        np.add.at(absw, self.edges[:, 1], np.abs(self.weights))
        return {"name": self.name, "n": self.n, "m": self.m, "min_deg": int(deg.min()), "max_deg": int(deg.max()),
                "mean_deg": round(float(deg.mean()), 3), "max_abs_w": float(np.abs(self.weights).max()),
                "max_weighted_deg": float(absw.max()), "best_known": self.best_known}


def best_known(name):
    with open(BKS_CSV) as f:
        for r in csv.DictReader(f):
            if r["graph"] == name and r["current_best_known"]:
                return int(float(r["current_best_known"]))
    return None


def load_gset(name, path=None):
    """G-set file: header "n m", then "u v w" (1-based). Pure text read; nothing is executed."""
    p = Path(path) if path else GSET_DIR / name
    lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
    n, m = (int(t) for t in lines[0].split()[:2])
    E, W = [], []
    for ln in lines[1:]:
        t = ln.split()
        if len(t) < 3:
            continue
        u, v = int(t[0]) - 1, int(t[1]) - 1
        E.append((min(u, v), max(u, v)))
        W.append(float(t[2]))
    if len(E) != m:
        raise ValueError(f"{name}: header says {m} edges, counted {len(E)}")
    return MaxCut(name, n, E, W, best_known(name))


def torus_pm1(L, seed=0):
    """L x L toroidal grid, +-1 weights (the reference software study torus family, degree 4)."""
    rng = np.random.default_rng(seed)
    E = set()
    for r in range(L):
        for c in range(L):
            a = r * L + c
            for b in (r * L + (c + 1) % L, ((r + 1) % L) * L + c):
                E.add((min(a, b), max(a, b)))
    E = sorted(E)
    return MaxCut(f"torus{L}", L * L, E, rng.choice([-1.0, 1.0], len(E)))


def random_graph(n, m, seed=0, pm1=False):
    """G-set-like G(n, m) random graph, unit or +-1 weights."""
    rng = np.random.default_rng(seed)
    E = set()
    while len(E) < m:
        u, v = rng.integers(0, n, 2)
        if u != v:
            E.add((int(min(u, v)), int(max(u, v))))
    E = sorted(E)
    w = rng.choice([-1.0, 1.0], len(E)) if pm1 else np.ones(len(E))
    return MaxCut(f"gnm{n}_{m}", n, E, w)


def degree_table(names, out_csv):
    rows = [load_gset(g).degree_stats() for g in names]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows
