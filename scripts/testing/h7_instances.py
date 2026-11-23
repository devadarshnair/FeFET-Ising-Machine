"""H7 colouring instances (prereg/hw/H7_scaleup.md section 3), all generated, none downloaded.

1. Planted k-colourable families at 240 / 480 / 960 spins (n vertices x k colours): the H6 generator (h6_instances.planted_colouring),
   same degrees as H6 col3p / col4p, larger n. Optimum energy 0 by construction.
2. 'dimacs': DIMACS-benchmark graphs rebuilt from their mathematical definition, so no benchmark file and no licence question:
   queenN_N (N x N board, two cells adjacent iff same row, column or diagonal; Mehrotra-Trick 1996 / DIMACS 1993 set) and
   mycielK (Mycielski construction applied to C5; myciel3 = Groetzsch graph). k = the known chromatic number, so a proper
   k-colouring exists and the target energy is 0. tests/hw/test_h7.py checks vertex/edge counts against the DIMACS headers and,
   when a local copy of the DIMACS files exists (05_external_tools, read only, never executed), the identical edge set.
"""
from __future__ import annotations

import numpy as np

from scripts.problems.colouring import Colouring
from h6_instances import planted_colouring

from plan_h7 import DIMACS, PLANTED  # noqa: E402  (size tables live in the design module, no machine imports there)


def queen_edges(N: int) -> np.ndarray:
    r, c = np.divmod(np.arange(N * N), N)
    iu, ju = np.triu_indices(N * N, 1)
    adj = (r[iu] == r[ju]) | (c[iu] == c[ju]) | (np.abs(r[iu] - r[ju]) == np.abs(c[iu] - c[ju]))
    return np.stack([iu[adj], ju[adj]], axis=1)


def mycielskian(n: int, edges: np.ndarray) -> tuple[int, np.ndarray]:
    """Vertices 0..n-1 (original), n..2n-1 (shadows u_i, adjacent to the neighbours of v_i), 2n (w, adjacent to every u_i)."""
    out = [tuple(e) for e in edges]
    out += [(int(v), n + int(u)) for u, v in edges] + [(int(u), n + int(v)) for u, v in edges]
    out += [(n + i, 2 * n) for i in range(n)]
    E = np.unique(np.sort(np.array(out, np.int64), axis=1), axis=0)
    return 2 * n + 1, E


def myciel_edges(K: int) -> tuple[int, np.ndarray]:
    n, E = 5, np.array([(i, (i + 1) % 5) for i in range(5)], np.int64)       # C5 = M3; myciel3 = M4 = mycielskian(C5)
    E = np.sort(E, axis=1)
    for _ in range(K - 2):
        n, E = mycielskian(n, E)
    return n, E


def dimacs_graph(name: str) -> tuple[int, np.ndarray]:
    if name.startswith("queen"):
        N = int(name[5:].split("_")[0])
        return N * N, queen_edges(N)
    if name.startswith("myciel"):
        return myciel_edges(int(name[6:]))
    raise ValueError(name)


def problem(family: str, key: str) -> Colouring:
    if family in PLANTED:
        n, k, deg = PLANTED[family]
        return planted_colouring(n, k, deg, int(key))
    if family == "dimacs":
        n, E = dimacs_graph(key)
        chi = DIMACS[key][2]
        return Colouring(key, n, E, chi, chi=chi)
    raise ValueError(family)


def spins(family: str, key: str) -> int:
    p = problem(family, key)
    return p.n * p.k
