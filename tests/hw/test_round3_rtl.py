"""Round 3 RTL blocks (rtl/r3/r3_blocks.v): self-checking Icarus testbench of the T-1 lane (gated field update), spare-row remap and the
per-column correction table."""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_r3_blocks_testbench(tmp_path):
    exe = tmp_path / "tb.vvp"
    src = [REPO / "rtl/src/field_unit.v", REPO / "rtl/src/clk_gate.v", REPO / "rtl/r3/r3_blocks.v", REPO / "rtl/r3/tb_r3.v"]
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), *map(str, src)], check=True)
    out = subprocess.run(["vvp", "-n", str(exe)], capture_output=True, text=True, check=True).stdout
    assert "R3TB PASS" in out
