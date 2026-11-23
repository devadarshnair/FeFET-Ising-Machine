"""Summarise the activity-annotated gate-level power runs (gl_power.py) against the canonical cost-table dynamic rows (C3).

For each representative run the golden machine gives the exact counters (adds, LUT reads, register writes, RNG draws per step); the
cost table prices them with e_add / e_lut_read / e_reg_write / e_rng_draw (gscl45nm-derived). The annotated gate-level run gives the
Nangate45 energy per clock cycle of sampled lane logic, lane generators and the selection tree, measured from the toggles of the real
run (OpenSTA read_vcd + report_power, internal + switching; leakage reported apart).

  gl_power_report.py <gl root>  [--write docs/hw/results/timing_v2/gl_power_summary.json]
<gl root> holds one subdirectory per run with gl_power.json and params.json (written by gl_cfg.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "golden"))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from cost_model import CostModel  # noqa: E402


def canonical_per_step(run: str, steps: int) -> dict:
    import gl_cfg
    import rtl_spotcheck as rs
    import tim_golden as tg
    from counters import CycleCfg
    mq, arm, tw = gl_cfg.runs()[run]
    inst, rcfg, cim, pw = rs.make_case(mq, arm, True, steps)
    m = tg.Machine(inst, restart=rcfg, cim=cim, power=pw, counters=CycleCfg(), tweaks=tw)
    m.run()
    c, v = m.counters.total, CostModel().v
    n = inst.n
    digital = c["adds"] * v("e_add") + c["lut_reads"] * v("e_lut_read") + c["reg_writes"] * v("e_reg_write")
    rng = c["rng_draws"] * v("e_rng_draw")
    return {"digital_fj_per_lane_step": digital / steps / n, "rng_fj_per_lane_step": rng / steps / n, "n": n,
            "rng_draws_per_step": c["rng_draws"] / steps, "adds_per_step": c["adds"] / steps}


def summarise(root: Path) -> dict:
    out = {}
    for d in sorted(p for p in root.iterdir() if "__" in p.name and (p / "gl_power.json").exists()):
        g, par = json.loads((d / "gl_power.json").read_text()), json.loads((d.parent / d.name.split("__")[0] / "params.json").read_text())
        cps, steps = g["cps"], par["steps"]
        b = g["blocks"]
        mean = lambda pref, key: sum(v[key] for k, v in b.items() if k.startswith(pref) and k[len(pref):].isdigit()) / sum(
            1 for k in b if k.startswith(pref) and k[len(pref):].isdigit())   # noqa: E731
        lane = mean("lane", "dyn_energy_per_cycle_pj") * cps * 1e3        # fJ per lane per step
        rng_cands = [v["dyn_energy_per_cycle_pj"] for k, v in b.items() if k.startswith("rng") and k != f"rng{par['n']}"]
        rng_lane = sum(rng_cands) / len(rng_cands) * cps * 1e3
        sel = b["sel"]["dyn_energy_per_cycle_pj"] * cps * 1e3
        icg = sum(v["dyn_energy_per_cycle_pj"] for k, v in b.items() if k.startswith("icg")) * cps * 1e3
        can = canonical_per_step(d.parent.name if "__" not in d.name else d.name.split("__")[0], steps)
        out[d.name] = {"cycles_per_step": cps, "steps": steps, "n": par["n"], "mismatches": g["mismatches"],
                       "lane_dyn_fj_per_step": lane, "lane_gen_dyn_fj_per_step": rng_lane, "select_dyn_fj_per_step": sel, "icg_dyn_fj_per_step_total": icg,
                       "lane_leak_pj_per_cycle": mean("lane", "leak_energy_per_cycle_pj"),
                       "canonical": can,
                       "ratio_lane_vs_digital_row": lane / can["digital_fj_per_lane_step"] if can["digital_fj_per_lane_step"] else None,
                       "ratio_rng_vs_rng_row": rng_lane / can["rng_fj_per_lane_step"] if can["rng_fj_per_lane_step"] else None}
    return out


def annotated_rows(s: dict) -> dict:
    """Numbers fed to the sensitivity pricing (MeasuredCostV2 annotated=..., reprice_v2 --annotated): measured / canonical ratios and per-cycle energies.
    gen_idle_cycle_fj: energy of one UNGATED lane generator per clock cycle in the greedy (I11) runs, where the cost table charges no draws (it assumes the
    idle generator is clock-gated); sel_cycle_fj_per_lane: select-tree dynamic energy per lane per cycle (not priced at all in measured_v1)."""
    mean = lambda xs: sum(xs) / len(xs)   # noqa: E731
    v1 = {k: v for k, v in s.items() if k.endswith("__v1")}
    pipe = {k: v for k, v in s.items() if k.endswith("__pipe")}
    cg = {k: v for k, v in s.items() if k.endswith("__cg")}
    i11 = [v for k, v in v1.items() if "i11" in k]
    return {"lane_ratio": mean([v["ratio_lane_vs_digital_row"] for v in v1.values()]),
            "rng_ratio_nongated": mean([v["ratio_rng_vs_rng_row"] for k, v in v1.items() if "none" in k]),
            "gen_idle_cycle_fj": mean([v["lane_gen_dyn_fj_per_step"] / v["cycles_per_step"] for v in i11]),
            "sel_cycle_fj_per_lane_single": mean([v["select_dyn_fj_per_step"] / v["cycles_per_step"] / v["n"] for v in v1.values()]),
            "sel_cycle_fj_per_lane_pipe": mean([v["select_dyn_fj_per_step"] / v["cycles_per_step"] / v["n"] for v in pipe.values()]),
            "gated": {k: {"cycles_per_step": v["cycles_per_step"], "lane_gen_dyn_fj_per_step": v["lane_gen_dyn_fj_per_step"],
                          "icg_dyn_fj_per_step_total": v["icg_dyn_fj_per_step_total"], "select_dyn_fj_per_step": v["select_dyn_fj_per_step"],
                          "lane_dyn_fj_per_step": v["lane_dyn_fj_per_step"]} for k, v in cg.items()},
            "runs": sorted(s)}


if __name__ == "__main__":
    root = Path(sys.argv[1])
    s = summarise(root)
    print(json.dumps(s, indent=1))
    if "--write" in sys.argv:
        w = Path(sys.argv[sys.argv.index("--write") + 1])
        w.write_text(json.dumps(s, indent=1))
        (w.parent / "annotated_rows.json").write_text(json.dumps(annotated_rows(s), indent=1))
