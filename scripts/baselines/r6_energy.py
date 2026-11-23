"""P4_v2 amendment 2 D: R6 priced under measured_v2 (timing study v2 primary, MeasuredCostV2 defaults). ETS99 ratio ours / B3 v2 with the
H7 bootstrap (evalcommon), d_success with CI; a comparator at 0 % success is not evaluable (H7 rule). Report-only.

  r6_energy.py [--boot 2000]   -> docs/hw/results/baselines_v2/r6_energy_measured_v2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE, REPO / "scripts" / "golden", REPO / "scripts" / "testing", REPO):
    sys.path.insert(0, str(p))

import evalcommon as ev  # noqa: E402
import evaluate_h7 as e7  # noqa: E402
import plan_h7 as p7  # noqa: E402
from cost_model import MeasuredCostV2  # noqa: E402

OUT = REPO / "docs/hw/results/baselines_v2/r6_energy_measured_v2.json"
NEW = REPO / "sim/out/hw/baselines_v2/test"
STAGE4 = REPO / "sim/out/hw/stage4"
FAMILIES = ("p3n240", "p4n240", "p3n480", "p4n480", "dimacs")
NEW_ARMS = {"B3_v2": "b3.b3v2", "ours_kc2c": "ours.kc2.fs"}       # labels -> spec arm in the P4_v2 test records
STAGE4_ARMS = ("ours_kc2_i11", "ours_none", "B1_best")
CONTRASTS = (("ours_kc2_i11", "B3_v2"), ("ours_none", "B3_v2"), ("ours_kc2c", "B3_v2"), ("B1_best", "B3_v2"))


def arms_for(fam: str, cost) -> tuple[dict, list[str]]:
    s4 = e7.records_by_label(STAGE4, "h7", "x7", fam)
    new = ev.load_records(NEW, "h7", "test")
    recs = {lab: s4.get(lab, []) for lab in STAGE4_ARMS}
    for lab, key in NEW_ARMS.items():
        recs[lab] = [r for r in new if r["spec"]["arm"] == key and r["spec"]["family"] == fam]
    recs = {k: v for k, v in recs.items() if v}
    insts = [i for i in e7.instance_order(fam) if all(any(r["spec"]["instance"] == i for r in v) for v in recs.values())]
    tg = {i: {"E_ref": 0.0, "E_target": 0.0} for i in insts}
    return {lab: ev.arm_data(lab, [r for r in v if r["spec"]["instance"] in tg], tg, cost, instances=insts) for lab, v in recs.items()}, insts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args(argv)
    cost = MeasuredCostV2()
    res = {"pricing": "MeasuredCostV2() defaults (timing study v2 primary; pipelined tree, Kc2-only unit, idle charge, median clocks)",
           "families": {}}
    for fam in FAMILIES:
        arms, insts = arms_for(fam, cost)
        if "B3_v2" not in arms:
            continue
        bs = ev.boot_stats(arms, a.boot)
        out = {"instances": insts, "arms": {lab: {k: (np.asarray(v).tolist() if hasattr(v, "tolist") else v)
                                                   for k, v in bs["__obs__"][lab].items()} for lab in arms}, "contrasts": {}}
        for x, y in CONTRASTS:
            if x in arms and y in arms:
                c = ev.contrast(bs, x, y)
                if float(np.ravel(bs["__obs__"][y]["success"])[0]) <= 0.0:
                    c["energy_note"] = "not evaluable (comparator at 0 % success)"
                if float(np.ravel(bs["__obs__"][x]["success"])[0]) <= 0.0:
                    c["energy_note"] = "ours at 0 % success: ETS99 infinite"
                out["contrasts"][f"{x} vs {y}"] = c
        res["families"][fam] = out
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=float))
    for fam, o in res["families"].items():
        for k, c in o["contrasts"].items():
            print(fam, k, "ETS99 ratio", round(c["ets_ratio"], 3) if np.isfinite(c["ets_ratio"]) else c["ets_ratio"],
                  [round(v, 3) for v in c["ets_ci"]], "d_success", round(c["d_success"], 2), c.get("energy_note", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
