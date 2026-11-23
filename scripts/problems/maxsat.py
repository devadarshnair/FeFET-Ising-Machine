"""PROVENANCE: copied (not imported) from sw_ref_wt/qubo, branch study/qubo-bridge, commit 19619e4782c8086783fb4db629b4a8b665c7c931,
file histmem/instances/external/cnf.py. The worktree was only read. Local edits: package-relative imports replaced by
scripts/problems/_qubo_base.py (copy of Family/onehot_penalty/merge/read_text from external/__init__.py); the
qubo_bridge-dependent to_graph/row_fields are omitted (Max-Cut bridging is not needed for the machines here).

SAT / MaxSAT (.cnf DIMACS, .wcnf old "p wcnf n m top" and new 2022+ "h"/weight formats) as a penalty QUBO.

A clause is violated iff every literal is false. With z_l = 1 - y_l (y_l the literal's value: x_v or 1 - x_v) the
violation indicator is prod_l z_l. Clauses of length <= 2 are quadratic. Longer clauses (audit T9: the cores are
pairwise) use Rosenberg's one-ancilla-per-step reduction: a_1 = z_1 z_2, a_t = a_{t-1} z_{t+2}, enforced by
  P(u, v, a) = u v - 2 u a - 2 v a + 3 a   (>= 0, and 0 iff a = u v),
so a k-literal clause adds k - 2 ancillas and the term a_{k-2} z_k + sum P (all weighted by the clause weight w).
Minimised over the ancillas, the gadget equals w * [clause violated] exactly (tested exhaustively). For 3-SAT that
is one ancilla per clause. Variables: 0..nv-1 = SAT variables, nv.. = ancillas.

Family objective = total weight of violated soft clauses (unit weights for .cnf: #unsatisfied clauses), minimised;
feasible = every hard clause holds (always true for .cnf). Hard clauses get weight `hard` (default: 1 + total soft
weight). violations = #violated hard clauses.
"""

from __future__ import annotations

import numpy as np

from ._qubo_base import Family, read_text


def parse(text: str):
    """-> (nv, clauses [list of int lists], weights [float or None for hard]). A file without a "p" line is read as
    the 2022+ MaxSAT Evaluation wcnf format (leading weight or "h" on every clause)."""
    nv, top, clauses, weights, fmt = 0, None, [], [], None  # no "p" line = the 2022+ wcnf format
    toks: list[str] = []
    for line in text.splitlines():
        t = line.split()
        if not t or t[0] in ("c", "%"):
            if t and t[0] == "%":
                break
            continue
        if t[0] == "p":
            fmt, nv = t[1], int(t[2])
            if fmt == "wcnf" and len(t) >= 5:
                top = float(t[4])
            continue
        toks.extend(t)
        if toks[-1] != "0":
            continue
        if fmt == "cnf" and toks[0] != "h":
            w, lits = 1.0, toks[:-1]
        elif toks[0] == "h":
            w, lits = None, toks[1:-1]
        else:
            w, lits = float(toks[0]), toks[1:-1]
            if top is not None and w >= top:
                w = None
        lits = [int(v) for v in lits]
        if lits:
            clauses.append(lits); weights.append(w)
            nv = max(nv, max(abs(v) for v in lits))
        toks = []
    return nv, clauses, weights


def _lit_z(lit: int):
    """z = 1 - literal value, as (var, coeff, const): z = const + coeff * x_var."""
    v = abs(lit) - 1
    return (v, -1.0, 1.0) if lit > 0 else (v, 1.0, 0.0)


class MaxSat(Family):
    family = "sat"
    sense = "min"

    def __init__(self, name: str, nv: int, clauses, weights=None):
        super().__init__(name)
        self.nv = int(nv)
        self.clauses = [list(c) for c in clauses]
        self.weights = list(weights) if weights is not None else [1.0] * len(self.clauses)
        self.n_anc = sum(max(0, len(c) - 2) for c in self.clauses)
        self.n_vars = self.nv + self.n_anc

    @classmethod
    def from_file(cls, path, name: str | None = None):
        nv, C, W = parse(read_text(path))
        return cls(name or str(path), nv, C, W)

    def _weights(self, hard):
        soft = sum(w for w in self.weights if w is not None)
        hw = (1.0 + soft) if hard is None else float(hard)
        return [hw if w is None else w for w in self.weights]

    def to_qubo(self, hard: float | None = None):
        n = self.n_vars
        c, c0 = np.zeros(n), 0.0
        I, J, V = [], [], []

        def add_lin(e, w):  # e = (var, coeff, const) ; adds w * e
            nonlocal c0
            c[e[0]] += w * e[1]
            c0 += w * e[2]

        def add_prod(e, f, w):  # w * e * f for affine e, f in distinct vars
            nonlocal c0
            (u, a, b), (v, p, q) = e, f
            if u == v:  # same variable: x^2 = x
                c[u] += w * (a * p + a * q + b * p)
                c0 += w * b * q
                return
            I.append(u); J.append(v); V.append(w * a * p)
            c[u] += w * a * q
            c[v] += w * b * p
            c0 += w * b * q

        anc = self.nv
        for lits, w in zip(self.clauses, self._weights(hard)):
            zs = [_lit_z(l) for l in lits]
            if len(zs) == 1:
                add_lin(zs[0], w)
            elif len(zs) == 2:
                add_prod(zs[0], zs[1], w)
            else:
                prev = zs[0]
                for t in range(1, len(zs) - 1):
                    a = (anc, 1.0, 0.0)
                    # w * P(prev, z_t, a) = w (prev z_t - 2 prev a - 2 z_t a + 3 a)
                    add_prod(prev, zs[t], w)
                    add_prod(prev, a, -2.0 * w)
                    add_prod(zs[t], a, -2.0 * w)
                    add_lin(a, 3.0 * w)
                    prev, anc = a, anc + 1
                add_prod(prev, zs[-1], w)
        return (np.array(I, np.int64), np.array(J, np.int64), np.array(V, np.float64)), c, c0

    def unsat(self, xv) -> np.ndarray:
        xv = np.asarray(xv, np.int64)
        return np.array([not any((xv[abs(l) - 1] == 1) == (l > 0) for l in cl) for cl in self.clauses], bool)

    def decode(self, x) -> dict:
        u = self.unsat(np.asarray(x)[:self.nv])
        hard = np.array([w is None for w in self.weights], bool)
        soft_w = np.array([0.0 if w is None else w for w in self.weights])
        obj = float(soft_w[u & ~hard].sum())
        return {"objective": int(obj) if obj.is_integer() else obj, "feasible": not (u & hard).any(),
                "violations": int((u & hard).sum()), "unsat_clauses": int(u.sum())}
