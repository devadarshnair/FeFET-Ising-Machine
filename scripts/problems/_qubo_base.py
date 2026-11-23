"""PROVENANCE: copied from sw_ref_wt/qubo (study/qubo-bridge, commit 19619e4782c8086783fb4db629b4a8b665c7c931),
histmem/instances/external/__init__.py (Family, onehot_penalty, merge, read_text). to_graph/row_fields and data-root
helpers dropped (they depend on qubo_bridge / the reference software study data layout)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


class Family:
    family = "qubo"
    sense = "min"
    n_vars = 0

    def __init__(self, name: str):
        self.name = name
        self.ref: dict | None = None

    def to_qubo(self, **pen):
        raise NotImplementedError

    def decode(self, x) -> dict:
        raise NotImplementedError

    def reference(self) -> dict | None:
        return self.ref


def onehot_penalty(groups, A: float, n: int):
    """A * sum_g (1 - sum_{k in g} x_k)^2 = A * sum_g (1 - sum x + 2 sum_{k<l} x_k x_l), as (i, j, v), c, c0."""
    I, J, V = [], [], []
    c = np.zeros(n)
    for grp in groups:
        grp = np.asarray(grp, np.int64)
        c[grp] -= A
        a, b = np.triu_indices(len(grp), 1)
        I.append(grp[a]); J.append(grp[b]); V.append(np.full(len(a), 2.0 * A))
    cat = (lambda L, t: np.concatenate(L).astype(t) if L else np.zeros(0, t))  # noqa: E731
    return (cat(I, np.int64), cat(J, np.int64), cat(V, np.float64)), c, A * len(groups)


def merge(*parts):
    """Sum several ((i, j, v), c, c0) terms."""
    I = np.concatenate([p[0][0] for p in parts])
    J = np.concatenate([p[0][1] for p in parts])
    V = np.concatenate([p[0][2] for p in parts])
    return (I, J, V), sum(p[1] for p in parts), float(sum(p[2] for p in parts))


def read_text(path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")
