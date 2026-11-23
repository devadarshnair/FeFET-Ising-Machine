"""P4.03: B3 = Fujitsu DA (Aramon 2019) as a configuration of the golden machine (scripts/baselines/fujitsu_da.py)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import fujitsu_da as da  # noqa: E402
from cost_model import total  # noqa: E402
from instances import maxcut_qubo, qubo_instance, random_graph, temp_reg  # noqa: E402
from restart import RestartCfg  # noqa: E402
from tim_golden import Machine  # noqa: E402


def mc(n=16, seed=2, steps=3000, deoff=1):
    d, P = maxcut_qubo(n, random_graph(n, 0.4, seed))
    return qubo_instance(d, P, seed=0x3C16, steps=steps, t_start=3.0, t_end=0.1, deoff=deoff)


def test_config_and_rtl_cfg():
    cfg = da.B3Cfg()
    assert (cfg.offset_rate, cfg.coupler_bits, cfg.bias_bits, cfg.label) == (0, 16, 26, "literature-parameterised")
    m = da.b3_machine(mc())
    assert m.cim is None and m.power is None and m.deoff == 0 and m.restart.cfg.arm == "da_offset"
    assert (Path(__file__).resolve().parents[2] / "rtl" / "cfg" / "b3_da.cfg").read_text().strip()


def test_geom_trace_equals_plain_machine():
    """schedule geom: B3 golden trace = plain da_offset machine (the RTL b3_maxcut16 reference)."""
    inst = mc()
    a = Machine(inst, restart=RestartCfg(arm="da_offset")).run().trace
    b = da.b3_machine(inst, da.B3Cfg(offset_rate=1), counters=False).run().trace
    assert a == b


@pytest.mark.parametrize("rate", [1, 3])
def test_offset_resets_on_accept(rate):
    """Alg. 2: E_off += rate on every step with no accepted lane, E_off := 0 on the step that accepts."""
    m = da.b3_machine(mc(steps=4000, deoff=0), da.B3Cfg(offset_rate=rate), counters=False)
    prev, grew, reset = 0, 0, 0
    for _ in range(4000):
        f = m.step().split()
        k, eoff = int(f[1]), int(f[6])
        if k >= 0:
            assert eoff == 0
            reset += prev > 0
        else:
            assert eoff == prev + rate
            grew += 1
        prev = eoff
    assert grew > 0 and reset > 0


def test_rate0_holds_offset():
    m = da.b3_machine(mc(steps=2000), da.B3Cfg(), counters=False)
    for _ in range(2000):
        assert int(m.step().split()[6]) == 0


def test_lin_beta_schedule():
    cfg = da.B3Cfg(schedule="lin_beta", t_high=4.0, t_low=0.5)
    temps = da.lin_beta_temps(cfg, 101)
    assert temps[0] == temp_reg(4.0) and temps[-1] == temp_reg(0.5)
    beta = 1.0 / (np.array(temps) / 65536.0)
    assert np.allclose(np.diff(beta), (2.0 - 0.25) / 100, rtol=1e-2)   # UQ16.16 register rounding
    m = da.b3_machine(mc(steps=101), cfg, counters=False)
    for _ in range(101):
        m.step()
    assert m.temp == temps[100]


def test_sk_qubo_matches_ising():
    rng = np.random.default_rng(0)
    for kind in ("bimodal", "gaussian"):
        d, P = da.sk_qubo(32, 1, kind)
        J = P // 4
        for _ in range(10):
            x = rng.integers(0, 2, 32)
            s = 2 * x - 1
            ising = int(s @ np.triu(J, 1) @ s)
            qubo = int(d @ x + (x @ P @ x) // 2)
            assert qubo == ising - int(np.triu(J, 1).sum())


def test_cost_digital_no_adc():
    inst = qubo_instance(*maxcut_qubo(64, random_graph(64, 0.1, 1)), seed=3, steps=200, t_start=3.0, t_end=0.1, deoff=0)
    m = da.b3_machine(inst, da.B3Cfg(offset_rate=1))
    m.run(keep_trace=False)
    c = da.b3_counts(m)
    assert c["sram_bit_reads"] == m.flips * 64 * 16 and c["adc_conv_bits"] == 0
    e = da.b3_energy(m)
    assert e["adc"] == 0 and e["array"] == 0 and e["sram"] > 0 and e["restart"] > 0 and total(e) > 0
    a = da.b3_area(64)
    assert a["adc"] == 0 and a["sram"] == pytest.approx((64 * 64 * 16 + 64 * 26) * da.b3_cost().v("a_sram_bit"))
    # Yosys-based digital counts come from the P3.11 table, not the v1 placeholders
    assert da.b3_cost().v("g_digital_per_lane") > 1000


def test_acceptance_boost_bounds():
    d, P = da.sk_qubo(64, 1, "bimodal")
    inst = qubo_instance(d, P, seed=5, steps=3000, t_start=1.0, t_end=None, deoff=0)
    m = da.b3_machine(inst, da.B3Cfg(schedule="lin_beta", t_high=20.0, t_low=1.0), counters=False)
    m.window = (2000, 0, 0)
    m.run(keep_trace=False)
    r = da.acceptance_boost(m)
    assert 1.0 <= r <= 64.0


def test_tts99():
    assert da.tts99(0.0, 10) == float("inf") and da.tts99(1.0, 10) == 10.0
    assert da.tts99(0.5, 100) == pytest.approx(100 * np.log(0.01) / np.log(0.5))


def _calib():
    import calib_b3
    return calib_b3


def test_t4_sigma_finite_and_verdict_unchanged():
    cb = _calib()
    rows = [dict(kind=k, n=256, arm="off", attempt=1, boost=[v + j for j in range(5)])
            for k, v in (("bimodal", 100.0), ("gaussian", 50.0)) for _ in range(6)]
    r = cb.t4_result(rows, 256, np.random.default_rng(0))
    assert r["sigma"] == r["sigma"] and r["sigma"] >= 0           # regression: attempt 1 reported sigma = NaN
    assert r["value"] == 52.0 and not r["passed"] and r["excluded"] == 0


def test_t4_nan_runs_excluded_and_counted():
    cb = _calib()
    rows = [dict(kind=k, n=256, arm="off", attempt=1, boost=[200.0, float("nan"), 220.0]) for k in cb.CLASSES for _ in range(4)]
    r = cb.t4_result(rows, 256, np.random.default_rng(0))
    assert r["excluded"] == 8 and r["passed"] and r["sigma"] == r["sigma"]


def test_tts_opt_prefers_early_full_success():
    cb = _calib()
    assert cb.tts_opt([], 10) == float("inf")
    assert cb.tts_opt([5] * 10, 10) == 5.0                          # p = 1 at t = 5 does not pin TTS to the budget
    assert cb.tts_opt([10, 1000], 2) == pytest.approx(min(10 * da.tts99(0.5, 1), 1000.0))


def test_lin_beta_lane_acceptance_is_metropolis():
    """Machine lane acceptance (LUT, UQ16.16 T) matches min(1, exp(gain/T)) at a random state for the DA schedule."""
    from tim_golden import lane_accept_prob, make_lut
    d, P = da.sk_qubo(64, 3, "gaussian")
    t_low, t_high = da.dE_percentiles(d, P, seed=1)
    x = np.random.default_rng(4).integers(0, 2, 64).astype(np.int64)
    for T in (t_low, 0.5 * (t_low + t_high), t_high):
        inst = qubo_instance(d, P, seed=1, steps=10, t_start=T, t_end=None, deoff=0)
        got = lane_accept_prob(inst, x, np.array(make_lut(inst.lab), dtype=np.int64))
        gain = np.where(x == 1, -(d + P @ x), d + P @ x)
        want = np.minimum(1.0, np.exp(gain / np.floor(T * 65536) * 65536))
        assert np.abs(got - want).max() < 0.08
