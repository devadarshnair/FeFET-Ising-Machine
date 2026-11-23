"""P2.06: op counters and cycle model, checked on a 3-step hand trace and on the I10 / I7 splits."""
import pytest

from cim_field import CimCfg
from counters import CycleCfg
from instances import maxcut_qubo, qubo_instance, random_graph, random_qubo
from power import PowerCfg
from restart import RestartCfg
from tcam_lite import TcamLiteCfg
from tim_golden import Machine

CY = CycleCfg(search_lat=2, cim_array_lat=1)


def tiny():
    d, P = random_qubo(4, 3, pmax=3, dmax=3)
    return qubo_instance(d, P, seed=5, steps=3, t_start=4.0, t_end=1.0, deoff=1)


def test_three_step_hand_trace():
    # n = 4 lanes, w = 2 weight bits -> cols = 2*2*4 = 16 columns; ADC 4 bits; QUBO: 4 base cycles.
    m = Machine(tiny(), RestartCfg("da_offset"), cim=CimCfg(adc_bits=4, w_bits=2), counters=CY)
    ref, bests = Machine(tiny(), RestartCfg("da_offset"), cim=CimCfg(adc_bits=4, w_bits=2)), []
    for _ in range(3):
        ref.step()
        bests.append(ref.best_f)
    n_improved = sum(1 for a, b in zip([0] + bests, bests) if b > a)
    trace = m.run().trace
    flips = [int(line.split()[1]) >= 0 for line in trace[:3]]
    nf = sum(flips)
    assert nf >= 1                       # the hand trace must contain a flip
    t = m.counters.total
    assert t["field_reads"] == 3 and t["skipped_reads"] == 0
    assert t["array_reads"] == 3 and t["array_cell_reads"] == 3 * 4 * 16
    assert t["adc_conversions"] == 3 * 16 and t["adc_conv_bits"] == 3 * 16 * 4
    assert t["adc_lowbit_conv"] == 0
    assert t["adds"] == 3 * (2 * 2 * 4 + 2 * 4) + nf * 4        # shift-add 16 + accept 8 per step, h update 4 per flip
    assert t["rng_draws"] == 3 * 5 and t["lut_reads"] == 3 * 4
    regs = 3 * (1 + 1 + 1) + nf * (1 + 4 + 1)                    # step ctr, T, E_off per step; x, h, f per flip
    assert t["reg_writes"] == regs + n_improved
    assert t["cycles"] == 3 * (4 + 1 + 4)
    assert t["restarts"] == 0 and t["array_writes"] == 0 and t["tcam_searches"] == 0 and t["gated_cycles"] == 0


def stall_heavy():
    d, P = maxcut_qubo(16, random_graph(16, 0.3, 0))
    return qubo_instance(d, P, seed=11, steps=600, t_start=0.5, t_end=0.01, deoff=1)


def test_i10_skips_counted_separately_and_save_cycles():
    cim = CimCfg(adc_bits=8, w_bits=4)
    off = Machine(stall_heavy(), cim=cim, power=PowerCfg(), counters=CY)
    on = Machine(stall_heavy(), cim=cim, power=PowerCfg(i10=True, K_g=8), counters=CY)
    off.run(), on.run()
    a, b = off.counters.total, on.counters.total
    assert a["skipped_reads"] == 0 and a["field_reads"] == 600
    assert b["skipped_reads"] == on.power.skipped > 0
    assert b["field_reads"] + b["skipped_reads"] == 600 == b["field_reads"] + on.power.skipped
    assert b["array_reads"] == b["field_reads"] == on.power.reads
    assert b["gated_cycles"] == on.power.bias_gated > 0
    assert b["cycles"] == a["cycles"] - b["skipped_reads"] * (CY.cim_array_lat + 8)
    assert b["adc_lowbit_conv"] == 0


def test_i7_lowbit_conversions_separate_from_skips():
    cim = CimCfg(adc_bits=16, w_bits=4)
    cfg = PowerCfg(i7=True, i10=True, b_hi=16, b_lo=5, K_p=5, K_g=20)
    m = Machine(stall_heavy(), cim=cim, power=cfg, counters=CY)
    m.run()
    t, cols = m.counters.total, 2 * 4 * 16
    lo_reads = sum(1 for c in m.counters.steps if c["adc_lowbit_conv"])
    assert lo_reads > 0 and t["adc_lowbit_conv"] == lo_reads * cols
    assert t["adc_lowbit_bits"] == lo_reads * cols * 5
    assert t["adc_conv_bits"] == (t["array_reads"] - lo_reads) * cols * 16 + lo_reads * cols * 5
    assert t["skipped_reads"] > 0 and t["adc_conversions"] == t["array_reads"] * cols
    assert all(not (c["skipped_reads"] and c["adc_lowbit_conv"]) for c in m.counters.steps)


def test_restarts_rng_and_tcam_counts():
    m = Machine(stall_heavy(), RestartCfg("kc2", K=20, L=3), tcam=TcamLiteCfg(on=True, M=4, K_w=5), counters=CY)
    m.run()
    t = m.counters.total
    assert t["restarts"] == len(m.restart.events) > 0
    assert t["rng_draws"] == 600 * 17 + 3 * t["restarts"]
    assert t["array_writes"] == m.tcam.writes > 0 and t["tcam_searches"] == m.tcam.searches
    assert t["cycles"] == 600 * 4 + m.tcam.searches


def test_counters_do_not_change_trajectory():
    ref = Machine(stall_heavy(), cim=CimCfg(adc_bits=6)).run().trace
    assert Machine(stall_heavy(), cim=CimCfg(adc_bits=6), counters=CY).run().trace == ref
