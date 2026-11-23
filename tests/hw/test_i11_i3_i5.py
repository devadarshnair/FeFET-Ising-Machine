"""H2 rungs 4c-4e: I11 greedy + Kc2 kick, I3 ramped penalty gain, I5 Vth-spread acceptance noise (golden, defaults off)."""
import math

import numpy as np
import pytest

import cost_model as cm
from cim_field import CimCfg
from counters import FIELDS, CycleCfg
from instances import d5c_make_instance, d5c_to_tim, maxcut_qubo, qubo_instance, random_graph, random_qubo
from power import PowerCfg
from restart import RestartCfg
from tim_golden import Machine
from tweaks import TweakCfg, TweakUnit

STEPS = 600


def qubo(seed=0, t_start=1.0, deoff=1):
    d, P = maxcut_qubo(16, random_graph(16, 0.3, seed))
    return qubo_instance(d, P, seed=seed + 5, steps=STEPS, t_start=t_start, t_end=0.05, deoff=deoff)


def knap(rule, lam=2.0, seed=0):
    raw = d5c_make_instance(14, 2, seed)
    return d5c_to_tim(raw, rule=rule, T0=2.0, T_min=0.05, budget=STEPS, seed=seed, lam=lam, dE_off=0.5, Q=8)


def run(inst, arm="da_offset", **kw):
    m = Machine(inst, RestartCfg(arm), counters=CycleCfg(), **kw)
    return m, m.run()


# ------------------------------------------------------------------------------------------------ off switches
@pytest.mark.parametrize("arm", ("da_offset", "kc2", "mesa", "none"))
def test_default_tweaks_off_bit_exact_qubo(arm):
    inst = qubo()
    for cim in (None, CimCfg(adc_bits=8)):
        ref = Machine(inst, RestartCfg(arm), cim=cim, power=PowerCfg(i10=True, i7=cim is not None, b_hi=8, b_lo=5)).run().trace
        got = Machine(inst, RestartCfg(arm), cim=cim, power=PowerCfg(i10=True, i7=cim is not None, b_hi=8, b_lo=5),
                      tweaks=TweakCfg()).run().trace
        assert got == ref


@pytest.mark.parametrize("rule", ("hw", "penalty", "filter"))
def test_default_tweaks_off_bit_exact_knap(rule):
    inst = knap(rule)
    assert Machine(inst, tweaks=TweakCfg()).run().trace == Machine(inst).run().trace


def test_off_counters_unchanged():
    inst = qubo()
    a, _ = run(inst, "kc2")
    b, _ = run(inst, "kc2", tweaks=TweakCfg())
    assert a.counters.total == b.counters.total
    assert a.counters.total["ramp_updates"] == a.counters.total["vth_samples"] == 0


# ------------------------------------------------------------------------------------------------ I11
def test_i11_needs_kc2():
    with pytest.raises(AssertionError):
        Machine(qubo(), RestartCfg("mesa"), tweaks=TweakCfg(i11=True))


def test_i11_no_lane_rng_greedy_monotone_between_kicks():
    inst = qubo()
    m = Machine(inst, RestartCfg("kc2"), tweaks=TweakCfg(i11=True))
    res = m.run()
    fresh = Machine(inst, RestartCfg("kc2")).lanes
    assert all(np.array_equal(getattr(m.lanes, k), getattr(fresh, k)) for k in ("s0", "s1", "s2", "s3")), "lane streams advance"
    assert m.eoff == 0 and m.deoff == 0
    kicks = set(m.restart.events)
    assert kicks, "stall kick must fire on this cold instance"
    f = [int(line.split()[4]) for line in res.trace[:-1]]      # the trace line of step t already shows a kick at t
    drops = [t for t in range(2, len(f) + 1) if f[t - 1] < f[t - 2]]
    assert drops == [] or all(t in kicks for t in drops), "f may drop only at a kick step"


def test_i11_counters_and_cost():
    inst = qubo()
    off, _ = run(inst, "kc2")
    on, _ = run(inst, "kc2", tweaks=TweakCfg(i11=True))
    c, o = on.counters.total, off.counters.total
    assert c["lut_reads"] == 0 and o["lut_reads"] == inst.n * STEPS
    assert c["rng_draws"] == STEPS + c["restarts"] * on.restart.L and o["rng_draws"] == (inst.n + 1) * STEPS + o["restarts"] * on.restart.L
    cost = cm.CostModel()
    e_on = cost.energy(c, cm.Arch(n=inst.n, arm="kc2", i11=True), STEPS)
    e_off = cost.energy(o, cm.Arch(n=inst.n, arm="kc2"), STEPS)
    assert e_on["rng"] == pytest.approx(c["rng_draws"] * cost.v("e_rng_draw")) and e_on["rng"] < e_off["rng"]
    a_on, a_off = cost.area(cm.Arch(n=inst.n, arm="kc2", i11=True)), cost.area(cm.Arch(n=inst.n, arm="kc2"))
    assert a_on["rng"] == pytest.approx(cost.v("g_rng_per_lane") * cost.v("a_nand2")) and a_on["rng"] < a_off["rng"]


def test_i11_with_cim_and_power_runs():
    inst = qubo()
    m = Machine(inst, RestartCfg("kc2"), cim=CimCfg(adc_bits=8), power=PowerCfg(i10=True, K_g=4), counters=CycleCfg(),
                tweaks=TweakCfg(i11=True))
    m.run()
    assert m.counters.total["skipped_reads"] > 0


# ------------------------------------------------------------------------------------------------ I3
def test_i3_needs_penalised_knapsack():
    with pytest.raises(AssertionError):
        Machine(qubo(), tweaks=TweakCfg(i3=True))
    with pytest.raises(AssertionError):
        Machine(knap("filter"), tweaks=TweakCfg(i3=True))


def test_i3_ramp_values_hand_computed():
    class M:
        inst = knap("penalty")
        restart = type("R", (), {"cfg": RestartCfg()})()
        cim = None
    tu = TweakUnit(TweakCfg(i3=True, lam_lo=2, ramp_steps=4), M)
    lam = 10
    assert [tu.lam_at(t, lam) for t in (1, 2, 3, 4, 5, 9)] == [4, 6, 8, 10, 10, 10]
    assert tu.ramp_updates == 4 and TweakUnit(TweakCfg(), M).lam_at(3, lam) is None


@pytest.mark.parametrize("rule", ("hw", "penalty"))
def test_i3_degenerate_ramps_equal_fixed(rule):
    inst = knap(rule)
    ref = Machine(inst).run().trace
    assert Machine(inst, tweaks=TweakCfg(i3=True, lam_lo=inst.lam)).run().trace == ref
    assert Machine(inst, tweaks=TweakCfg(i3=True, ramp_steps=1)).run().trace == ref


@pytest.mark.parametrize("rule", ("hw", "penalty"))
def test_i3_ramp_changes_trace_and_counts_updates(rule):
    inst = knap(rule, lam=6.0)
    ref = Machine(inst).run().trace
    m, res = run(inst, tweaks=TweakCfg(i3=True, ramp_steps=STEPS // 2))
    assert res.trace != ref and m.counters.total["ramp_updates"] == STEPS // 2


def test_i3_cost_rows():
    cost = cm.CostModel()
    base = dict.fromkeys(FIELDS, 0)
    hi = dict(base, ramp_updates=7)
    arch = cm.Arch(n=16, arm="none", i3=True)
    d = cost.energy(hi, arch, 10)["digital"] - cost.energy(base, arch, 10)["digital"]
    assert d == pytest.approx(7 * cost.v("e_ramp_update"))
    assert cost.area(arch)["digital"] - cost.area(cm.Arch(n=16, arm="none"))["digital"] == pytest.approx(
        cost.v("g_ramp_unit") * cost.v("a_nand2"))


# ------------------------------------------------------------------------------------------------ I5
def test_i5_independent_equals_off_trace_but_counts_device_noise():
    inst = qubo()
    off, r_off = run(inst, "kc2")
    on, r_on = run(inst, "kc2", tweaks=TweakCfg(i5=True))
    assert r_on.trace == r_off.trace
    c = on.counters.total
    assert c["vth_samples"] == inst.n * STEPS and c["lut_reads"] == 0
    assert c["rng_draws"] == STEPS + c["restarts"] * on.restart.L


def test_i5_hold_and_group():
    inst = qubo()
    _, ref = run(inst)
    m, r = run(inst, tweaks=TweakCfg(i5=True, hold=3))
    assert r.trace != ref.trace and m.counters.total["vth_samples"] == inst.n * math.ceil(STEPS / 3)
    m4, _ = run(inst, tweaks=TweakCfg(i5=True, group=4))
    assert m4.counters.total["vth_samples"] == math.ceil(inst.n / 4) * STEPS


def test_i5_group_shares_sample_within_group():
    class Lanes:
        def __init__(self):
            self.k = 0

        def next(self):
            self.k += 1
            return np.arange(8, dtype=np.uint64) + 100 * self.k

    class M:
        inst = qubo()
        restart = type("R", (), {"cfg": RestartCfg()})()
        cim = None
    tu = TweakUnit(TweakCfg(i5=True, group=4, hold=2), M)
    tu._n = 8
    lanes = Lanes()
    u1, u2, u3 = tu.draw(lanes), tu.draw(lanes), tu.draw(lanes)
    assert list(u1) == [100] * 4 + [104] * 4 and u2 is u1 and lanes.k == 2 and list(u3) == [200] * 4 + [204] * 4


def test_i5_i11_exclusive():
    with pytest.raises(AssertionError):
        TweakCfg(i5=True, i11=True)


def test_i5_cost_rows_and_area():
    inst = qubo()
    on, _ = run(inst, "kc2", tweaks=TweakCfg(i5=True))
    cost = cm.CostModel()
    c = on.counters.total
    e = cost.energy(c, cm.Arch(n=inst.n, arm="kc2", i5=True), STEPS)
    assert e["rng"] == pytest.approx(c["rng_draws"] * cost.v("e_rng_draw") + c["vth_samples"] * cost.v("e_vth_noise_sample")
                                     + STEPS * cost.v("e_i5_hold_ctl_rtl"))
    a = cost.area(cm.Arch(n=inst.n, arm="kc2", i5=True))["rng"]
    assert a == pytest.approx((cost.v("g_rng_per_lane") + inst.n * cost.v("g_vth_noise_per_lane")
                               + cost.v("g_i5_hold_ctl_rtl")) * cost.v("a_nand2"))


# ------------------------------------------------------------------------------------------------ table
def test_tweak_rows_flags_and_in_canonical_table():
    t = cm.canonical_table()
    assert t["g_ramp_unit"]["value"] == t["g_i3_lam_ramp_rtl"]["value"] == 1877.5
    assert t["g_vth_noise_per_lane"]["value"] == t["g_i5_group_mux_per_lane_rtl"]["value"] == 887.25
    for k in ("e_ramp_update", "e_vth_noise_sample", "g_ramp_unit", "g_vth_noise_per_lane", "e_i5_hold_ctl_rtl"):
        assert t[k]["placeholder"] == 0 and k not in cm.placeholders(t)
