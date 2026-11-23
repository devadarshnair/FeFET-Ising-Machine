"""Round 2, architecture-review hooks (reports/Ising machine component architecture review.md): configuration checking with the stall
burst, breakout weights, RNG-free escalating offset, colour-parallel exact commits, leaky-zero screening + sparse per-cell correction,
periodic refresh of the incremental field. All default-off."""
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import arch_t as at  # noqa: E402
import cost_flags as cf  # noqa: E402
import cost_model as cm  # noqa: E402
import machines as mc  # noqa: E402
import plan as pl  # noqa: E402
import run_h8 as rh  # noqa: E402
import variation_v2 as v2  # noqa: E402
from tweaks import TweakCfg  # noqa: E402

COST = cm.CostModel()
TUNED = v2._tuned()["colouring"]["ours.kc2.i10.i11"]


def spec(cfg=None, sweeps=40, family="col3p", inst="501"):
    return pl.Spec(study="t", phase="t", family=family, instance=inst, r=0, arm="ours.kc2.fs.i11", cfg={**TUNED, **(cfg or {})}, sweeps=sweeps,
                   inst_index=400, tag=v2.SEED_TAG)


def test_defaults_off():
    t = TweakCfg(i11=True)
    assert not t.cc and t.bo_K == 0 and t.esc_step == 0 and not t.colour_par
    m = v2.Mitigation.parse("wv+diff+cal")
    assert m.scr == 0 and m.lcor == 0


# ------------------------------------------------------------------ configuration checking
def test_cc_blocks_flip_back_until_a_neighbour_flips():
    b = mc.build(spec({"cc": "always"}), COST, 2000)
    m = b.m
    P = np.asarray(m.P)
    last_flip = {}
    for _ in range(2000):
        x0, h = m.x.copy(), m.h.copy()
        ok = m.tw.cc_ok.copy()
        m.step()
        if m.restart.events and m.restart.events[-1] == m.t:
            continue
        for k in np.flatnonzero(m.x != x0):
            g = h[k] if x0[k] == 0 else -h[k]
            assert ok[k] or g > 0
    assert b.desc["cc"] == "always"


def test_cc_burst_mode_only_acts_during_a_burst():
    b = mc.build(spec({"cc": "burst"}), COST, 10)
    assert b.m.tw.cc_mask(False) is None and b.m.tw.cc_mask(True) is not None


# ------------------------------------------------------------------ breakout
def test_breakout_bias_grows_on_conflicted_spins_and_decays():
    b = mc.build(spec({"bo_K": 5, "bo_T": 50}), COST, 3000)
    m = b.m
    mx = 0
    for _ in range(3000):
        m.step()
        mx = max(mx, int(m.tw.bo.max()))
    assert m.tw.bo_updates > 0 and 0 < mx <= 15
    c = m.tw.conflicted(m)
    assert not (c & (m.x == 0)).any()


def test_breakout_never_changes_the_true_objective():
    b = mc.build(spec({"bo_K": 3, "bo_T": 0}), COST, 500)
    m = b.m
    for _ in range(500):
        m.step()
        x = m.x.astype(np.int64)
        assert m.f == int(np.asarray(m.inst.d) @ x + x @ np.triu(np.asarray(m.P), 1) @ x)


# ------------------------------------------------------------------ escalating offset
def test_escalating_offset_is_deterministic_bounded_and_reset_on_a_move():
    b = mc.build(spec({"esc_step": 1, "esc_max": 3}), COST, 2000)
    m = b.m
    assert m.deoff == 1
    for _ in range(2000):
        e0, f0 = m.eoff, m.flips
        m.step()
        assert m.eoff <= 3
        if m.flips == f0 and not (m.restart.events and m.restart.events[-1] == m.t):
            assert m.eoff == min(e0 + 1, 3)
    a, c = mc.execute(spec({"esc_step": 1, "esc_max": 3}), COST), mc.execute(spec({"esc_step": 1, "esc_max": 3}), COST)
    assert a["curve"] == c["curve"]


# ------------------------------------------------------------------ colour-parallel
def test_colour_classes_are_independent_sets_and_commits_are_exact():
    b = mc.build(spec({"colour_par": True}), COST, 2000)
    m = b.m
    P = np.asarray(m.P)
    for cls in m.tw.classes:
        idx = np.flatnonzero(cls)
        assert not P[np.ix_(idx, idx)].any()
    for _ in range(2000):
        m.step()
    x = m.x.astype(np.int64)
    assert m.f == int(np.asarray(m.inst.d) @ x + x @ np.triu(P, 1) @ x)
    assert m.tw.par_commits > 0


@pytest.mark.parametrize("cfg", [{"cc": "always"}, {"bo_K": 5, "bo_T": 50}, {"esc_step": 1, "esc_max": 2}, {"colour_par": True}])
def test_hooks_change_the_run_and_are_priced(cfg):
    kw = {"family": "p3n240", "inst": "2101", "sweeps": 10} if "esc_step" in cfg else {}   # col3p has no no-move steps to escalate on
    a, b = mc.execute(spec(**kw), COST), mc.execute(spec(cfg, **kw), COST)
    assert a["curve"] != b["curve"] or a["flips"] != b["flips"]
    assert b["price"]["area"]["restart"] > a["price"]["area"]["restart"]


# ------------------------------------------------------------------ screening / sparse correction / refresh
def _spec480(cfg=None, family="p3n240"):
    a = SimpleNamespace(label="ours_kc2_i11", family=family, phase="main", cond="nominal", mit="none", c2c=0.5, sweeps=4.0, ours_tile_rows=0)
    s = rh.make_spec(a, "2101", 0)
    return dataclasses.replace(s, tag=10, inst_index=1601, cfg={**s.cfg, **(cfg or {})})


def _err(mit, cfg=None, share=0.0, states=20):
    with v2.c2c_share(share):
        b = mc.build(_spec480(cfg), COST, 10, v2.Mitigation.parse(mit))
    m = b.m
    rng = np.random.default_rng(5)
    e = []
    for _ in range(states):
        x = (rng.random(m.inst.n) < 0.3).astype(np.int64)
        if m.lane_en is not None:
            x[~m.lane_en] = 0
        m.load_state(x)
        e.append(m.cim.field(x)[:m.cim.n_act] - m.h[:m.cim.n_act])
    return np.concatenate(e), b


def test_mitigation_labels_roundtrip():
    for lab in ("wv+diff+cal+scr5", "wv+cal+lcor4", "wv+diff+cal+scr3+lcor2"):
        assert v2.Mitigation.parse(lab).label == lab


@pytest.mark.parametrize("mit", ["wv+cal+scr5", "wv+diff+cal+lcor4", "wv+diff+cal+scr5+lcor4"])
def test_ideal_device_bit_exact(mit):
    s = _spec480()
    base = mc.execute(dataclasses.replace(s, pert=None), COST)
    r = mc.execute(dataclasses.replace(s, pert=v2.vx(0).as_dict()), COST, v2.Mitigation.parse(mit))
    assert base["curve"] == r["curve"] and base["flips"] == r["flips"]


def test_screening_and_correction_reduce_the_share0_field_error():
    e0, _ = _err("wv+diff+cal")
    e1, b1 = _err("wv+diff+cal+scr5")
    e2, _ = _err("wv+diff+cal+lcor8")
    assert b1.m.cim.cf.spares > 0
    assert (e1 != 0).mean() < (e0 != 0).mean() and (e2 != 0).mean() < (e0 != 0).mean()


def test_screening_and_correction_are_priced():
    s = dataclasses.replace(_spec480(), pert=v2.vx(1).as_dict())
    mit = v2.Mitigation.parse("wv+diff+cal+scr5+lcor4")
    r = mc.execute(s, COST, mit)
    c = v2.mitigation_cost(r, mit, COST)
    assert c["items"]["scr_once_fJ"] > 0 and c["items"]["lcor_fJ"] > 0


def test_refresh_bounds_the_register_drift_and_is_priced():
    e, b = _err("wv+diff+cal", {"sim_incremental": True, "sim_refresh": 5})
    assert b.m.cim.refreshes > 0
    assert b.desc["sim_refresh"] == 5
    rec = mc.execute(dataclasses.replace(_spec480({"sim_incremental": True, "sim_refresh": 50}), pert=None), COST)
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse("t1"))
    s = rec["snaps"][-1]
    c = at.transform(rec["desc"], s["c"], s["t"], s["flips"], cost)
    assert c["t1_refreshes"] == s["t"] // 50
