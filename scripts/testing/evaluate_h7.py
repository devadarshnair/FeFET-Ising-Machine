"""H7 evaluator (prereg/hw/H7_scaleup.md DRAFT, sections 5-6). Pure function of the Stage 4 raw records; reuses the frozen H2 statistics
(evalcommon: ETS99/TTS99, paired two-level bootstrap, Holm, win/tie/loss rules, +-1 pp / 5 % margins). Target on every family:
energy 0 = a proper k-colouring (planted: exists by construction; DIMACS graphs: k = the known chromatic number).

  --raw DIR --out h7_report.json   hardware contrasts per family (Holm over the 4 registered contrasts of the family), software
                                   quality references (success difference CI only, no energy), TabuCol-20x solvability, the
                                   scale verdict (largest N at which L1 holds on both planted families), H7-V variation table.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evalcommon as ev  # noqa: E402
import plan_h7 as p7  # noqa: E402
from cost_model import CostModel, MeasuredCost, table_hash  # noqa: E402

HW_CONTRASTS = (("ours_kc2_i11", "@B1"), ("ours_none", "@B1"), ("ours_kc2_i11", "B3"), ("ours_kc2_i11", "ours_none"))
SW_REFS = ("SW_sa", "SW_tabucol", "SW_dsatur")


def instance_order(fam: str) -> list[str]:
    return sorted(p7.TEST_SET[fam], key=lambda s: (len(s), s))


def records_by_label(raw, study: str, prefix: str, fam: str) -> dict:
    by: dict = {}
    for f in sorted(glob.glob(str(Path(raw) / study / f"{prefix}_*_{fam}_*[0-9][0-9][0-9].json"))):
        stem = Path(f).stem
        rest = stem[len(prefix) + 1:]
        label = rest[:rest.index(f"_{fam}_")]
        by.setdefault(label, []).extend(json.loads(Path(f).read_text()).get("records", []))
    return by


def sw_arm(name: str, recs: list[dict], insts: list[str], n_seed: int) -> ev.ArmData:
    """Quality-only ArmData of a software reference: success = best_E <= 0 at the end of its budget; energy/time arrays are zero
    (never used: software arms enter quality contrasts only). A deterministic arm (one record per instance) is broadcast over seeds."""
    by = {(r["spec"]["instance"], r["spec"]["r"]): r for r in recs}
    I, S = len(insts), n_seed
    ok, e = np.zeros((I, S), bool), np.zeros((I, S))
    for a, i in enumerate(insts):
        for s in range(S):
            r = by.get((i, s)) or by[(i, 0)]
            e[a, s] = r["best_E"]
            ok[a, s] = r["best_E"] <= 1e-9
    z = np.zeros((I, S, 1))
    return ev.ArmData(name, insts, ok[:, :, None], z, z.copy(), ok, e, e[:, :, None], 0.0, np.zeros((I, S)), np.zeros((I, S)))


def family_report(raw, fam: str, cost, B: int) -> dict:
    by = records_by_label(raw, "h7", "x7", fam)
    hw = [a.label for a in p7.test_arms(fam) if a.kind == "hw" and by.get(a.label)]
    have = [{r["spec"]["instance"] for r in by[lab]} for lab in hw]
    insts = [i for i in instance_order(fam) if have and all(i in h for h in have)]     # complete data: every TEST instance
    tg = {i: {"E_ref": 0.0, "E_target": 0.0} for i in insts}
    arms: dict = {}
    for a in p7.test_arms(fam):
        rs = by.get(a.label)
        if not rs:
            continue
        if a.kind == "hw":
            arms[a.label] = ev.arm_data(a.label, [r for r in rs if r["spec"]["instance"] in tg], tg, cost, instances=insts)
    if not arms:
        return {}
    missing = sorted(set(p7.TEST_SET[fam]) - set(insts))
    n_seed = next(iter(arms.values())).succ.shape[1]
    for lab in SW_REFS:
        if by.get(lab):
            arms[lab] = sw_arm(lab, by[lab], insts, n_seed)
    obs = {lab: ev.pooled(arms[lab], None, None) for lab in arms}
    b1 = [lab for lab in ("B1_best", "B1_mesa_epoch") if lab in arms]
    comp = min(b1, key=lambda k: (obs[k]["ets"][0], b1.index(k))) if b1 else None      # lower observed ETS99 (favours B1)
    pairs = [(a, comp if b == "@B1" else b) for a, b in HW_CONTRASTS]
    pairs = [(a, b) for a, b in pairs if a in arms and b in arms]
    bs = ev.boot_stats(arms, B)
    res = {f"{a} vs {b}": ev.contrast(bs, a, b) for a, b in pairs}
    hp = ev.holm({k: v["p_ets_lt1"] for k, v in res.items()})
    for (a, b), (k, v) in zip(pairs, res.items()):
        v.update(holm_p=hp[k], energy=ev.energy_verdict(v, hp[k]), quality=ev.quality_verdict(v),
                 area_ratio=arms[a].area / arms[b].area)
        if float(np.ravel(bs["__obs__"][b]["success"])[0]) <= 0.0:       # frozen rule (prereg section 5): a comparator at 0 % is never a win
            v["energy"] = "not evaluable (comparator at 0 % success)"
        v["area"] = ev.area_verdict(v["area_ratio"])
    sw = {}
    for lab in SW_REFS:
        if lab in arms and "ours_kc2_i11" in arms:
            ds = bs["ours_kc2_i11"]["success"] - bs[lab]["success"]
            c = {"d_success": bs["__obs__"]["ours_kc2_i11"]["success"] - bs["__obs__"][lab]["success"], "d_success_ci": ev.ci(ds)}
            c["quality"] = ev.quality_verdict(c)
            sw[f"ours_kc2_i11 vs {lab}"] = c
    wall = {lab: float(np.mean([r.get("wall_s", 0.0) for r in by[lab]])) for lab in by}
    return {"B1_comparator": comp, "contrasts": res, "instances_missing": missing, "software_quality": sw,
            "arms": {lab: bs["__obs__"][lab] | {"area_um2": arms[lab].area, "mean_end_conflicts": float(arms[lab].gap_end.mean()),
                                                     "per_instance_success": {i: float(x) for i, x in zip(arms[lab].instances, arms[lab].ok_final.mean(axis=1))}}
                     for lab in arms}, "wall_s_per_run": wall}


def solvability(raw) -> dict:
    out = {}
    for fam in p7.FAMILIES:
        rs = records_by_label(raw, "h7", "r7", fam).get(p7.SW_REF.label, [])
        if rs:
            solved = {i: any(r["best_E"] <= 0 for r in rs if r["spec"]["instance"] == i) for i in {r["spec"]["instance"] for r in rs}}
            out[fam] = {"solved_frac": float(np.mean(list(solved.values()))), "unsolved": sorted(i for i, v in solved.items() if not v)}
    return out


def scale_verdict(fams: dict) -> dict:
    """L1 holds at size N iff ours_kc2_i11 vs the B1 comparator is an energy win on BOTH planted families of size N. The scale
    verdict is the largest N such that L1 holds at every size up to N (None if it fails at 240)."""
    held = {}
    for n in p7.SIZES:
        v = []
        for k in (3, 4):
            fr = fams.get(f"p{k}n{n}") or {}
            c = next((c for name, c in fr.get("contrasts", {}).items() if name.startswith("ours_kc2_i11 vs B1")), None)
            v.append(c["energy"] if c else "missing")
        held[n] = {"verdicts": v, "holds": all(x == "win" for x in v)}
    largest = None
    for n in p7.SIZES:
        if not held[n]["holds"]:
            break
        largest = n
    return {"per_size": held, "largest_N_L1_holds": largest}


def variation_report(raw, cost) -> dict:
    recs = ev.load_records(raw, "h7v", "var")
    out: dict = {}
    for fam in p7.V_FAMILIES:
        insts = instance_order(fam)[:p7.V_INSTANCES]
        tg = {i: {"E_ref": 0.0, "E_target": 0.0} for i in insts}
        for a in p7.V_ARMS:
            row = {}
            for pt in p7.v_points():
                rs = [r for r in recs if r["spec"]["family"] == fam and r["spec"]["arm"] == a.arm and r["spec"]["pert"]["pid"] == pt.pid]
                if rs:
                    d = ev.arm_data(a.label, rs, tg, cost)
                    m = ev.pooled(d, None, None)
                    row[pt.pid] = {"success": float(m["success"][0]), "ets99": float(m["ets"][0]), "n": len(rs),
                                   "mean_end_conflicts": float(np.mean([r["best_E"] for r in rs]))}
            if row:
                nom, ideal = row.get("nominal", {}).get("success"), row.get("dev_x0", {}).get("success")
                row["_escalate"] = bool(nom is not None and ideal is not None and nom < ideal - 0.01)
            out.setdefault(fam, {})[a.label] = row
    return out


def _view(raw, cost, B: int) -> dict:
    fams = {f: family_report(raw, f, cost, B) for f in p7.FAMILIES}
    return {"families": fams, "scale": scale_verdict(fams)}


SENSITIVITIES = {"canonical_table": lambda: CostModel(),
                 "baseline_lane_path_clock": lambda: MeasuredCost(baseline_clock="lane_path")}


def evaluate(raw, B: int = ev.N_BOOT, sensitivities: bool = True) -> dict:
    """PRIMARY pricing = measured_v1 with the registered clock / restart-unit policy (MeasuredCost, same_tree). Stated secondary
    sensitivities (prereg section 2): the canonical table, and measured_v1 with B1 / B3 at the 2.41 ns lane-path clock. The verdict
    is the primary one; a sensitivity whose scale verdict differs is flagged."""
    cost = MeasuredCost()
    prim = _view(raw, cost, B)
    sens = {name: _view(raw, mk(), B) for name, mk in SENSITIVITIES.items()} if sensitivities else {}
    flags = {n: v["scale"]["largest_N_L1_holds"] for n, v in sens.items() if v["scale"]["largest_N_L1_holds"] != prim["scale"]["largest_N_L1_holds"]}
    return {**prim, "primary_pricing": "measured_v1 (timing study v1), clock = select tree at each machine's padded N, restart unit charged",
            "cost_table_sha256": table_hash(cost.t), "sensitivity": sens, "sensitivity_verdict_differs": flags,
            "solvability_tabucol_20x": solvability(raw), "variation": variation_report(raw, cost),
            "stand_in_label": "stand-in BSIM4 / FreePDK45 models, ratios only, absolute numbers carry about x2 uncertainty; "
                              "software references are quality-only (no hardware energy)"}


def markdown(rep: dict) -> str:
    L = ["# H7 report (generated by evaluate_h7.py; stand-in model labels apply to every table)", "",
         f"Primary pricing: {rep['primary_pricing']}",
         f"Scale verdict (primary): largest N at which L1 holds on both planted families = {rep['scale']['largest_N_L1_holds']}"]
    for n, v in rep.get("sensitivity", {}).items():
        L.append(f"Sensitivity {n}: scale verdict {v['scale']['largest_N_L1_holds']}" + (" (DIFFERS from primary)" if n in rep["sensitivity_verdict_differs"] else ""))
    L.append("")
    for fam, fr in rep["families"].items():
        if not fr:
            continue
        L += [f"## {fam} (B1 comparator: {fr['B1_comparator']})", "| contrast | ETS99 ratio [CI] | Holm p | success diff [CI] | energy | area | quality |",
              "|---|---|---|---|---|---|---|"]
        for k, v in fr["contrasts"].items():
            L.append(f"| {k} | {v['ets_ratio']:.3f} [{v['ets_ci'][0]:.3f}, {v['ets_ci'][1]:.3f}] | {v['holm_p']:.3f} | "
                     f"{v['d_success']:+.3f} [{v['d_success_ci'][0]:+.3f}, {v['d_success_ci'][1]:+.3f}] | {v['energy']} | "
                     f"{v['area']} ({v['area_ratio']:.2f}) | {v['quality']} |")
        for k, v in fr["software_quality"].items():
            L.append(f"| {k} (quality only) | - | - | {v['d_success']:+.3f} [{v['d_success_ci'][0]:+.3f}, {v['d_success_ci'][1]:+.3f}] | - | - | {v['quality']} |")
        L += ["", "| arm | success | mean end conflicts | wall s/run |", "|---|---|---|---|"]
        for lab, a in fr["arms"].items():
            L.append(f"| {lab} | {a['success']:.3f} | {a['mean_end_conflicts']:.2f} | {fr['wall_s_per_run'].get(lab, float('nan')):.2f} |")
        if fam == "dimacs":
            L += ["", "| arm | " + " | ".join(p7.TEST_SET[fam]) + " |", "|---|" + "---|" * len(p7.TEST_SET[fam])]
            for lab, a in fr["arms"].items():
                L.append(f"| {lab} | " + " | ".join(f"{a['per_instance_success'].get(i, float('nan')):.2f}" for i in p7.TEST_SET[fam]) + " |")
        L.append("")
    L += ["## TabuCol 20x solvability", str(rep["solvability_tabucol_20x"]), "", "## H7-V variation (report-only)",
          "| family | arm | point | success | mean end conflicts |", "|---|---|---|---|---|"]
    for fam, arms in rep["variation"].items():
        for arm, rows in arms.items():
            for pid, v in rows.items():
                if not pid.startswith("_"):
                    L.append(f"| {fam} | {arm} | {pid} | {v['success']:.3f} | {v['mean_end_conflicts']:.2f} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=ev.N_BOOT)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    res = evaluate(a.raw, a.boot)
    out.with_suffix(".md").write_text(markdown(res))
    out.write_text(json.dumps(res, indent=1, default=float))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
