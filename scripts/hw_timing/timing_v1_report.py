"""timing study v1 report: parse the rtl/pnr/run_timing_v1.sh outputs (Yosys stat -liberty, OpenSTA, OpenROAD) into a JSON summary and the
measured_v1 overlay rows (docs/hw/energy_table_measured_v1.csv).

Usage: timing_v1_report.py <timing_v1 out dir> [--write <repo root>]

Rows produced (everything else in the canonical table is untouched):
  t_clk            max over the per-phase register-to-register paths (lane ACC, select tree SEL, control, restart) at the
                   largest N run, post-global-route if available else post-synthesis; ports stand for flops (DFF clk-to-Q
                   0.10 ns in, setup 0.05 ns out, see the SDC).
  a_nand2          EFFECTIVE um2 per generic NAND2-eq: (Nangate45 post-P&R cell area of lane + RNG) / (their generic NAND2-eq counts from
                   the canonical table, + the I11 greedy gating) / utilisation. Keeps every gate_eq() count of the cost model.
  p_leak_nand2_nw  Nangate45 typical leakage of lane + RNG / the same NAND2-eq count.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

UTIL = 0.60                       # floorplan utilisation of the P&R runs; die area = cell area / UTIL
LANE_EQ_KEYS = ("g_digital_per_lane", "g_i11_greedy_per_lane_rtl", "g_rng_per_lane")
PHASES = ("lane", "sel_N{n}", "ctrl_N{n}", "rng")     # restart_unit reported apart: absent in arm none, its N-wide MESA diff
                                                      # priority encoder (x vs best_x) is unused by Kc2 but sets its path


def _f(pat: str, text: str) -> float | None:
    m = re.search(pat, text, re.M)
    return float(m.group(1)) if m else None


def block(d: Path) -> dict:
    r: dict = {"block": d.name}
    rd = lambda n: (d / n).read_text() if (d / n).exists() else ""  # noqa: E731
    r["cell_area_um2"] = _f(r"Chip area for (?:module|top module) .*?:\s*([\d.]+)", rd("stat.txt"))
    r["cells"] = _f(r"^\s*(\d+)\s+\S+\s+cells\s*$", rd("stat.txt"))
    r["arrival_ns"] = _f(r"^\s*([\d.]+)\s+data arrival time", rd("sta_paths.txt"))
    tot = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", rd("power.txt"), re.M)
    if tot:
        r["p_internal_w"], r["p_switching_w"], r["p_leak_w"], r["p_total_w"] = map(float, tot.groups())
    if rd("pnr_paths.txt"):
        r["pnr_arrival_ns"] = _f(r"^\s*([\d.]+)\s+data arrival time", rd("pnr_paths.txt"))
        r["pnr_design_area_um2"] = _f(r"Design area ([\d.]+) u\^2", rd("pnr.log"))
        r["pnr_util"] = _f(r"Design area [\d.]+ u\^2 ([\d.]+)% utilization", rd("pnr.log"))
        r["pnr_die_um2"] = _f(r"DIE_AREA_UM ([\d.eE+-]+)", rd("pnr.log"))
        t = re.search(r"^Total\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", rd("pnr_power.txt"), re.M)
        if t:
            r["pnr_p_leak_w"], r["pnr_p_total_w"] = float(t.group(3)), float(t.group(4))
    return r


def path_ns(b: dict) -> float | None:
    return b.get("pnr_arrival_ns") or b.get("arrival_ns")


def summarise(out: Path, canon: dict) -> dict:
    blocks = {d.name: block(d) for d in sorted(out.iterdir()) if d.is_dir()}
    ns = sorted({int(m.group(1)) for k in blocks for m in [re.match(r"sel_N(\d+)$", k)] if m})
    per_n = {}
    for n in ns:
        ph = {p.format(n=n): path_ns(blocks[p.format(n=n)]) for p in PHASES if p.format(n=n) in blocks}
        ph = {k: v for k, v in ph.items() if v is not None}
        crit = max(ph, key=ph.get)
        rs = blocks.get(f"restart_N{n}")
        per_n[n] = {"paths_ns": ph, "critical": crit, "t_clk_ns": ph[crit], "f_max_mhz": 1e3 / ph[crit],
                    "restart_unit_ns": path_ns(rs) if rs else None,
                    "area_um2": {k: (blocks[k].get("pnr_design_area_um2") or blocks[k]["cell_area_um2"])
                                 for k in (f"sel_N{n}", f"ctrl_N{n}", f"restart_N{n}") if k in blocks}}
    lane_eq = sum(canon[k] for k in LANE_EQ_KEYS)
    lr = [blocks["lane"], blocks["rng"]]
    cell = sum(b.get("pnr_design_area_um2") or b["cell_area_um2"] for b in lr)      # post-P&R (buffers, CTS) if available
    leak = sum(b.get("pnr_p_leak_w") or b["p_leak_w"] for b in lr)
    return {"blocks": blocks, "per_n": per_n, "lane_generic_nand2_eq": lane_eq, "lane_rng_cell_area_um2": cell, "lane_only_path_ns": path_ns(blocks["lane"]),
            "util": UTIL, "a_nand2_eff_um2": cell / lane_eq / UTIL, "a_nand2_cell_only_um2": cell / lane_eq,
            "p_leak_nand2_nw": leak * 1e9 / lane_eq, "n_max": max(ns) if ns else None}


def rows(s: dict) -> list[dict]:
    n = s["n_max"]
    pn = s["per_n"][n]
    src = "timing study v1 (rtl/pnr/run_timing_v1.sh, Yosys 0.69 + ABC on Nangate45 typical 1.1 V 25 C; OpenSTA 3.1; OpenROAD 2.0 place/CTS/GRT)"
    return [
        dict(key="t_clk", block="time", kind="time", unit="ns per cycle", value=round(pn["t_clk_ns"], 4), band_lo_x=0.8, band_hi_x=1.5,
             source=f"{src}: worst per-phase reg-to-reg path at N = {n} ({pn['critical']}, single-cycle as written; restart_unit MESA encoder "
                    f"{pn['restart_unit_ns']:.2f} ns excluded); band 0.8-1.5x (slow corner, detailed-route margin); typical corner only", placeholder=0),
        dict(key="a_nand2", block="digital", kind="area", unit="um2 per NAND2-eq", value=round(s["a_nand2_eff_um2"], 4), band_lo_x=0.8,
             band_hi_x=1.3, source=f"{src}: effective = Nangate45 post-P&R (buffered, CTS) cell area of lane (I11 greedy pin free) + xoshiro128** "
                    f"{s['lane_rng_cell_area_um2']:.1f} um2 / generic NAND2-eq {s['lane_generic_nand2_eq']:.2f} / utilisation {UTIL}",
             placeholder=0),
        dict(key="p_leak_nand2_nw", block="leakage", kind="power", unit="nW per NAND2-eq", value=round(s["p_leak_nand2_nw"], 4),
             band_lo_x=0.5, band_hi_x=2, source=f"{src}: OpenSTA leakage of lane + xoshiro128** (Nangate45 typical) / generic NAND2-eq "
                    f"{s['lane_generic_nand2_eq']:.2f}", placeholder=0),
    ]


def main() -> int:
    out = Path(sys.argv[1])
    root = Path(sys.argv[sys.argv.index("--write") + 1]) if "--write" in sys.argv else None
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "golden"))
    from cost_model import canonical_table
    canon = {k: r["value"] for k, r in canonical_table().items()}
    s = summarise(out, canon)
    (out / "timing_v1_summary.json").write_text(json.dumps(s, indent=1))
    rr = rows(s)
    for r in rr:
        print(f"{r['key']:16s} {r['value']}")
    if root:
        with open(root / "docs/hw/energy_table_measured_v1.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rr[0]))
            w.writeheader()
            w.writerows(rr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
