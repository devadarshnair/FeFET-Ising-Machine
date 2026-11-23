"""Stage 1 hooks (docs/hw/diagnosis/STAGE1_JOBLIST.tsv `needs`): R4 kick size / K in desc, R6 tabu, R5 targeted kick, R10 dither and
zero-gain tolerance, the fixed-T Metropolis control (R12(b)), R12(a) anneal-then-greedy, R9 reference column, R11 operating-point
calibration, s0_sweep --k / --cfg, s0_h4_field --mit. Every hook is off by default (the golden / RTL suites cover the default path)."""
import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import cost_model as cm  # noqa: E402
import machines as mc  # noqa: E402
import plan as pl  # noqa: E402
import s0_sweep  # noqa: E402
import variation_v2 as v2  # noqa: E402
from restart import RestartCfg  # noqa: E402
from tweaks import TweakCfg  # noqa: E402

COST = cm.CostModel()
TUNED = v2._tuned()["colouring"]["ours.kc2.i10.i11"]


def spec(cfg=None, pert=None, sweeps=8, family="col3p", inst="501"):
    return pl.Spec(study="t", phase="t", family=family, instance=inst, r=0, arm="ours.kc2.fs.i11", cfg={**TUNED, **(cfg or {})},
                   sweeps=sweeps, pert=pert, inst_index=400, tag=v2.SEED_TAG)


def run(cfg=None, **kw):
    return mc.execute(spec(cfg, **kw), COST)


# ------------------------------------------------------------------ R4
def test_kick_size_rules():
    assert mc.kick_size({}, 480) is None
    assert mc.kick_size({"kick_L": 39}, 480) == 39
    assert mc.kick_size({"kick_c": 0.04}, 480) == 20 and mc.kick_size({"kick_c": 0.01}, 480) == 10
    assert mc.kick_size({"kick_c": 0.08}, 960) == 77 and mc.kick_size({"kick_L": 500}, 100) == 99


def test_desc_carries_kick_L_and_K_and_default_is_unchanged():
    base = run()
    assert base["desc"]["kick_L"] == 10 and base["desc"]["K"] == max(1, round(TUNED["knob"] * base["desc"]["n_act"]))
    r = run({"kick_L": 5, "knob": 0.5})
    assert r["desc"]["kick_L"] == 5 and r["desc"]["K"] == max(1, round(0.5 * r["desc"]["n_act"]))
    assert "tabu" not in base["desc"] and "kick_target" not in base["desc"] and "i11_temp" not in base["desc"]


# ------------------------------------------------------------------ R6 / R5
def _built(cfg, sweeps=8):
    return mc.build(spec(cfg, sweeps=sweeps), COST, 400)


def test_tabu_marks_exactly_the_kicked_lanes_for_the_tenure():
    b = _built({"tabu": 1.0})
    m, ru = b.m, b.m.restart
    assert ru.tabu_steps == b.desc["n_act"] and b.desc["tabu"] == 1.0
    x0 = m.x.copy()
    ru._kick(m)
    kicked = np.flatnonzero(m.x != x0)
    assert len(kicked) == ru.L and (ru.tabu_until[kicked] == m.t + ru.tabu_steps).all()
    assert not ru.tabu_mask(m.t + 1)[kicked].any() and ru.tabu_mask(m.t + ru.tabu_steps + 1)[kicked].all()


def test_tabu_blocks_non_improving_flips_of_kicked_lanes():
    b = _built({"tabu": 2.0})
    m = b.m
    for _ in range(300):
        free = m.restart.tabu_mask(m.t + 1)
        x0 = m.x.copy()
        h = m.h.copy()
        m.step()
        moved = np.flatnonzero(m.x != x0)
        if len(moved) == 1 and not m.restart.events or (m.restart.events and m.restart.events[-1] != m.t):
            k = moved[0] if len(moved) == 1 else None
            if k is not None and not free[k]:
                assert (h[k] if x0[k] == 0 else -h[k]) > 0


def test_tabu_changes_the_trajectory_and_is_priced():
    a, b = run(sweeps=60), run({"tabu": 1.0}, sweeps=60)
    assert a["restarts"] > 0
    assert a["curve"] != b["curve"] or a["flips"] != b["flips"]
    assert b["price"]["area"]["restart"] > a["price"]["area"]["restart"]


def test_targeted_kick_takes_half_the_spins_from_the_smallest_gain_lanes():
    b = _built({"kick_target": True})
    m, ru = b.m, b.m.restart
    for _ in range(50):
        m.step()
    x0, h = m.x.copy(), m.h.copy()
    ru._kick(m)
    kicked = set(np.flatnonzero(m.x != x0))
    n_rand = ru.L - ru.L // 2
    rand = set(ru.perm[:n_rand])
    tgt = kicked - rand
    rest = [i for i in ru.perm[n_rand:]]
    thr = sorted(np.abs(h[rest]))[ru.L // 2 - 1]
    assert len(tgt) == ru.L // 2 and all(abs(h[i]) <= thr for i in tgt)
    assert ru.restart_cycles(m) == 6 * ru.L + 1 + 2 * (ru.L // 2) and b.desc["kick_target"]


# ------------------------------------------------------------------ R10 / R12
def test_i11_tolerance_and_fixed_T_metropolis_and_lane_draw_counting():
    base = run()
    tol = run({"i11_tol": 1})
    met = run({"i11_temp": 1.0})
    assert tol["curve"] != base["curve"] or tol["flips"] != base["flips"]
    steps = base["steps"]
    n = base["desc"]["n_pad"]
    cb, cm_ = base["snaps"][-1]["c"], met["snaps"][-1]["c"]
    assert cm_["rng_draws"] >= steps * (n + 1) > cb["rng_draws"]
    assert cm_["lut_reads"] == steps * n and cb["lut_reads"] == 0
    assert met["price"]["area"]["rng"] > base["price"]["area"]["rng"]          # lane RNGs come back


def test_hybrid_anneals_then_turns_greedy():
    b = _built({"hyb_f": 0.5})
    m = b.m
    sw = m.tw.switch
    assert sw == int(0.5 * m.inst.steps) and sw > 0
    m.t = sw - 1
    assert not m.greedy
    m.t = sw + 1
    assert m.greedy
    r = run({"hyb_f": 0.5})
    assert r["desc"]["hyb_f"] == 0.5 and r["snaps"][-1]["c"]["lut_reads"] > 0


def test_tweak_cfg_defaults_are_off():
    t = TweakCfg(i11=True)
    assert t.i11_temp == 0 and t.i11_tol == 0 and t.hyb_f == 0
    r = RestartCfg(arm="kc2")
    assert r.tabu == 0 and not r.target


# ------------------------------------------------------------------ R9 / R11 / R10 dither
def test_mitigation_labels_roundtrip():
    for lab in ("wv+cal+ref", "wv+diff+cal+cal2x8", "wv+cal+dith", "wv+diff+cal+ref+cal2x4+dith"):
        assert v2.Mitigation.parse(lab).label == lab
    with pytest.raises(AssertionError):
        v2.Mitigation.parse("wv+cal2x4")


@pytest.mark.parametrize("mit", ["wv+cal+ref", "wv+diff+cal+ref", "wv+cal+cal2x4", "wv+diff+cal+cal2x4+ref", "wv+cal+dith"])
def test_ideal_device_stays_bit_exact(mit):
    base = run(sweeps=4)
    r = mc.execute(spec(pert=v2.vx(0).as_dict(), sweeps=4), COST, v2.Mitigation.parse(mit))
    assert base["curve"] == r["curve"] and base["flips"] == r["flips"] and base["best_E"] == r["best_E"]


def _field_bias(mit, share=0.0, states=30):
    with v2.c2c_share(share):
        b = mc.build(spec(pert=v2.vx(1).as_dict(), family="p3n240", inst="2101"), COST, 10, v2.Mitigation.parse(mit))
    cim, m = b.m.cim, b.m
    rng = np.random.default_rng(3)
    err = []
    for _ in range(states):
        x = (rng.random(m.inst.n) < 0.3).astype(np.int64)
        if m.lane_en is not None:
            x[~m.lane_en] = 0
        m.load_state(x)
        err.append(cim.field(x)[:cim.n_act] - m.h[:cim.n_act])
    return np.concatenate(err)


def test_ref_column_removes_most_of_the_one_sided_leakage_bias_without_diff():
    e0, e1 = _field_bias("wv+cal"), _field_bias("wv+cal+ref")
    assert e0.mean() > 0.3 and abs(e1.mean()) < 0.7 * e0.mean()        # measured 0.73 -> 0.38 (p3n240 2101, share 0)


def test_oppoint_calibration_fits_a_nonzero_slope_and_does_not_worsen_the_error():
    e0, e1 = _field_bias("wv+cal"), _field_bias("wv+cal+cal2x8")
    assert np.mean(np.abs(e1)) < 0.8 * np.mean(np.abs(e0))              # measured 1.81 -> 1.06


def test_new_mitigations_are_priced():
    r = mc.execute(spec(pert=v2.vx(1).as_dict()), COST, v2.Mitigation.parse("wv+cal+ref+cal2x4+dith"))
    mcst = v2.mitigation_cost(r, v2.Mitigation.parse("wv+cal+ref+cal2x4+dith"), COST)
    assert mcst["items"]["ref_fJ"] > 0 and mcst["items"]["cal2_once_fJ"] > 0 and mcst["items"]["dith_fJ"] > 0


# ------------------------------------------------------------------ scripts
def test_s0_sweep_options():
    argv, k, cfg = s0_sweep.parse_opts(["ours_kc2_i11", "p3n240", "nominal", "wv+diff+cal", "0", "2101", "1", "o.jsonl",
                                        "--k", "2", "--cfg", "kick_L=20,tabu=1.0,kick_target=true"])
    assert len(argv) == 8 and k == 2.0 and cfg == {"kick_L": 20, "tabu": 1.0, "kick_target": True}
    assert s0_sweep.cond_at_k("nominal", 2.0) == "vx2" and s0_sweep.cond_at_k("nominal", 1.0) == "nominal"
    assert v2.point(s0_sweep.cond_at_k("nominal", 3.0)).dev == 3.0
    with pytest.raises(AssertionError):
        s0_sweep.cond_at_k("ideal", 2.0)


def test_s0_sweep_runs_with_k_and_cfg(tmp_path):
    out = tmp_path / "o.jsonl"
    s0_sweep.main(["ours_kc2_i11", "p3n120", "nominal", "wv+diff+cal", "0.5", "2101", "1", str(out), "--k", "2", "--cfg", "kick_L=12"])
    import json
    row = json.loads(out.read_text().splitlines()[0])
    assert row["k"] == 2.0 and row["cfg_over"] == {"kick_L": 12}


def test_s0_sweep_resume_does_not_skip_a_different_cfg(tmp_path):
    out = tmp_path / "o.jsonl"
    for c in ("kick_L=12", "kick_L=14"):
        s0_sweep.main(["ours_kc2_i11", "p3n120", "ideal", "none", "0", "2101", "1", str(out), "--cfg", c])
    assert len(out.read_text().splitlines()) == 2


def test_s0_sweep_cfg_accepts_bare_strings():
    _, _, cfg = s0_sweep.parse_opts(["a", "b", "c", "d", "e", "f", "g", "h", "--cfg", "cc=burst,knob=0.25"])
    assert cfg == {"cc": "burst", "knob": 0.25}
