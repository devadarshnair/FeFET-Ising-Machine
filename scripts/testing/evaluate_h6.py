"""H6 evaluator (prereg/hw/H6_followup.md sections 5-6). Pure function of the Stage 3 raw records; reuses the frozen H2 statistics
(evalcommon: targets, ETS99/TTS99, paired two-level bootstrap, Holm, win/tie/loss rules, +-1 pp / 5 % margins).

  --select --raw DIR --out h6_sweep.json   restart-sweep selection from the TUNE split only (lowest mean normalised end gap,
                                           ties -> lower energy); per-config mean restarts logged (never-triggered visible)
  --report --raw DIR --out h6_report.json  registered contrasts per family + H5 re-run table (+ markdown next to it)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evalcommon as ev  # noqa: E402
import plan as pl  # noqa: E402
import plan_h6 as p6  # noqa: E402
import pricing as pr  # noqa: E402
from cost_model import CostModel  # noqa: E402


def targets(family: str, instances: list[str]) -> dict:
    if family == "maxcut":
        return ev.targets("maxcut", instances)
    return {i: {"E_ref": 0.0, "E_target": 0.0} for i in instances}       # planted colouring: optimum 0 by construction


def load(raw, study, phase=None):
    return ev.load_records(raw, study, phase)


# ------------------------------------------------------------------------------------------------------------ select
def select(raw) -> dict:
    recs = load(raw, "h6", "tune")
    table: dict = {}
    for r in recs:
        s = r["spec"]
        tg = targets(s["family"], [s["instance"]])[s["instance"]]
        gap = float(ev.gap_of(np.array([r["best_E"]]), tg["E_ref"])[0])
        table.setdefault(s["family"], {}).setdefault(s["arm"], {}).setdefault(s["cfg"]["cid"], []).append(
            (gap, r["price"]["e_total"], r["restarts"], s["cfg"]))
    selected, log = {}, {}
    for fam, arms in table.items():
        for arm, cfgs in arms.items():
            rows = {cid: {"gap": float(np.mean([v[0] for v in vs])), "energy": float(np.mean([v[1] for v in vs])),
                          "restarts_mean": float(np.mean([v[2] for v in vs])), "never_triggered_frac": float(np.mean([v[2] == 0 for v in vs])),
                          "n": len(vs)} for cid, vs in cfgs.items()}
            best = min(rows, key=lambda c: (round(rows[c]["gap"], 12), rows[c]["energy"]))
            selected.setdefault(fam, {})[arm] = cfgs[best][0][3]
            log.setdefault(fam, {})[arm] = rows | {"_selected": best}
    return {"selected": selected, "tune_table": log}


# ------------------------------------------------------------------------------------------------------------ arms
def _fs_arrays(rec: dict, cost) -> ev.RunArrays:
    """'fs' variant: noise-free I7-off trajectory priced with the ADC full scale = max column sum (pricing.ours_fs_rebits)."""
    snaps, desc = rec["snaps"], rec["desc"]
    key = "c_ns" if snaps[0]["c_ns"] is not None else "c"
    ts, es, tn = [0], [0.0], [0.0]
    for s in snaps:
        c, d = pr.ours_fs_rebits(s[key], desc)
        p = pr.price(d, c, s["t"], s["flips"], cost)
        ts.append(s["t"]); es.append(p["e_total"]); tn.append(p["time_ns"])
    fine = np.asarray(rec["curve_t"], float)
    c, d = pr.ours_fs_rebits(snaps[-1][key], desc)
    f = pr.price(d, c, snaps[-1]["t"], snaps[-1]["flips"], cost)
    return ev.RunArrays(np.asarray(rec["curve"], float), fine, np.interp(fine, ts, es), np.interp(fine, ts, tn), rec["best_E"],
                        f["a_total"], f["e_total"], f["time_ns"], rec["restarts"], rec["prog"], f["blocks"])


def arm_data(name, recs, tg, cost, variant: str) -> ev.ArmData:
    if variant != "fs":
        return ev.arm_data(name, recs, tg, cost, noskip=variant == "off")
    orig = ev.run_arrays
    ev.run_arrays = lambda rec, cost, noskip=False, rebits=0: _fs_arrays(rec, cost)
    try:
        return ev.arm_data(name, recs, tg, cost)
    finally:
        ev.run_arrays = orig


def test_records_by_label(raw, fam: str) -> dict:
    """{H6 arm label: records} from the TEST job files x6_<label>_<family>_<k>.json (the job id carries the label)."""
    import glob
    by: dict = {}
    for f in sorted(glob.glob(str(Path(raw) / "h6" / f"x6_*_{fam}_[0-9][0-9][0-9].json"))):
        jid = Path(f).stem
        label = jid[3:-len(f"_{fam}_000")]
        by.setdefault(label, []).extend(json.loads(Path(f).read_text()).get("records", []))
    return by


def build_arms(raw, fam: str, cost) -> dict:
    tg = targets(fam, p6.TEST_SET[fam])
    by = test_records_by_label(raw, fam)
    out = {}
    for a in p6.test_arms(fam):
        rs = by.get(a.label)
        if not rs:
            continue
        if a.arm.startswith("ours.") and "i7v2" not in a.arm:     # I10-simulated, noise-free: price the I10-free ('off') counters
            out[a.label + "_off"] = arm_data(a.label + "_off", rs, tg, cost, "off")
            if a.label in ("ours_none", "ours_kc2_i11"):
                out[a.label + "_fs"] = arm_data(a.label + "_fs", rs, tg, cost, "fs")
        elif "i7v2" in a.arm:
            out[a.label] = arm_data(a.label, rs, tg, cost, "off")              # I7v2 alone (I10 savings removed)
        else:
            out[a.label] = arm_data(a.label, rs, tg, cost, "")
    return out


def contrasts_for(fam: str, arms: dict) -> dict:
    o = {}
    b1 = [lab for lab in ("B1_best", "B1_mesa_epoch") if lab in arms]
    if b1:      # B1 comparator = the B1 arm with the lower observed ETS99 (conservative for ours; prereg section 5)
        obs = {lab: ev.pooled(arms[lab], None, None)["ets"][0] for lab in b1}
        o["_B1_comp"] = min(b1, key=lambda k: obs[k])
    comp = o.get("_B1_comp")
    pairs = []
    if comp:
        pairs += [("ours_none_off", comp), ("ours_none_fs", comp), ("ours_kc2_i11_off", comp), ("ours_kc2_i11_fs", comp)]
        pairs += [(f"ours_kc2_i11_S{s}_off", comp) for s in p6.L3_SWEEPS]
    if "B3" in arms:
        pairs += [("ours_none_off", "B3"), ("ours_kc2_i11_off", "B3")]
    pairs += [("ours_none_fs", "ours_none_off"), ("ours_none_i7v2", "ours_none_fs"), ("ours_kc2_i11_i7v2", "ours_kc2_i11_fs"),
              ("ours_kc2_swept_off", "ours_none_off"), ("ours_mesa_swept_off", "ours_none_off"), ("ours_da_swept_off", "ours_none_off")]
    o["pairs"] = [(a, b) for a, b in pairs if a in arms and b in arms]
    return o


def family_report(raw, fam: str, cost, B: int) -> dict:
    arms = build_arms(raw, fam, cost)
    if not arms:
        return {}
    cs = contrasts_for(fam, arms)
    bs = ev.boot_stats(arms, B)
    res = {f"{a} vs {b}": ev.contrast(bs, a, b) for a, b in cs["pairs"]}
    hp = ev.holm({k: v["p_ets_lt1"] for k, v in res.items()})          # Holm over every registered contrast of the family
    for (a, b), (k, v) in zip(cs["pairs"], res.items()):
        v["holm_p"] = hp[k]
        v["energy"] = ev.energy_verdict(v, hp[k])
        v["quality"] = ev.quality_verdict(v)
        v["area_ratio"] = arms[a].area / arms[b].area
        v["area"] = ev.area_verdict(v["area_ratio"])
    restarts = {lab: {"mean": float(a.restarts.mean()), "never_triggered_frac": float((a.restarts == 0).mean())} for lab, a in arms.items()}
    return {"B1_comparator": cs.get("_B1_comp"), "arms": {lab: bs["__obs__"][lab] | {"area_um2": a.area} for lab, a in arms.items()},
            "contrasts": res, "restarts": restarts}


GRADED_GAP_SCALE = 0.10     # amendment 1: graded H5 score = mean over runs of max(0, 1 - end gap / 10 % of best-known)


def graded_stats(family: str, rs: list[dict], tg: dict) -> dict:
    """Graded H5 metrics of a set of runs: mean best-cut fraction of best-known (Max-Cut), mean colouring conflicts (energy at
    the end of the budget, 0 = proper colouring) and the graded score used for the 10 %-loss point."""
    gaps = np.array([float(ev.gap_of(np.array([r["best_E"]]), tg[r["spec"]["instance"]]["E_ref"])[0]) for r in rs])
    out = {"score": float(np.mean(np.clip(1.0 - gaps / GRADED_GAP_SCALE, 0.0, 1.0))), "gap_mean": float(gaps.mean())}
    if family == "maxcut":
        out["cut_frac"] = float(1.0 - gaps.mean())
    else:
        out["conflicts"] = float(np.mean([r["best_E"] for r in rs]))
    return out


def graded_loss_points(row: dict) -> dict:
    """10 %-loss point per perturbation axis on the graded score (same rule and levels as evaluate_h5.loss_point)."""
    import evaluate_h5 as h5
    out = {}
    for ax, lv in h5.AXES.items():
        pts = [(lvl, pid) for lvl, pid in lv if pid in row]
        if len(pts) == len(lv) and len(pts) > 1:
            out[ax] = h5.loss_point([x for x, _ in pts], [row[pid]["score"] for _, pid in pts], row[lv[0][1]]["score"])
    return out


def h5_report(raw, cost) -> dict:
    recs = load(raw, "h6h5", "h5")
    out: dict = {}
    fam = p6.H5_FAMILY
    tg = targets(fam, p6.TEST_SET[fam][:p6.H5_INSTANCES])
    for a in p6.H5_ARMS + (p6.H5_B1,):
        row = {}
        for pt in p6.h5_arm_points(a):
            rs = [r for r in recs if r["spec"]["arm"] == a.arm and r["spec"].get("pert", {}) and r["spec"]["pert"]["pid"] == pt.pid]
            if rs:
                d = ev.arm_data(a.label, rs, tg, cost)
                m = ev.pooled(d, None, None)
                row[pt.pid] = {"success": float(m["success"][0]), "ets99": float(m["ets"][0]), "n": len(rs),
                               "false_stall": _sum_fs(rs)} | graded_stats(fam, rs, tg)
        if row:
            nom, ideal = row.get("nominal", {}).get("success"), row.get("dev_x0", {}).get("success")
            row["_escalate"] = bool(nom is not None and ideal is not None and nom < ideal - 0.01)
            row["_floor"] = bool(nom is not None and ideal is not None and nom == 0 and ideal == 0)
            sn, si = row.get("nominal", {}).get("score"), row.get("dev_x0", {}).get("score")
            row["_escalate_graded"] = bool(sn is not None and si is not None and sn < si - 0.01)
            row["_graded_loss_points"] = graded_loss_points(row)
        out[a.label] = row
    import hycim as hc
    opt = json.loads(hc.OPTIMA.read_text())["instances"]
    b2 = {}
    for pid in pl.H5_B2_POINTS:
        rs = [r for r in recs if r["spec"]["arm"].startswith("b2") and r["spec"]["pert"]["pid"] == pid]
        if rs:
            ok = [r["best_profit"] >= pl.QKP_TARGET_FRAC * opt[r["spec"]["instance"]]["value"] for r in rs]
            b2[pid] = {"success": float(np.mean(ok)), "n": len(rs),
                       "false_accept_states_mean": float(np.mean([r.get("false_accept_states", 0) for r in rs]))}
    out["b2_qkp"] = b2
    return out


def _sum_fs(rs):
    t = {}
    for r in rs:
        for k, v in (r.get("false_stall") or {}).items():
            t[k] = t.get(k, 0) + v
    return t


def evaluate(raw, B: int = ev.N_BOOT) -> dict:
    cost = CostModel()
    fams = {f: family_report(raw, f, cost, B) for f in p6.FAMILIES}
    sweep = json.loads((Path(raw) / "h6_sweep.json").read_text()) if (Path(raw) / "h6_sweep.json").exists() else {}
    return {"families": fams, "h5": h5_report(raw, cost), "restart_sweep_tuning": sweep.get("tune_table"),
            "stand_in_label": "stand-in BSIM4 / FreePDK45 models, ratios only, absolute numbers carry about x2 uncertainty"}


def markdown(rep: dict) -> str:
    L = ["# H6 report (generated by evaluate_h6.py; stand-in model labels apply to every table)", ""]
    for fam, fr in rep["families"].items():
        if not fr:
            continue
        L += [f"## {fam} (B1 comparator: {fr['B1_comparator']})", "| contrast | ETS99 ratio [CI] | Holm p | success diff [CI] | energy | area | quality |",
              "|---|---|---|---|---|---|---|"]
        for k, v in fr["contrasts"].items():
            L.append(f"| {k} | {v['ets_ratio']:.3f} [{v['ets_ci'][0]:.3f}, {v['ets_ci'][1]:.3f}] | {v['holm_p']:.3f} | "
                     f"{v['d_success']:+.3f} [{v['d_success_ci'][0]:+.3f}, {v['d_success_ci'][1]:+.3f}] | {v['energy']} | "
                     f"{v['area']} ({v['area_ratio']:.2f}) | {v['quality']} |")
        L += ["", "| arm | success | restarts/run | never triggered |", "|---|---|---|---|"]
        for lab, a in fr["arms"].items():
            rr = fr["restarts"][lab]
            L.append(f"| {lab} | {a['success']:.3f} | {rr['mean']:.1f} | {rr['never_triggered_frac']:.2f} |")
        L.append("")
    L += ["## H5 re-run (Max-Cut): graded metric (primary), success rate (secondary)",
          "| arm | point | cut fraction | graded score | success | ETS99 |", "|---|---|---|---|---|---|"]
    for arm, rows in rep["h5"].items():
        if arm == "b2_qkp":
            continue
        for pid, v in rows.items():
            if not pid.startswith("_"):
                L.append(f"| {arm} | {pid} | {v.get('cut_frac', float('nan')):.4f} | {v['score']:.3f} | {v['success']:.3f} | {v['ets99']:.3g} |")
        L.append(f"| {arm} | graded 10 %-loss points | {rows.get('_graded_loss_points')} | escalate (graded): {rows.get('_escalate_graded')} | | |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--select", action="store_true")
    g.add_argument("--report", action="store_true")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=ev.N_BOOT)
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    res = select(a.raw) if a.select else evaluate(a.raw, a.boot)
    if a.report:
        out.with_suffix(".md").write_text(markdown(res))
    out.write_text(json.dumps(res, indent=1, default=float))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
