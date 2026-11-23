"""Idle (quiet) dynamic energy per clock cycle of a Yosys netlist (timing study v2): the clock toggles, every data input is held constant, the netlist is
simulated at gate level (zero delay) and OpenSTA `read_vcd` + `report_power` gives the internal + switching power of the quiet block; times the 10 ns
simulation clock it is the energy per idle cycle (clock-pin and sequential energy that every cycle costs whether or not the block works).
  gl_idle.py --net <net.v> --out <dir> [--clk clk] [--tie name=1 ...] [--cycles 120]
Prints / writes <dir>/idle.json {"dyn_fj_per_cycle", "leak_nw", ...}. Run under the local job queue (--rss 1)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gl_power import CLK_NS, LIB, STA, netlist_ports  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--clk", default="clk")
    ap.add_argument("--tie", nargs="*", default=[], help="port=value (default every input 0, rst_n 1)")
    ap.add_argument("--cycles", type=int, default=120)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    net = Path(a.net)
    top, ports = netlist_ports(net)
    text = net.read_text()
    outs = set()
    for m in re.finditer(r"^\s*output\s+(\\\S+|\w+)\s*;", text, re.M):
        outs.add(m.group(1).strip())
    ties = {k: v for k, v in (t.split("=") for t in a.tie)}
    ties.setdefault("rst_n", "1")
    conns = []
    for p in ports:
        if p in outs or p.replace("\\", "") in {o.replace("\\", "") for o in outs}:
            conns.append(f".{p} ()")
        elif p == a.clk:
            conns.append(f".{p} (clk)")
        else:
            base = re.match(r"\\?(\w+)", p).group(1)
            conns.append(f".{p} (1'b{ties.get(base, '0')})")
    tb = out / "tb_idle.v"
    tb.write_text("`timescale 1ns/1ps\nmodule tb_idle;\n  reg clk = 1'b0;\n  always #5 clk = ~clk;\n"
                  f"  {top} dut ({', '.join(conns)});\n"
                  f"  initial begin $dumpfile(\"{out / 'idle.vcd'}\"); $dumpvars(0, dut); #{int(CLK_NS) * a.cycles} $finish; end\nendmodule\n")
    cells = out / "cells.v"
    subprocess.run([sys.executable, "-I", str(HERE / "lib2v.py"), str(LIB), str(cells)], check=True, capture_output=True)
    exe = out / "idle.vvp"
    r = subprocess.run(["iverilog", "-g2012", "-s", "tb_idle", "-o", str(exe), str(tb), str(net), str(cells)], capture_output=True, text=True)
    (out / "compile.log").write_text(r.stdout + r.stderr)
    if r.returncode:
        print(r.stderr[-2000:])
        return 2
    subprocess.run(["vvp", "-n", str(exe)], capture_output=True, text=True, check=True)
    tcl = out / "sta.tcl"
    tcl.write_text(f"read_liberty {LIB}\nread_verilog {net}\nlink_design {top}\ncreate_clock -name clk -period {CLK_NS} [get_ports {a.clk}]\n"
                   f"read_vcd -scope tb_idle/dut -begin_time {int(CLK_NS) * 1000 * 10} {out / 'idle.vcd'}\nreport_power -digits 6\nexit\n")
    p = subprocess.run([str(STA), "-no_splash", "-exit", str(tcl)], capture_output=True, text=True)
    (out / "sta.log").write_text(p.stdout + p.stderr)
    m = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", p.stdout, re.M)
    res = {"net": str(net), "cycles": a.cycles, "ties": ties}
    if m:
        i, s_, l, t = map(float, m.groups())
        res.update(dyn_fj_per_cycle=(i + s_) * CLK_NS * 1e-9 * 1e15, leak_nw=l * 1e9)
    (out / "idle.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))
    return 0 if m else 1


if __name__ == "__main__":
    sys.exit(main())
