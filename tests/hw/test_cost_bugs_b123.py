"""Regression tests for the H8 diagnosis cost bugs B-1 (noisy restart cycles unpriced), B-2 (linear ADC pricing),
B-3 (tiled ours priced at full-column bits). docs/hw/diagnosis/PROBLEMS_AGREED.md."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ("scripts/testing", "scripts/golden", "scripts/baselines", "."):
    sys.path.insert(0, str(ROOT / sub))

import cost_model as cm  # noqa: E402
import hycim_b2  # noqa: E402
import machines as mc  # noqa: E402
import pricing as pr  # noqa: E402
from cim_field import max_column_sum, max_tile_column_sum  # noqa: E402
from restart import RestartCfg  # noqa: E402


class _Sel:
    def __init__(self):
        self.s = 12345

    def next(self):
        self.s = (self.s * 1103515245 + 12345) & 0xFFFFFFFF
        return self.s


class _FakeMachine:
    """Minimal machine for the restart unit: n lanes, f stays 0 so the unit stalls every K steps."""

    def __init__(self, n=40):
        self.inst = SimpleNamespace(n=n, t0=5)
        self.lane_en = None
        self.x = np.zeros(n, np.int64)
        self.best_x = self.x.copy()
        self.f = self.best_f = 0
        self.best_step = self.t = 0
        self.sel = _Sel()
        self.cim = SimpleNamespace(last_eta=0.0)
        self.temp = self.eoff = 0

    def is_feasible(self):
        return True

    def load_state(self, x):
        self.x = np.asarray(x).copy()


@pytest.mark.parametrize("arm", ["kc2", "mesa"])
def test_b1_noisy_restart_unit_records_restart_cycles(arm):
    m = _FakeMachine()
    u = mc.NoisyRestartUnit(RestartCfg(arm=arm, K=3, L=7), m)
    fired = [u.after_step(m) for _ in range(3)]
    assert fired[-1] and u.last_cycles > 0
    assert u.event_cycles == [u.last_cycles]
    if arm == "kc2":
        assert u.last_cycles == 6 * 7 + 1


def test_b1_noisy_kc2_cycles_equal_golden_rule():
    m = _FakeMachine()
    u = mc.NoisyRestartUnit(RestartCfg(arm="kc2", K=2, L=10), m)
    for _ in range(6):
        u.after_step(m)
    assert u.event_cycles == [61] * len(u.events) and len(u.events) >= 2


def test_b2_curve_off_is_the_frozen_linear_rule():
    cost = cm.CostModel()
    c = {"adc_conversions": 10, "adc_conv_bits": 50, "adc_lowbit_conv": 0, "adc_lowbit_bits": 0}
    assert cost.adc_fj(c) == pytest.approx(50 * cost.v("e_adc_conv_bit"))


def test_b2_curve_matches_spice_points_and_e8():
    cost = cm.CostModel()
    cost.adc_curve = True
    pts = cm.adc_curve_points()
    e8 = 8 * cost.v("e_adc_conv_bit")
    for b in (3, 5, 8):
        c = {"adc_conversions": 1, "adc_conv_bits": b}
        assert cost.adc_fj(c) == pytest.approx(pts[b] * e8 / pts[8])
    assert cost.adc_fj({"adc_conversions": 1, "adc_conv_bits": 8}) == pytest.approx(e8)


def test_b2_curve_prices_low_bit_conversions_separately_and_cheaper_than_linear():
    cost = cm.CostModel()
    c = {"adc_conversions": 10, "adc_conv_bits": 6 * 8 + 4 * 4, "adc_lowbit_conv": 4, "adc_lowbit_bits": 16}
    lin = cost.adc_fj(c)
    cost.adc_curve = True
    pts, e8 = cm.adc_curve_points(), 8 * cost.v("e_adc_conv_bit")
    assert cost.adc_fj(c) == pytest.approx(6 * e8 + 4 * pts[4] * e8 / pts[8])
    assert cost.adc_fj(c) < lin


def test_b2_curve_is_applied_to_baselines_too():
    cost = cm.CostModel()
    lin = hycim_b2.adc_energy_fj(100, 2, cost)
    cost.adc_curve = True
    assert hycim_b2.adc_energy_fj(100, 2, cost) < lin


def test_b3_tile_full_scale_is_at_most_column_full_scale_and_exact_for_one_tile():
    rng = np.random.default_rng(1)
    P = rng.integers(-7, 8, size=(600, 600))
    P = np.triu(P, 1) + np.triu(P, 1).T
    assert max_tile_column_sum(P, 3, 1000) == max_column_sum(P, 3)
    assert max_tile_column_sum(P, 3, 256) <= max_column_sum(P, 3)
    assert max_tile_column_sum(P, 3, 256).bit_length() < max_column_sum(P, 3).bit_length()


def _desc(n_pad, bits, tile_bits):
    return {"kind": "ours", "n_pad": n_pad, "adc_bits": bits, "adc_bits_tile": tile_bits}


def test_b3_tile_rebits_is_off_by_default_and_for_single_tile():
    c = {"adc_conversions": 100, "adc_conv_bits": 800, "cycles": 1000, "array_reads": 10}
    cost = cm.CostModel()
    assert pr.tile_rebits(c, _desc(1024, 8, 6), cost) is c
    cost.tile_bits = True
    assert pr.tile_rebits(c, _desc(256, 8, 6), cost) is c


def test_b3_tile_rebits_reprices_bits_and_sar_cycles():
    cost = cm.CostModel()
    cost.tile_bits = True
    c = {"adc_conversions": 100, "adc_conv_bits": 800, "adc_lowbit_conv": 0, "cycles": 1000, "array_reads": 10}
    out = pr.tile_rebits(c, _desc(1024, 8, 6), cost)
    assert out["adc_conv_bits"] == 600 and out["cycles"] == 980 and c["adc_conv_bits"] == 800


def test_b3_tile_rebits_keeps_sar_cycles_of_i7_low_bit_reads():
    cost = cm.CostModel()
    cost.tile_bits = True
    # 10 reads x 10 conversions; 4 reads were I7 low-bit (40 conversions at 4 bits); only the 6 full-width reads lose 2 SAR cycles
    c = {"adc_conversions": 100, "adc_conv_bits": 60 * 8 + 40 * 4, "adc_lowbit_conv": 40, "adc_lowbit_bits": 160,
         "cycles": 1000, "array_reads": 10}
    out = pr.tile_rebits(c, _desc(1024, 8, 6), cost)
    assert out["cycles"] == 1000 - 6 * 2 and out["adc_conv_bits"] == c["adc_conv_bits"] - 60 * 2


# ------------------------------------------------------------------ cost_flags: re-pricing stored records (Stage 0.1)
import cost_flags as cf  # noqa: E402


def _kc2_rec(restart_cycles, restarts=5, n_act=100):
    c = {k: 0 for k in pr.FIELDS_KEEP}
    c.update(restarts=restarts, restart_cycles=restart_cycles, cycles=10_000, field_reads=1000, array_reads=1000,
             adc_conversions=1000 * 12, adc_conv_bits=1000 * 12 * 6, rng_draws=1000, adds=1000 * 6 * n_act)
    desc = {"kind": "ours", "restart": "kc2", "n_pad": 128, "n_act": n_act, "tweak": "i11", "w_bits": 2, "adc_bits": 6}
    return {"desc": desc, "snaps": [{"t": 1000, "flips": 10, "c": c}], "counters": dict(c), "power_mode": "fs",
            "spec": {"family": "x", "instance": "y"}}


def test_cost_flags_parse():
    assert cf.parse("none") == frozenset() and cf.parse("all") == {"b1", "b2", "b3"} and cf.parse("b1,b3") == {"b1", "b3"}
    with pytest.raises(AssertionError):
        cf.parse("b4")


def test_cost_flags_apply_sets_model_switches_without_touching_the_original():
    base = cm.MeasuredCostV2()
    c = cf.apply(base, cf.parse("b2,b3"))
    assert c.adc_curve and c.tile_bits and not base.adc_curve and not base.tile_bits
    assert c.at({"kind": "ours", "n_pad": 128, "restart": "kc2"}).adc_curve      # survives the per-record copy


def test_b1_stale_zero_restart_cycles_are_repriced_only_with_the_flag():
    rec = _kc2_rec(0)
    off = cf.apply(cm.MeasuredCostV2(), frozenset())
    on = cf.apply(cm.MeasuredCostV2(), cf.parse("b1"))
    assert cf.prepare(rec, off) is rec
    s0, s1 = cf.prepare(rec, off)["snaps"][-1], cf.prepare(rec, on)["snaps"][-1]
    assert "restart_cycles" in rec["snaps"][-1]["c"]                                       # stored record untouched
    p0 = pr.price(rec["desc"], s0["c"], s0["t"], s0["flips"], off)
    p1 = pr.price(rec["desc"], s1["c"], s1["t"], s1["flips"], on)
    t_clk = on.at(rec["desc"]).v("t_clk")
    assert p1["time_ns"] - p0["time_ns"] == pytest.approx(5 * (6 * 10 + 1) * t_clk)        # restarts x (6L + 1), L = 10


def test_b1_flag_keeps_real_restart_cycles():
    rec = _kc2_rec(305)
    on = cf.apply(cm.MeasuredCostV2(), cf.parse("b1"))
    assert cf.prepare(rec, on)["snaps"][-1]["c"]["restart_cycles"] == 305


def test_b2_b1_energy_uses_the_curve():
    import yin_mesa as b1
    c = {k: 0 for k in pr.FIELDS_KEEP}
    c.update(adc_conversions=1000, adc_conv_bits=3000, cycles=100, array_reads=10)
    sh = pr._b1_shim({"n_pad": 128, "n_act": 120, "adc_bits": 3}, c, 10)
    cost = cm.CostModel()
    lin = b1.b1_energy(sh, cost, c)
    cost.adc_curve = True
    cur = b1.b1_energy(sh, cost, c)
    pts = cm.adc_curve_points()
    assert lin["adc"] == pytest.approx(3000 * cost.v("e_adc_conv_bit"))
    assert cur["adc"] == pytest.approx(1000 * pts[3] * 8 * cost.v("e_adc_conv_bit") / pts[8])
    assert {k: v for k, v in cur.items() if k != "adc"} == {k: v for k, v in lin.items() if k != "adc"}


STORED = ROOT / "sim/out/hw/h8/h8/h8_main_ours_kc2_i11_maxcut_1000_nominal_000.json"


def _stored_or_live():
    """SKIP-1: the stored H8 Max-Cut record when present; otherwise a live tiled record (p3n960, 1024 lanes, 4 tiles) whose
    restart_cycles are zeroed exactly as the pre-90fa2cf noisy records stored them."""
    import json
    if STORED.exists():
        return json.loads(STORED.read_text())["records"][0]
    import dataclasses
    from types import SimpleNamespace
    import run_h8 as rh
    a = SimpleNamespace(label="ours_kc2_i11", family="p3n960", phase="main", cond="ideal", mit="none", c2c=0.5, sweeps=2.0, ours_tile_rows=0)
    s = rh.make_spec(a, "2101", 0)
    s = dataclasses.replace(s, tag=10, inst_index=1601, cfg={**s.cfg, "knob": 0.1})
    rec = mc.execute(s, cm.CostModel())
    for sn in rec["snaps"]:
        sn["c"]["restart_cycles"] = 0
    assert rec["snaps"][-1]["c"]["restarts"] > 0 and rec["desc"]["n_pad"] == 1024
    return rec


def test_end_to_end_price_of_a_stored_tiled_record_with_every_flag():
    rec = _stored_or_live()
    out = {}
    for fl in ("none", "b1", "b3", "all"):
        cost = cf.apply(cm.MeasuredCostV2(), cf.parse(fl))
        r = cf.prepare(rec, cost)
        s = r["snaps"][-1]
        out[fl] = pr.price(r["desc"], s["c"], s["t"], s["flips"], cost)
    assert out["none"]["e_total"] == pytest.approx(pr.price(rec["desc"], rec["snaps"][-1]["c"], rec["snaps"][-1]["t"],
                                                            rec["snaps"][-1]["flips"], cm.MeasuredCostV2())["e_total"])
    assert out["b1"]["time_ns"] > out["none"]["time_ns"]                    # stored restart_cycles = 0 now priced
    assert out["b3"]["blocks"]["adc"] < out["none"]["blocks"]["adc"]        # 4 tiles at tile bits, not 8 bits
    assert out["all"]["e_total"] < out["b3"]["e_total"]                     # curve on top (tile bits < 8)


# ------------------------------------------------------------------ B2-LIN
def test_b2lin_mixed_width_class_is_refused_unless_allowed():
    cost = cm.CostModel()
    cost.adc_curve = True
    c = {"adc_conversions": 2, "adc_conv_bits": 7}                       # one 3-bit and one 4-bit conversion in one class
    with pytest.raises(AssertionError):
        cost.adc_fj(c)
    cost.adc_mixed_width_ok = True
    assert cost.adc_fj(c) > 0


def test_b2lin_sar_logic_sensitivity_adds_one_flop_per_bit():
    cost = cm.CostModel()
    cost.adc_curve = True
    c = {"adc_conversions": 10, "adc_conv_bits": 50}
    base = cost.adc_fj(c)
    cost.adc_sar_logic = True
    assert cost.adc_fj(c) == pytest.approx(base + 50 * cost.v("e_shadow_bit"))
    assert cf.apply(cm.MeasuredCostV2(), cf.parse("b2,b2s")).adc_sar_logic


def test_cost_flags_all_token_combines_with_other_flags():
    assert cf.parse("all,t1,t5") == {"b1", "b2", "b3", "t1", "t5"}
