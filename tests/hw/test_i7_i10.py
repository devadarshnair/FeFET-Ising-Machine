"""P2.04: I10 stall-gated power (lossless read skipping) and I7 stall-adaptive ADC precision."""
import numpy as np
import pytest

from cim_field import CimCfg
from instances import maxcut_qubo, qubo_instance, random_graph, random_qubo
from power import PowerCfg
from restart import RestartCfg
from tim_golden import Machine

STEPS = 1500


def stall_heavy(seed=0):
    """Cold, long run: the walker sits in a local optimum for most steps (few accepts)."""
    d, P = maxcut_qubo(16, random_graph(16, 0.3, seed))
    return qubo_instance(d, P, seed=seed + 11, steps=STEPS, t_start=0.5, t_end=0.01, deoff=1)


def qubo(seed=0):
    d, P = random_qubo(16, seed, pmax=4, dmax=4)
    return qubo_instance(d, P, seed=seed + 21, steps=STEPS, t_start=2.0, t_end=0.1, deoff=1)


@pytest.mark.parametrize("arm", ("da_offset", "kc2", "mesa"))
@pytest.mark.parametrize("cim", (None, CimCfg(adc_bits=16), CimCfg(adc_bits=6)))
def test_i10_lossless_and_fewer_reads(arm, cim):
    inst = stall_heavy()
    off = Machine(inst, RestartCfg(arm), cim=cim, power=PowerCfg())
    on = Machine(inst, RestartCfg(arm), cim=cim, power=PowerCfg(i10=True, K_g=8))
    assert on.run().trace == off.run().trace
    assert off.power.reads == STEPS and on.power.reads < off.power.reads
    assert on.power.reads + on.power.skipped == STEPS and on.power.bias_gated > 0


@pytest.mark.parametrize("inst", (stall_heavy(), qubo()))
def test_power_off_equals_p203(inst):
    cim = CimCfg(adc_bits=6)
    ref = Machine(inst, cim=cim).run().trace
    assert Machine(inst, cim=cim, power=PowerCfg()).run().trace == ref
    assert Machine(inst, cim=cim, power=PowerCfg(i10=True)).run().trace == ref


class _StubCim:
    def __init__(self):
        self.adc_bits = 16

    def set_bits(self, bits):
        self.adc_bits = bits

    def field(self, x):
        return x


class _Stub:
    """Hand-crafted best-so-far trace: improvements at steps 1 and 9, flat otherwise."""
    def __init__(self):
        self.cim, self.best_f, self.x, self.h = _StubCim(), 0, 0, 0


def test_i7_switches_at_the_right_step_on_crafted_trace():
    from power import PowerUnit
    m = _Stub()
    pu = PowerUnit(PowerCfg(i7=True, b_hi=16, b_lo=4, K_p=3), m)
    best = [5, 5, 5, 5, 5, 5, 5, 5, 7, 7, 7, 7, 7, 7]          # after steps 1..14
    for b in best:
        pu.field(m)
        m.best_f = b
        pu.after_step(m)
    # counter after step t: 0,1,2,3,4,5,6,7,0,1,2,3,4,5; bits of step t use the counter after t-1 (> 3 -> lo)
    assert pu.bits_trace == [16, 16, 16, 16, 16, 4, 4, 4, 4, 16, 16, 16, 16, 4]


def test_i7_on_machine_matches_counter_rule():
    inst = stall_heavy(1)
    cfg = PowerCfg(i7=True, b_hi=16, b_lo=3, K_p=5)
    m = Machine(inst, cim=CimCfg(adc_bits=16), power=cfg)
    bests = []
    for _ in range(400):
        m.step()
        bests.append(m.best_f)
    counter, last, expect = 0, 0, []
    for b in bests:
        expect.append(cfg.b_lo if counter > cfg.K_p else cfg.b_hi)
        counter = 0 if b > last else counter + 1
        last = b
    assert m.power.bits_trace == expect and cfg.b_lo in expect


def test_i7_needs_cim():
    with pytest.raises(AssertionError):
        Machine(qubo(), power=PowerCfg(i7=True))
