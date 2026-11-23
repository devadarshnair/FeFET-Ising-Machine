"""timing study v1: measured_v1 cost table overlay, the explicit area model, and a CI-fast smoke of the synthesis/STA flow."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cost_model import TABLE_MEASURED_V1, Arch, CostModel, canonical_table, load_table, measured_v1_table, table_by_name, table_hash

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "hw_timing"))
import area_model  # noqa: E402

MEASURED_KEYS = {"t_clk", "a_nand2", "p_leak_nand2_nw"}


def test_default_table_is_unchanged_canonical():
    assert table_hash(CostModel().t) == table_hash(canonical_table()) == table_hash(table_by_name("canonical"))


def test_measured_v1_overlays_only_its_rows():
    canon, meas = canonical_table(), measured_v1_table()
    assert set(meas) == set(canon)
    changed = {k for k in canon if canon[k]["value"] != meas[k]["value"]}
    assert changed <= MEASURED_KEYS and set(load_table(TABLE_MEASURED_V1)) == MEASURED_KEYS
    assert all("timing study v1" in meas[k]["source"] and meas[k]["placeholder"] == 0 for k in MEASURED_KEYS)


def test_measured_values_are_physical():
    m = measured_v1_table()
    assert 0.5 < m["t_clk"]["value"] < 10          # ns
    assert 0.5 < m["a_nand2"]["value"] < 5         # um2 per NAND2-eq, 45 nm class
    assert 0.1 < m["p_leak_nand2_nw"]["value"] < 100


def test_unknown_table_name_rejected():
    with pytest.raises(AssertionError):
        table_by_name("nope")


def test_area_model_range_brackets_nominal_and_override_is_linear():
    arch = Arch(n=64, w_bits=2, arm="kc2", i11=True)
    r = area_model.tile_area_range(arch)
    assert r["lo"] < r["nom"] < r["hi"]
    base = area_model.tile_area(arch, a_array_cell=0.1)["array"]
    assert area_model.tile_area(arch, a_array_cell=0.2)["array"] == pytest.approx(2 * base)


def test_area_model_nominal_equals_cost_model():
    arch = Arch(n=64, w_bits=2, arm="kc2", i11=True)
    assert area_model.tile_area(arch) == CostModel(table=measured_v1_table()).area(arch)


TOOLS = [Path.home() / "tools/yosys/bin/yosys", Path.home() / "tools/sta/bin/sta",
         Path.home() / "tools/pdk/nangate45/NangateOpenCellLibrary_typical.lib"]


@pytest.mark.skipif(not all(p.exists() for p in TOOLS) or os.environ.get("TT_SKIP_FLOW") == "1",
                    reason="EDA tools / Nangate45 lib not installed (see docs/hw/results/TIMING_AREA_V1.md)")
def test_flow_smoke(tmp_path):
    env = dict(os.environ, TT_OUT=str(tmp_path / "smoke"))
    p = subprocess.run([str(ROOT / "rtl/pnr/run_timing_v1.sh"), "--smoke"], env=env, capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stdout + p.stderr
    sys.path.insert(0, str(ROOT / "scripts" / "hw_timing"))
    import timing_v1_report as tr
    for b in ("lane", "rng", "sel_N16"):
        r = tr.block(tmp_path / "smoke" / b)
        assert r["cell_area_um2"] > 0 and 0.1 < r["arrival_ns"] < 20 and r["p_leak_w"] > 0
    shutil.rmtree(tmp_path / "smoke")
