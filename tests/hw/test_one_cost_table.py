"""P4.08 (P4_CHECK M1): ours, B1, B2 and B3 are all costed on the identical canonical table (hash-equal)."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import pytest  # noqa: E402
import cost_model as cm  # noqa: E402
import fujitsu_da as b3  # noqa: E402
import hycim_b2 as b2  # noqa: E402
import yin_mesa as b1  # noqa: E402


def _default_table_hashes(monkeypatch) -> list[str]:
    seen = []
    orig = cm.CostModel.__init__

    def spy(self, *a, **kw):
        orig(self, *a, **kw)
        seen.append(cm.table_hash(self.t))

    monkeypatch.setattr(cm.CostModel, "__init__", spy)
    cm.CostModel()                       # ours (cost_report uses the default CostModel())
    b1.b1_area(16)                       # B1 default cost
    b3.b3_area(16)                       # B3 default cost
    return seen


def test_all_machines_load_identical_table(monkeypatch):
    hashes = _default_table_hashes(monkeypatch)
    assert len(hashes) == 3 and len(set(hashes)) == 1
    assert hashes[0] == cm.table_hash(cm.canonical_table())


def test_b2_defaults_to_canonical_cost_model():
    assert "cost or CostModel()" in inspect.getsource(b2.run_energy)
    assert b2.CostModel is cm.CostModel


def test_canonical_table_is_p309_backfill():
    t = cm.canonical_table()
    assert cm.TABLE.name == "energy_table_v1_p309.csv"
    assert t["g_digital_per_lane"]["value"] == 6578.75 and t["a_nand2"]["value"] == 1.88
    assert {"e_sram_read_bit", "a_sram_bit"} <= set(t)


def _bias_delta(leak_of) -> float:
    """Leakage change when only the ADC comparator-bias row is tripled (everything else fixed)."""
    return leak_of(cm.CostModel(scale={"e_adc_bias_step": 3.0})) - leak_of(cm.CostModel())


def test_one_adc_rule_bias_charged_per_step_on_every_machine_with_an_adc():
    """P4.08 M2: e_adc_bias_step is charged once per ungated step by ours, B1 and B2; B3 has no ADC and pays none."""
    from counters import FIELDS
    from instances import maxcut_qubo, qubo_instance, random_graph
    import fujitsu_da as da
    bias, steps = cm.CostModel().v("e_adc_bias_step"), 50
    c = {f: 0 for f in FIELDS}
    c["cycles"] = 1000
    ours = _bias_delta(lambda k: k.energy(c, cm.Arch(n=16, w_bits=4, arm="none"), steps)["leakage"])
    assert ours == 2 * steps * bias
    inst = qubo_instance(*maxcut_qubo(64, random_graph(64, 0.1, 1)), seed=3, steps=steps, t_start=3.0, t_end=0.1, deoff=0)
    m1, _ = b1.run_b1(inst)
    assert _bias_delta(lambda k: b1.b1_energy(m1, k)["leakage"]) == pytest.approx(2 * len(m1.counters.steps) * bias)
    assert _bias_delta(lambda k: b2.leakage_fj(steps, k)) == pytest.approx(2 * steps * bias)
    m3 = da.b3_machine(inst, da.B3Cfg(offset_rate=1))
    m3.run(keep_trace=False)
    assert _bias_delta(lambda k: da.b3_energy(m3, k)["leakage"]) == 0
    assert bias > 0


def test_one_adc_rule_tiles_scale_conversions_on_b2_like_ours_and_b1():
    """P4.08 M3: every extra row/column tile costs one more conversion per step; B2 adds a 1-bit comparator conversion per tile."""
    k, steps = cm.CostModel(), 100
    one = b2.adc_energy_fj(steps, 1, k)
    assert one == steps * b2.PROFIT_BITS * k.v("e_adc_conv_bit")
    assert b2.adc_energy_fj(steps, 3, k) - one == pytest.approx(2 * steps * k.v("e_adc_conv_bit"))
    assert b2.run_energy.__code__.co_names.count("adc_energy_fj") == 1      # run_energy tiles by ceil(n / COLS)
