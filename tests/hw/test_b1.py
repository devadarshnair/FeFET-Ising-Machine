"""P4.01: B1 = Yin 2024 MESA as a configuration of the golden machine (scripts/baselines/yin_mesa.py)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import yin_mesa as ym  # noqa: E402
from cim_field import CimCfg  # noqa: E402
from cost_model import CostModel, total  # noqa: E402
from instances import maxcut_qubo, qubo_instance, random_graph  # noqa: E402
from restart import RestartCfg  # noqa: E402
from tim_golden import Machine  # noqa: E402


def mc(n, seed=1, steps=2000, t0=3.0, t1=0.1):
    d, P = maxcut_qubo(n, random_graph(n, 0.1 if n > 32 else 0.4, seed))
    return qubo_instance(d, P, seed=seed + 7, steps=steps, t_start=t0, t_end=t1, deoff=1)


def test_config_loads():
    cfg = ym.B1Cfg()
    assert (cfg.tile, cfg.w_bits, cfg.adc_bits, cfg.label) == (32, 3, 8, "literature-parameterised")
    rs = cfg.restart()
    assert rs.arm == "mesa" and rs.K is None
    m = ym.b1_machine(mc(16))
    assert m.deoff == 0 and m.power is None and m.restart.K == 32
    cfg_file = Path(__file__).resolve().parents[2] / "rtl" / "cfg" / "b1_yin.cfg"
    assert cfg_file.read_text().strip()


def test_tiling_counts_100():
    c = ym.tile_counts(100)
    # 4 x 4 blocks, 2 polarities x 3 planes per block -> 96 tiles of 32 x 32
    assert c == dict(blocks=4, tiles=96, conversions=96 * 32, cell_reads=96 * 1024,
                     tile_sum_adds=3 * 6 * 128, shift_adds=600)
    inst = mc(100, steps=50)
    m, res = ym.run_b1(inst)
    c = ym.b1_counts(m)
    assert c["array_reads"] == 50
    assert c["adc_conversions"] == 50 * 3072 and c["adc_conv_bits"] == 50 * 3072 * 8
    assert c["array_cell_reads"] == 50 * 98304
    assert m.cim.conversions == 50 * 3072


def test_tiled_field_exact_at_sigma0():
    inst = mc(100, steps=1)
    f = ym.TiledCimField(ym.B1Cfg(), inst.P, inst.d)
    rng = np.random.default_rng(3)
    for _ in range(20):
        x = rng.integers(0, 2, 100)
        assert np.array_equal(f.field(x), inst.d + inst.P @ x)


def test_single_tile_matches_plain_cim():
    """n <= 32: B1 golden trace equals the plain CiM machine (the RTL b1_maxcut16 reference)."""
    inst = ym.b1_instance(mc(16))
    plain = Machine(inst, restart=RestartCfg(arm="mesa"), cim=CimCfg(adc_bits=8, w_bits=3))
    a = plain.run().trace
    b = ym.b1_machine(inst, counters=False).run().trace
    assert a == b


@pytest.mark.parametrize("seed", range(3))
def test_mesa_epochs_fire(seed):
    """Replay: restart exactly when 2n consecutive steps pass without best-so-far improvement; reload best, T := T0."""
    inst = mc(16, seed=seed, steps=3000, t0=2.0, t1=0.5)
    m = ym.b1_machine(inst, counters=False)
    K, stall, last, fired = 2 * 16, 0, m.best_f, []
    for _ in range(inst.steps):
        m.step()
        stall = 0 if m.best_f > last else stall + 1
        last = m.best_f
        if stall >= K:
            fired.append(m.t)
            assert np.array_equal(m.x, m.best_x) and m.temp == inst.t0 and m.eoff == 0
            stall = 0
    assert fired and fired == m.restart.events


def test_cost_shared_table():
    m, _ = ym.run_b1(mc(100, steps=30))
    e, a = ym.b1_energy(m), ym.b1_area(100)
    assert total(e) > 0 and total(a) > 0 and e["tcam"] == 0 and e["restart"] > 0
    assert ym.b1_energy(m, CostModel(scale={"e_adc_conv_bit": 2.0}))["adc"] == pytest.approx(2 * e["adc"])
