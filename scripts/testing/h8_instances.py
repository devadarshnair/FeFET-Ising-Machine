"""H8 instances (prereg/hw/H8_full.md section 3), all generated or read from the already-vendored G-set, none downloaded.

Colouring (target energy 0 = a proper k-colouring; a proper colouring exists by construction or by the known chromatic number):
  planted   h6_instances.planted_colouring at 120 / 240 / 480 / 960 spins (core) and 2040 spins (full), H6 degrees, FRESH seeds.
  queenN_N, mycielK   rebuilt from their definitions (h7_instances), k = the known chromatic number (queen9_9 = 10, queen10_10 = 11).
  kneserN_K           Kneser graph KG(N, K): vertices = K-subsets of {1..N}, adjacent iff disjoint; chi = N - 2K + 2 (Lovasz 1978). Exact
                      chromatic number from a theorem, no file, no licence question. Hard for greedy / local search by construction.
Max-Cut: Stanford G-set names (read by machines.mapped -> load_maxcut), best-known cut from the vendored CSV.
"""
from __future__ import annotations

import itertools
import numpy as np


# planted family -> (vertices, colours, expected degree); spins = n x k. H6 degrees (3-col near the hardness region, 4-col denser).
PLANTED = {"p3n120": (40, 3, 4.5), "p3n240": (80, 3, 4.5), "p3n480": (160, 3, 4.5), "p3n960": (320, 3, 4.5), "p3n2040": (680, 3, 4.5),
           "p4n120": (30, 4, 8.0), "p4n240": (60, 4, 8.0), "p4n480": (120, 4, 8.0), "p4n960": (240, 4, 8.0), "p4n2040": (510, 4, 8.0)}
# graph name -> (vertices, k = chromatic number)
GRAPHS = {"myciel4": (23, 5), "myciel5": (47, 6), "myciel6": (95, 7), "myciel7": (191, 8),
          "queen5_5": (25, 5), "queen6_6": (36, 7), "queen7_7": (49, 7), "queen8_8": (64, 9), "queen9_9": (81, 10), "queen10_10": (100, 11),
          "kneser7_2": (21, 5), "kneser8_3": (56, 4), "kneser9_3": (84, 5), "kneser10_3": (120, 6), "kneser10_4": (210, 4)}
GRAPH_FAMILY = "dimacs8"                       # family label of every graph above (one job per graph, like H7 'dimacs')
FAMILIES_COLOURING = tuple(PLANTED) + (GRAPH_FAMILY,)


def _imports():
    """Lazy: the job generator only needs the size tables, and runs with `python -I` (repo root not on sys.path)."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for p in (str(root), str(Path(__file__).resolve().parent)):
        if p not in sys.path:
            sys.path.insert(0, p)


def kneser_edges(N: int, K: int) -> tuple[int, np.ndarray]:
    sets = [frozenset(c) for c in itertools.combinations(range(N), K)]
    E = [(i, j) for i in range(len(sets)) for j in range(i + 1, len(sets)) if not (sets[i] & sets[j])]
    return len(sets), np.asarray(E, np.int64).reshape(-1, 2)


def graph(name: str) -> tuple[int, np.ndarray]:
    if name.startswith("kneser"):
        N, K = (int(x) for x in name[6:].split("_"))
        return kneser_edges(N, K)
    _imports()
    from h7_instances import dimacs_graph
    return dimacs_graph(name)


def problem(family: str, key: str):
    _imports()
    from scripts.problems.colouring import Colouring
    from h6_instances import planted_colouring
    if family in PLANTED:
        n, k, deg = PLANTED[family]
        return planted_colouring(n, k, deg, int(key))
    if family == GRAPH_FAMILY:
        n, E = graph(key)
        k = GRAPHS[key][1]
        return Colouring(key, n, E, k, chi=k)
    raise ValueError(family)


def spins(family: str, key: str) -> int:
    if family in PLANTED:
        n, k, _ = PLANTED[family]
        return n * k
    n, k = GRAPHS[key]
    return n * k


def padded(spins_: int) -> int:
    return max(4, 1 << (spins_ - 1).bit_length())
