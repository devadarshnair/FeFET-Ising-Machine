"""P4.06 A1: B2 HyCiM hardware filter equals the exact knapsack check at sigma = 0; cost wiring."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import hycim as hc  # noqa: E402
import hycim_b2 as b2  # noqa: E402


@pytest.mark.parametrize("name", ["jeu_100_25_1.txt", "jeu_100_75_1.txt"])
@pytest.mark.parametrize("state_set", ["S_bern", "S_prop"])
def test_filter_exact_at_sigma0(name, state_set):
    inst = hc.load(name)
    X = b2.state_sets(inst, 10_000, hc.seed_of(406, 0))[state_set]
    assert np.array_equal(b2.Filter.build(inst).decide(X), X @ inst.w <= inst.C)


def test_boundary_states_exact():
    inst = hc.load("jeu_100_25_1.txt")
    f = b2.Filter.build(inst)
    order = np.argsort(inst.w)
    x = np.zeros(inst.n, np.int64)
    for i in order:
        x[i] = 1
        if inst.w @ x >= inst.C:
            break
    assert f.decide(x[None])[0] == (inst.w @ x <= inst.C)


def test_digits_encode_weights():
    for w in range(0, 65):
        d = b2.digits(w, b2.ROWS)
        assert d.sum() == w and d.max() <= b2.MAXD


def test_write_verify_costed():
    att = b2.wv_attempts()
    assert att[0] == 1.0 and all(a > 1.0 for a in att[1:])
    pc = b2.program_cost(hc.load("jeu_100_25_1.txt"))
    assert pc["e_program_fJ"] > 0 and pc["t_program_us"] > 0 and pc["cells"] == b2.ROWS * b2.COLS * 2


def test_energy_blocks_finite():
    inst = hc.load("jeu_100_25_1.txt")
    x = hc.feasible_random(inst, np.random.default_rng(0))
    e = b2.run_energy(inst, 1000, x)
    assert all(np.isfinite(v) and v >= 0 for v in e.values()) and e["filter"] > 0
