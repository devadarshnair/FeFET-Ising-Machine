"""Idle (quiet-clock) gate-level energy of every block of the machine, all padded sizes (timing study v2). One gl_idle.py run per netlist:
lane, free-running generator, the library clock gate (E = 0 idle, E = 1 passing), restart units (full, Kc2-only), controller and pipelined select tree
at the chosen cut masks (rule A and B). Outputs sim/out/hw/t2b_idle/<name>/idle.json (read by t2_report.py).
  gl_idle_all.py <t1 dir> <t2 dir> <t2b dir> <sweep dir> <out dir>      (run under the local job queue --rss 1.5, a few minutes)"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NS = (64, 128, 256, 512, 1024)


def run(name: str, net: Path, out: Path, clk: str = "clk", tie: list[str] | None = None) -> None:
    d = out / name
    if (d / "idle.json").exists():
        return
    if not net.exists():
        print("MISSING", name, net)
        return
    cmd = [sys.executable, "-I", str(HERE / "gl_idle.py"), "--net", str(net), "--out", str(d), "--clk", clk, "--cycles", "80"]
    if tie:
        cmd += ["--tie", *tie]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(name, r.stdout.strip()[-160:] or r.stderr.strip()[-200:])


def main() -> int:
    t1, t2, t2b, sw, out = (Path(p) for p in sys.argv[1:6])
    choice = json.loads((ROOT / "docs/hw/results/timing_v2/cut_choice.json").read_text())
    run("lane", t1 / "lane/net.v", out)
    run("rng", t1 / "rng/net.v", out)
    run("icg0", t2b / "icg/net.v", out, clk="CK", tie=["E=0"])
    run("icg1", t2b / "icg/net.v", out, clk="CK", tie=["E=1"])
    for n in NS:
        for stem in ("restart", "restartk"):
            run(f"{stem}_N{n}", t2b / f"{stem}_N{n}/net.v", out)
        run(f"ctrl_N{n}", (t1 / f"ctrl_N{n}") / "net.v" if (t1 / f"ctrl_N{n}").exists() else t2 / f"ctrl_N{n}/net.v", out)
        for sfx, key in (("p", "chosen"), ("q", "chosen_lane")):
            ch = choice[str(n)][key]
            tag = ch.split("_", 2)[2]
            run(f"sel{sfx}_N{n}", sw / ch / "net.v", out)
            run(f"ctrl{sfx}_N{n}", t2 / f"ctrl{sfx}_N{n}_{tag}/net.v", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
