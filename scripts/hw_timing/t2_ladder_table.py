"""Markdown tables of the measured_v2 re-pricing ladder (Stage 3 L2 / colouring L1, Stage 4 L1 / DIMACS): ETS99 ratio [CI] and area ratio of each
registered contrast under measured_v1 (published) and every T2 variant. Reads docs/hw/results/timing_v2/{h6,h7}_<variant>.json.
  t2_ladder_table.py [variants ...]   (default: the ladder)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[2] / "docs/hw/results"
S3 = [("maxcut", "ours_none_off vs B1_best"), ("maxcut", "ours_none_fs vs B1_best"), ("maxcut", "ours_kc2_i11_off vs B1_best"),
      ("col3p", "ours_kc2_i11_off vs B1_best"), ("col4p", "ours_kc2_i11_off vs B1_best")]
S4 = [(f, c) for f in ("p3n240", "p3n480", "p4n240", "p4n480", "dimacs") for c in ("ours_kc2_i11 vs B1_best", "ours_none vs B1_best")]
LADDER = ["L1_kc2only", "L2_pipe", "L3_sel", "L3_clk", "L3_rc", "L3_v2", "L3_lane", "L3_laneclk", "L3_laneclk_worst", "L4_settle20", "L5_ungated", "L5_laneratio", "L5_mesa0", "L5_mesa1", "L5_worst"]


def cell(rep: dict, fam: str, con: str) -> str:
    c = rep["families"][fam]["contrasts"].get(con)
    if not c:
        return "n/a"
    r = c["ets_ratio"]
    if r != r:
        return "n/e"
    return f"{r:.3f} [{c['ets_ci'][0]:.2f}, {c['ets_ci'][1]:.2f}] {c['energy']} / area {c['area_ratio']:.2f}"


def table(stage: int, variants: list[str]) -> str:
    base = json.loads((R / ("timing_v1/h6_report_measured_v1.json" if stage == 3 else "stage4_eval/h7_report.json")).read_text())
    reps = {"measured_v1 (published)": base}
    for v in variants:
        p = R / f"timing_v2/h{'6' if stage == 3 else '7'}_{v}.json"
        if p.exists():
            reps[v] = json.loads(p.read_text())
    rows = S3 if stage == 3 else S4
    out = ["| contrast | " + " | ".join(reps) + " |", "|---|" + "---|" * len(reps)]
    for fam, con in rows:
        out.append(f"| {fam}: {con} | " + " | ".join(cell(r, fam, con) for r in reps.values()) + " |")
    if stage == 4:
        out.append("| scale verdict (largest N with L1) | " + " | ".join(str(r["scale"]["largest_N_L1_holds"]) for r in reps.values()) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    vs = sys.argv[1:] or LADDER
    print("## Stage 3\n\n" + table(3, vs) + "\n\n## Stage 4\n\n" + table(4, vs))
