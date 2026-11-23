"""Round 3: activity-annotated energy per EVENT of the T-1 / T-6 / screening blocks (rtl/r3/r3_blocks.v), from zero-delay gate-level
simulation of the Yosys netlists (sim/out/hw/r3/<tag>/net_vec.v) + OpenSTA read_vcd/report_power (Nangate45 typical), as gl_idle.py does for
the timing study v2 idle rows. Each block is driven in two modes with the same clock: 'idle' (no event) and 'event' (one event every cycle, random
data); energy per event = dyn(event) - dyn(idle) per cycle; leakage from the same report. The clock gate is simulated at gate level, so the
gated idle energy is real (vectorless STA cannot see it).
  gl_event_r3.py [--root sim/out/hw/r3] [--cycles 400]   -> <root>/events.json        Run under the local job queue (--rss 1)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gl_power import CLK_NS, LIB, STA  # noqa: E402

DRIVE = {   # tag -> (top, port declarations + instance, idle stimulus, event stimulus); stimulus runs every posedge (blocking at negedge)
    "lane_t1": ("r3_lane_t1", "reg init=1, upd=0, dir=0, chg=0; reg [3:0] sbits=0; reg [7:0] bias=8'd5; wire [15:0] h; wire ovf;",
                ".clk(clk), .init(init), .bias(bias), .upd(upd), .dir(dir), .chg(chg), .sbits(sbits), .h(h), .ovf(ovf)",
                "init=0; upd=0; chg=0;", "init=0; upd=1; chg=1; dir=$random; sbits=$random;"),
    "lane_t1_gated_nochg": ("r3_lane_t1", "reg init=1, upd=0, dir=0, chg=0; reg [3:0] sbits=0; reg [7:0] bias=8'd5; wire [15:0] h; wire ovf;",
                ".clk(clk), .init(init), .bias(bias), .upd(upd), .dir(dir), .chg(chg), .sbits(sbits), .h(h), .ovf(ovf)",
                "init=0; upd=0; chg=0;", "init=0; upd=1; chg=0; dir=$random; sbits=$random;"),
    "lane_t1_ungated": ("r3_lane_t1_ungated", "reg init=1, upd=0, dir=0; reg [3:0] sbits=0; reg [7:0] bias=8'd5; wire [15:0] h; wire ovf;",
                ".clk(clk), .init(init), .bias(bias), .upd(upd), .dir(dir), .sbits(sbits), .h(h), .ovf(ovf)",
                "init=0; upd=0;", "init=0; upd=1; dir=$random; sbits=$random;"),
}
for n in (512, 1024):
    L = (n - 1).bit_length()
    S = n // 32
    LS = (S - 1).bit_length()
    DRIVE[f"remap_N{n}"] = ("r3_remap", f"reg wr=0; reg [{LS-1}:0] wsel=0; reg [{L-1}:0] wrow=0, row=0; wire hit; wire [{LS-1}:0] spare; integer q=0;",
                            ".clk(clk), .wr(wr), .wsel(wsel), .wrow(wrow), .row(row), .hit(hit), .spare(spare)",
                            f"wr=(q<{S}); wsel=q; wrow=q*7; q=q+1;", f"wr=(q<{S}); wsel=q; wrow=q*7; q=q+1; row=$random;")
    for k in (4, 16):
        LK = (k - 1).bit_length()
        DRIVE[f"lcor{k}_N{n}"] = ("r3_lcor_col", f"reg wr=0; reg [{LK-1}:0] wsel=0; reg [{L-1}:0] wrow=0, row=0; reg sbit=0; wire obit; integer q=0;",
                                  ".clk(clk), .wr(wr), .wsel(wsel), .wrow(wrow), .row(row), .sbit(sbit), .obit(obit)",
                                  f"wr=(q<{k}); wsel=q; wrow=q*5; q=q+1;", f"wr=(q<{k}); wsel=q; wrow=q*5; q=q+1; row=$random; sbit=$random;")
    DRIVE[f"screen_N{n}"] = ("r3_screen_ctl", f"reg rst_n=0, start=0, code_vld=0; reg [7:0] cutoff=8'd20, code=0; wire [{L-1}:0] row, col; wire erase, verify, retire, done;",
                             ".clk(clk), .rst_n(rst_n), .start(start), .cutoff(cutoff), .code(code), .code_vld(code_vld), .row(row), .col(col), .erase(erase), .verify(verify), .retire(retire), .done(done)",
                             "rst_n=1; start=0; code_vld=0;", "rst_n=1; start=1; code_vld=1; code=($random & 8'h1f);")


def run(root: Path, tag: str, mode: str, cycles: int) -> dict:
    top, decl, conn, idle, ev = DRIVE[tag]
    src = root / (tag if not tag.startswith("lane_t1_gated") else "lane_t1") / "net_vec.v"
    net = src.with_name("net_vec_sta.v")
    net.write_text(re.sub(r"\bwire signed ", "wire ", src.read_text()))          # OpenSTA's reader rejects 'wire signed' 
    out = root / tag / f"gl_{mode}"
    out.mkdir(parents=True, exist_ok=True)
    stim = idle if mode == "idle" else ev
    tb = out / "tb.v"
    tb.write_text("`timescale 1ns/1ps\nmodule tb;\n  reg clk = 1'b0;\n  always #5 clk = ~clk;\n"
                  f"  {decl}\n  {top} dut ({conn});\n"
                  f"  always @(negedge clk) begin {stim} end\n"
                  f"  initial begin $dumpfile(\"{out / 'w.vcd'}\"); $dumpvars(0, dut); #{int(CLK_NS) * cycles} $finish; end\nendmodule\n")
    cells = root / "cells.v"
    if not cells.exists():
        subprocess.run([sys.executable, "-I", str(HERE / "lib2v.py"), str(LIB), str(cells)], check=True, capture_output=True)
    exe = out / "sim.vvp"
    r = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(exe), str(tb), str(net), str(cells)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])
    subprocess.run(["vvp", "-n", str(exe)], capture_output=True, text=True, check=True)
    tcl = out / "sta.tcl"
    tcl.write_text(f"read_liberty {LIB}\nread_verilog {net}\nlink_design {top}\ncreate_clock -name clk -period {CLK_NS} [get_ports clk]\n"
                   f"read_vcd -scope tb/dut -begin_time {int(CLK_NS) * 1000 * 20} {out / 'w.vcd'}\nreport_power -digits 6\nexit\n")
    p = subprocess.run([str(STA), "-no_splash", "-exit", str(tcl)], capture_output=True, text=True)
    (out / "sta.log").write_text(p.stdout + p.stderr)
    m = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", p.stdout, re.M)
    i, s_, lk, _ = map(float, m.groups())
    return {"dyn_fj_per_cycle": (i + s_) * CLK_NS * 1e-9 * 1e15, "leak_nw": lk * 1e9}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE.parents[1] / "sim" / "out" / "hw" / "r3"))
    ap.add_argument("--cycles", type=int, default=400)
    a = ap.parse_args()
    root = Path(a.root)
    res = {}
    for tag in DRIVE:
        idle, ev = run(root, tag, "idle", a.cycles), run(root, tag, "event", a.cycles)
        area_tag = "lane_t1" if tag.startswith("lane_t1_gated") else tag
        area = float(re.search(r"Chip area for module '\S+': (\S+)", (root / area_tag / "stat.txt").read_text()).group(1))
        res[tag] = {"area_um2": area, "leak_nw": idle["leak_nw"], "idle_fj_per_cycle": idle["dyn_fj_per_cycle"],
                    "event_fj": ev["dyn_fj_per_cycle"] - idle["dyn_fj_per_cycle"]}
        print(tag, json.dumps(res[tag]), flush=True)
    (root / "events.json").write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
