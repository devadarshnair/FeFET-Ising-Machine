"""P4_v2 section 8 (checklist A8): the one-cost-rule checks hold for ours, B1, B2 and B3 on EVERY table in cost_model.TABLES
(canonical, measured_v1, measured_v2 and any later table): ADC comparator bias once per ungated step on every machine with an
ADC, one more conversion per extra tile, B3 has no ADC / array charge, and all four machines price from the same table."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import cost_model as cm  # noqa: E402
import fujitsu_da as b3  # noqa: E402
import hycim_b2 as b2  # noqa: E402
import yin_mesa as b1  # noqa: E402
from counters import FIELDS  # noqa: E402
from instances import maxcut_qubo, qubo_instance, random_graph  # noqa: E402

STEPS = 40


def _available(name: str) -> bool:
    try:
        cm.table_by_name(name)
        return True
    except FileNotFoundError:
        return False


TABLES = [pytest.param(t, marks=pytest.mark.skipif(not _available(t), reason=f"{t} table file not produced yet (timing study v2)"))
          for t in cm.TABLES]


def _cost(name, **kw):
    return cm.CostModel(table=cm.table_by_name(name), **kw)


@pytest.fixture(scope="module")
def runs():
    inst = qubo_instance(*maxcut_qubo(64, random_graph(64, 0.1, 1)), seed=3, steps=STEPS, t_start=3.0, t_end=0.1, deoff=0)
    m1, _ = b1.run_b1(inst)
    m3 = b3.b3_machine(inst, b3.B3Cfg())
    m3.run(keep_trace=False)
    return m1, m3


@pytest.mark.parametrize("name", TABLES)
def test_adc_bias_once_per_step_on_every_adc_machine(name, runs):
    m1, m3 = runs
    base, trip = _cost(name), _cost(name, scale={"e_adc_bias_step": 3.0})
    bias = base.v("e_adc_bias_step")
    assert bias > 0
    c = {f: 0 for f in FIELDS}
    c["cycles"] = 1000
    arch = cm.Arch(n=16, w_bits=4, arm="none")
    assert trip.energy(c, arch, STEPS)["leakage"] - base.energy(c, arch, STEPS)["leakage"] == pytest.approx(2 * STEPS * bias)
    d1 = b1.b1_energy(m1, trip)["leakage"] - b1.b1_energy(m1, base)["leakage"]
    assert d1 == pytest.approx(2 * len(m1.counters.steps) * bias)
    assert b2.leakage_fj(STEPS, trip) - b2.leakage_fj(STEPS, base) == pytest.approx(2 * STEPS * bias)
    assert b3.b3_energy(m3, trip)["leakage"] == b3.b3_energy(m3, base)["leakage"]


@pytest.mark.parametrize("name", TABLES)
def test_tiles_scale_conversions(name):
    k = _cost(name)
    one = b2.adc_energy_fj(STEPS, 1, k)
    assert b2.adc_energy_fj(STEPS, 3, k) - one == pytest.approx(2 * STEPS * k.v("e_adc_conv_bit"))
    n1, n2 = b1.tile_counts(32), b1.tile_counts(64)
    assert n2["conversions"] == 4 * n1["conversions"] and n2["tiles"] == 4 * n1["tiles"]


@pytest.mark.parametrize("name", TABLES)
def test_b3_has_no_adc_or_array_charge(name, runs):
    _, m3 = runs
    e, a = b3.b3_energy(m3, _cost(name)), b3.b3_area(64, cost=_cost(name))
    assert e["adc"] == e["array"] == 0 and a["adc"] == a["array"] == 0 and e["sram"] > 0


@pytest.mark.parametrize("name", TABLES)
def test_every_machine_prices_from_the_named_table(name, monkeypatch, runs):
    m1, m3 = runs
    seen = []
    orig = cm.CostModel.v

    def spy(self, key):
        seen.append(cm.table_hash(self.t))
        return orig(self, key)

    monkeypatch.setattr(cm.CostModel, "v", spy)
    k = _cost(name)
    k.energy({f: 0 for f in FIELDS} | {"cycles": 10}, cm.Arch(n=16, w_bits=4, arm="none"), 5)
    b1.b1_energy(m1, k)
    b2.leakage_fj(5, k)
    b3.b3_energy(m3, k)
    assert set(seen) == {cm.table_hash(cm.table_by_name(name))}
