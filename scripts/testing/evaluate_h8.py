"""H8 evaluator (prereg/hw/H8_full.md sections 5-7). Pure function of the raw records under <raw>/h8/*.json; reuses the frozen H2 statistics
(evalcommon: ETS99/TTS99, paired two-level bootstrap, Holm, win/tie/loss, +-1 pp / 5 % margins).

Sections of the report
  cells      main grid: per family (planted size ladder, generated graphs pooled, G-set size groups) and condition (ideal | nominal+mitigation):
             per-arm success / ETS99 / TTS99 / area and the registered contrasts with Holm (within cell and across all primary contrasts)
  scaling    per machine and condition: success and ETS99 against spins, log-log ETS99 slope, largest size with success >= 0.5 / 0.1
  ablation   ladder rungs (restart arms, I11, I7v2, I10, I5) with the chosen mitigation, contrasts against the previous rung and against 'none'
  stress     success against the variation point per machine and mitigation (Wilson CI, Newcombe difference to the ideal device, restored flag),
             k axis, C2C-share axis, drift axis, unmitigated
  software   DSATUR / TabuCol / SA success context, wall-clock to solution (CPU-s, NOT a hardware cost), 20x TabuCol solvability
  sensitivity primary-pricing verdicts re-derived under the stated sensitivities; flips are flagged and never change the primary
  power      realised minimum detectable success difference per cell (plan_h8.mde)
Primary pricing: measured_v2 L3_v2 (MeasuredCostV2()) + mitigation overheads priced with the same table (variation_v2.mitigation_cost):
runtime overhead as a factor on cumulative energy, one-time programming + calibration energy charged to EVERY run (conservative; sensitivity
'no_once' drops it). N > 1024 lanes are extrapolated (log-log) beyond the measured block table: such cells carry extrapolated_N = true.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[1] / "scripts" / "golden"))
sys.path.insert(0, str(HERE.parents[1] / "scripts" / "baselines"))
import cost_flags as cf  # noqa: E402
import evalcommon as ev  # noqa: E402
import plan as pl  # noqa: E402
import plan_h8 as p8  # noqa: E402
import pricing as pr  # noqa: E402

RESTORED_MARGIN = -0.10          # a mitigated cell is 'restored' if the Newcombe lower bound of (success - ideal success) >= -0.10
MIN_SIZE_SUCCESS = (0.5, 0.1)
EXTRAPOLATED_LANES = 1024


# ---------------------------------------------------------------------------------------------------------------- loading
@dataclass
class Run:
    label: str
    cond: str
    mit: str
    c2c: float
    phase: str
    fam: str                   # family key (planted family | dimacs8 | maxcut<spins>)
    spins: int
    inst: str
    seed: int
    ra: object                 # evalcommon.RunArrays (primary or sensitivity pricing)
    d_area: float
    best_E: float
    wall_s: float
    file: str


def fam_key(rec: dict) -> str:
    s = rec["spec"]
    return f"maxcut{rec['desc']['n_act']}" if s["family"] == "maxcut" else s["family"]


def load_files(raw: str | Path) -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(Path(raw) / "h8" / "*.json"))):
        d = json.loads(Path(f).read_text())
        d["file"] = Path(f).name
        out.append(d)
    return out


def target_of(rec: dict) -> tuple[float, float]:
    s = rec["spec"]
    if s["family"] == "maxcut":
        bks = ev.best_known_cut(s["instance"])
        return -float(bks), -pl.MAXCUT_TARGET_FRAC * bks
    return 0.0, 0.0


def _price_run(rec: dict, cost, once: bool) -> tuple[object, float]:
    """(RunArrays with mitigation overhead applied, mitigation area). Software records get zero arrays (never priced)."""
    if rec["desc"]["kind"] == "sw":
        K = 2
        z = np.zeros(K)
        ra = ev.RunArrays(np.full(K, rec["best_E"]), np.arange(1, K + 1.0), z, z.copy(), rec["best_E"], 0.0, 0.0, 0.0, 0, {}, {})
        return ra, 0.0
    rec = cf.prepare(rec, cost)
    ra = ev.run_arrays(rec, cost)
    d_area = 0.0
    if rec.get("mit") and rec.get("mit_cost") is not None:
        import variation_v2 as v2
        snaps = rec["snaps"]
        desc = rec["desc"]
        c = snaps[-1]["c"]
        fin = pr.price(desc, c, snaps[-1]["t"], snaps[-1]["flips"], cost)
        r2 = {"price": fin, "desc": desc, "counters": rec.get("counters", c), "spec": rec["spec"], "prog_v2": rec.get("prog_v2")}
        mc = v2.mitigation_cost(r2, v2.Mitigation.parse(rec["mit"]), cost.at(desc))
        f = 1.0 + (mc["d_run_fJ"] / fin["e_total"] if fin["e_total"] else 0.0)
        ft = 1.0 + (mc["d_time_ns"] / fin["time_ns"] if fin["time_ns"] else 0.0)
        once_fJ = mc["e_once_fJ"] if once else 0.0
        ra = ev.RunArrays(ra.curve, ra.t_steps, ra.ecum * f + once_fJ, ra.tcum * ft, ra.best_E, ra.a_total + mc["d_area_um2"],
                          ra.e_total * f + once_fJ, ra.t_total * ft, ra.restarts, ra.prog, ra.blocks)
        d_area = mc["d_area_um2"]
    return ra, d_area


def runs_of(files: list[dict], cost, once: bool = True) -> list[Run]:
    out = []
    for d in files:
        m = d["h8"]
        for rec in d["records"]:
            ra, da = _price_run(rec, cost, once)
            s = rec["spec"]
            out.append(Run(m["label"], m["cond"], m["mit"] if rec.get("mit") else "none", float(m["c2c"]), m["phase"], fam_key(rec),
                           int(rec["desc"].get("n_act", 0)), s["instance"], int(s["r"]), ra, da, float(rec["best_E"]),
                           float(rec.get("wall_s", 0.0)), d["file"]))
    return out


# ---------------------------------------------------------------------------------------------------------------- arms
def arm_of(name: str, runs: list[Run], insts: list[str], seeds: list[int], family_kind_maxcut: bool) -> ev.ArmData:
    by = {(r.inst, r.seed): r for r in runs}
    K = len(next(iter(by.values())).ra.curve)
    I, S = len(insts), len(seeds)
    succ = np.zeros((I, S, K), bool)
    ecum, tcum, gap = np.zeros((I, S, K)), np.zeros((I, S, K)), np.zeros((I, S, K))
    ok, restarts, ef = np.zeros((I, S), bool), np.zeros((I, S)), np.zeros((I, S))
    area = 0.0
    for a, i in enumerate(insts):
        for b, s in enumerate(seeds):
            r = by[(i, s)]
            rec_t = _targets(runs[0], i)
            succ[a, b] = r.ra.curve <= rec_t[1] + 1e-9
            gap[a, b] = ev.gap_of(r.ra.curve, rec_t[0])
            ecum[a, b], tcum[a, b] = r.ra.ecum, r.ra.tcum
            ok[a, b] = succ[a, b, -1]
            restarts[a, b], ef[a, b], area = r.ra.restarts, r.ra.e_total, r.ra.a_total
    return ev.ArmData(name, insts, succ, ecum, tcum, ok, gap[:, :, -1], gap, area, restarts, ef)


_TG: dict = {}


def _targets(run: Run, inst: str) -> tuple[float, float]:
    key = (run.fam.startswith("maxcut"), inst)
    if key not in _TG:
        if run.fam.startswith("maxcut"):
            bks = ev.best_known_cut(inst)
            _TG[key] = (-float(bks), -pl.MAXCUT_TARGET_FRAC * bks)
        else:
            _TG[key] = (0.0, 0.0)
    return _TG[key]


def common(groups: dict[str, list[Run]]) -> tuple[list[str], list[int]]:
    """Instances and seeds present for EVERY arm of a contrast (complete (instance, seed) rectangle)."""
    sets = [{(r.inst, r.seed) for r in rs} for rs in groups.values()]
    pairs = set.intersection(*sets) if sets else set()
    insts = sorted({i for i, _ in pairs}, key=lambda s: (len(s), s))
    seeds = sorted({s for _, s in pairs})
    full_i = [i for i in insts if all((i, s) in pairs for s in seeds)]
    return full_i, seeds


def contrast_block(arms: dict[str, ev.ArmData], pairs: list[tuple[str, str]], B: int, holm_over: dict | None = None) -> dict:
    pairs = [(a, b) for a, b in pairs if a in arms and b in arms]
    if not pairs:
        return {}
    bs = ev.boot_stats(arms, B)
    res = {f"{a} vs {b}": ev.contrast(bs, a, b) for a, b in pairs}
    hp = ev.holm({k: v["p_ets_lt1"] for k, v in res.items()})
    for (a, b), (k, v) in zip(pairs, res.items()):
        v.update(holm_p=hp[k], energy=ev.energy_verdict(v, hp[k]), quality=ev.quality_verdict(v), area_ratio=arms[a].area / arms[b].area if arms[b].area else float("nan"))
        v["not_evaluable"] = None
        if float(np.ravel(bs["__obs__"][b]["success"])[0]) <= 0.0 and float(np.ravel(bs["__obs__"][a]["success"])[0]) <= 0.0:
            v["not_evaluable"] = "not evaluable (both at 0 % success)"
        elif float(np.ravel(bs["__obs__"][b]["success"])[0]) <= 0.0:
            v["not_evaluable"] = "not evaluable (comparator at 0 % success)"
        if v["not_evaluable"]:
            v["energy"] = v["not_evaluable"]
        v["energy_cell"] = v["energy"]                 # per-cell Holm verdict: secondary for the primary contrasts, the verdict for all others
        v["area"] = ev.area_verdict(v["area_ratio"]) if math.isfinite(v["area_ratio"]) else "n/a"
    obs = {n: {k: float(x) for k, x in bs["__obs__"][n].items()} | {"area_um2": arms[n].area} for n in arms}
    return {"contrasts": res, "arms": obs, "n_inst": len(arms[next(iter(arms))].instances), "n_seed": arms[next(iter(arms))].succ.shape[1]}


# ---------------------------------------------------------------------------------------------------------------- sections
def main_cells(runs: list[Run], B: int, kc2c: bool, m_family: int = 20) -> tuple[dict, set]:
    """family -> cond -> block. B3 (digital) has only the ideal condition and is used as the comparator in both."""
    used: set = set()
    cells: dict = {}
    fams = sorted({r.fam for r in runs if r.phase == "main"})
    for fam in fams:
        fr = [r for r in runs if r.phase == "main" and r.fam == fam]
        used |= {r.file for r in fr}
        spins = int(np.median([r.spins for r in fr]))
        cells[fam] = {"spins": spins, "extrapolated_N": p8.lanes_of(spins) > EXTRAPOLATED_LANES}
        for cond in p8.CONDS:
            groups: dict = {}
            for r in fr:
                machine = p8.ARMS[r.label].machine
                if r.cond == cond or (machine == "b3" and cond == "nominal"):      # digital B3 has no variation: its one condition serves both
                    groups.setdefault(r.label, []).append(r)
            if len(groups) < 2:
                continue
            insts, seeds = common(groups)
            if not insts or not seeds:
                continue
            arms = {lab: arm_of(lab, [r for r in rs if r.inst in insts and r.seed in seeds], insts, seeds, fam.startswith("maxcut"))
                    for lab, rs in groups.items()}
            blk = contrast_block(arms, [c for c in p8.HW_CONTRASTS if kc2c or "ours_kc2c" not in c], B)
            if not blk:                                     # no registered contrast has both arms in this rectangle (partial data): report nothing, not a stub
                continue
            blk["mde_success_diff"] = round(p8.mde(len(insts), len(seeds), m=m_family), 3)
            if fam == "dimacs8":
                blk["per_instance_success"] = {lab: {i: float(a.ok_final[k].mean()) for k, i in enumerate(a.instances)} for lab, a in arms.items()}
            cells[fam][cond] = blk
    return cells, used


def holm_primary(cells: dict) -> dict:
    """Global Holm over the primary contrasts: ours_kc2_i11 vs B3_v2 and vs B1_best at the nominal condition, every family."""
    ps = {}
    for fam, fr in cells.items():
        for cond in ("nominal",):
            for k in (f"ours_kc2_i11 vs B3_v2", f"ours_kc2_i11 vs B1_best"):
                c = fr.get(cond, {}).get("contrasts", {}).get(k)
                if c:
                    ps[f"{fam}|{cond}|{k}"] = c["p_ets_lt1"]
    hp = ev.holm(ps)
    for key, p in hp.items():
        fam, cond, k = key.split("|")
        c = cells[fam][cond]["contrasts"][k]
        c["holm_p_global"] = p
        c["energy"] = c["not_evaluable"] or ev.energy_verdict(c, p)       # PRIMARY verdict (prereg section 1 / 7): global Holm over the primary family
        c["primary"] = True
    return hp


def scaling(cells: dict) -> dict:
    out: dict = {}
    for lab in ("ours_kc2_i11", "ours_none", "B1_best", "B3_v2", "ours_kc2c"):
        for cond in p8.CONDS:
            for fam_prefix in ("p3", "p4", "maxcut"):
                pts = []
                for fam, fr in cells.items():
                    if not fam.startswith(fam_prefix) or cond not in fr or lab not in fr[cond]["arms"]:
                        continue
                    a = fr[cond]["arms"][lab]
                    pts.append((fr["spins"], a["success"], a["ets"], fam))
                if not pts:
                    continue
                pts.sort()
                fit = [(math.log(s), math.log(e)) for s, su, e, _ in pts if su > 0 and math.isfinite(e) and e > 0]
                slope = float(np.polyfit(*zip(*fit), 1)[0]) if len(fit) >= 3 else None
                big = {f"success>={t}": max([s for s, su, _, _ in pts if su >= t], default=None) for t in MIN_SIZE_SUCCESS}
                out[f"{lab}|{cond}|{fam_prefix}"] = {"points": [{"spins": s, "success": su, "ets99": e, "family": f} for s, su, e, f in pts],
                                                      "loglog_ets_slope": slope, "slope_points": len(fit), "largest_spins": big}
    return out


LADDER_ORDER = ("L_none", "L_da", "L_mesa", "L_kc2", "L_kc2_i11", "L_kc2_i7v2_i11", "L_kc2_i7v2i10_i11", "L_kc2_i11_i5")
LADDER_MAIN = {"L_none": "ours_none", "L_kc2_i11": "ours_kc2_i11"}


def ablation(runs: list[Run], B: int) -> tuple[dict, set]:
    used: set = set()
    out: dict = {}
    for fam in sorted({r.fam for r in runs if r.phase == "abl"}):
        for cond in p8.CONDS:
            groups: dict = {}
            for r in runs:
                if r.fam != fam or r.cond != cond:
                    continue
                if r.phase == "abl":
                    groups.setdefault(r.label, []).append(r)
                    used.add(r.file)
                elif r.phase == "main" and r.label in LADDER_MAIN.values():
                    lab = next(k for k, v in LADDER_MAIN.items() if v == r.label)
                    groups.setdefault(lab, []).append(r)
            groups = {k: v for k, v in groups.items() if v}
            if len(groups) < 2:
                continue
            insts, seeds = common(groups)
            if not insts or not seeds:
                continue
            arms = {lab: arm_of(lab, [r for r in rs if r.inst in insts and r.seed in seeds], insts, seeds, fam.startswith("maxcut"))
                    for lab, rs in groups.items()}
            order = [a for a in LADDER_ORDER if a in arms]
            pairs = [(b, a) for a, b in zip(order[:-1], order[1:])] + [(b, "L_none") for b in order[1:] if b != order[1] or True]
            seen, uniq = set(), []
            for p in pairs:
                if p[0] != p[1] and p not in seen:
                    seen.add(p)
                    uniq.append(p)
            out.setdefault(fam, {})[cond] = contrast_block(arms, uniq, B)
    return out, used


def stress(runs: list[Run]) -> tuple[dict, set]:
    import variation_v2 as v2
    used: set = set()
    out: dict = {}
    ideal: dict = {}
    for r in runs:
        if r.phase == "main" and r.cond == "ideal":
            ideal.setdefault((r.label, r.fam), []).append(r)
    nominal: dict = {}
    for r in runs:
        if r.phase == "main" and r.cond == "nominal":
            nominal.setdefault((r.label, r.fam), []).append(r)
    cells: dict = {}
    for r in runs:
        if r.phase == "var":
            used.add(r.file)
            cells.setdefault((r.label, r.fam, r.cond, r.mit, r.c2c), []).append(r)
    for (lab, fam, cond, mit, c2c), rs in sorted(cells.items()):
        insts = {r.inst for r in rs}
        seeds = {r.seed for r in rs}
        ref = [r for r in ideal.get((lab, fam), []) if r.inst in insts and r.seed in seeds]
        k, n = sum(_ok(r) for r in rs), len(rs)
        row = {"success": k / n, "n": n, "wilson": v2.wilson(k, n), "mean_end_energy": float(np.mean([r.best_E for r in rs])),
               "mean_energy_fJ": float(np.mean([r.ra.e_total for r in rs]))}
        if ref:
            k0, n0 = sum(_ok(r) for r in ref), len(ref)
            d, lo, hi = v2.newcombe_diff(k, n, k0, n0)
            row.update(ideal_success=k0 / n0, d_vs_ideal=d, d_vs_ideal_ci=(lo, hi), restored=bool(lo >= RESTORED_MARGIN))
        out.setdefault(lab, {}).setdefault(fam, {})[f"{cond}|{mit}|c2c{c2c:g}"] = row
    for (lab, fam), rs in nominal.items():            # the main grid's nominal + chosen-mitigation point belongs to the same axis
        ref = [r for r in ideal.get((lab, fam), []) if (r.inst, r.seed) in {(x.inst, x.seed) for x in rs}]
        if lab in p8.STRESS_ARMS and fam in p8.STRESS_FAMILIES and ref:
            k, n = sum(_ok(r) for r in rs), len(rs)
            k0, n0 = sum(_ok(r) for r in ref), len(ref)
            d, lo, hi = v2.newcombe_diff(k, n, k0, n0)
            out.setdefault(lab, {}).setdefault(fam, {})[f"vx1|{p8.ARMS[lab].mit}|c2c0.5"] = {
                "success": k / n, "n": n, "wilson": v2.wilson(k, n), "ideal_success": k0 / n0, "d_vs_ideal": d, "d_vs_ideal_ci": (lo, hi),
                "restored": bool(lo >= RESTORED_MARGIN), "source": "main grid"}
    return out, used


def _ok(r: Run) -> bool:
    return bool(r.ra.curve[-1] <= _targets(r, r.inst)[1] + 1e-9)


def software(runs: list[Run]) -> tuple[dict, set]:
    used: set = set()
    out: dict = {"context": {}, "solvability_tabucol_20x": {}}
    for fam in sorted({r.fam for r in runs if r.phase in ("sw", "ref", "ctx")}):
        hw = [r for r in runs if r.phase == "main" and r.fam == fam]
        for lab in sorted({r.label for r in runs if r.phase == "sw" and r.fam == fam}):
            rs = [r for r in runs if r.phase == "sw" and r.fam == fam and r.label == lab]
            used |= {r.file for r in rs}
            k = sum(_ok(r) for r in rs)
            out["context"].setdefault(fam, {})[lab] = {"success": k / len(rs), "n": len(rs),
                                                      "cpu_s_per_run": float(np.mean([r.wall_s for r in rs])) if rs else None,
                                                      "note": "software CPU wall-clock on one cloud vCPU: context only, not a hardware energy or time"}
        for lab in sorted({r.label for r in hw}):
            rs = [r for r in hw if r.label == lab and r.cond == ("ideal" if p8.ARMS[lab].machine in ("b3", "b1y") else "nominal")]
            if rs:
                out["context"].setdefault(fam, {})[lab + " (hw nominal)"] = {"success": sum(_ok(r) for r in rs) / len(rs), "n": len(rs)}
        for r_ in [r for r in runs if r.phase == "ctx" and r.fam == fam]:
            used.add(r_.file)
        for lab in sorted({r.label for r in runs if r.phase == "ctx" and r.fam == fam}):
            rs = [r for r in runs if r.phase == "ctx" and r.fam == fam and r.label == lab]
            out["context"].setdefault(fam, {})[lab + " (hw ideal, faithful B1 reading)"] = {"success": sum(_ok(r) for r in rs) / len(rs), "n": len(rs),
                                                                                           "mean_end_energy": float(np.mean([r.best_E for r in rs]))}
        ref = [r for r in runs if r.phase == "ref" and r.fam == fam]
        if ref:
            used |= {r.file for r in ref}
            solved = {i: any(_ok(r) for r in ref if r.inst == i) for i in {r.inst for r in ref}}
            out["solvability_tabucol_20x"][fam] = {"solved_frac": float(np.mean(list(solved.values()))), "unsolved": sorted(i for i, v in solved.items() if not v)}
    return out, used


SENSITIVITIES = {
    "canonical_table": lambda: __import__("cost_model").CostModel(),
    "baselines_lane_path_clock": lambda: __import__("cost_model").MeasuredCostV2(baseline_clock="lane_path"),
    "ungated_generators": lambda: __import__("cost_model").MeasuredCostV2(gen_gated=False),
    "worst_clock_N1024": lambda: __import__("cost_model").MeasuredCostV2(clock_stat="worst"),
    "analog_settle_20ns": lambda: __import__("cost_model").MeasuredCostV2(settle_ns=20.0),
}


def evaluate(raw: str | Path, B: int = ev.N_BOOT, smoke: bool = False, sensitivities: bool = True, tier: str = "core",
             cost_flags: frozenset = frozenset()) -> dict:
    """cost_flags (cost_flags.py): corrected pricing B-1..B-3 for primary and every sensitivity; with any flag set the frozen H8
    pricing is added as the sensitivity 'frozen_h8_pricing'. Empty = the frozen H8 evaluator."""
    from cost_model import MeasuredCostV2, table_hash, measured_v2_table
    files = load_files(raw)
    cost = cf.apply(MeasuredCostV2(), cost_flags)
    runs = runs_of(files, cost)
    kc2c = any(r.label == "ours_kc2c" for r in runs)
    m_fam = p8.primary_family_size(tier)
    cells, used_main = main_cells(runs, B, kc2c, m_fam)
    hp = holm_primary(cells)
    abl, used_abl = ablation(runs, B)
    st, used_st = stress(runs)
    sw, used_sw = software(runs)
    used = used_main | used_abl | used_st | used_sw
    sens: dict = {}
    flips: list = []
    if sensitivities:
        prim = {f"{fam}|{k}": c["energy"] for fam, fr in cells.items() for k, c in fr.get("nominal", {}).get("contrasts", {}).items()
                if k in ("ours_kc2_i11 vs B3_v2", "ours_kc2_i11 vs B1_best")}
        main_files = [d for d in files if d["h8"]["phase"] == "main"]
        sens_mk = {k: (lambda mk=mk: cf.apply(mk(), cost_flags)) for k, mk in SENSITIVITIES.items()}
        if cost_flags:
            sens_mk["frozen_h8_pricing"] = MeasuredCostV2
        for name, mk in sens_mk.items():
            rs = [r for r in runs_of(main_files, mk(), once=True)]
            sc, _ = main_cells(rs, max(20, B // 5), kc2c, m_fam)
            holm_primary(sc)
            sens[name] = {f"{fam}|{k}": c["energy"] for fam, fr in sc.items() for k, c in fr.get("nominal", {}).get("contrasts", {}).items()
                          if k in ("ours_kc2_i11 vs B3_v2", "ours_kc2_i11 vs B1_best")}
            flips += [{"sensitivity": name, "cell": k, "primary": prim.get(k), "sens": v} for k, v in sens[name].items() if prim.get(k) != v]
        rs = runs_of([d for d in files if d["h8"]["phase"] == "main"], cost, once=False)
        sc, _ = main_cells(rs, max(20, B // 5), kc2c, m_fam)
        holm_primary(sc)
        sens["no_once_cost"] = {f"{fam}|{k}": c["energy"] for fam, fr in sc.items() for k, c in fr.get("nominal", {}).get("contrasts", {}).items()
                                if k in ("ours_kc2_i11 vs B3_v2", "ours_kc2_i11 vs B1_best")}
        flips += [{"sensitivity": "no_once_cost", "cell": k, "primary": prim.get(k), "sens": v} for k, v in sens["no_once_cost"].items() if prim.get(k) != v]
    return {"primary_pricing": "measured_v2 L3_v2 (MeasuredCostV2()) + variation_v2.mitigation_cost per run, one-time energy charged to every run"
                               + (f"; corrected cost flags {sorted(cost_flags)}" if cost_flags else ""),
            "cost_flags": sorted(cost_flags),
            "cost_table_sha256": table_hash(measured_v2_table()), "n_files": len(files), "n_files_read": len(used),
            "unread_files": sorted(d["file"] for d in files if d["file"] not in used),
            "kc2c_arm": "present" if kc2c else ("no kc2c records in this raw dir (selection exists; add-on or main list not run yet)" if p8.kc2c_ready() else f"PENDING: {p8.KC2C_PENDING}"),
            "cells": cells, "holm_primary_global": hp, "global_family_size_design": m_fam, "global_family_size_present": len(hp),
            "global_family_complete": len(hp) == m_fam, "scaling": scaling(cells), "ablation": abl, "stress": st, "software": sw,
            "sensitivity_verdicts": sens, "verdict_flips": flips, "power": p8.power_table(), "tier": tier,
            "stand_in_label": "stand-in BSIM4 / FreePDK45 models, ratios only, absolute numbers carry about x2 uncertainty; N > 1024 lanes extrapolated; "
                              "variation claims are conditional on the unmeasured C2C share (>= 0.25 ours / 0.5 B1)"}


def _f(x, nd=3):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) and math.isfinite(x) else str(x)


def markdown(rep: dict) -> str:
    L = ["# H8 report (generated by evaluate_h8.py; stand-in model labels apply to every table)", "", f"Primary pricing: {rep['primary_pricing']}",
         f"Files read: {rep['n_files_read']} / {rep['n_files']}; fairness arm ours_kc2c: {rep['kc2c_arm']}", ""]
    L += [f"Global Holm family (primary contrasts: ours_kc2_i11 vs B3_v2 / vs B1_best, nominal): design size {rep['global_family_size_design']}, present {rep['global_family_size_present']}"
          + ("" if rep["global_family_complete"] else " (INCOMPLETE: the global adjustment is less strict than the prereg; no headline verdict)"),
          "The energy column of a primary contrast is the verdict under the GLOBAL Holm p; `cell` is the per-cell Holm verdict (secondary, shown for transparency).", "",
          "## Main grid: energy-to-solution contrasts (ETS99 ratio first / second, < 1 favours the first)", ""]
    for fam, fr in rep["cells"].items():
        for cond in p8.CONDS:
            b = fr.get(cond)
            if not b:
                continue
            L += [f"### {fam} ({fr['spins']} spins{', N extrapolated' if fr['extrapolated_N'] else ''}), {cond}, {b['n_inst']} instances x {b['n_seed']} seeds, MDE {b['mde_success_diff']}",
                  "| contrast | ETS99 ratio [CI] | Holm p cell / global | success diff [CI] | energy (primary: global) | cell | area | quality |", "|---|---|---|---|---|---|---|---|"]
            for k, v in b["contrasts"].items():
                gp = _f(v["holm_p_global"]) if "holm_p_global" in v else "-"
                L.append(f"| {k}{' (primary)' if v.get('primary') else ''} | {_f(v['ets_ratio'])} [{_f(v['ets_ci'][0])}, {_f(v['ets_ci'][1])}] | {_f(v['holm_p'])} / {gp} | {_f(v['d_success'], 3)} "
                         f"[{_f(v['d_success_ci'][0])}, {_f(v['d_success_ci'][1])}] | {v['energy']} | {v['energy_cell']} | {v['area']} | {v['quality']} |")
            L += ["", "| arm | success | ETS99 (fJ) | area um2 |", "|---|---|---|---|"]
            for lab, a in b["arms"].items():
                L.append(f"| {lab} | {_f(a['success'])} | {_f(a['ets'], 4)} | {_f(a['area_um2'], 1)} |")
            L.append("")
    L += ["## Scaling (success and ETS99 against spins)", "| machine | condition | family | spins -> success | log-log ETS slope | largest spins at success >= 0.5 / 0.1 |", "|---|---|---|---|---|---|"]
    for k, v in rep["scaling"].items():
        lab, cond, fam = k.split("|")
        L.append(f"| {lab} | {cond} | {fam} | " + ", ".join(f"{p['spins']}: {_f(p['success'], 2)}" for p in v["points"]) +
                 f" | {_f(v['loglog_ets_slope'], 2) if v['loglog_ets_slope'] is not None else 'n/a'} ({v['slope_points']} pts) | "
                 f"{v['largest_spins'].get('success>=0.5')} / {v['largest_spins'].get('success>=0.1')} |")
    L += ["", "## Ablation ladder with the chosen mitigation stack"]
    for fam, d in rep["ablation"].items():
        for cond, b in d.items():
            L += [f"### {fam}, {cond}", "| contrast | ETS99 ratio [CI] | success diff [CI] | energy | quality |", "|---|---|---|---|---|"]
            for k, v in b["contrasts"].items():
                L.append(f"| {k} | {_f(v['ets_ratio'])} [{_f(v['ets_ci'][0])}, {_f(v['ets_ci'][1])}] | {_f(v['d_success'])} "
                         f"[{_f(v['d_success_ci'][0])}, {_f(v['d_success_ci'][1])}] | {v['energy']} | {v['quality']} |")
            L.append("")
    L += ["## Variation stress at the design point", "| machine | family | point / mitigation / C2C | success [Wilson] | ideal | diff vs ideal [Newcombe] | restored |", "|---|---|---|---|---|---|---|"]
    for lab, d in rep["stress"].items():
        for fam, rows in d.items():
            for k, v in rows.items():
                ci = v.get("d_vs_ideal_ci")
                L.append(f"| {lab} | {fam} | {k} | {_f(v['success'], 2)} [{_f(v['wilson'][0], 2)}, {_f(v['wilson'][1], 2)}] | {_f(v.get('ideal_success'), 2)} | "
                         + (f"{_f(v['d_vs_ideal'], 2)} [{_f(ci[0], 2)}, {_f(ci[1], 2)}]" if ci else "n/a") + f" | {v.get('restored', 'n/a')} |")
    L += ["", "## Software context (success; CPU seconds are not a hardware cost)", "| family | arm | success | n | cpu s/run |", "|---|---|---|---|---|"]
    for fam, d in rep["software"]["context"].items():
        for lab, v in d.items():
            L.append(f"| {fam} | {lab} | {_f(v['success'], 2)} | {v['n']} | {_f(v.get('cpu_s_per_run'), 2)} |")
    L += ["", "TabuCol 20x solvability: " + json.dumps(rep["software"]["solvability_tabucol_20x"]), "", "## Sensitivities and verdict flips",
          f"Flipped primary verdicts: {len(rep['verdict_flips'])}"]
    for f in rep["verdict_flips"]:
        L.append(f"- {f['sensitivity']}: {f['cell']}: {f['primary']} -> {f['sens']}")
    L += ["", "## Power (minimum detectable SUCCESS difference, 80 % power, alpha / m with m = the global family; the verdict test itself is the ETS99 bootstrap p)", "| size | tier | instances | seeds | m | MDE |", "|---|---|---|---|---|---|"]
    for p in rep["power"]:
        L.append(f"| {p['size']} | {p['tier']} | {p['instances']} | {p['seeds']} | {p['m']} | {p['mde_success_diff']} |")
    L += ["", rep["stand_in_label"]]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=ev.N_BOOT)
    ap.add_argument("--tier", default="core")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--cost-flags", default="none", help="none (frozen H8) | all | comma list of b1,b2,b3 (cost_flags.py)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rep = evaluate(a.raw, a.boot, smoke=a.smoke, sensitivities=not a.smoke, tier=a.tier.removesuffix('-kc2c'),
                   cost_flags=cf.parse(a.cost_flags))
    assert rep["n_files"] > 0, f"no raw files under {a.raw}/h8"
    assert not rep["unread_files"], f"files not read by any section: {rep['unread_files'][:5]}"
    assert any(rep["cells"].values()), "empty main grid"
    out.with_suffix(".md").write_text(markdown(rep))
    out.write_text(json.dumps(rep, indent=1, default=float))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
