"""P2.01: lane-enable mask (FIXES G6). Padded lanes never win the selection; n = 200 runs on N = 256."""
import numpy as np

from instances import maxcut_qubo, qubo_instance, random_graph, random_qubo
from tim_golden import Machine, objective, pad_instance

STEPS = 100_000


def _run_masked(n_act, n_tot, steps, seed):
    d, P = random_qubo(n_act, seed, pmax=3, dmax=3)
    base = qubo_instance(d, P, seed=seed, steps=steps, t_start=2.0, t_end=None, deoff=1)
    inst = pad_instance(base, n_tot)
    inst.check_widths()
    m = Machine(inst)
    picks = []
    for _ in range(steps):
        picks.append(int(m.step().split()[1]))
    return inst, m, np.array(picks)


def test_padded_lanes_never_selected_1e5_steps():
    inst, m, picks = _run_masked(12, 16, STEPS, seed=3)
    assert (picks < 12).all()
    assert (picks >= 0).sum() > STEPS // 2           # the machine really flips
    assert not m.x[12:].any()
    assert m.f == objective(inst, m.x)


def test_n200_on_N256_runs():
    inst, m, picks = _run_masked(200, 256, 3000, seed=5)
    assert (picks < 200).all() and (picks >= 0).any()
    assert not m.x[200:].any() and m.f == objective(inst, m.x)
    assert np.array_equal(m.h, inst.d + inst.P @ m.x)


def test_all_enabled_mask_equals_no_mask():
    d, P = maxcut_qubo(16, random_graph(16, 0.3, 1))
    a = qubo_instance(d, P, seed=9, steps=500, t_start=1.0, t_end=0.1, deoff=2)
    b = pad_instance(a, 16)
    assert Machine(a).run().trace == Machine(b).run().trace
