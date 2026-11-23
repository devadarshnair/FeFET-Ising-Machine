"""PROVENANCE: copied (not imported) from sw_ref_wt/qubo, branch study/qubo-bridge, commit 19619e4782c8086783fb4db629b4a8b665c7c931,
file histmem/instances/external/dimacs_col.py. The worktree was only read. Local edits: package-relative imports replaced by
scripts/problems/_qubo_base.py (copy of Family/onehot_penalty/merge/read_text from external/__init__.py); the
qubo_bridge-dependent to_graph/row_fields are omitted (Max-Cut bridging is not needed for the machines here).

DIMACS graph colouring (.col, "p edge n m" / "e u v") as a k-colour penalty QUBO (Lucas 2014 section 6.1).

x_{v,c} = 1 iff vertex v has colour c; variable index v * k + c.
  H = A sum_v (1 - sum_c x_{v,c})^2 + B sum_{(u,v) in E} sum_c x_{u,c} x_{v,c}
Feasible = every vertex has exactly one colour. Family objective = number of monochromatic edges (minimised; 0 =
proper k-colouring). violations = number of vertices whose one-hot row is broken.
"""

from __future__ import annotations

import numpy as np

from ._qubo_base import Family, merge, onehot_penalty, read_text


def parse_col(text: str):
    n, edges, m_header = None, [], None
    for line in text.splitlines():
        t = line.split()
        if not t or t[0] == "c":
            continue
        if t[0] == "p":
            n, m_header = int(t[2]), int(t[3])
        elif t[0] == "e":
            u, v = int(t[1]) - 1, int(t[2]) - 1
            if u != v:
                edges.append((min(u, v), max(u, v)))
    if n is None:
        raise ValueError("DIMACS .col: no 'p edge' line")
    E = np.unique(np.array(edges, dtype=np.int64).reshape(-1, 2), axis=0)
    return n, E, m_header


class Colouring(Family):
    family = "col"
    sense = "min"

    def __init__(self, name: str, n: int, edges, k: int, chi: int | None = None):
        super().__init__(name)
        self.n, self.edges, self.k = int(n), np.asarray(edges, np.int64).reshape(-1, 2), int(k)
        self.n_vars = self.n * self.k
        if chi is not None and k >= chi:
            self.ref = {"value": 0, "sense": "min", "kind": "optimal",
                        "source": f"chromatic number {chi}"}

    @classmethod
    def from_file(cls, path, k: int, name: str | None = None, chi: int | None = None):
        n, E, _ = parse_col(read_text(path))
        return cls(name or str(path), n, E, k, chi)

    def to_qubo(self, A: float = 1.0, B: float = 1.0):
        k = self.k
        oh = onehot_penalty([np.arange(v * k, v * k + k) for v in range(self.n)], A, self.n_vars)
        u, v = self.edges[:, 0], self.edges[:, 1]
        I = (u[:, None] * k + np.arange(k)).ravel()
        J = (v[:, None] * k + np.arange(k)).ravel()
        conf = ((I, J, np.full(len(I), float(B))), np.zeros(self.n_vars), 0.0)
        return merge(oh, conf)

    def decode(self, x) -> dict:
        X = np.asarray(x, np.int64).reshape(self.n, self.k)
        bad = X.sum(1) != 1
        conflicts = int(np.sum(X[self.edges[:, 0]] * X[self.edges[:, 1]]))
        colour = np.where(bad, -1, X.argmax(1))
        return {"objective": conflicts, "feasible": not bad.any(), "violations": int(bad.sum()),
                "conflicts": conflicts, "colour": colour}

    def encode(self, colour) -> np.ndarray:
        x = np.zeros((self.n, self.k), np.int8)
        x[np.arange(self.n), np.asarray(colour)] = 1
        return x.ravel()


def greedy_colouring(n: int, edges) -> np.ndarray:
    """Largest-degree-first greedy colouring (for acceptance checks)."""
    adj = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v); adj[v].append(u)
    col = -np.ones(n, np.int64)
    for v in sorted(range(n), key=lambda t: -len(adj[t])):
        used = {col[w] for w in adj[v]}
        col[v] = next(c for c in range(n) if c not in used)
    return col
