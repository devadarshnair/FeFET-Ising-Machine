"""Round 2 algorithm hooks (FIX_LEDGER R7, R8/A5; R2 barrier proposals): adaptive kick, half-to-even b_lo rounding, bounded uphill
burst, 1-2-spin conflict kicks, late-acceptance greedy. All default-off; temperature-free; priced."""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import machines as mc  # noqa: E402
import plan as pl  # noqa: E402
import variation_v2 as v2  # noqa: E402
from cim_field import CimCfg, CimField  # noqa: E402
from cost_model import CostModel  # noqa: E402
from restart import RestartCfg  # noqa: E402

COST = CostModel()
TUNED = v2._tuned()["colouring"]["ours.kc2.i10.i11"]


def spec(cfg=None, sweeps=40, family="col3p", inst="501", arm="ours.kc2.fs.i11"):
    return pl.Spec(study="t", phase="t", family=family, instance=inst, r=0, arm=arm, cfg={**TUNED, **(cfg or {})}, sweeps=sweeps,
                   inst_index=400, tag=v2.SEED_TAG)


def run(cfg=None, **kw):
    return mc.execute(spec(cfg, **kw), COST)


def test_defaults_are_off():
    r = RestartCfg(arm="kc2")
    assert r.adaptive_m == 0 and not r.conflict and r.burst_K == 0
    assert not CimCfg().round_even
    base = run()
    for k in ("adaptive_m", "kick_conflict", "burst_K", "lahc_len", "round_even"):
        assert k not in base["desc"]


# ------------------------------------------------------------------ R8 / A5
def test_round_half_even_is_zero_mean_where_half_up_is_one_sided():
    P = np.zeros((4, 4), np.int64)
    d = np.zeros(4, np.int64)
    sums = np.arange(0, 64)
    up = CimField(CimCfg(adc_bits=5, w_bits=1, fs=63), P, d)
    ev = CimField(CimCfg(adc_bits=5, w_bits=1, fs=63, round_even=True), P, d)
    assert up.lsb == ev.lsb > 1
    e_up = up._adc(sums) - sums
    e_ev = ev._adc(sums) - sums
    assert e_up.mean() > 0.4 and abs(e_ev.mean()) < 0.05
    assert np.abs(e_ev).max() <= ev.lsb // 2


def test_round_even_flag_reaches_the_machine():
    b = mc.build(spec({"round_even": True}), COST, 10)
    assert b.m.cim.cfg.round_even and b.desc["round_even"]


# ------------------------------------------------------------------ R7
def test_adaptive_kick_doubles_on_failed_kicks_and_wraps():
    b = mc.build(spec({"adaptive_m": 3, "kick_L": 2}), COST, 4000)
    m, ru = b.m, b.m.restart
    seen = set()
    for _ in range(4000):
        m.step()
        seen.add(ru.L)
    assert seen <= {2, 4, 8} and len(seen) >= 2


def test_adaptive_cycles_follow_the_escalated_L():
    b = mc.build(spec({"adaptive_m": 3, "kick_L": 2}), COST, 4000)
    m, ru = b.m, b.m.restart
    for _ in range(4000):
        m.step()
        if ru.events and ru.events[-1] == m.t:
            assert ru.event_cycles[-1] == 6 * ru.L + 1
    assert ru.events


# ------------------------------------------------------------------ barrier
def test_conflict_kick_flips_only_set_lanes_of_smallest_gain():
    b = mc.build(spec({"kick_conflict": True, "kick_L": 2}), COST, 400)
    m, ru = b.m, b.m.restart
    for _ in range(200):
        m.step()
    x0, h = m.x.copy(), m.h.copy()
    ru._kick(m)
    flipped = np.flatnonzero(m.x != x0)
    ones = np.flatnonzero(x0 == 1)
    assert len(flipped) == 2 and set(flipped) <= set(ones)
    assert max(abs(h[flipped])) <= sorted(abs(h[ones]))[1]
    assert ru.restart_cycles(m) == 6 * 2 + 1 + 2 * 2


def test_burst_accepts_bounded_uphill_moves_then_returns_to_greedy():
    b = mc.build(spec({"burst_K": 0.2, "burst_len": 0.2, "burst_up": 2}), COST, 3000)
    m, ru = b.m, b.m.restart
    uphill_in_burst, uphill_outside = 0, 0
    for _ in range(3000):
        f0, in_burst = m.f, ru.tolerance() > 0
        m.step()
        if m.restart.events and m.restart.events[-1] == m.t:
            continue
        if m.f < f0:
            if in_burst:
                uphill_in_burst += 1
                assert f0 - m.f == 1
            else:
                uphill_outside += 1
    assert ru.bursts > 0 and uphill_in_burst > 0 and uphill_outside == 0
    assert uphill_in_burst <= 2 * ru.bursts


def test_lahc_accepts_down_to_the_history_value_only():
    b = mc.build(spec({"lahc_len": 50}), COST, 3000)
    m = b.m
    for _ in range(3000):
        thr = m.tw.lahc_threshold(m.t + 1, m.f)
        f0 = m.f
        m.step()
        if m.restart.events and m.restart.events[-1] == m.t:
            continue
        assert m.f - f0 >= thr
    assert b.desc["lahc_len"] == 50


@pytest.mark.parametrize("cfg", [{"kick_conflict": True, "kick_L": 2, "knob": 0.1}, {"burst_K": 0.2, "burst_len": 0.1, "burst_up": 3},
                                 {"lahc_len": 64}, {"adaptive_m": 3}])
def test_barrier_hooks_change_the_run_and_are_priced(cfg):
    a, b = run(), run(cfg)
    assert a["curve"] != b["curve"] or a["flips"] != b["flips"]
    if any(k in cfg for k in ("burst_K", "lahc_len", "kick_conflict")):
        assert b["price"]["area"]["restart"] > a["price"]["area"]["restart"]
