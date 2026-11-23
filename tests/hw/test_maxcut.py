import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.problems import maxcut as mc  # noqa: E402


def test_g1_loads_with_reference():
    g = mc.load_gset("G1")
    assert g.n == 800 and g.m == 19176
    assert g.best_known == 11624


def test_qubo_energy_is_minus_cut():
    rng = np.random.default_rng(0)
    for g in (mc.load_gset("G1"), mc.load_gset("G6"), mc.torus_pm1(8, 1), mc.random_graph(50, 200, 2, pm1=True)):
        Q, c, c0 = g.to_qubo()
        for _ in range(100):
            x = rng.integers(0, 2, g.n)
            assert abs(float(x @ Q @ x + c @ x + c0) + g.cut(x)) < 1e-9


def test_degree_table(tmp_path):
    rows = mc.degree_table(["G1", "G11", "G14"], tmp_path / "t.csv")
    assert rows[0]["max_deg"] == 67 and rows[1]["max_deg"] == 4
