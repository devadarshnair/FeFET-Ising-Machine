"""P2.05: TCAM-lite visited-state arm (off = P2.04 bit-exact; writes counted; lockout on a crafted cycle)."""
import numpy as np
import pytest

from cim_field import CimCfg
from instances import maxcut_qubo, qubo_instance, random_graph
from power import PowerCfg
from restart import RestartCfg
from tcam_lite import TcamLite, TcamLiteCfg
from tim_golden import Machine


def inst(seed=0):
    d, P = maxcut_qubo(16, random_graph(16, 0.3, seed))
    return qubo_instance(d, P, seed=seed + 11, steps=1200, t_start=0.5, t_end=0.01, deoff=1)


@pytest.mark.parametrize("arm", ("da_offset", "kc2", "mesa"))
def test_off_equals_p204(arm):
    kw = dict(cim=CimCfg(adc_bits=6), power=PowerCfg(i10=True, K_g=8))
    ref = Machine(inst(), RestartCfg(arm), **kw).run().trace
    assert Machine(inst(), RestartCfg(arm), tcam=None, **kw).run().trace == ref
    assert Machine(inst(), RestartCfg(arm), tcam=TcamLiteCfg(on=False), **kw).run().trace == ref


class _M:
    class inst:
        n = 3
    best_f, t = 0, 0
    x = np.zeros(3, dtype=np.int64)


def test_lockout_on_crafted_cycle():
    m = _M()
    tc = TcamLite(TcamLiteCfg(on=True, M=2, K_w=2, L_lock=3), m)
    A, B = np.array([1, 0, 0]), np.array([0, 1, 0])
    # (state after step, lane flipped): the walker cycles A -> B -> A -> B; no improvement ever
    for t, (x, k) in enumerate([(A, 0), (B, 1), (A, 0), (B, 1), (A, 0)], start=1):
        m.t, m.x = t, x
        tc.after_step(m, k)
        if t == 1:
            assert tc.writes == 0 and tc.hits == 0
        if t == 2:                                   # stall 2: B written
            assert tc.writes == 1 and tc.hits == 0
        if t == 3:                                   # A: miss (not stored yet), then stall 3: no write
            assert tc.hits == 0
        if t == 4:                                   # stall 4: B written again? B is searched first: hit
            assert tc.hits == 1 and tc.lock_until[1] == 4 + 3 and tc.writes == 2
    assert tc.locked(5).tolist() == [False, True, False]
    assert tc.locked(8).tolist() == [False, False, False]
    assert tc.hits == 1 and tc.writes == 2


def test_on_counts_writes_and_locks_lanes():
    m = Machine(inst(), RestartCfg("da_offset"), tcam=TcamLiteCfg(on=True, M=8, K_w=8, L_lock=4))
    m.run()
    assert m.tcam.writes > 0 and m.tcam.searches > 0
    assert m.tcam.hits > 0 and m.tcam.lockout_blocks > 0


def test_on_changes_trajectory_only_after_a_hit():
    base = Machine(inst(), RestartCfg("da_offset")).run().trace
    mt = Machine(inst(), RestartCfg("da_offset"), tcam=TcamLiteCfg(on=True, M=8, K_w=8, L_lock=4))
    tr = mt.run().trace
    first_block = next(i for i, (a, b) in enumerate(zip(base, tr)) if a != b)
    assert first_block >= 8
