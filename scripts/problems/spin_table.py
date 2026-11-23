"""P5.03: spin counts, coupling range and per-machine fit flags for the mapped problem families.

Counts come from the mappings in this folder (maxcut.py, maxsat.py, colouring.py). tests/hw/test_spin_table.py checks
the SAT and colouring counts against the qubo-bridge code and the Max-Cut counts against the G-set headers.

Machine capacities are working assumptions, not measurements (see MACHINE_NOTES). Regenerate with
`python -m scripts.problems.spin_table` from the worktree root.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from . import maxcut as mc
from .colouring import Colouring
from .maxsat import MaxSat

OUT_CSV = Path(__file__).resolve().parent / "spin_table.csv"

OURS_SPINS = 256  # monolithic KIM-F crossbar; P3.09 synthesis point N = 256 [U], pending P1/P2
B1_TILE = 32  # Yin 2024 32x32 1FeFET1R array (P0.07)
B2_VARS = 100  # HyCiM 16x100 array: 100 variable columns, 16 filter rows (PLAN.md, B2 row)
B3_COUPLING_BITS = 16  # Fujitsu DA digital SRAM couplings (IMPL_PLAN P4.03)

MACHINE_NOTES = {
    "fit_ours": f"monolithic array, capacity {OURS_SPINS} spins [U]",
    "fit_b1": f"{B1_TILE}x{B1_TILE} tiles, dense n x n tiled as ceil(n/{B1_TILE})^2 tiles (tiling charged)",
    "fit_b2": f"{B2_VARS} variable columns (HyCiM 16x100); QKP-only machine, spin families not run on it",
    "fit_b3": f"digital all-to-all, fits if integer couplings <= {B3_COUPLING_BITS} bits",
}

FIELDS = [
    "family", "instance", "logical_vars", "spins", "extra_spins", "coupling_min", "coupling_max",
    "coupling_bits", "b1_tiles", "fit_ours", "fit_b1", "fit_b2", "fit_b3",
]


def random_ksat(nv: int, m: int, k: int, seed: int) -> MaxSat:
    rng = np.random.default_rng(seed)
    clauses = []
    for _ in range(m):
        variables = rng.choice(nv, size=k, replace=False) + 1
        signs = rng.choice([-1, 1], size=k)
        clauses.append([int(v * s) for v, s in zip(variables, signs)])
    return MaxSat(f"ksat{k}_n{nv}_m{m}_s{seed}", nv, clauses)


def random_colouring(n: int, p: float, k: int, seed: int) -> Colouring:
    rng = np.random.default_rng(seed)
    iu, ju = np.triu_indices(n, 1)
    keep = rng.random(len(iu)) < p
    edges = np.stack([iu[keep], ju[keep]], axis=1)
    return Colouring(f"gnp{n}_p{p}_k{k}_s{seed}", n, edges, k)


def problem_instances():
    """(family, problem, logical_vars) for every row of the table."""
    rows = []
    for name in ("G1", "G6", "G11", "G14"):
        g = mc.load_gset(name)
        rows.append(("maxcut", g, g.n))
    rows.append(("maxcut", mc.torus_pm1(8, 1), 64))
    rows.append(("maxcut", mc.random_graph(100, 400, 2, pm1=True), 100))
    for nv in (20, 50, 100):
        sat = random_ksat(nv, round(4.26 * nv), 3, seed=nv)
        rows.append(("maxsat3", sat, nv))
    sat4 = random_ksat(20, 40, 4, seed=7)
    rows.append(("maxsat4", sat4, 20))
    for n, k in ((20, 3), (50, 4), (100, 4)):
        col = random_colouring(n, 0.3, k, seed=n)
        rows.append(("colouring", col, n))
    return rows


def dense_qubo(problem) -> tuple[np.ndarray, np.ndarray]:
    """Upper-triangular coupling matrix (zero diagonal) and linear vector c, both integer-valued."""
    if isinstance(problem, mc.MaxCut):
        Q, c, _ = problem.to_qubo()
        return np.triu(Q, 1), c
    (I, J, V), c, _ = problem.to_qubo()
    n = len(c)
    Q = np.zeros((n, n))
    np.add.at(Q, (np.minimum(I, J), np.maximum(I, J)), V)
    return np.triu(Q, 1), c


def signed_bits(max_abs: int) -> int:
    return max(1, math.ceil(math.log2(max_abs + 1))) + 1


def fit_flags(spins: int, coupling_bits: int) -> dict:
    b1_tiles = math.ceil(spins / B1_TILE) ** 2
    return {
        "b1_tiles": b1_tiles,
        "fit_ours": "fits" if spins <= OURS_SPINS else "does_not_fit",
        "fit_b1": "fits" if spins <= B1_TILE else f"tiled:{b1_tiles}",
        "fit_b2": "fits" if spins <= B2_VARS else "does_not_fit",
        "fit_b3": "fits" if coupling_bits <= B3_COUPLING_BITS else "does_not_fit",
    }


def table_row(family: str, problem, logical_vars: int) -> dict:
    Q, c = dense_qubo(problem)
    spins = len(c)
    values = np.concatenate([Q[np.triu_indices(spins, 1)], c])
    if not np.allclose(values, np.round(values)):
        raise ValueError(f"{problem.name}: non-integer couplings")
    values = np.round(values).astype(np.int64)
    coupling_min = int(min(values.min(), 0))
    coupling_max = int(max(values.max(), 0))
    bits = signed_bits(int(np.abs(values).max()))
    row = {
        "family": family,
        "instance": problem.name,
        "logical_vars": logical_vars,
        "spins": spins,
        "extra_spins": spins - logical_vars,
        "coupling_min": coupling_min,
        "coupling_max": coupling_max,
        "coupling_bits": bits,
    }
    row.update(fit_flags(spins, bits))
    return row


def build_table() -> list[dict]:
    return [table_row(family, problem, logical) for family, problem, logical in problem_instances()]


def write_table(path: Path = OUT_CSV) -> list[dict]:
    rows = build_table()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    for row in write_table():
        print(row["family"], row["instance"], row["spins"], row["coupling_bits"], row["fit_ours"], row["fit_b1"],
              row["fit_b2"], row["fit_b3"])
