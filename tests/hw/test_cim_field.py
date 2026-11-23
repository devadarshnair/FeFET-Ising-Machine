"""P2.03: CiM field path. b = 16, sigma = 0 is bit-exact; b = 4 error within 1/2 LSB x columns; noise seeded."""
import numpy as np
import pytest

from cim_field import CimCfg, CimField
from instances import maxcut_qubo, qubo_instance, random_graph, random_qubo
from tim_golden import Machine


def _states(n, count, seed):
    return np.random.default_rng(seed).integers(0, 2, size=(count, n))


@pytest.mark.parametrize("n", (16, 64, 256))
def test_b16_sigma0_equals_exact_field(n):
    d, P = random_qubo(n, 1, pmax=127, dmax=127)
    cf = CimField(CimCfg(adc_bits=16), P, d)
    assert cf.lsb == 1
    for x in _states(n, 50, n):
        assert np.array_equal(cf.field(x), d + P @ x)


def test_b16_machine_trace_bit_exact():
    d, P = maxcut_qubo(16, random_graph(16, 0.4, 2))
    inst = qubo_instance(d, P, seed=4, steps=2000, t_start=1.0, t_end=0.05, deoff=1)
    assert Machine(inst, cim=CimCfg(adc_bits=16)).run().trace == Machine(inst).run().trace


@pytest.mark.parametrize("n", (16, 64, 256))
def test_b4_error_within_half_lsb_times_columns(n):
    d, P = random_qubo(n, 2, pmax=127, dmax=10)
    cf = CimField(CimCfg(adc_bits=4), P, d)
    assert cf.lsb > 1
    worst = 0
    for x in _states(n, 100, 7 + n):
        err = np.abs(cf.field(x) - (d + P @ x)).max()
        assert err <= cf.error_bound()
        worst = max(worst, err)
    assert worst > 0                         # b = 4 really quantises


def test_noise_seeded_reproducible():
    d, P = random_qubo(32, 3, pmax=20, dmax=5)
    xs = _states(32, 20, 1)
    a = CimField(CimCfg(adc_bits=8, sigma=0.7, seed=5), P, d)
    b = CimField(CimCfg(adc_bits=8, sigma=0.7, seed=5), P, d)
    c = CimField(CimCfg(adc_bits=8, sigma=0.7, seed=6), P, d)
    fa, fb, fc = ([f.field(x) for x in xs] for f in (a, b, c))
    assert all(np.array_equal(u, v) for u, v in zip(fa, fb))
    assert any(not np.array_equal(u, v) for u, v in zip(fa, fc))
    inst = qubo_instance(d, P, seed=2, steps=500, t_start=1.0, t_end=0.1, deoff=1)
    cfg = CimCfg(adc_bits=6, sigma=0.5, seed=9)
    assert Machine(inst, cim=cfg).run().trace == Machine(inst, cim=cfg).run().trace
