"""RTL spot check (P6.01): Verilator model of tim_top vs the golden model, bit-exact on state/energy and activity traces.
Needs Verilator (VERILATOR_BIN, PATH, or ~/tools/verilator) and the RTL tree (HW_RTL_ROOT, default this repository); skipped if absent."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import rtl_spotcheck as sc  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (sc.VERILATOR / "verilator").exists()
    or not (Path(os.environ.get("HW_RTL_ROOT", sc.REPO)) / "rtl" / "src" / "tim_top.v").exists(),
    reason="Verilator or RTL worktree not available")


@pytest.mark.parametrize("family", ["maxcut", "maxsat", "colouring"])
def test_family_all_arms_and_power_modes_bit_exact(family):
    rows = sc.run_all(steps=300, only=family)
    assert len(rows) == 8, "4 restart arms x I7/I10 off/on"
    bad = [r for r in rows if r["status"] != "ok"]
    assert not bad, bad
    assert all(r["trace_lines"] == 301 for r in rows)
    assert all(r["act_lines"] == 300 for r in rows if r["i7_i10"] == "on")


def test_restarts_are_exercised_in_the_rtl_cells():
    rows = sc.run_all(steps=300, only="maxcut")
    assert any(r["restarts"] > 0 for r in rows if r["arm"] != "none")


def test_comparison_detects_a_wrong_golden():
    rtl = sc.rtl_root()
    mq = sc.small_families()["maxcut"]
    inst, rs, cim, _ = sc.make_case(mq, "kc2", False, 300)
    exe = sc.build(rtl, inst.n, sc.WORK)
    assert exe.exists()
    row = sc.run_cell(rtl, "maxcut", mq, "kc2", False, 300)
    rtl_trace = sc.read_lines(sc.WORK / "maxcut_kc2_plain" / "rtl.trace")
    other = sc.tg.Machine(inst, restart=sc.RestartCfg(arm="kc2", K=3, L=10), cim=cim).run().trace   # different K: wrong golden
    assert row["status"] == "ok"
    assert sc.first_difference(other, rtl_trace) is not None


@pytest.mark.parametrize("family", ["maxcut", "maxsat", "colouring"])
def test_i11_and_i5_cells_bit_exact(family):
    rows = sc.run_tweaks(steps=300, only=family)
    assert {(r["tweak"], r["i7_i10"]) for r in rows} == {(t, p) for t in ("i11", "i5") for p in ("off", "on")}
    bad = [r for r in rows if r["status"] != "ok"]
    assert not bad, bad


def test_i3_knapsack_off_and_ramped_bit_exact():
    rows = sc.run_tweaks(steps=300, only="knap")
    assert sorted(r["tweak"] for r in rows) == ["i3", "i3_off"]
    assert all(r["status"] == "ok" for r in rows), rows


def test_tweaks_change_the_golden_trace():
    """The tweak cells would pass trivially if the tweaks did nothing: the golden trace of each differs from tweaks-off."""
    mq = sc.small_families()["maxcut"]
    inst, rs, cim, _ = sc.make_case(mq, "kc2", False, 300)
    off = sc.tg.Machine(inst, restart=rs, cim=cim).run().trace
    for _, arm, tw in sc.TWEAK_CELLS:
        i2, r2, c2, _ = sc.make_case(mq, arm, False, 300)
        ref = sc.tg.Machine(i2, restart=r2, cim=c2).run().trace
        assert sc.tg.Machine(i2, restart=r2, cim=c2, tweaks=tw).run().trace != ref
    k_off, _ = sc.knap_case(300, False)
    k_on, tw = sc.knap_case(300, True)
    assert sc.tg.Machine(k_on, tweaks=tw).run().trace != sc.tg.Machine(k_off).run().trace
    assert off


@pytest.mark.parametrize("family", ["maxcut", "maxsat", "colouring"])
def test_i7v2_cells_bit_exact_and_use_the_column_full_scale(family):
    rows = sc.run_i7v2(steps=300, only=family)
    assert len(rows) == 2 and all(r["tweak"] == "i7v2" for r in rows)
    bad = [r for r in rows if r["status"] != "ok"]
    assert not bad, bad
    assert all(r["act_lines"] == 300 for r in rows)
