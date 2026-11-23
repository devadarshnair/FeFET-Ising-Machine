"""H5 evaluator: variation, drift, temperature and supply (prereg/hw/H5_variation.md sections 4-5). Report-only gate. NOT run on
real data at the time of writing.

Outputs per arm and point: success probability at the H2 target, TTS99, ETS99, normalised gap, restarts per 1000 steps, false-stall and
false-reset rates (Kc2 / MESA), 10 %-loss point per perturbation axis (smallest level whose success is below 0.9 x nominal, linear
interpolation in the level, bootstrap CI over instances), the ratio of the machines' loss points, the Kc2-vs-MESA ETS99 ratio per point
against the H2 equivalence band ("level-dependent" flag), and the nominal-sigma escalation test.

Axes and levels (plan.H5_POINTS): dev x{1,2,4} | write x{1,2,4} | read x{1,2,4} | drift 0/0.02/0.05 V per decade | temperature, cold side
(0 C) and hot side (45, 85 C) from 25 C | supply, low side (0.9) and high side (1.1) | mismatch x{1,2} | level-0 as-measured and
combined (single points, reported as retained/lost). Corner points (SS, FF): no process-corner card exists in the repo, so the runner
writes an explicit not-evaluable record per corner (`not_evaluable` key in the raw JSON) and the evaluator reports that reason. Endurance
(point 6): not applicable when every record has array_writes == 0 (asserted and reported). T7 sign-magnitude coding is an extra arm
(`ours.kc2.i7.sm`), reported under "t7_sign_magnitude_extra", outside the 24-point decision and the machine-ratio table. B2 (HyCiM filter
arm, QKP) is run through the unchanged hycim kernel with a perturbed filter at the device-sigma and read-noise points only
("b2_qkp"); success = best truly feasible profit >= 0.99 x the exact optimum. B3 is perturbed through the supply axis only (energy rows
x supply^2), temperature/corner scaling of the digital machine has no model.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evalcommon as ev  # noqa: E402
import plan as pl  # noqa: E402
from cost_model import CostModel  # noqa: E402

LOSS_FRACTION = 0.9
AXES = {   # axis -> list of (level, point id) in order of increasing departure from nominal; nominal point id first
    "dev": [(1.0, "nominal"), (2.0, "dev_x2"), (4.0, "dev_x4")],
    "write": [(1.0, "nominal"), (2.0, "write_x2"), (4.0, "write_x4")],
    "read": [(1.0, "nominal"), (2.0, "read_x2"), (4.0, "read_x4")],
    "drift_v_per_decade": [(0.0, "nominal"), (0.02, "drift_0.02"), (0.05, "drift_0.05")],
    "temp_hot_C_above_25": [(0.0, "nominal"), (20.0, "temp_45"), (60.0, "temp_85")],
    "temp_cold_C_below_25": [(0.0, "nominal"), (25.0, "temp_0")],
    "supply_low": [(0.0, "nominal"), (0.1, "supply_0.9")],
    "supply_high": [(0.0, "nominal"), (0.1, "supply_1.1")],
    "mismatch": [(1.0, "nominal"), (2.0, "mismatch_x2")],
}
SINGLE = ("l0_measured", "combined")
MACHINES = {"ours_kc2": "ours.kc2.i7", "ours_mesa": "ours.mesa.i7", "ours_none": "ours.none.i7", "b1_mesa": "b1.mesa",
            "ours_kc2_i10": "ours.kc2.i7i10"}


T7_ARM = "ours.kc2.i7.sm"


def loss_point(levels: list[float], success: list[float], nominal: float) -> float:
    """Smallest level at which success < 0.9 x nominal, linear interpolation between the bracketing levels; inf if never."""
    thr = LOSS_FRACTION * nominal
    for k in range(1, len(levels)):
        if success[k] < thr:
            s0, s1, l0, l1 = success[k - 1], success[k], levels[k - 1], levels[k]
            return float(levels[k]) if s0 == s1 else float(l0 + (s0 - thr) / (s0 - s1) * (l1 - l0))
    return math.inf


def success_table(recs: list[dict], tg: dict, family: str) -> dict:
    """{(arm, point): ndarray (I,S) of final success} from H5 records."""
    out: dict = {}
    for r in recs:
        s = r["spec"]
        if s["family"] != family:
            continue
        out.setdefault((s["arm"], s["pert"]["pid"]), {})[(s["instance"], s["r"])] = float(r["best_E"] <= tg[s["instance"]]["E_target"] + 1e-9)
    tab = {}
    for k, d in out.items():
        inst = sorted({i for i, _ in d}, key=lambda x: (len(x), x))
        seeds = sorted({r for _, r in d})
        tab[k] = np.array([[d[(i, r)] for r in seeds] for i in inst])
    return tab


def boot_loss_points(tab: dict, arm: str, B: int, rng) -> dict:
    out = {}
    for ax, lv in AXES.items():
        pts = [p for _, p in lv]
        if any((arm, p) not in tab for p in pts):
            continue
        I, S = tab[(arm, pts[0])].shape
        ii = rng.integers(0, I, (B, I))
        ss = rng.integers(0, S, (B, I, S))
        succ = [tab[(arm, p)][ii[:, :, None], ss].mean(axis=(1, 2)) for p in pts]
        obs = [float(tab[(arm, p)].mean()) for p in pts]
        levels = [l for l, _ in lv]
        samples = np.array([loss_point(levels, [s[b] for s in succ], succ[0][b]) for b in range(B)])
        out[ax] = {"point": loss_point(levels, obs, obs[0]), "ci": ev.ci(samples[np.isfinite(samples)]) if np.isfinite(samples).any() else None,
                   "frac_resamples_reached": float(np.isfinite(samples).mean()), "levels": levels, "success": obs}
    for p in SINGLE:
        if (arm, p) in tab and (arm, "nominal") in tab:
            s0, s1 = float(tab[(arm, "nominal")].mean()), float(tab[(arm, p)].mean())
            out[p] = {"success_nominal": s0, "success": s1, "lost_10pct": bool(s1 < LOSS_FRACTION * s0)}
    return out


def _supply_scale(spec: dict) -> float:
    """Energy rows scale with supply^2 at the supply points, for every machine (frozen, pre-Stage 2 review MINOR 7)."""
    v = float((spec.get("pert") or {}).get("supply", 1.0))
    return v * v


def point_stats(recs: list[dict], tg: dict, family: str) -> dict:
    """Per (arm, point): success, restarts/1000 steps, false-stall and false-reset rates, mean energy, array writes."""
    acc: dict = {}
    for r in recs:
        s = r["spec"]
        if s["family"] != family:
            continue
        a = acc.setdefault((s["arm"], s["pert"]["pid"]), {"n": 0, "ok": 0, "restarts": 0.0, "steps": 0, "stalls": 0, "fs": 0, "resets": 0,
                                                       "fr": 0, "e": 0.0, "writes": 0})
        fsd = r.get("false_stall", {})
        a["n"] += 1
        a["ok"] += r["best_E"] <= tg[s["instance"]]["E_target"] + 1e-9
        a["restarts"] += r["restarts"]
        a["steps"] += r["steps"]
        a["stalls"] += fsd.get("stalls", 0)
        a["fs"] += fsd.get("false_stalls", 0)
        a["resets"] += fsd.get("resets", 0)
        a["fr"] += fsd.get("false_resets", 0)
        a["e"] += r["price"]["e_total"] * _supply_scale(s)
        a["writes"] += r["array_writes"]
    return {f"{k[0]}|{k[1]}": {"success": v["ok"] / v["n"], "restarts_per_1000": 1000 * v["restarts"] / v["steps"],
                              "false_stall_rate": v["fs"] / v["stalls"] if v["stalls"] else None,
                              "false_reset_rate": v["fr"] / v["resets"] if v["resets"] else None,
                              "energy_fJ_per_run": v["e"] / v["n"], "array_writes": v["writes"], "runs": v["n"]} for k, v in acc.items()}


def kc2_vs_mesa(recs: list[dict], tg: dict, family: str, B: int) -> dict:
    """ETS99 ratio Kc2/MESA (ours, I7) per point on shared resamples with its CI, against the H2 equivalence band."""
    e_keys = [k for k in CostModel().t if k.startswith("e_")]
    out = {}
    for pt in pl.H5_POINTS:
        if not pt.evaluable:
            continue
        cost = CostModel(scale={k: pt.supply * pt.supply for k in e_keys}) if pt.supply != 1.0 else CostModel()
        arms = {}
        for name, arm in (("kc2", "ours.kc2.i7"), ("mesa", "ours.mesa.i7")):
            rs = [r for r in recs if r["spec"]["arm"] == arm and r["spec"]["family"] == family and r["spec"]["pert"]["pid"] == pt.pid]
            if rs:
                arms[name] = ev.arm_data(name, rs, tg, cost)
        if len(arms) < 2:
            continue
        c = ev.contrast(ev.boot_stats(arms, B), "kc2", "mesa")
        lo, hi = c["ets_ci"]
        out[pt.pid] = {"ets_ratio": c["ets_ratio"], "ci": (lo, hi), "inside_band": bool(lo >= ev.EQ_LO and hi <= ev.EQ_HI),
                       "entirely_outside_band": bool(hi < ev.EQ_LO or lo > ev.EQ_HI)}
    return out


def nominal_escalation(recs: list[dict], h2: list[dict], tg: dict, family: str) -> dict:
    """Escalate if ours' H5 nominal success is below its H5 ideal point dev_x0 (same arm, instances, seeds) by more than 1 pp
    (frozen, pre-Stage 2 review MINOR 6). The legacy comparison with the H2 i7i10 arm is reported, not used."""
    def succ(rs):
        return float(np.mean([r["best_E"] <= tg[r["spec"]["instance"]]["E_target"] + 1e-9 for r in rs]))
    out = {}
    for restart in ("kc2", "mesa", "none"):
        arm = f"ours.{restart}.i7"
        h5 = [r for r in recs if r["spec"]["arm"] == arm and r["spec"]["pert"]["pid"] == "nominal" and r["spec"]["family"] == family]
        if not h5:
            continue
        keys = {(r["spec"]["instance"], r["spec"]["r"]) for r in h5}
        x0 = [r for r in recs if r["spec"]["arm"] == arm and r["spec"]["pert"]["pid"] == "dev_x0" and r["spec"]["family"] == family
              and (r["spec"]["instance"], r["spec"]["r"]) in keys]
        h2r = [r for r in h2 if r["spec"]["arm"] == f"ours.{restart}.i7i10" and r["spec"]["family"] == family
               and (r["spec"]["instance"], r["spec"]["r"]) in keys]
        s5 = succ(h5)
        s0 = succ(x0) if x0 else None
        out[restart] = {"h5_nominal": s5, "h5_dev_x0": s0, "h2_i7i10_legacy": succ(h2r) if h2r else None,
                        "escalate_to_author": bool(s0 is not None and s5 < s0 - ev.EQ_SUCC)}
    return out


def b3_supply(h2_b3: list[dict], tg: dict) -> dict:
    """B3 under the supply axis: table energy rows x supply^2 on its H2 runs (cost-only; temperature/corner have no model)."""
    import pricing as pr
    e_keys = [k for k in CostModel().t if k.startswith("e_")]
    out = {}
    for s in (0.9, 1.0, 1.1):
        cm = CostModel(scale={k: s * s for k in e_keys})
        arr = ev.arm_data(f"b3_supply_{s}", h2_b3, tg, cm)
        out[str(s)] = ev.pooled(arr, None, None)["ets"][0]
    return out


def not_evaluable_points(raw) -> dict:
    """{point id: reason} from the explicit not-evaluable records the runner writes (corner rows)."""
    out = {}
    for f in sorted(glob.glob(str(Path(raw) / "h5" / "*.json"))):
        d = json.loads(Path(f).read_text())
        if d.get("not_evaluable"):
            out[d["point"]] = d["not_evaluable"]
    return out


def b2_qkp(recs: list[dict]) -> dict:
    """B2 (HyCiM filter arm) under the device-sigma and read-noise points: success vs 0.99 x optimum, false-accept states, per point."""
    import hycim as hc
    opt = json.loads(hc.OPTIMA.read_text())["instances"] if hc.OPTIMA.exists() else {}
    acc: dict = {}
    for r in recs:
        s = r["spec"]
        if not s["arm"].startswith("b2") or s["pert"] is None:
            continue
        if s["instance"] not in opt:
            continue
        a = acc.setdefault(s["pert"]["pid"], {"n": 0, "ok": 0, "fa": 0, "gap": 0.0})
        v = opt[s["instance"]]["value"]
        a["n"] += 1
        a["ok"] += r["best_profit"] >= pl.QKP_TARGET_FRAC * v
        a["fa"] += r.get("false_accept_states", 0)
        a["gap"] += (v - r["best_profit"]) / v
    return {pid: {"success": a["ok"] / a["n"], "mean_gap": a["gap"] / a["n"], "false_accept_states_per_run": a["fa"] / a["n"], "runs": a["n"]}
            for pid, a in acc.items()}


def evaluate(raw, B: int = ev.N_BOOT) -> dict:
    recs = ev.load_records(raw, "h5")
    h2 = ev.load_records(raw, "h2", "test")
    ref = ev.load_records(raw, "ref")
    rng = np.random.default_rng(ev.SEED_BOOT)
    corner = not_evaluable_points(raw)
    res = {"not_evaluable": {"corners (SS, FF)": corner.get("corner_SS", pl.CORNER_REASON),
                             "corner records written by the runner": sorted(corner),
                             "B2 points other than device sigma and read noise": "ratiometric filter (array and replica scale together): not applied",
                             "B3 temperature/corner": "no model",
                             "endurance (point 6)": "not applicable: array writes = 0 in every record" if not any(r["array_writes"] for r in recs)
                             else "array writes non-zero: NEEDS REVIEW"},
           "families": {}, "labels": "stand-in models; temperature, drift and mismatch mappings are parametric (plan.py constants)"}
    res["b2_qkp"] = b2_qkp(recs)
    for fam in pl.H5_INSTANCES:
        tg = ev.targets(fam, pl.TEST_SET[fam], ref)
        tab = success_table(recs, tg, fam)
        loss = {m: boot_loss_points(tab, arm, B, rng) for m, arm in MACHINES.items()}
        ratio = {}
        for ax in AXES:
            a, b = loss["ours_kc2"].get(ax), loss["b1_mesa"].get(ax)
            if a and b and math.isfinite(a["point"]) and math.isfinite(b["point"]) and b["point"] > 0:
                ratio[ax] = a["point"] / b["point"]
        h2_b3 = [r for r in h2 if r["spec"]["arm"] == "b3.b3" and r["spec"]["family"] == fam
                 and r["spec"]["instance"] in pl.TEST_SET[fam][:pl.H5_INSTANCES[fam]] and r["spec"]["r"] < pl.H5_SEEDS]
        res["families"][fam] = {"points": point_stats(recs, tg, fam), "loss_points": loss, "loss_point_ratio_ours_over_b1": ratio,
                                "kc2_vs_mesa": kc2_vs_mesa(recs, tg, fam, B), "nominal_escalation": nominal_escalation(recs, h2, tg, fam),
                                "b3_supply_ets99": b3_supply(h2_b3, tg) if h2_b3 else None}
        t7 = boot_loss_points(tab, T7_ARM, B, rng)
        res["families"][fam]["t7_sign_magnitude_extra"] = {
            "arm": T7_ARM, "note": "extra arm, not in the 24-point decision; compare with loss_points.ours_kc2", "loss_points": t7,
            "points": {k: v for k, v in res["families"][fam]["points"].items() if k.startswith(T7_ARM + "|")}}
        kv = res["families"][fam]["kc2_vs_mesa"]
        res["families"][fam]["h2_restart_verdict_level_dependent"] = any(v["entirely_outside_band"] for v in kv.values())   # H5 section 4: moves outside the band
        res["families"][fam]["h2_restart_ci_not_inside_band"] = [p for p, v in kv.items() if not v["inside_band"]]       # wide-CI points, reported only
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=ev.N_BOOT)
    a = ap.parse_args()
    Path(a.out).write_text(json.dumps(evaluate(a.raw, a.boot), indent=1, default=float))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
