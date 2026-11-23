"""Stage 2 evaluator (DRAFT prereg prereg/hw/S2_confirmatory_DRAFT.md). Reads the full run records of the Stage 2 jobs (run_s1.py run --records), prices them with MeasuredCostV2
(corrected cost flags B-1..B-3 as primary; frozen H8 pricing as sensitivity) plus the mitigation overhead exactly as evaluate_h8._price_run, and evaluates the pre-declared contrasts:
  primary (nominal, p3n480 and p4n480): ours_new vs B3_sel, vs B3_h8, vs B1_sel; Holm over m = 6; verdict classes of the H8 evaluator.
  dual-B3 rule: SUPPORTED only if ours_new WINS against BOTH B3 comparators at p3n480; FALSIFIED if it LOSES to EITHER; otherwise NO ENERGY ADVANTAGE SHOWN (never read as parity).
  report-only: bridge (ours_new vs ours_h8, ideal and nominal), bit-sliced B1, no-regression at 240, ETS-selected sensitivity, energy per run and block shares, frozen-pricing sensitivity.
usage: evaluate_s2.py --records DIR --out FILE.md [--boot B] [--smoke]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import numpy as np  # noqa: E402
import cost_flags as cf  # noqa: E402
import evalcommon as ev  # noqa: E402
import evaluate_h8 as e8  # noqa: E402
from cost_model import MeasuredCostV2  # noqa: E402

PRIMARY_CELLS = ("p3n480", "p4n480")
COMPARATORS = ("B3_sel", "B3_h8", "B1_sel")


def load(rec_dir: str):
    groups = {}
    for f in sorted(glob.glob(f"{rec_dir}/*.json")):
        d = json.loads(Path(f).read_text())
        groups.setdefault((d["arm"], d["cell"], d["cond"]), []).append(d)
    return groups


def price_group(files: list, cost) -> list:
    out = []
    for d in files:
        for rec in d["records"]:
            ra, da = e8._price_run(rec, cost, True)
            s = rec["spec"]
            out.append(e8.Run(d["arm"], d["cond"], d["mit"] if rec.get("mit") else "none", 0.5, "main", d["cell"], int(rec["desc"].get("n_act", 0)),
                              s["instance"], int(s["r"]), ra, da, float(rec["best_E"]), float(rec.get("wall_s", 0.0)), d["id"]))
    return out


def arm_for(runs: list, insts: list, seeds: list):
    return e8.arm_of(runs[0].label, runs, insts, seeds, False)


def evaluate(rec_dir: str, B: int, flags: frozenset, smoke: bool = False) -> dict:
    cost = cf.apply(MeasuredCostV2(), flags)
    groups = load(rec_dir)
    runs = {k: price_group(v, cost) for k, v in groups.items()}
    res = {"flags": sorted(flags), "cells": {}, "primary": {}, "notes": []}
    e8._TG.clear()
    # per cell and condition: complete (instance, seed) rectangle common to the arms of a contrast
    def arms_of(cell, cond, names):
        gs = {n: runs.get((n, cell, cond if n not in ("B3_sel", "B3_h8", "B3_ets") else "ideal")) for n in names}
        gs = {n: g for n, g in gs.items() if g}
        if len(gs) < 2:
            return None
        sets = [{(r.inst, r.seed) for r in g} for g in gs.values()]
        pairs = set.intersection(*sets)
        insts = sorted({i for i, _ in pairs}, key=lambda s: (len(s), s))
        seeds = sorted({s for _, s in pairs})
        insts = [i for i in insts if all((i, s) in pairs for s in seeds)]
        if not insts or not seeds:
            return None
        arms = {n: arm_for([r for r in g if r.inst in insts and r.seed in seeds], insts, seeds) for n, g in gs.items()}
        return arms, insts, seeds
    primary = []
    for cell in PRIMARY_CELLS:
        got = arms_of(cell, "nominal", ("ours_new",) + COMPARATORS)
        if not got:
            res["notes"].append(f"{cell}: primary arms incomplete")
            continue
        arms, insts, seeds = got
        bs = ev.boot_stats(arms, B=B)
        for comp in COMPARATORS:
            if comp in arms:
                c = ev.contrast(bs, "ours_new", comp)
                primary.append((cell, comp, c))
        res["cells"][cell] = {"n_instances": len(insts), "n_seeds": len(seeds), "obs": bs["__obs__"]}
    pv = {f"{cell}|{comp}": c["p_ets_lt1"] for cell, comp, c in primary}
    hp = ev.holm(pv) if pv else {}
    for cell, comp, c in primary:
        k = f"{cell}|{comp}"
        res["primary"][k] = {**{x: c[x] for x in ("ets_ratio", "ets_ci", "d_success", "d_success_ci", "p_ets_lt1")}, "holm_p": hp[k], "holm_m": len(pv),
                             "energy": ev.energy_verdict(c, hp[k])}
    # dual-B3 decision at p3n480
    v = {comp: res["primary"].get(f"p3n480|{comp}", {}).get("energy") for comp in ("B3_sel", "B3_h8")}
    if v["B3_sel"] == "win" and v["B3_h8"] == "win":
        dec = "SUPPORTED: win against BOTH B3 comparators at p3n480"
    elif "loss" in v.values():
        dec = "FALSIFIED: loss to at least one B3 comparator at p3n480"
    else:
        dec = "NO ENERGY ADVANTAGE SHOWN (inconclusive, tie, or not evaluable against at least one B3 comparator; not parity)"
    res["decision"] = {"verdicts": v, "text": dec}
    # report-only contrasts
    rep = []
    for cell in sorted({k[1] for k in runs}):
        for cond in ("nominal", "ideal"):
            got = arms_of(cell, cond, ("ours_new", "ours_h8"))
            if got:
                arms, insts, seeds = got
                c = ev.contrast(ev.boot_stats(arms, B=B), "ours_new", "ours_h8")
                rep.append((f"{cell} {cond}: ours_new vs ours_h8 (bridge)", c, len(insts), len(seeds)))
    for cell in sorted({k[1] for k in runs}):
        for comp in COMPARATORS + ("B1_bs",):
            if cell in PRIMARY_CELLS and comp in COMPARATORS:
                continue
            got = arms_of(cell, "nominal", ("ours_new", comp))
            if got:
                arms, insts, seeds = got
                rep.append((f"{cell} nominal: ours_new vs {comp}", ev.contrast(ev.boot_stats(arms, B=B), "ours_new", comp), len(insts), len(seeds)))
    got = arms_of("p3n480", "nominal", ("ours_ets", "B3_ets"))
    if got:
        arms, insts, seeds = got
        rep.append(("p3n480 nominal: ETS-selected ours_ets vs ETS-selected B3_ets (sensitivity)", ev.contrast(ev.boot_stats(arms, B=B), "ours_ets", "B3_ets"), len(insts), len(seeds)))
    res["report"] = [(lab, {x: c[x] for x in ("ets_ratio", "ets_ci", "d_success", "d_success_ci")}, ni, ns) for lab, c, ni, ns in rep]
    # energy per run and block shares
    eb = []
    for (arm, cell, cond), rs in sorted(runs.items()):
        tot, n = {}, 0
        for r in rs:
            for b, x in r.ra.blocks.items():
                tot[b] = tot.get(b, 0.0) + x
            n += 1
        s = sum(tot.values()) or 1.0
        eb.append((arm, cell, cond, n, float(np.mean([r.ra.e_total for r in rs])), tot.get("restart", 0.0) / s, tot.get("rng", 0.0) / s, float(np.mean([r.best_E <= 0 for r in rs]))))
    res["energy_blocks"] = eb
    return res


def fmt(x):
    return "inf" if x is None or x == float("inf") else f"{x:.3g}"


def md(res: dict, title: str) -> list[str]:
    L = [f"## {title}", "", f"cost flags: {res['flags'] or 'none (frozen H8 pricing)'}", ""]
    m = next(iter(res["primary"].values()), {}).get("holm_m", 6)
    L += [f"| cell | comparator | ETS ratio ours_new / comparator [95 % CI] | d success [95 % CI] | Holm p (m = {m}) | verdict |", "|---|---|---|---|---|---|"]
    for k, v in res["primary"].items():
        cell, comp = k.split("|")
        L.append(f"| {cell} | {comp} | {fmt(v['ets_ratio'])} [{fmt(v['ets_ci'][0])}, {fmt(v['ets_ci'][1])}] | {v['d_success']:+.2f} [{v['d_success_ci'][0]:+.2f}, {v['d_success_ci'][1]:+.2f}] | {v['holm_p']:.3g} | **{v['energy']}** |")
    L += ["", f"**Dual-B3 decision (p3n480): {res['decision']['text']}** ({res['decision']['verdicts']})", ""]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--eval1", action="store_true", help="post-hoc EVAL-1 (not the frozen reading): 0 %%-success comparator -> not evaluable")
    a = ap.parse_args(argv)
    ev.ZERO_COMPARATOR_NOT_EVALUABLE = bool(a.eval1)
    B = 20 if a.smoke else a.boot
    prim = evaluate(a.records, B, cf.parse("all"), a.smoke)
    L = ["# Stage 2 report (DRAFT; energy primary)", "", "A not-resolved outcome is read as **no energy advantage shown**, never as parity.", ""]
    if a.eval1:
        L += ["POST-HOC (EVAL-1): a comparator with 0 % success is labelled not evaluable (H8 convention), not an energy win.", ""]
    L += md(prim, "Primary pricing (corrected: B-1, B-2, B-3)")
    sens = evaluate(a.records, B, frozenset(), a.smoke)
    L += md(sens, "Sensitivity: frozen H8 pricing")
    L += ["## Report-only contrasts (primary pricing)", "", "| contrast | instances x seeds | ETS ratio [95 % CI] | d success [95 % CI] |", "|---|---|---|---|"]
    for lab, c, ni, ns in prim["report"]:
        L.append(f"| {lab} | {ni} x {ns} | {fmt(c['ets_ratio'])} [{fmt(c['ets_ci'][0])}, {fmt(c['ets_ci'][1])}] | {c['d_success']:+.2f} [{c['d_success_ci'][0]:+.2f}, {c['d_success_ci'][1]:+.2f}] |")
    L += ["", "## Energy per run and block shares", "", "| arm | cell | cond | runs | energy / run (fJ) | restart share | rng share | success |", "|---|---|---|---|---|---|---|---|"]
    for arm, cell, cond, n, e, rs_, rg, su in prim["energy_blocks"]:
        L.append(f"| {arm} | {cell} | {cond} | {n} | {e:.3g} | {rs_:.4f} | {rg:.4f} | {su:.2f} |")
    if prim["notes"]:
        L += ["", "Notes: " + "; ".join(prim["notes"])]
    Path(a.out).write_text("\n".join(L) + "\n")
    Path(a.out).with_suffix(".json").write_text(json.dumps({"primary": prim, "sensitivity": sens}, indent=1, default=float))
    print("\n".join(L[:30]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
