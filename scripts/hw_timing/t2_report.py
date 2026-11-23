"""timing study v2 report: choose the pipelined select-tree cut mask per padded N, collect every measured block (post-global-route Nangate45),
and write the measured_v2 tables.

  t2_report.py choose <sweep dir> [<sweep dir> ...]      -> docs/hw/results/timing_v2/cut_choice.json (per N: every config and the chosen one)
  t2_report.py tables <t1 dir> <t2 dir> <sweep dir> <t2b dir> <idle dir>      -> docs/hw/energy_table_measured_v2.csv, docs/hw/energy_table_measured_v2_blocks.csv,
                                                           docs/hw/results/timing_v2/timing_v2_summary.json
Choice rules (stated before looking at the repricing). (A) `chosen`, primary: minimise the time of one QUBO step, (3 + SEL_LAT) * max(select-tree
path, lane path, RNG path) in ns, over the swept configurations; ties by smaller area. (B) `chosen_lane`: the fewest SEL cycles whose tree path is
<= 2.5 ns, i.e. the clock stays at (about) the lane path (the original T2 goal); ties by smaller area. The path is the post-route data arrival time, same convention as
timing study v1 (ports stand for flops: input delay 0.10 ns, output delay 0.05 ns).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from timing_v1_report import block  # noqa: E402

LANE_CLOCK_CAP_NS = 2.5          # (B): the select tree may not set a clock slower than the lane path by more than ~4 %
OUT = ROOT / "docs/hw/results/timing_v2"
U30 = ROOT / "sim/out/hw/timing_v1/t2u30"
NS = (64, 128, 256, 512, 1024)
SRC = ("timing study v2 (rtl/pnr/run_timing_v2.sh; Yosys 0.69 + ABC, OpenSTA 3.1, OpenROAD 2.0 post-global-route; Nangate45 typical 1.1 V 25 C); "
       "docs/hw/results/timing_v2/timing_v2_summary.json")


def lat_of(n: int, ac: int, wc: int) -> int:
    lg = n.bit_length() - 1
    return 2 + bin(ac & ((1 << lg) - 1)).count("1") + bin(wc & ((1 << (lg - 1)) - 1)).count("1")


def read_cuts(path: Path) -> dict:
    out = {}
    for l in path.read_text().splitlines():
        if l and not l.startswith("#"):
            n, tag, ac, wc = l.split()
            out[f"selp_N{n}_{tag}"] = (int(n), int(ac), int(wc))
    return out


def masks_of(d: Path) -> tuple[int, int, int] | None:
    """(N, ADD_CUT, WALK_CUT) of a synthesised selp block, read from its Yosys script (chparam lines): the ground truth of what was built."""
    ys = d / "synth.ys"
    if not ys.exists():
        return None
    t = ys.read_text()
    g = lambda k: int(re.search(rf"chparam -set {k} (\d+)", t).group(1))  # noqa: E731
    return g("N"), g("ADD_CUT"), g("WALK_CUT")


def choose(sweeps: list[Path], lane_ns: float, rng_ns: float, cuts: dict) -> dict:
    res: dict[int, dict] = {n: {"configs": {}, "chosen": None} for n in NS}
    for sw in sweeps:
        for d in sorted(sw.glob("selp_N*")):
            b = block(d)
            m = masks_of(d)
            if m is None or b.get("pnr_arrival_ns") is None:
                continue
            n, ac, wc = m
            lat = lat_of(n, ac, wc)
            t = max(b["pnr_arrival_ns"], lane_ns, rng_ns)
            res[n]["configs"][d.name] = {"add_cut": ac, "walk_cut": wc, "sel_lat": lat, "sel_path_ns": b["pnr_arrival_ns"], "t_clk_ns": t,
                                         "step_ns": (3 + lat) * t, "area_um2": b["pnr_design_area_um2"], "leak_w": b.get("pnr_p_leak_w")}
    for n, r in res.items():
        if r["configs"]:
            cf = r["configs"]
            r["chosen"] = min(cf, key=lambda k: (round(cf[k]["step_ns"], 3), cf[k]["area_um2"]))              # (A) shortest QUBO step time
            ok = [k for k in cf if cf[k]["sel_path_ns"] <= LANE_CLOCK_CAP_NS]
            r["chosen_lane"] = min(ok, key=lambda k: (cf[k]["sel_lat"], cf[k]["area_um2"])) if ok else None   # (B) fewest cycles at the lane-path clock
    return res


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1]
    if cmd == "choose":
        t1 = json.loads((ROOT / "docs/hw/results/timing_v1/timing_v1_summary.json").read_text())["blocks"]
        lane, rng = t1["lane"]["pnr_arrival_ns"], t1["rng"]["pnr_arrival_ns"]
        cuts = {}
        for f in list((ROOT / "sim/out/hw").glob("t2_cuts_*.txt")) + [ROOT / "rtl/pnr/t2_cuts.txt"]:
            cuts.update(read_cuts(f))
        res = choose([Path(p) for p in sys.argv[2:]], lane, rng, cuts)
        (OUT / "cut_choice.json").write_text(json.dumps(res, indent=1))
        for n, r in res.items():
            c = r["configs"].get(r["chosen"]) if r["chosen"] else None
            print(n, r["chosen"], c and (c["sel_lat"], round(c["sel_path_ns"], 3), round(c["step_ns"], 2), c["area_um2"]))
        return 0
    t1d, t2d, swd, t2bd, idled = (Path(p) for p in sys.argv[2:7])
    choice = json.loads((OUT / "cut_choice.json").read_text())
    blocks = {}
    rows = []

    def add(key, kind, unit, value, src, lo, hi):
        rows.append(dict(key=key, block=kind, kind=kind, unit=unit, value=round(float(value), 6), band_lo_x=lo, band_hi_x=hi, source=src, placeholder=0))

    t1s = json.loads((ROOT / "docs/hw/results/timing_v1/timing_v1_summary.json").read_text())["blocks"]
    lane, rng = t1s["lane"]["pnr_arrival_ns"], t1s["rng"]["pnr_arrival_ns"]
    add("tt_t_lane_path", "time", "ns per cycle", lane, SRC + " (lane ACC path, unchanged from timing study v1)", 0.8, 1.5)
    add("tt_t_rng_path", "time", "ns per cycle", rng, SRC + " (xoshiro128**, unchanged from timing study v1)", 0.8, 1.5)

    def get(name, bases=None):
        for base in (bases or (t2d, swd, t1d)):
            if (base / name).exists() and block(base / name).get("pnr_arrival_ns") is not None:
                return block(base / name)
        return None

    for n in NS:
        for stem, name, label, bases in (("sel", f"sel_N{n}", "single-cycle partitioned select tree", None), ("ctrl", f"ctrl_N{n}", "tim_ctrl CIM = 1", None),
                                         ("restart", f"restart_N{n}", "full restart unit (pipelined MESA encoder + Kc2 kick), RTL of this report", (t2bd,)),
                                         ("restartk", f"restartk_N{n}", "Kc2-only restart unit (RS_MESA = 0), pipelined kick, RTL of this report", (t2bd,)),
                                         ("restart0", f"restart_N{n}", "full restart unit, first issue (unpipelined RTL of timing study v1 / T2 first issue)", (t2d, t1d)),
                                         ("restartk0", f"restartk_N{n}", "Kc2-only restart unit, first issue (unpipelined RTL)", (t2d,))):
            if n == 1024 and stem in ("restart", "restartk") and U30.exists():
                bases = (U30,) + tuple(bases)          # N = 1024 restart units: the 30 % utilisation re-run when it exists (see TIMING_PIPELINE_V2.md, congestion note)
            b = get(name, bases)
            if b is None:
                continue
            if n == 1024 and stem in ("restart", "restartk") and get(name, (U30,)) is not None:
                label += " [floorplan utilisation 30 %: at 60 % the global-route parasitics of the 10,000-flop permutation table are congestion-dominated]"
            blocks[f"{name}[{stem}]"] = b
            add(f"tt_t_{stem}_n{n}", "time", "ns per cycle", b["pnr_arrival_ns"], f"{SRC}: {label}, post-route data arrival ({name})", 0.8, 1.5)
            add(f"tt_a_{stem}_n{n}", "area", "um2", b["pnr_design_area_um2"], f"{SRC}: {label}, post-P&R design area ({name})", 0.8, 1.3)
            add(f"tt_p_leak_{stem}_n{n}", "power", "nW", b["pnr_p_leak_w"] * 1e9, f"{SRC}: {label}, OpenSTA leakage ({name})", 0.5, 2)
        for sfx, key, label in (("p", "chosen", "A: shortest step"), ("q", "chosen_lane", "B: lane-path clock")):
            ch = choice[str(n)][key]
            if not ch:
                continue
            c = choice[str(n)]["configs"][ch]
            b = block(swd / ch)
            blocks[f"{ch}[{sfx}]"] = b
            add(f"tt_t_sel{sfx}_n{n}", "time", "ns per cycle", b["pnr_arrival_ns"], f"{SRC}: pipelined select tree {ch} rule {label} (ADD_CUT {c['add_cut']}, WALK_CUT {c['walk_cut']})", 0.8, 1.5)
            add(f"tt_a_sel{sfx}_n{n}", "area", "um2", b["pnr_design_area_um2"], f"{SRC}: pipelined select tree {ch} rule {label}, post-P&R design area", 0.8, 1.3)
            add(f"tt_p_leak_sel{sfx}_n{n}", "power", "nW", b["pnr_p_leak_w"] * 1e9, f"{SRC}: pipelined select tree {ch} rule {label}, OpenSTA leakage", 0.5, 2)
            add(f"tt_sel_lat{sfx}_n{n}", "time", "cycles in state SEL", c["sel_lat"], f"{SRC}: SEL_LAT of {ch} rule {label} = 2 + popcount(ADD_CUT) + popcount(WALK_CUT)", 1.0, 1.0)
            cp = t2d / f"ctrl{sfx}_N{n}_{ch.split('_', 2)[2]}"
            bc = block(cp)
            blocks[f"{cp.name}"] = bc
            add(f"tt_t_ctrl{sfx}_n{n}", "time", "ns per cycle", bc["pnr_arrival_ns"], f"{SRC}: tim_ctrl CIM = 1 SEL_LAT = {c['sel_lat']} ({cp.name})", 0.8, 1.5)
            add(f"tt_a_ctrl{sfx}_n{n}", "area", "um2", bc["pnr_design_area_um2"], f"{SRC}: tim_ctrl with SEL counter, post-P&R design area ({cp.name})", 0.8, 1.3)
            add(f"tt_p_leak_ctrl{sfx}_n{n}", "power", "nW", bc["pnr_p_leak_w"] * 1e9, f"{SRC}: tim_ctrl with SEL counter, OpenSTA leakage ({cp.name})", 0.5, 2)
    def idle(name):
        p = idled / name / "idle.json"
        return json.loads(p.read_text())["dyn_fj_per_cycle"] if p.exists() else None

    ISRC = (f"{SRC}: idle (quiet clock, data inputs constant) gate-level simulation of the timing study v1 netlist, OpenSTA read_vcd internal + switching power x 10 ns "
            "(scripts/hw_timing/gl_idle.py, gl_idle_all.py; leakage separate)")
    for key, name, label in (("tt_e_idle_lane_fj", "lane", "one lane logic block (tt_lane_i11) per clock cycle"),
                             ("tt_e_idle_gen_fj", "rng", "one free-running xoshiro128** per clock cycle (RNG_CG = 0)"),
                             ("tt_e_idle_icg_fj", "icg0", "one library clock gate, enable low, per clock cycle (RNG_CG = 1: the lane and selection clock gates)"),
                             ("tt_e_idle_icg_on_fj", "icg1", "one library clock gate, enable high, per clock cycle (clock passes, no load modelled)")):
        v = idle(name)
        if v is not None:
            add(key, "digital", "fJ per cycle", v, f"{ISRC}: {label}", 0.5, 2)
    for n in NS:
        add(f"tt_e_idle_sel_n{n}", "digital", "fJ per cycle", 0.0, f"{ISRC}: the single-cycle select tree is combinational (no clock): 0", 1.0, 1.0)
        for stem, name in (("ctrl", f"ctrl_N{n}"), ("ctrlp", f"ctrlp_N{n}"), ("ctrlq", f"ctrlq_N{n}"), ("selp", f"selp_N{n}"), ("selq", f"selq_N{n}"),
                           ("restart", f"restart_N{n}"), ("restartk", f"restartk_N{n}")):
            v = idle(name)
            if v is not None:
                add(f"tt_e_idle_{stem}_n{n}", "digital", "fJ per cycle", v, f"{ISRC}: {name}", 0.5, 2)
    for name, label in (("rngg", "gated xoshiro128** (GATED = 1, no enable multiplexer)"), ("icg", "library clock gate CLKGATETST_X1")):
        b = block(t2bd / name) if (t2bd / name / "stat.txt").exists() else None
        if b is not None:
            blocks[name] = b
            add(f"tt_a_{name}", "area", "um2", b["pnr_design_area_um2"] if b.get("pnr_design_area_um2") else b["cell_area_um2"], f"{SRC}: {label}, area", 0.8, 1.3)
            add(f"tt_p_leak_{name}", "power", "nW", (b.get("pnr_p_leak_w") or b["p_leak_w"]) * 1e9, f"{SRC}: {label}, leakage", 0.5, 2)
    # ---- N = 1024 P&R variance (seeds x utilisations): ONE rule for every N = 1024 clock-setting block: path = median over all runs of the block
    # (main run(s) + seed runs, 30 % and 60 % utilisation), worst = largest path (row *_worst); area and leakage = median over the same runs.
    SEEDD = ROOT / "sim/out/hw/timing_v1/t2seed"
    main_runs = {"selp": [swd / choice["1024"]["chosen"]], "selq": [swd / choice["1024"]["chosen_lane"]],
                 "restart": [t2bd / "restart_N1024", U30 / "restart_N1024"], "restartk": [t2bd / "restartk_N1024", U30 / "restartk_N1024"]}
    seed_names = {"selp": choice["1024"]["chosen"], "selq": choice["1024"]["chosen_lane"], "restart": "restart_N1024", "restartk": "restartk_N1024"}
    import statistics
    variance = {}
    for stem, mains in main_runs.items():
        dirs = [m for m in mains if m.exists()] + sorted(SEEDD.glob(f"{seed_names[stem]}_s*_u*"))
        runs, excluded = [], []
        for m in dirs:
            b = block(m)
            if not b.get("pnr_arrival_ns"):
                continue
            wns = lambda f: float(re.search(r"worst slack (-?[\d.]+)", (m / f).read_text()).group(1)) if (m / f).exists() else None  # noqa: E731
            place, grt = wns("pnr_place_wns.txt"), wns("pnr_wns.txt")
            if place is not None and grt is not None and place >= 0 and place - grt > 1.0:
                excluded.append({"run": m.name, "arrival_ns": b["pnr_arrival_ns"], "post_place_slack": place, "post_grt_slack": grt})
                continue                       # exclusion rule: the global-route estimate loses > 1 ns against a post-placement netlist that met timing = routing congestion, not logic
            runs.append(b)
        if len(runs) < 2:
            continue
        t = [r["pnr_arrival_ns"] for r in runs]
        ar = [r["pnr_design_area_um2"] for r in runs]
        lk = [r["pnr_p_leak_w"] * 1e9 for r in runs]
        variance[stem] = {"runs": len(runs), "excluded_congestion": excluded, "t_ns": sorted(t), "t_median": statistics.median(t), "t_worst": max(t), "t_best": min(t),
                          "area_median": statistics.median(ar), "area_min": min(ar), "area_max": max(ar), "leak_nw_median": statistics.median(lk)}
        note = f" [N = 1024 P&R variance rule: median over {len(runs)} runs (main + seeds, 30 / 60 % utilisation; {len(excluded)} congestion-dominated run(s) excluded by the stated rule); worst = {max(t):.3f} ns]"
        for r in rows:
            if r["key"] == f"tt_t_{stem}_n1024":
                r["value"] = round(statistics.median(t), 6); r["source"] += note
            elif r["key"] == f"tt_a_{stem}_n1024":
                r["value"] = round(statistics.median(ar), 6); r["source"] += note
            elif r["key"] == f"tt_p_leak_{stem}_n1024":
                r["value"] = round(statistics.median(lk), 6); r["source"] += note
        add(f"tt_t_{stem}_n1024_worst", "time", "ns per cycle", max(t), f"{SRC}: worst path over {len(runs)} P&R runs of the N = 1024 block ({stem})", 0.8, 1.5)
    (OUT / "pnr_variance_1024.json").write_text(json.dumps(variance, indent=1))
    path = ROOT / "docs/hw/energy_table_measured_v2_blocks.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (OUT / "timing_v2_summary.json").write_text(json.dumps({"blocks": blocks, "choice": {n: {"A_step": choice[str(n)]["chosen"], "B_lane_clock": choice[str(n)]["chosen_lane"]} for n in NS}}, indent=1))
    v = {r["key"]: r["value"] for r in rows}
    t_clk = max(lane, rng, v["tt_t_selp_n1024"], v["tt_t_ctrlp_n1024"])
    v1 = list(csv.DictReader(open(ROOT / "docs/hw/energy_table_measured_v1.csv")))
    over = []
    for r in v1:
        r = dict(r)
        if r["key"] == "t_clk":
            r.update(value=round(t_clk, 4), source=f"timing study v2: worst per-phase path at N = 1024 with the pipelined select tree ({choice['1024']['chosen']}); single-cycle tree 9.1527 ns in measured_v1. "
                     f"The clock of every machine is set per padded N by cost_model.MeasuredCostV2; this row is the N = 1024 value. {SRC}")
        else:
            r["source"] = r["source"] + " [unchanged in measured_v2: same lane + RNG blocks]"
        over.append(r)
    with open(ROOT / "docs/hw/energy_table_measured_v2.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(over[0]))
        w.writeheader()
        w.writerows(over)
    print("wrote", path, len(rows), "rows; t_clk", t_clk)
    return 0


if __name__ == "__main__":
    sys.exit(main())
