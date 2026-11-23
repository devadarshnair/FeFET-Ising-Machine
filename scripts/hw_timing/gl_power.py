"""Activity-annotated power (timing study v2, item C3): gate-level simulation of the timing study v1 Yosys netlists driven by the signals of an RTL
run of tim_top, then OpenSTA `read_vcd` + `report_power` on the same netlists.

One RTL run = a test cfg + tim_top build parameters. The generated testbench `tb_gl` instantiates tb_top (the RTL top) and next to it
zero-delay gate-level copies of the sampled lanes (tt_lane_i11), their xoshiro128** generators and the select tree (single-cycle
partitioned netlist or the pipelined one). Gate-level inputs are hierarchical taps of the RTL signals of the same names (the stimulus is
the run's real activity); every gate-level output is compared with its RTL counterpart at every negedge once the step phase has started
(mismatch count in the summary = FAIL; this also checks the netlist against the RTL on the run). VCD of the gate-level instances
(step phase only) goes to OpenSTA, annotated on the same netlist with the 10 ns simulation clock; per instance the report gives the
internal / switching / leakage power and the energy per clock cycle.

  gl_power.py --out <dir> --cfg <test.cfg> --params "N=64 SEL_PIPE=1 SEL_ADD_CUT=5 SEL_WALK_CUT=3" --lanes 0,21,42,63 \\
              --lane-net <lane net.v> --rng-net <xoshiro net.v> --sel-net <select netlist net.v> --sel-kind part|pipe [--maxcyc N]
Run under the local job queue (--rss 2).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STA = Path.home() / "tools" / "sta" / "bin" / "sta"
LIB = Path.home() / "tools" / "pdk" / "nangate45" / "NangateOpenCellLibrary_typical.lib"
CLK_NS = 10.0                                   # tb_top: always #5 clk = ~clk


def netlist_ports(net: Path) -> tuple[str, list[str]]:
    text = net.read_text()
    m = re.search(r"^module\s+(\S+?)\s*\((.*?)\);", text, re.S | re.M)
    return m.group(1), [p.strip() for p in m.group(2).replace("\n", " ").split(",")]


def renamed(net: Path, new: str, out: Path) -> None:
    old = netlist_ports(net)[0]
    out.write_text(re.sub(rf"^module\s+{re.escape(old)}\b", f"module {new}", net.read_text(), count=1, flags=re.M))


def split(p: str) -> tuple[str, int | None]:
    m = re.match(r"\\(\w+)\[(\d+)\]", p)
    return (m.group(1), int(m.group(2))) if m else (p, None)


class Block:
    """One gate-level instance: input taps, outputs compared with RTL expressions."""

    def __init__(self, inst: str, top: str, net: Path, ins: dict[str, str], outs: dict[str, str], sample: str = "negedge clk"):
        self.inst, self.top, self.net, self.ins, self.outs, self.sample = inst, top, net, ins, outs, sample

    def verilog(self) -> list[str]:
        _, ports = netlist_ports(self.net)
        conns, obits = [], {}
        for p in ports:
            base, idx = split(p)
            if base in self.outs:
                obits.setdefault(base, []).append(idx)
                continue
            conns.append(f".{p} ({self.ins[base]}{'' if idx is None else f'[{idx}]'})")
        v = [f"  {self.top} {self.inst} ({', '.join(conns)});"]
        for base, rtl in self.outs.items():
            bits = obits.get(base, [])
            if bits == [None]:
                gl = f"{self.inst}.{base}"
            else:
                w = max(bits) + 1
                v.append(f"  wire [{w-1}:0] {self.inst}_{base};")
                v += [f"  assign {self.inst}_{base}[{b}] = {self.inst}.\\{base}[{b}] ;" for b in bits]
                gl = f"{self.inst}_{base}"
            v.append(f"  always @({self.sample}) {'#1 ' if self.sample.startswith('posedge') else ''}if (run && ({gl} !== {rtl})) begin errs = errs + 1; "
                     f"if (errs < 6) $display(\"GLMISMATCH {self.inst}.{base} gl=%h rtl=%h t=%0t\", {gl}, {rtl}, $time); end")
        return v


def blocks_for(a, work: Path) -> list[Block]:
    d, n = "u_top.dut", int(a.params["N"])
    bl: list[Block] = []
    renamed(Path(a.lane_net), "gl_lane", work / "gl_lane.v")
    renamed(Path(a.rng_net), "gl_rng", work / "gl_rng.v")
    renamed(Path(a.sel_net), "gl_sel", work / "gl_sel.v")
    for i in a.lanes:
        L = f"{d}.lane[{i}]"
        ins = dict(clk="clk", init=f"{d}.init", flip=f"{d}.flp_m", dir=f"{d}.dir", cnt_add_ld=f"{d}.cnt_add_ld", cnt_rem_ld=f"{d}.cnt_rem_ld",
                   seg_cnt=f"lane{i}_seg", x=f"{d}.x[{i}]", h_acc=f"{L}.h_acc_i", lam=f"{d}.lam_eff", gsh=f"{d}.r_gsh", eoff=f"{d}.eoff_w",
                   temp=f"{d}.temp_w", pk=f"{L}.u_lane.pk", bias=f"{L}.u_lane.bias", lval=f"{L}.u_lane.lval", greedy=f"{d}.r_i11")
        outs = dict(h=f"{L}.h_i", gain=f"{L}.gain_i", acc=f"{d}.acc_c[{i}]", cnt_add=f"{L}.ca_i", cnt_rem=f"{L}.cr_i", ovf=f"{d}.ovf_lane[{i}]")
        bl.append(Block(f"lane{i}", "gl_lane", work / "gl_lane.v", ins, outs))
    for g in a.lanes[:2] + [n]:             # two sampled lane generators and the selection generator
        X = f"{d}.rng[{g}].u_x"
        ins = dict(clk=f"{X}.clk", ld=f"{X}.ld", ld_state=f"{X}.ld_state", adv=f"{X}.adv")       # clk = the (gated) clock the RTL generator really gets
        bl.append(Block(f"rng{g}", "gl_rng", work / "gl_rng.v", ins, dict(out=f"{X}.out", state=f"{X}.state")))
    if a.icg_net:
        renamed(Path(a.icg_net), "gl_icg", work / "gl_icg.v")
        for nm in ("u_lane", "u_sel"):
            bl.append(Block(f"icg_{nm[2:]}", "gl_icg", work / "gl_icg.v", dict(CK="clk", E=f"{d}.cg.{nm}.en"), dict(GCK=f"{d}.cg.{nm}.gclk"),
                            sample="posedge clk"))
    ins = dict(acc=f"{d}.acc_q", r16="sel_r16")
    if a.sel_kind == "pipe":
        ins["clk"] = "clk"
    bl.append(Block("sel", "gl_sel", work / "gl_sel.v", ins, dict(valid=f"{d}.sel_valid_c", idx=f"{d}.sel_idx_c", count=f"{d}.sel_cnt_c")))
    return bl


def write_tb(a, work: Path) -> list[Block]:
    d, n = "u_top.dut", int(a.params["N"])
    bl = blocks_for(a, work)
    t = ["`timescale 1ns/1ps", "module tb_gl;", "  wire clk = u_top.clk;", "  reg run = 1'b0;", "  integer errs = 0;",
         f"  tb_top #({', '.join(f'.{k}({v})' for k, v in a.params.items())}) u_top ();",
         f"  wire [15:0] sel_r16 = {d}.rng[{n}].o[31:16];"]
    t += [f"  wire [6:0] lane{i}_seg = {d}.r_cnt[{i}*7 +: 7];" for i in a.lanes]
    for b in bl:
        t += b.verilog()
    t += [f"  always @(posedge clk) if ({d}.st == 4'd8) run <= 1'b1;",
          "  initial begin wait (run); $dumpfile(\"%s\"); $dumpvars(0, %s); end" % (work / "gl.vcd", ", ".join(b.inst for b in bl)),
          f"  always @(posedge {d}.done) begin $display(\"GLSUMMARY mismatches=%0d\", errs); end",
          "endmodule"]
    (work / "tb_gl.v").write_text("\n".join(t) + "\n")
    return bl


def vcd_toggles(vcd: Path, inst: str, port: str) -> int:
    """Value changes of `port` of the top-level instance `inst` (scope tb_gl/<inst>) after the initial $dumpvars block of the VCD."""
    ident, depth, scope, in_init, n = None, [], [], False, 0
    with open(vcd) as fh:
        for line in fh:
            t = line.split()
            if not t:
                continue
            if t[0] == "$scope":
                scope.append(t[2])
            elif t[0] == "$upscope":
                scope.pop()
            elif t[0] == "$var" and ident is None and scope == ["tb_gl", inst] and t[4] == port:
                ident = t[3]
            elif t[0] == "$dumpvars":
                in_init = True
            elif in_init and t[0] == "$end":
                in_init = False
            elif ident and not in_init and not line.startswith(("$", "#")) and line[1:].strip() == ident:
                n += 1
    return n


def sta_power(net: Path, top: str, vcd: Path, scope: str, out: Path) -> dict:
    """OpenSTA power of one instance from the run VCD. A gated clock is not periodic: STA derives the clock-network activity from the SDC clock, so the
    first pass reports the VCD clock period ("vcd period X differs") and the second pass uses it as the SDC period, which makes the clock pin
    activity (and with it the sequential internal power) equal to the real pulse rate. Energies below are power x the real time of one cycle (CLK_NS)."""
    tcl = out / f"sta_{scope.replace('/', '_')}.tcl"
    clkport = "CK" if "CK" in netlist_ports(net)[1] else "clk"
    period = CLK_NS
    for _ in range(2):
        tcl.write_text(f"""read_liberty {LIB}
read_verilog {net}
link_design {top}
create_clock -name clk -period {period} [get_ports {clkport}]
read_vcd -scope {scope} {vcd}
report_power -digits 6
exit
""")
        r = subprocess.run([str(STA), "-no_splash", "-exit", str(tcl)], capture_output=True, text=True)
        (out / (tcl.stem + ".log")).write_text(r.stdout + r.stderr)
        w = re.search(r"vcd period ([\d.]+) differs", r.stdout + r.stderr)
        if not w or abs(float(w.group(1)) - period) < 1e-6:
            break
        period = float(w.group(1))
    m = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", r.stdout, re.M)
    c = {k: float(v) for k, v in zip(("internal_w", "switching_w", "leakage_w", "total_w"), m.groups())} if m else {}
    if c:
        c["sdc_period_ns"] = period
        c["clk_toggles"] = vcd_toggles(vcd, scope.split("/")[1], clkport)
        if c["clk_toggles"] == 0:        # the (gated) clock never pulsed in the window: STA would still assume the SDC clock; no clock = no dynamic energy
            c["internal_w"] = c["switching_w"] = 0.0
            c["total_w"] = c["leakage_w"]
        c["dyn_energy_per_cycle_pj"] = (c["internal_w"] + c["switching_w"]) * CLK_NS * 1e-9 * 1e12
        c["leak_energy_per_cycle_pj"] = c["leakage_w"] * CLK_NS * 1e-9 * 1e12
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--lanes", required=True)
    ap.add_argument("--lane-net", required=True)
    ap.add_argument("--rng-net", required=True)
    ap.add_argument("--sel-net", required=True)
    ap.add_argument("--sel-kind", choices=("part", "pipe"), required=True)
    ap.add_argument("--icg-net", help="netlist of tt_icg (library clock gate): adds gate-level copies of the two generator clock gates (RNG_CG = 1 runs)")
    ap.add_argument("--maxcyc", type=int, default=200000)
    ap.add_argument("--resta", action="store_true", help="only redo the OpenSTA power of an existing run (gl.vcd, gl_power.json)")
    a = ap.parse_args()
    a.params = dict(kv.split("=") for kv in a.params.split())
    a.lanes = [int(x) for x in a.lanes.split(",")]
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bl = write_tb(a, out)
    if a.resta:
        res = json.loads((out / "gl_power.json").read_text())
        for b in bl:
            res["blocks"][b.inst] = sta_power(b.net, b.top, out / "gl.vcd", f"tb_gl/{b.inst}", out)
        (out / "gl_power.json").write_text(json.dumps(res, indent=1))
        print(json.dumps(res["blocks"], indent=1))
        return 0
    cells = out / "cells.v"
    subprocess.run([sys.executable, "-I", str(HERE / "lib2v.py"), str(LIB), str(cells)], check=True, capture_output=True)
    srcs = sorted(str(p) for p in (REPO / "rtl" / "src").glob("*.v"))
    exe = out / "gl.vvp"
    cmd = ["iverilog", "-g2012", "-s", "tb_gl", "-o", str(exe), str(out / "tb_gl.v"), str(REPO / "rtl/tb/tb_top.v"), *srcs, str(cells),
           str(out / "gl_lane.v"), str(out / "gl_rng.v"), str(out / "gl_sel.v")] + ([str(out / "gl_icg.v")] if a.icg_net else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    (out / "compile.log").write_text(r.stdout + r.stderr)
    if r.returncode:
        print(r.stderr[-3000:])
        return 2
    sim = subprocess.run(["vvp", "-n", str(exe), f"+cfg={a.cfg}", f"+trace={out/'rtl.trace'}", f"+maxcyc={a.maxcyc}"], capture_output=True, text=True)
    (out / "sim.log").write_text(sim.stdout + sim.stderr)
    mm = re.search(r"GLSUMMARY mismatches=(\d+)", sim.stdout)
    res = {"mismatches": int(mm.group(1)) if mm else None, "tb_end": "TB_TOP_END ok" in sim.stdout, "blocks": {}}
    cyc = re.search(r"steps=(\d+) run_cycles=(\d+) cps=(\d+)", sim.stdout)
    if cyc:
        res.update(steps=int(cyc.group(1)), run_cycles=int(cyc.group(2)), cps=int(cyc.group(3)))
    nets = {"lane": (out / "gl_lane.v", "gl_lane"), "rng": (out / "gl_rng.v", "gl_rng"), "sel": (out / "gl_sel.v", "gl_sel")}
    for b in bl:
        res["blocks"][b.inst] = sta_power(b.net, b.top, out / "gl.vcd", f"tb_gl/{b.inst}", out)
    (out / "gl_power.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0 if res["mismatches"] == 0 and res["tb_end"] else 1


if __name__ == "__main__":
    sys.exit(main())
