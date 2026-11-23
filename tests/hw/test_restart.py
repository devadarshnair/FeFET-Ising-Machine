"""P2.02: restart arms none / da_offset / mesa / kc2.

Kc2 reference: the the reference software study stall rule (sw_ref histmem/ptemp/cpu.py, 'step best -> epoch best' block and the
'restart when stall >= K' rule, restart_from current), transcribed below independently of restart.py and driven
from outside a plain da_offset machine. The trajectory test runs the legacy variant (L = 0, kc2_reset_sched);
the the reference software study default (kick, no schedule reset) is checked in test_kc2_swref.py."""
import numpy as np
import pytest

from instances import d5c_make_instance, d5c_to_tim, maxcut_qubo, qubo_instance, random_graph, random_qubo
from restart import RestartCfg
from tim_golden import Machine, objective, pad_instance

SEEDS = range(5)
STEPS = 1500
NEG = np.iinfo(np.int64).min


def family(name, seed):
    if name == "maxcut":
        d, P = maxcut_qubo(16, random_graph(16, 0.3, seed))
        return qubo_instance(d, P, seed=seed + 11, steps=STEPS, t_start=1.0, t_end=0.05, deoff=1)
    if name == "qubo":
        d, P = random_qubo(16, seed, pmax=4, dmax=4)
        return qubo_instance(d, P, seed=seed + 21, steps=STEPS, t_start=2.0, t_end=0.1, deoff=1)
    raw = d5c_make_instance(16, 4, seed)
    return d5c_to_tim(raw, rule="hw", T0=2.0, T_min=0.02, budget=STEPS, seed=seed, lam=2.0, dE_off=0.5, Q=8)


FAMILIES = ("maxcut", "qubo", "qkp")


def reference_run(inst, arm, K):
    """Plain da_offset machine; the the reference software study stall rule (kc2) or the MESA rule is applied from outside."""
    m = Machine(inst, RestartCfg("da_offset"))
    trace, events = [], []
    stall, epoch_best, last_best = 0, 0, 0
    for _ in range(inst.steps):
        line = m.step()
        if arm == "kc2":
            wc = m.f if m.is_feasible() else NEG
            if wc > epoch_best:
                epoch_best, stall = wc, 0
            else:
                stall += 1
        else:
            if m.best_f > last_best:
                stall = 0
            else:
                stall += 1
            last_best = m.best_f
        if stall >= K:
            if arm == "mesa":
                m.x = m.best_x.copy()
                m.h = inst.d + inst.P @ m.x
                m.load = inst.W @ m.x if inst.mode == "knap" else m.load
                m.f = m.best_f
            else:
                epoch_best = wc
            m.temp, m.eoff, stall = inst.t0, 0, 0
            events.append(m.t)
            t, k, c, acs, f, hcs, _, _, lcs, ccs = line.split()
            line = " ".join([t, k, c, acs, str(m.f), str(sum((i + 1) * int(v) for i, v in enumerate(m.h)) % 2**32),
                             "0", str(m.temp), lcs if inst.mode != "knap" else
                             str(sum((i + 1) * int(v) for i, v in enumerate(m.load)) % 2**32), ccs])
        trace.append(line)
    return trace, events


def arm_run(inst, arm, K=None):
    cfg = RestartCfg(arm, K, L=0, kc2_reset_sched=True) if arm == "kc2" else RestartCfg(arm, K)
    m = Machine(inst, cfg)
    return [m.step() for _ in range(inst.steps)], m


@pytest.mark.parametrize("fam", FAMILIES)
@pytest.mark.parametrize("arm", ("kc2", "mesa"))
def test_trigger_steps_and_trajectory_bit_exact(fam, arm):
    fired = 0
    for seed in SEEDS:
        inst = family(fam, seed)
        ref_trace, ref_events = reference_run(inst, arm, 2 * inst.n)
        trace, m = arm_run(inst, arm)
        assert m.restart.events == ref_events, (fam, seed)
        assert trace == ref_trace, (fam, seed)
        fired += len(ref_events)
    assert fired > 0                       # the rule really fires on this family


def test_mesa_reload_copies_best_exactly():
    inst = family("qkp", 1)
    m = Machine(inst, RestartCfg("mesa", K=20))
    seen = 0
    for _ in range(inst.steps):
        before = m.best_x.copy(), m.best_f
        m.step()
        if m.restart.events and m.restart.events[-1] == m.t:
            seen += 1
            assert np.array_equal(m.x, before[0]) and m.f == before[1] == objective(inst, m.x)
            assert np.array_equal(m.h, inst.d + inst.P @ m.x) and np.array_equal(m.load, inst.W @ m.x)
            assert m.temp == inst.t0 and m.eoff == 0
    assert seen > 0


@pytest.mark.parametrize("fam", FAMILIES)
def test_da_offset_matches_existing_golden(fam):
    inst = family(fam, 2)
    assert Machine(inst).run().trace == Machine(inst, RestartCfg("da_offset")).run().trace


def test_none_holds_offset_at_zero():
    inst = family("maxcut", 0)
    trace, m = arm_run(inst, "none")
    assert all(line.split()[6] == "0" for line in trace) and not m.restart.events


def test_K_default_counts_enabled_lanes_only():
    d, P = random_qubo(12, 0, pmax=3, dmax=3)
    inst = pad_instance(qubo_instance(d, P, seed=1, steps=10, t_start=1.0, t_end=None, deoff=1), 16)
    assert Machine(inst, RestartCfg("kc2")).restart.K == 24
