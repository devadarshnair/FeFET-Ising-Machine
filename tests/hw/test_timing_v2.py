"""timing study v2: selection-latency parameter in the golden cycle model, pipelined select tree RTL (Icarus unit bench, Verilator smoke cells,
lint), Kc2-only restart unit equivalence, measured_v2 cost model and offline re-pricing hooks."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "hw_timing"))
import rtl_spotcheck as sc  # noqa: E402
import analog_model  # noqa: E402
import gen_tests  # noqa: E402
from cost_model import (Arch, CostModel, MeasuredCost, MeasuredCostV2, canonical_table, measured_v1_table, measured_v2_table,  # noqa: E402
                        table_by_name, table_hash)
from counters import CycleCfg  # noqa: E402
from instances import maxcut_qubo, qubo_instance, random_graph  # noqa: E402
from power import PowerCfg  # noqa: E402
from restart import RestartCfg  # noqa: E402
from cim_field import CimCfg  # noqa: E402
from tim_golden import Machine  # noqa: E402

IVERILOG = shutil.which("iverilog")
HAVE_VERILATOR = (sc.VERILATOR / "verilator").exists()


def _machine(sel_lat):
    d, P = maxcut_qubo(8, random_graph(8, 0.5, 1))
    inst = qubo_instance(d, P, seed=3, steps=20, t_start=3.0, t_end=0.2, deoff=1)
    pw = PowerCfg(i7=True, i10=True, b_hi=6, b_lo=3, K_p=5, K_g=8)
    return Machine(inst, restart=RestartCfg("kc2", K=8, L=3), cim=CimCfg(adc_bits=6, w_bits=8, lfsr=True, sg=100, seed=7), power=pw,
                   counters=CycleCfg(sel_lat=sel_lat))


def test_default_selection_latency_is_old_behaviour():
    assert CycleCfg().sel_lat == 1


@pytest.mark.parametrize("lat", [2, 5, 9])
def test_selection_latency_changes_only_cycles(lat):
    base, piped = _machine(1), _machine(lat)
    rb, rp = base.run(), piped.run()
    assert rb.trace == rp.trace                                   # the selected spin of every step is identical
    assert piped.counters.total["cycles"] - base.counters.total["cycles"] == 20 * (lat - 1)
    for a, b in zip(base.counters.steps, piped.counters.steps):
        assert {k: v for k, v in a.items() if k != "cycles"} == {k: v for k, v in b.items() if k != "cycles"}


def test_sel_lat_of_matches_rtl_formula():
    assert gen_tests.sel_lat_of(0, 0, 16) == 2
    assert gen_tests.sel_lat_of(0b1111, 0b111, 16) == 2 + 4 + 3
    assert gen_tests.sel_lat_of(0xFFFF, 0xFFFF, 16) == 2 + 4 + 3          # masks above LOG2N are ignored


@pytest.mark.skipif(IVERILOG is None, reason="iverilog not available")
def test_pipelined_tree_equals_single_cycle_tree(tmp_path):
    exe = tmp_path / "sp.vvp"
    srcs = sorted(str(p) for p in (ROOT / "rtl" / "src").glob("*.v"))
    subprocess.run([IVERILOG, "-g2012", "-s", "tb_select_pipe", "-o", str(exe), str(ROOT / "rtl/tb/tb_select_pipe.v"), *srcs], check=True,
                   capture_output=True)
    out = subprocess.run(["vvp", "-n", str(exe)], capture_output=True, text=True).stdout
    assert "PASS tb_select_pipe 1494 checks" in out, out


@pytest.mark.skipif(not HAVE_VERILATOR, reason="Verilator not available")
def test_lint_clean_with_pipelined_tree_and_kc2_only_unit():
    r = subprocess.run(["bash", str(ROOT / "rtl/verilator/lint.sh")], capture_output=True, text=True)
    assert r.returncode == 0 and "LINT OK" in r.stdout, r.stdout + r.stderr


@pytest.mark.skipif(not HAVE_VERILATOR, reason="Verilator not available")
@pytest.mark.parametrize("mode", ["off", "mid", "max"])
def test_rtl_spotcheck_bit_exact_for_every_selection_latency(mode):
    sc.SEL_MODE = mode
    try:
        rows = sc.run_all(steps=120, only="maxcut_kc2") + sc.run_all(steps=120, only="colouring_none")
    finally:
        sc.SEL_MODE = "off"
    assert rows and all(r["status"] == "ok" for r in rows), rows


def test_measured_v2_overlays_only_its_rows_and_keeps_v1():
    v1, v2, canon = measured_v1_table(), measured_v2_table(), canonical_table()
    assert table_hash(table_by_name("measured_v1")) == table_hash(v1) and table_hash(v1) != table_hash(v2)
    assert set(v2) == set(canon)
    assert 0.5 < v2["t_clk"]["value"] < v1["t_clk"]["value"]


def test_v2_block_table_is_consistent():
    cm = MeasuredCostV2()
    for n in (64, 256, 512, 1024):
        assert cm.sel_lat_at(n, "ours") >= 2
        assert cm.t_clk_at(n, "ours") < MeasuredCost().t_clk_at(n, "ours") or n == 64
        # measured result: the Fisher-Yates permutation table, not the MESA encoder, is the area of the unit (Kc2-only within 10 % of the full unit)
        assert 0.9 < cm._at("tt_a_restartk", n) / cm._at("tt_a_restart", n) < 1.1
    # pipelined restart units no longer set the clock of a machine with the pipelined select tree (rule A, the primary): their paths are below the tree's;
    # the first-issue unpipelined units were above it (3.83 / 14.08 ns at N = 1024)
    for n in (64, 128, 256, 512, 1024):
        assert cm._at("tt_t_restartk", n) <= max(cm._at("tt_t_selp", n), cm.blocks["tt_t_lane_path"]["value"]) and cm._at("tt_t_restart", n) <= cm._at("tt_t_selp", n) * 1.01
    assert cm._at("tt_t_restart0", 1024) > 5 * cm._at("tt_t_restart", 1024)         # first issue: MESA encoder 14.08 ns
    assert cm._at("tt_t_restartk0", 1024) > cm._at("tt_t_restartk", 1024)           # first issue: 3.83 ns


def test_pipelined_repricing_adds_exactly_the_latency_cycles():
    cm, c = MeasuredCostV2(), {"cycles": 1000, "array_reads": 50, "field_reads": 40, "skipped_reads": 60}
    desc = {"kind": "ours", "n_pad": 256, "n_act": 240, "restart": "kc2"}
    lat = cm.sel_lat_at(256, "ours")
    assert cm.adjust_counters(desc, c, 100)["cycles"] == 1000 + 100 * (lat - 1)
    assert MeasuredCostV2(pipelined=False).adjust_counters(desc, c, 100)["cycles"] == 1000
    lane_only = MeasuredCostV2(baseline_clock="lane_path")
    assert lane_only.adjust_counters({**desc, "kind": "b1"}, c, 100)["cycles"] == 1000           # baseline has no wide tree in that sensitivity


def test_settle_in_ns_costs_cycles_not_free_at_a_fast_clock():
    desc = {"kind": "ours", "n_pad": 256, "n_act": 240, "restart": "kc2"}
    c = {"cycles": 0, "array_reads": 10}
    cm = MeasuredCostV2(pipelined=True, settle_ns=20.0)
    tclk = cm.t_clk_at(256, "ours")
    extra = cm.adjust_counters(desc, c, 0)["cycles"]
    assert extra == 10 * (analog_model.settle_cycles(20.0, tclk) - 1) and extra * tclk >= 10 * (20.0 - tclk) - 1e-6


def test_kc2_arm_is_charged_the_kc2_only_unit_and_mesa_the_full_one():
    desc = {"kind": "ours", "n_pad": 256, "n_act": 240}
    for arm, stem in (("kc2", "restartk"), ("mesa", "restart")):
        cm = MeasuredCostV2(charge_select=False).at({**desc, "restart": arm})
        area, blocks = {"restart": 0.0}, {"leakage": 0.0}
        cm.charge_restart_unit({**desc, "restart": arm}, blocks, area, 100.0)
        assert area["restart"] == pytest.approx(cm._at(f"tt_a_{stem}", 256))
    cm = MeasuredCostV2(kc2_only=False, charge_select=False)
    area = {"restart": 0.0}
    cm.charge_restart_unit({**desc, "restart": "kc2"}, {"leakage": 0.0}, area, 1.0)
    assert area["restart"] == pytest.approx(cm._at("tt_a_restart", 256))


def test_analog_model_ranges_bracket_nominal():
    p = analog_model.parameters()
    assert all(v["lo"] < v["nom"] < v["hi"] for v in p.values())
    arch = Arch(n=64, w_bits=2, arm="kc2", i11=True)
    lo, nom, hi = (sum(analog_model.tile_area(arch, c).values()) for c in ("lo", "nom", "hi"))
    assert lo < nom < hi
    corners = analog_model.sensitivity_corners()
    assert {"nominal", "all_lo", "all_hi"} <= set(corners)
    assert corners["all_hi"]["scale"]["a_adc_col"] == pytest.approx(3.0)


def test_default_cost_model_unchanged_by_v2():
    assert table_hash(CostModel().t) == table_hash(canonical_table())


def _lane_cycle_energy(cm, kind, n_pad, n_act, arm=None, cycles=1000):
    desc = {"kind": kind, "n_pad": n_pad, "n_act": n_act, "restart": arm}
    c = cm.at(desc)
    c.adjust_counters(desc, {"cycles": cycles, "array_reads": 0}, 0)
    blocks, area = {"digital": 0.0, "rng": 0.0, "restart": 0.0, "leakage": 0.0}, {"digital": 0.0, "restart": 0.0}
    c.charge_restart_unit(desc, blocks, area, 1.0)
    return blocks, c._cycles


def test_idle_energy_is_charged_to_every_machine_under_one_rule():
    cm = MeasuredCostV2()
    lane = cm._row("tt_e_idle_lane_fj")
    for kind, n_act in (("ours", 240), ("b1", 240), ("b3", 240)):
        blocks, cyc = _lane_cycle_energy(cm, kind, 256, n_act)
        lanes = 256 if kind == "ours" else n_act
        assert blocks["digital"] >= cyc * lanes * lane, kind              # lane idle energy (tree / controller come on top)
        assert blocks["rng"] == pytest.approx(cyc * 2 * cm._row("tt_e_idle_icg_fj")), kind     # gated generators: only the two clock gates


def test_ungated_generators_cost_every_lane_every_cycle():
    gated, ungated = MeasuredCostV2(), MeasuredCostV2(gen_gated=False)
    for kind in ("ours", "b1", "b3"):
        bg, cyc = _lane_cycle_energy(gated, kind, 256, 240)
        bu, _ = _lane_cycle_energy(ungated, kind, 256, 240)
        lanes = 256 if kind == "ours" else 240
        assert bu["rng"] == pytest.approx(cyc * lanes * ungated._row("tt_e_idle_gen_fj"))
        assert bu["rng"] > 20 * bg["rng"]


def test_idle_charge_can_be_switched_off_and_restart_unit_idle_is_charged():
    off = MeasuredCostV2(idle_charge=False)
    blocks, _ = _lane_cycle_energy(off, "ours", 256, 240, arm="kc2")
    assert blocks["digital"] == 0.0 and blocks["rng"] == 0.0 and blocks["restart"] == 0.0
    on = MeasuredCostV2()
    blocks, cyc = _lane_cycle_energy(on, "ours", 256, 240, arm="kc2")
    assert blocks["restart"] == pytest.approx(cyc * on._at("tt_e_idle_restartk", 256))
    blocks, cyc = _lane_cycle_energy(on, "b1", 256, 240, arm="mesa")
    assert blocks["restart"] == pytest.approx(cyc * on._at("tt_e_idle_restart", 256))


def test_restart_unit_is_in_the_clock_of_every_machine_that_has_one():
    cm = MeasuredCostV2()
    for kind, arm, stem in (("ours", "kc2", "restartk"), ("b1", "mesa", "restart")):
        t = cm.at({"kind": kind, "n_pad": 1024, "n_act": 800, "restart": arm}).v("t_clk")
        assert t >= cm._at(f"tt_t_{stem}", 1024) - 1e-9
    off = MeasuredCostV2(restart_in_clock=False)
    assert off.at({"kind": "b1", "n_pad": 1024, "n_act": 800, "restart": "mesa"}).v("t_clk") == pytest.approx(off.t_clk_at(1024, "b1"))


def test_golden_restart_cycles_follow_the_rtl_fsm_formulas():
    d, P = maxcut_qubo(16, random_graph(16, 0.4, 2))
    for arm, K in (("kc2", 32), ("mesa", 32)):
        inst = qubo_instance(d, P, seed=0x3C16, steps=1500, t_start=3.0, t_end=0.1, deoff=1)
        m = Machine(inst, restart=RestartCfg(arm=arm, K=K, L=10), power=PowerCfg(i10=False), counters=CycleCfg())
        m.run()
        ev = m.restart.event_cycles
        assert len(ev) == len(m.restart.events) > 0
        if arm == "kc2":
            assert set(ev) == {6 * m.restart.L + 1}
        else:
            assert all(c >= 3 and (c - 3) % 4 == 0 for c in ev)
        assert sum(s["restart_cycles"] for s in m.counters.steps) == sum(ev)


def test_restart_cycles_are_priced_per_restart_and_old_raw_records_use_the_stated_rule():
    cm = MeasuredCostV2()
    base = {"cycles": 1000, "restarts": 4, "field_reads": 10, "skipped_reads": 0}
    kc2 = {"kind": "ours", "n_pad": 256, "n_act": 240, "restart": "kc2"}
    lat = cm.sel_lat_at(256, "ours")
    assert cm.adjust_counters(kc2, base, 10)["cycles"] == 1000 + 10 * (lat - 1) + 4 * (6 * 10 + 1)
    assert cm.adjust_counters({**kc2, "kick_L": 40}, base, 10)["cycles"] == 1000 + 10 * (lat - 1) + 4 * (6 * 40 + 1)
    mesa = {"kind": "b1", "n_pad": 256, "n_act": 240, "restart": "mesa"}
    assert cm.adjust_counters(mesa, base, 10)["cycles"] == 1000 + 10 * (lat - 1) + 4 * (4 * 0.5 * 240 + 3)
    assert MeasuredCostV2(mesa_flip_frac=1.0).adjust_counters(mesa, base, 10)["cycles"] > cm.adjust_counters(mesa, base, 10)["cycles"]
    assert MeasuredCostV2(restart_cycles=False).adjust_counters(kc2, base, 10)["cycles"] == 1000 + 10 * (lat - 1)
    exact = {**base, "restart_cycles": 123}                      # new counters carry the exact number
    assert cm.adjust_counters(kc2, exact, 10)["cycles"] == 1000 + 10 * (lat - 1) + 123
    assert cm.adjust_counters({**kc2, "restart": "none"}, base, 10)["cycles"] == 1000 + 10 * (lat - 1)


def test_worst_clock_statistic_uses_the_worst_rows_when_present():
    cm_w = MeasuredCostV2(clock_stat="worst")
    assert cm_w.t_clk_at(1024, "ours") >= MeasuredCostV2().t_clk_at(1024, "ours")


def test_every_priced_table_draws_its_block_rows_from_the_same_source():
    """All committed Stage 3 / 4 re-pricing outputs (ladder, annotated, analog corners) carry the SHA-256 of docs/hw/energy_table_measured_v2_blocks.csv they were
    priced with (restart units, trees, idle energies, N = 1024 medians / worst); it must be one value and equal to the committed file."""
    import hashlib
    import json
    from cost_model import TABLE_MEASURED_V2_BLOCKS
    want = hashlib.sha256(Path(TABLE_MEASURED_V2_BLOCKS).read_bytes()).hexdigest()
    files = sorted((ROOT / "docs/hw/results/timing_v2").glob("h[67]_*.json"))
    assert len(files) >= 60, len(files)
    got = {f.name: json.loads(f.read_text()).get("blocks_sha256") for f in files}
    stale = [n for n, h in got.items() if h != want]
    assert not stale, f"priced with another block table: {stale[:5]} ({len(stale)})"
