"""T-1..T-6 architecture tweaks (scripts/testing/arch_t.py) and the B-3b idle fix: pricing transforms, fairness (t6 for every machine),
and the T-1 (incremental 1-bit sense) / T-2 (sparse) simulator modes. All default-off."""
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
import pricing as pr  # noqa: E402
import run_h8 as rh  # noqa: E402
import variation_v2 as v2  # noqa: E402


def _spec(label, family="p3n480", key="2101", sweeps=3.0, cfg=None, cond="ideal"):
    a = SimpleNamespace(label=label, family=family, phase="main", cond=cond, mit="none", c2c=0.5, sweeps=sweeps, ours_tile_rows=0)
    s = rh.make_spec(a, key, 0)
    return dataclasses.replace(s, tag=10, inst_index=1500 + int(key) % 1000, cfg={**s.cfg, **(cfg or {})})


@pytest.fixture(scope="module")
def recs():
    return {lab: mc.execute(_spec(lab), cm.CostModel()) for lab in ("ours_kc2_i11", "B3_v2", "B1_best")}


def _price(rec, flags):
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse(flags))
    r = cf.prepare(rec, cost)
    s = r["snaps"][-1]
    return pr.price(r["desc"], s["c"], s["t"], s["flips"], cost), s


def test_no_flag_is_the_measured_v2_price(recs):
    rec = recs["ours_kc2_i11"]
    s = rec["snaps"][-1]
    assert _price(rec, "none")[0]["e_total"] == pr.price(rec["desc"], s["c"], s["t"], s["flips"], cm.MeasuredCostV2())["e_total"]


def test_t1_counts_one_column_read_per_update(recs):
    rec = recs["ours_kc2_i11"]
    s = rec["snaps"][-1]
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse("t1"))
    c = at.transform(rec["desc"], s["c"], s["t"], s["flips"], cost)
    upd = s["flips"] + s["c"]["restarts"] * rec["desc"]["kick_L"] + 1
    cols = 2 * rec["desc"]["w_bits"] * rec["desc"]["n_pad"]
    assert c["array_reads"] == upd and c["adc_conv_bits"] == upd * cols and c["adc_lowbit_conv"] == upd * cols
    p0, p1 = _price(rec, "none")[0], _price(rec, "t1")[0]
    assert p1["time_ns"] < p0["time_ns"] and p1["blocks"]["array"] < p0["blocks"]["array"]
    assert p1["area"]["digital"] > p0["area"]["digital"]                      # field registers


def test_t4_removes_unchanged_step_reads(recs):
    rec = recs["ours_kc2_i11"]
    s = rec["snaps"][-1]
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse("t4"))
    c = at.transform(rec["desc"], s["c"], s["t"], s["flips"], cost)
    saved = min(s["t"] - s["flips"] - s["c"]["restarts"], s["c"]["array_reads"] - 1)
    assert c["array_reads"] == pytest.approx(s["c"]["array_reads"] - saved)


def test_t5_hides_read_cycles_behind_the_select_tree(recs):
    rec = recs["ours_kc2_i11"]
    s = rec["snaps"][-1]
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse("t5")).at(rec["desc"])
    c = at.transform(rec["desc"], s["c"], s["t"], s["flips"], cost)
    hide = min(1 + s["c"]["adc_conv_bits"] / s["c"]["adc_conversions"], cost.sel_lat_at(rec["desc"]["n_pad"], "ours") - 1)
    assert s["c"]["cycles"] - c["cycles"] == pytest.approx(s["c"]["array_reads"] * hide)


def test_t3_small_tiles_use_the_tile_full_scale(recs):
    rec = recs["ours_kc2_i11"]
    assert set(rec["desc"]["adc_bits_tile_rows"]) == {"64", "128"}
    p0, p3 = _price(rec, "b3")[0], _price(rec, "t3")[0]
    assert p3["tiles"] == rec["desc"]["n_pad"] // 64 and p3["tiles"] > p0["tiles"]


def test_t2_scales_array_reads_and_area_by_stored_fraction(recs):
    rec = recs["ours_kc2_i11"]
    p0, p2 = _price(rec, "none")[0], _price(rec, "t2")[0]
    f = rec["desc"]["ones_frac"]
    assert 0 < f < 0.1
    assert p2["blocks"]["array"] == pytest.approx(p0["blocks"]["array"] * f)


@pytest.mark.parametrize("lab", ["ours_kc2_i11", "B3_v2", "B1_best"])
def test_t6_lane_gating_applies_to_every_machine(recs, lab):
    rec = recs[lab]
    p0, p6 = _price(rec, "none")[0], _price(rec, "t6")[0]
    assert p6["blocks"]["digital"] < p0["blocks"]["digital"] and 0 < rec["desc"]["deg_frac"] < 0.1


def test_b3b_moves_the_sar_savings_into_the_idle_charge(recs):
    rec = recs["ours_kc2_i11"]
    p3, p3b = _price(rec, "b3")[0], _price(rec, "b3,b3b")[0]
    assert p3b["e_total"] <= p3["e_total"]


def test_prepare_derives_structure_for_old_records(recs):
    rec = dict(recs["ours_kc2_i11"])
    d = {k: v for k, v in rec["desc"].items() if k not in ("deg_frac", "ones_frac", "adc_bits_tile_rows")}
    rec["desc"] = d
    r = cf.prepare(rec, cf.apply(cm.MeasuredCostV2(), cf.parse("t2,t6")))
    assert r["desc"]["deg_frac"] == pytest.approx(recs["ours_kc2_i11"]["desc"]["deg_frac"])
    assert r["desc"]["ones_frac"] == pytest.approx(recs["ours_kc2_i11"]["desc"]["ones_frac"])


# ------------------------------------------------------------------ simulator modes
def _run(cfg, mit, pert):
    s = _spec("ours_kc2_i11", family="p3n240", sweeps=4.0, cfg=cfg)
    s = dataclasses.replace(s, pert=pert)
    return mc.execute(s, cm.CostModel(), v2.Mitigation.parse(mit) if pert else None)


@pytest.mark.parametrize("cfg,mit", [({"sim_incremental": True}, "wv+diff+cal"), ({"sim_incremental": True}, "wv+cal"),
                                     ({"sim_sparse": True}, "wv+cal")])
def test_ideal_device_bit_exact(cfg, mit):
    base = _run({}, "none", None)
    r = _run(cfg, mit, v2.vx(0).as_dict())
    assert base["curve"] == r["curve"] and base["flips"] == r["flips"]


def _field_err(cfg, mit, share=0.0):
    s = _spec("ours_kc2_i11", family="p3n240", cfg=cfg)
    s = dataclasses.replace(s, pert=v2.vx(1).as_dict())
    with v2.c2c_share(share):
        b = mc.build(s, cm.CostModel(), 10, v2.Mitigation.parse(mit))
    m = b.m
    rng = np.random.default_rng(5)
    e = []
    for _ in range(20):
        x = (rng.random(m.inst.n) < 0.3).astype(np.int64)
        if m.lane_en is not None:
            x[~m.lane_en] = 0
        m.load_state(x)
        e.append(m.cim.field(x)[:m.cim.n_act] - m.h[:m.cim.n_act])
    return np.concatenate(e)


def test_sparse_removes_the_share0_field_error_and_one_bit_sense_alone_does_not():
    """Measured (p3n240 2101, share 0, 20 states): column wv+diff+cal 20 % wrong fields; T-1 1-bit sense alone 52 % (a single cell does
    not average its D2D error); T-2 sparse 0 % (the level-0 cells that leak are gone); T-1 + T-2 0 %."""
    col = (_field_err({}, "wv+diff+cal") != 0).mean()
    inc = (_field_err({"sim_incremental": True}, "wv+diff+cal") != 0).mean()
    sp = (_field_err({"sim_sparse": True}, "wv+cal") != 0).mean()
    both = (_field_err({"sim_sparse": True, "sim_incremental": True}, "wv+cal") != 0).mean()
    assert sp < 0.02 and both < 0.02 and col > 0.1 and inc > col


def test_sparse_refuses_diff():
    with pytest.raises(AssertionError):
        _field_err({"sim_sparse": True}, "wv+diff+cal")


# ------------------------------------------------------------------ t1f: full T-1 stack (internal review s15.3.1)
def _p(rec, flags, **attrs):
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse(flags))
    for k, v_ in attrs.items():
        setattr(cost, k, v_)
    r = cf.prepare(rec, cost)
    s = r["snaps"][-1]
    return pr.price(r["desc"], s["c"], s["t"], s["flips"], cost)


def test_t1f_costs_more_than_bare_t1_and_each_term_is_present(recs):
    rec = recs["ours_kc2_i11"]
    p1, pf = _p(rec, "t1"), _p(rec, "t1f")
    assert pf["e_total"] > p1["e_total"] and pf["a_total"] > p1["a_total"]
    for k in ("t1_screen_once", "t1_lcor"):
        assert pf["blocks"][k] > 0
    assert pf["area"]["t1_tables"] > 0


def test_t1f_refresh_period_adds_full_reads(recs):
    rec = recs["ours_kc2_i11"]
    s = rec["snaps"][-1]
    for R in (10, 100):
        cost = cf.apply(cm.MeasuredCostV2(), cf.parse("t1f"))
        cost.t1_refresh = R
        c = at.transform(rec["desc"], s["c"], s["t"], s["flips"], cost)
        assert c["t1_refreshes"] == s["t"] // R
    assert _p(rec, "t1f", t1_refresh=10)["e_total"] > _p(rec, "t1f", t1_refresh=1000)["e_total"]


def test_t1f_screening_amortisation_spares_and_estimate_scale(recs):
    rec = recs["ours_kc2_i11"]
    a = _p(rec, "t1f", t1_runs_per_program=1)
    b = _p(rec, "t1f", t1_runs_per_program=100)
    assert b["blocks"]["t1_screen_once"] == pytest.approx(a["blocks"]["t1_screen_once"] / 100)
    assert _p(rec, "t1f", t1_spare_frac=0.05)["area"]["array"] > _p(rec, "t1f", t1_spare_frac=0.0)["area"]["array"]
    lo, hi = _p(rec, "t1f", t1_est_scale=0.5), _p(rec, "t1f", t1_est_scale=2.0)
    assert hi["e_total"] > a["e_total"] > lo["e_total"]


def test_t1f_field_registers_carry_leakage(recs):
    rec = recs["ours_kc2_i11"]
    p1, pf = _p(rec, "t1", t1_refresh=0), _p(rec, "t1f", t1_refresh=0, t1_lcor_k=0, t1_spare_frac=0.0, t1_screen_frac=0.0)
    assert pf["blocks"]["leakage"] > p1["blocks"]["leakage"]


# ------------------------------------------------------------------ m3: measured_v3 (Round 3 synthesis) pricing of the t1f digital blocks
def test_m3_rows_exist_and_are_positive():
    for k in ("r3_a_lane_t1", "r3_p_leak_lane_t1_nw", "r3_e_lane_update_fj", "r3_e_idle_lane_t1_gated_fj", "r3_e_remap_lookup_n512_fj",
              "r3_e_screen_cell_n1024_fj", "r3_p_leak_sram_bit_nw"):
        assert at.m3(k) > 0
    assert at.m3("r3_e_idle_lane_t1_gated_fj") < at.m3("r3_e_idle_lane_t1_ungated_fj")


def test_m3_replaces_the_estimated_lane_adds_and_adds_measured_blocks(recs):
    rec = recs["ours_kc2_i11"]
    pf, pm = _p(rec, "t1f"), _p(rec, "t1f,m3")
    assert pm["blocks"]["t1_lane"] > 0 and pm["area"]["t1_lanes"] > 0 and pm["blocks"]["t1_remap"] > 0
    assert pm["blocks"]["digital"] < pf["blocks"]["digital"]                    # the 2wn estimated adds per update are gone
    assert "t1_tables" not in pm["area"]


def test_m3_gating_uses_the_gated_lane_rows(recs):
    rec = recs["ours_kc2_i11"]
    assert _p(rec, "t1f,m3,t6")["blocks"]["t1_lane"] < _p(rec, "t1f,m3")["blocks"]["t1_lane"]


def test_m3_correction_table_sram_cheaper_than_flops_and_k0_free(recs):
    rec = recs["ours_kc2_i11"]
    s = _p(rec, "t1f,m3", t1_lcor_k=16, t1_lcor_impl="sram")
    f = _p(rec, "t1f,m3", t1_lcor_k=16, t1_lcor_impl="flop")
    z = _p(rec, "t1f,m3", t1_lcor_k=0)
    assert z["blocks"]["t1_lcor"] == 0
    assert s["e_total"] < f["e_total"] and s["area"]["t1_lcor"] < f["area"]["t1_lcor"]


def test_m3_estimate_scale_touches_only_analog_terms(recs):
    rec = recs["ours_kc2_i11"]
    a, b = _p(rec, "t1f,m3", t1_est_scale=1.0), _p(rec, "t1f,m3", t1_est_scale=2.0)
    assert b["blocks"]["t1_lane"] == a["blocks"]["t1_lane"] and b["blocks"]["adc"] > a["blocks"]["adc"]


def test_b3_symmetric_scales_reach_its_sram_and_rng(recs):
    rec = recs["B3_v2"]
    s = rec["snaps"][-1]
    base = pr.price(rec["desc"], s["c"], s["t"], s["flips"], cm.MeasuredCostV2())
    for key in ("e_sram_read_bit", "e_rng_draw"):
        c = cm.MeasuredCostV2(scale={key: 2.0})
        assert pr.price(rec["desc"], s["c"], s["t"], s["flips"], c)["e_total"] > base["e_total"]


# ------------------------------------------------------------------ Round 4: measured_v4 (OpenRAM), per-machine gating split, refresh fix
@pytest.fixture
def fake_m4(tmp_path, monkeypatch):
    """A synthetic OpenRAM / CACTI table (the real one is docs/hw/energy_table_measured_v4_r4.csv)."""
    vals = {"r4_bank_e_read_fj": 1600.0, "r4_bank_area_um2": 9000.0, "r4_bank_bits": 2048, "r4_leak_bit_openram_nw": 700.0,
            "r4_cacti_lstp_leak_bit_nw": 0.003, "r4_cacti_hp_leak_bit_nw": 70.0, "r4_cacti_lstp_e_bit_n512_fj": 70.0,
            "r4_cacti_hp_e_bit_n512_fj": 60.0}
    p = tmp_path / "m4.csv"
    p.write_text("key,block,kind,unit,value,band_lo_x,band_hi_x,source,placeholder\n" + "".join(f"{k},sram,x,u,{v},1,1,test,0\n" for k, v in vals.items()))
    monkeypatch.setattr(at, "M4_CSV", p)
    at.m4_rows.cache_clear()
    yield
    at.m4_rows.cache_clear()


def test_sram_bank_model(fake_m4):
    b = at.sram_bank(64, 4096)
    assert b["accesses"] == 2 and b["e_fj"] == pytest.approx(3200.0)
    assert b["leak_nw"] == pytest.approx(4096 * 0.003) and b["area_um2"] == pytest.approx(2 * 9000.0)
    hp = type("C", (), {"m4_sram_cells": "hp", "m4_sram_read": "cacti_hp"})()
    b = at.sram_bank(64, 4096, hp)
    assert b["leak_nw"] == pytest.approx(4096 * 70.0) and b["e_fj"] == pytest.approx(64 * 60.0)


def test_m4_reprices_b3_sram_read_and_adds_its_leakage(recs, fake_m4):
    rec = recs["B3_v2"]
    p0, p4 = _p(rec, "all"), _p(rec, "all,m4")
    assert p4["blocks"]["sram"] != p0["blocks"]["sram"] and p4["blocks"]["leakage"] > p0["blocks"]["leakage"]
    assert _p(rec, "all,m4", m4_sram_cells="hp")["blocks"]["leakage"] > p4["blocks"]["leakage"]
    nl = _p(rec, "all,m4", m4_b3_leak=False)
    assert nl["blocks"]["leakage"] == pytest.approx(p0["blocks"]["leakage"])
    half = _p(rec, "all,m4")
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse("all,m4"))
    cost.scale = {"e_sram_read_bit": 0.5}
    s = rec["snaps"][-1]
    assert pr.price(rec["desc"], s["c"], s["t"], s["flips"], cost)["blocks"]["sram"] == pytest.approx(0.5 * half["blocks"]["sram"])


def test_m4_correction_table_uses_the_bank_model(recs, fake_m4):
    rec = recs["ours_kc2_i11"]
    a = _p(rec, "t1f,m3,m4", t1_lcor_k=64)
    b = _p(rec, "t1f,m3", t1_lcor_k=64)
    assert a["blocks"]["t1_lcor"] != b["blocks"]["t1_lcor"] and a["area"]["t1_lcor"] > 0


def test_t6s_gates_b3_only_partly(recs):
    rec = recs["B3_v2"]
    full, split, none = _p(rec, "all,t6"), _p(rec, "all,t6s"), _p(rec, "all")
    assert full["blocks"]["digital"] < split["blocks"]["digital"] < none["blocks"]["digital"]
    o = recs["ours_kc2_i11"]
    assert _p(o, "all,t6")["blocks"]["digital"] == pytest.approx(_p(o, "all,t6s")["blocks"]["digital"])


def test_refresh_attribute_now_overrides_the_simulated_period(recs):
    rec = dict(recs["ours_kc2_i11"])
    rec["desc"] = {**rec["desc"], "sim_refresh": 200}
    s = rec["snaps"][-1]
    for R in (25, 400):
        cost = cf.apply(cm.MeasuredCostV2(), cf.parse("t1f"))
        cost.t1_refresh = R
        assert at.transform(rec["desc"], s["c"], s["t"], s["flips"], cost)["t1_refreshes"] == s["t"] // R
    cost = cf.apply(cm.MeasuredCostV2(), cf.parse("t1f"))
    assert at.transform(rec["desc"], s["c"], s["t"], s["flips"], cost)["t1_refreshes"] == s["t"] // 200


def test_t6s_gates_ours_t1_lanes_like_t6(recs):
    rec = recs["ours_kc2_i11"]
    assert _p(rec, "t1f,m3,t6s")["blocks"]["t1_lane"] == pytest.approx(_p(rec, "t1f,m3,t6")["blocks"]["t1_lane"])


# ------------------------------------------------------------------ review item s20: declared hybrid primary, wide-word / array-only B3 reads, area flag
def test_m4_declared_primary_and_area_flag():
    assert at.M4_PRIMARY == {"m4_sram_read": "openram", "m4_sram_cells": "lstp"}
    assert at.M4_AREA_USABLE is False
    assert at.sram_bank(64, 4096)["area_usable_vs_b3"] is False


def test_m4_real_table_has_wide_word_and_array_lower_bound_rows():
    at.m4_rows.cache_clear()
    p = at.m4_rows()
    lb, wide, bank = p["r4_array_lb_e_bit_n512_fj"], p["r4_cacti_wide_lstp_e_bit_n512_fj"], p["r4_bank_e_read_fj"] / 32
    assert 0 < lb < bank < wide


@pytest.mark.parametrize("rd", ["cacti_wide_lstp", "cacti_wide_hp", "array_lb"])
def test_m4_b3_read_options_reprice_b3(recs, rd):
    at.m4_rows.cache_clear()
    rec = recs["B3_v2"]
    base, alt = _p(rec, "all,m4"), _p(rec, "all,m4", m4_sram_read=rd)
    assert alt["blocks"]["sram"] != base["blocks"]["sram"]
    assert alt["area"]["sram"] == pytest.approx(base["area"]["sram"]) == pytest.approx(_p(rec, "all")["area"]["sram"])
