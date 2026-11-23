"""P2.07: cost model is linear in counts, zero activity = leakage only, every table row labelled."""
import pytest

from cost_model import Arch, CostModel, load_table, placeholders, total
from counters import FIELDS

ARCH = Arch(n=16, w_bits=4, arm="mesa", tcam_rows=4)


def counts(x):
    c = {f: x for f in FIELDS}
    c["array_writes"] = c["tcam_searches"] = 0          # TCAM dropped: never charged
    return c


def test_doubling_counts_doubles_energy():
    cm = CostModel()
    one, two = cm.energy(counts(7), ARCH, 7), cm.energy(counts(14), ARCH, 14)
    for b in one:
        assert two[b] == pytest.approx(2 * one[b], rel=1e-12)


def test_zero_activity_is_leakage_only():
    c = counts(0)
    c["cycles"] = 1000
    e = CostModel().energy(c, Arch(n=16, w_bits=4, arm="none"), 0)
    assert all(v == 0 for b, v in e.items() if b != "leakage") and e["leakage"] > 0


def test_skipped_reads_and_gating_cost_no_array_energy():
    cm, c = CostModel(), counts(0)
    c["skipped_reads"] = 50
    c["gated_cycles"] = 0
    e = cm.energy(c, ARCH, 0)
    assert e["array"] == 0 and e["adc"] == 0


def test_lowbit_conversions_cheaper():
    cm, hi, lo = CostModel(), counts(0), counts(0)
    hi["adc_conv_bits"], lo["adc_conv_bits"] = 128 * 8, 128 * 4
    assert cm.energy(lo, ARCH, 0)["adc"] == pytest.approx(cm.energy(hi, ARCH, 0)["adc"] / 2)


def test_restart_arm_logic_costed():
    cm, c = CostModel(), counts(0)
    c["best_updates"] = 3
    e = {a: cm.energy(c, Arch(n=16, arm=a), 10)["restart"] for a in ("none", "kc2", "mesa", "da_offset")}
    assert e["none"] == 0 < e["kc2"] < e["mesa"] and e["kc2"] < e["da_offset"]
    ar = {a: cm.area(Arch(n=16, arm=a))["restart"] for a in ("none", "kc2", "mesa", "da_offset")}
    assert ar["none"] == 0 < ar["kc2"] < ar["mesa"] and ar["kc2"] < ar["da_offset"]


def test_sensitivity_hook_and_bands():
    c = counts(5)
    c["vth_samples"] = 0          # I5 samples are priced by their own row, not e_rng_draw
    base = CostModel().energy(c, ARCH, 5)
    assert CostModel(scale={"e_rng_draw": 3.0}).energy(c, ARCH, 5)["rng"] == pytest.approx(3 * base["rng"])
    lo, hi = (total(CostModel(band=b).energy(c, ARCH, 5)) for b in ("lo", "hi"))
    assert lo < total(base) < hi


def test_every_entry_has_source_and_band():
    t = load_table()
    assert t and all(r["source"] and r["band_lo_x"] <= 1 <= r["band_hi_x"] and r["placeholder"] in (0, 1)
                     for r in t.values())


def test_no_placeholder_rows_remain():
    assert placeholders() == []


def test_tcam_is_never_charged():
    c = counts(0)
    c["tcam_searches"] = 1
    with pytest.raises(AssertionError):
        CostModel().energy(c, ARCH, 1)


def _leak(arch, cycles=1000):
    c = counts(0)
    c["cycles"] = cycles
    return CostModel().energy(c, arch, 0)["leakage"]


def test_leakage_scales_with_n_and_machine():
    small, big = _leak(Arch(n=64, w_bits=4, arm="mesa")), _leak(Arch(n=256, w_bits=4, arm="mesa"))
    assert 3.5 < big / small < 4.1
    assert _leak(Arch(n=64, w_bits=4, arm="mesa", i11=True)) < small            # greedy drops the lane RNG
    assert _leak(Arch(n=64, w_bits=4, arm="mesa", i5=True)) < small


def test_leakage_n256_is_milliwatt_scale():
    uw = _leak(Arch(n=256, w_bits=4, arm="da_offset"), cycles=1) / CostModel().v("t_clk") * 1e-3 * 1e3
    assert 2000 < uw < 20000            # about 7 mW at N = 256 (ENERGY_RECONCILE), not the old 10 uW constant


def test_i10_gating_removes_only_bias_and_time():
    c = counts(0)
    c["cycles"] = 100
    cm, a = CostModel(), Arch(n=16, w_bits=4, arm="none")
    ungated = cm.energy(c, a, 10)["leakage"]
    c["gated_cycles"] = 10
    assert cm.energy(c, a, 10)["leakage"] == pytest.approx(ungated - 10 * cm.v("e_adc_bias_step"))
