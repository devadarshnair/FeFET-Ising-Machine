"""H6 fresh colouring families (prereg/hw/H6_followup.md section 3): planted k-colourable graphs, so the optimum energy is 0
(a proper colouring exists by construction) and success = reaching a proper colouring, without enumeration.

Generator: vertex v gets the planted colour v mod k after a seeded permutation (balanced classes); every pair of vertices with
DIFFERENT planted colours becomes an edge with probability p = deg / (n (k - 1) / k), so the expected degree is `deg`.
Pure numpy, seeded; nothing here is a machine model.
"""
from __future__ import annotations

import numpy as np

from scripts.problems.colouring import Colouring

FAMILIES = {                      # family -> (n vertices, k colours, expected degree); spins = n x k
    "col3p": (40, 3, 4.5),        # 120 spins, near the 3-colouring hardness region (c ~ 4.7)
    "col4p": (30, 4, 8.0),        # 120 spins, a second family: 4 colours, denser
}


def planted_colouring(n: int, k: int, deg: float, seed: int) -> Colouring:
    rng = np.random.default_rng([20261117, n, k, seed])
    colour = rng.permutation(n) % k
    iu, ju = np.triu_indices(n, 1)
    cross = colour[iu] != colour[ju]
    p = deg / (n * (k - 1) / k)
    keep = cross & (rng.random(len(iu)) < p)
    edges = np.stack([iu[keep], ju[keep]], axis=1)
    return Colouring(f"planted{n}_k{k}_d{deg:g}_s{seed}", n, edges, k, chi=k)


def problem(family: str, key: str) -> Colouring:
    n, k, deg = FAMILIES[family]
    return planted_colouring(n, k, deg, int(key))
