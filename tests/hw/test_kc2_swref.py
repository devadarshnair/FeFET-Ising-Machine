"""Ruling R1: golden Kc2 follows the reference software study sw_ref/histmem/ptemp/cpu.py (stall vs epoch best, restart from the
current state with an L-spin kick from the engine stream, no T/E_off reset; default L = 10 from ptemp/engine.py:26).

Not a bit-exact the reference software study trace: the reference software study is a +-1 Max-Cut parallel-tempering engine (R replicas, float Metropolis,
its own rng_float streams, swap moves), the golden is a single-walker integer QUBO machine with xoshiro streams, so
no common trace exists. The rule semantics are instead transcribed independently of restart.py (kick_lane,
cpu.py:110-125, with the golden's 32-bit selection stream in place of rng_float) and driven from outside a
da_offset machine; trajectories must agree bit-exactly."""
import numpy as np
import pytest

from instances import maxcut_qubo, qubo_instance, random_graph, random_qubo
from restart import RestartCfg
from tim_golden import Machine

STEPS = 1500


def family(name, seed):
    if name == "maxcut":
        d, P = maxcut_qubo(16, random_graph(16, 0.3, seed))
        return qubo_instance(d, P, seed=seed + 11, steps=STEPS, t_start=1.0, t_end=0.05, deoff=1)
    d, P = random_qubo(16, seed, pmax=4, dmax=4)
    return qubo_instance(d, P, seed=seed + 21, steps=STEPS, t_start=2.0, t_end=0.1, deoff=1)


def reference(inst, K, L):
    m = Machine(inst, RestartCfg("da_offset"))
    perm = list(range(inst.n))
    L = min(L, inst.n - 1)
    stall, epoch_best, events, traj = 0, 0, [], []
    for _ in range(inst.steps):
        m.step()
        if m.f > epoch_best:
            epoch_best, stall = m.f, 0
        else:
            stall += 1
        if stall >= K:
            x = m.x.copy()
            for a in range(L):
                j = a + ((m.sel.next() * (inst.n - a)) >> 32)
                perm[a], perm[j] = perm[j], perm[a]
                x[perm[a]] ^= 1
            m.load_state(x)
            if m.f > m.best_f:
                m.best_f, m.best_x = m.f, m.x.copy()
            epoch_best, stall = m.f, 0
            events.append(m.t)
        traj.append((m.f, m.temp, m.eoff, m.x.tobytes(), m.best_f))
    return traj, events


@pytest.mark.parametrize("fam", ("maxcut", "qubo"))
@pytest.mark.parametrize("seed", range(3))
def test_kc2_default_matches_swref_rule(fam, seed):
    inst = family(fam, seed)
    ref, ref_events = reference(inst, 2 * inst.n, 10)
    m = Machine(inst, RestartCfg("kc2"))
    traj = []
    for _ in range(inst.steps):
        m.step()
        traj.append((m.f, m.temp, m.eoff, m.x.tobytes(), m.best_f))
    assert ref_events and m.restart.events == ref_events
    assert traj == ref


def test_kick_flips_L_distinct_spins_and_keeps_schedule():
    inst = family("qubo", 0)
    m = Machine(inst, RestartCfg("kc2", K=5))
    while not m.restart.events:
        before_x, before_T = m.x.copy(), m.temp
        line = m.step()
    k = int(line.split()[1])
    if k >= 0:
        before_x[k] ^= 1
    assert int((m.x != before_x).sum()) == 10
    assert inst.geom and m.temp == (before_T * inst.alpha) >> 32 != inst.t0


def test_reset_sched_flag_resets_T_and_offset():
    inst = family("qubo", 0)
    m = Machine(inst, RestartCfg("kc2", K=5, kc2_reset_sched=True))
    while not m.restart.events:
        m.step()
    assert m.temp == inst.t0 and m.eoff == 0
