"""Stage 3.2 evaluator (DRAFT prereg prereg/hw/S3_confirmatory_DRAFT.md). Reads the full records of the 3.2 jobs and evaluates, with per-arm pricing:
  primary: ours_stack vs B3_sel and vs B3_h8 on p3n480, p4n480, p3n960 and Max-Cut (nominal); Holm over m = 8; ETS99 ratio (H8 evaluator machinery), win = ratio <= 0.95, Holm p < 0.05, ETS CI upper < 1 and
  success difference not worse than -0.10 (lower CI bound >= -0.10); zero-success comparator = not evaluable (EVAL-1); decision per cell: SUPPORTED (win vs BOTH B3), FALSIFIED (loss to EITHER),
  else NO ENERGY ADVANTAGE SHOWN (a comparator at 0 % success is not evaluable and drops out of the dual rule, at least one comparator must be evaluable). Primary pricing: ours_stack = corrected flags + b3b + t1f + t5 + t6 (screening-only: t1_lcor_k = 0, refresh 200), screening priced once by t1f (the
  mitigation_cost screening term is removed to avoid double counting), B3 gated (t6), bridge / B1 with all + b3b.
  sensitivities (every one re-prices and re-bootstraps): margin -1 pp; frozen H8 pricing; B3 un-gated; hardware estimates x2 / x0.5; correction table 4 and 16; double-counted screening;
  Max-Cut target 0.995 and the post-hoc raised reference.
  A 'supported' statement additionally requires the verdict to hold at hardware estimates x2 (prereg section 1).
usage: evaluate_s3.py --records DIR --out FILE.md [--boot B] [--smoke]"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import numpy as np  # noqa: E402
import cost_flags as cf  # noqa: E402
import evalcommon as ev  # noqa: E402
import evaluate_h8 as e8  # noqa: E402
import plan as pl  # noqa: E402
from cost_model import MeasuredCostV2  # noqa: E402

_ORIG_BKC = ev.best_known_cut
CELLS = ("p3n480", "p4n480", "p3n960", "maxcut")
COMPS = ("B3_sel", "B3_h8")
BASE = dict(margin=0.10, ours="all,b3b,t1f,t5,t6", ours_attrs={"t1_lcor_k": 0, "t1_refresh": 200}, b3="all,b3b,t6", bridge="all,b3b", strip_scr=True, target=0.99, raised=False)
SENS = {
    "margin -1 pp": dict(margin=0.01),
    "frozen H8 pricing (no corrections, no tweaks)": dict(ours="none", ours_attrs={}, b3="none", bridge="none", strip_scr=False),
    "B3 un-gated (favourable to ours)": dict(b3="all,b3b"),
    "hardware estimates x2": dict(ours_attrs={"t1_lcor_k": 0, "t1_refresh": 200, "t1_est_scale": 2.0}),
    "hardware estimates x0.5": dict(ours_attrs={"t1_lcor_k": 0, "t1_refresh": 200, "t1_est_scale": 0.5}),
    "correction table 4": dict(ours_attrs={"t1_lcor_k": 4, "t1_refresh": 200}),
    "correction table 16": dict(ours_attrs={"t1_lcor_k": 16, "t1_refresh": 200}),
    "screening double-counted (mitigation_cost + t1f)": dict(strip_scr=False),
    "Max-Cut target 0.995": dict(target=0.995),
    "Max-Cut reference raised post hoc": dict(raised=True),
}


def load(rec_dir):
    g = {}
    for f in sorted(glob.glob(f"{rec_dir}/*.json")):
        d = json.loads(Path(f).read_text())
        g.setdefault((d["arm"], d["cell"]), []).append(d)
    return g


def cost_for(flags: str, attrs: dict):
    c = cf.apply(MeasuredCostV2(), cf.parse(flags))
    for k, v in attrs.items():
        setattr(c, k, v)
    return c


def price(files, cost, strip_scr):
    out = []
    for d in files:
        for rec in d["records"]:
            if strip_scr and rec.get("mit"):
                rec = dict(rec, mit=re.sub(r"\+scr[0-9.]+", "", rec["mit"]))
            ra, da = e8._price_run(rec, cost, True)
            s = rec["spec"]
            out.append(e8.Run(d["arm"], d["cond"], rec.get("mit") or "none", 0.5, "main", d["cell"], int(rec["desc"].get("n_act", 0)), s["instance"], int(s["r"]), ra, da, float(rec["best_E"]),
                              float(rec.get("wall_s", 0.0)), d["id"]))
    return out


def evaluate(groups, B, spec):
    ev.EQ_SUCC = spec["margin"]
    ev.ZERO_COMPARATOR_NOT_EVALUABLE = True
    pl.MAXCUT_TARGET_FRAC = spec["target"]
    e8._TG.clear()
    ev.best_known_cut = _ORIG_BKC
    if spec["raised"]:
        best = {}
        for (arm, cell), fs in groups.items():
            if cell == "maxcut":
                for d in fs:
                    for rec in d["records"]:
                        best[rec["spec"]["instance"]] = max(best.get(rec["spec"]["instance"], 0), -rec["best_E"])
        import mc_fresh
        orig = ev.best_known_cut
        ev.best_known_cut = lambda k: max(int(orig(k)), int(best.get(k, 0)))
    costs = {"ours_stack": cost_for(spec["ours"], spec["ours_attrs"]), "ours_new": cost_for(spec["bridge"], {}), "B1_sel": cost_for(spec["bridge"], {}),
             "B3_sel": cost_for(spec["b3"], {}), "B3_h8": cost_for(spec["b3"], {})}
    for k in ("B3_sel", "B3_h8"):              # Round 4: B3 cost attributes (default none)
        for a, v in spec.get("b3_attrs", {}).items():
            setattr(costs[k], a, v)
    if spec.get("b3_scale"):                  # Round 3 symmetry sensitivity (default absent: registered pricing unchanged)
        for k in ("B3_sel", "B3_h8"):
            costs[k].scale = {**costs[k].scale, **spec["b3_scale"]}
    runs = {k: price(v, costs[k[0]], spec["strip_scr"] and k[0] == "ours_stack") for k, v in groups.items() if k[0] in costs}
    res = {"primary": {}, "cells": {}, "notes": []}
    prim = []
    for cell in CELLS:
        need = [("ours_stack", cell)] + [(c, cell) for c in COMPS]
        if not all(k in runs for k in need):
            res["notes"].append(f"{cell}: arms incomplete")
            continue
        pairs = set.intersection(*[{(r.inst, r.seed) for r in runs[k]} for k in need])
        insts = sorted({i for i, _ in pairs}, key=lambda s: (len(s), s))
        seeds = sorted({s for _, s in pairs})
        insts = [i for i in insts if all((i, s) in pairs for s in seeds)]
        if not insts or not seeds:
            res["notes"].append(f"{cell}: no common rectangle")
            continue
        arms = {k[0]: e8.arm_of(k[0], [r for r in runs[k] if r.inst in insts and r.seed in seeds], insts, seeds, cell == "maxcut") for k in need}
        bs = ev.boot_stats(arms, B=B)
        for comp in COMPS:
            prim.append((cell, comp, ev.contrast(bs, "ours_stack", comp)))
        res["cells"][cell] = {"n_instances": len(insts), "n_seeds": len(seeds), "obs": {a: {k: float(v) for k, v in o.items()} for a, o in bs["__obs__"].items()}}
    pv = {f"{c}|{k}": x["p_ets_lt1"] for c, k, x in prim}
    hp = ev.holm(pv) if pv else {}
    for c, k, x in prim:
        key = f"{c}|{k}"
        res["primary"][key] = {**{n: x[n] for n in ("ets_ratio", "ets_ci", "d_success", "d_success_ci")}, "holm_p": hp[key], "holm_m": len(pv), "energy": ev.energy_verdict(x, hp[key])}
    dec = {}
    for cell in CELLS:
        v = [res["primary"].get(f"{cell}|{c}", {}).get("energy") for c in COMPS]
        ev_ok = [x for x in v if x and x != "not evaluable"]          # a comparator at 0 % success is not evaluable (EVAL-1) and drops out of the dual rule; it is still reported
        dec[cell] = ("incomplete" if not all(v) else "SUPPORTED" if ev_ok and all(x == "win" for x in ev_ok) else "FALSIFIED" if "loss" in v else "NO ENERGY ADVANTAGE SHOWN")
    res["decision"] = dec
    return res


def md_table(res, title):
    m = next(iter(res["primary"].values()), {"holm_m": 8})["holm_m"]
    L = [f"## {title}", "", f"| cell | comparator | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | Holm p (m = {m}) | verdict |", "|---|---|---|---|---|---|"]
    f = lambda x: "inf" if x is None or x == float("inf") else f"{x:.3g}"  # noqa: E731
    for k, v in res["primary"].items():
        cell, comp = k.split("|")
        L.append(f"| {cell} | {comp} | {f(v['ets_ratio'])} [{f(v['ets_ci'][0])}, {f(v['ets_ci'][1])}] | {v['d_success']:+.2f} [{v['d_success_ci'][0]:+.2f}, {v['d_success_ci'][1]:+.2f}] | {v['holm_p']:.3g} | **{v['energy']}** |")
    L += ["", "Decision per cell: " + "; ".join(f"{c}: **{d}**" for c, d in res["decision"].items()), ""]
    return L


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args(argv)
    B = 20 if a.smoke else a.boot
    groups = load(a.records)
    prim = evaluate(groups, B, BASE)
    L = ["# Stage 3.2 report (DRAFT; energy and success primary)", "", "A not-resolved outcome is read as **no energy advantage shown**, never as parity. A 'supported' statement also requires the verdict at hardware estimates x2.", ""]
    L += md_table(prim, "Primary (nominal estimates, margin -0.10, corrected pricing + b3b, T-1 screening-only stack, B3 gated)")
    x2 = None
    sens_out = {}
    for name, d in SENS.items():
        spec = {**BASE, **d}
        r = evaluate(groups, 20 if a.smoke else min(B, 3000), spec)
        sens_out[name] = r
        L += md_table(r, f"Sensitivity: {name}")
        if name == "hardware estimates x2":
            x2 = r
    ok = {c: (prim["decision"][c] == "SUPPORTED" and x2 is not None and x2["decision"].get(c) == "SUPPORTED") for c in CELLS}
    L += ["## Supported at hardware estimates x2?", "", "; ".join(f"{c}: {'yes' if v else 'no (supported at nominal estimates only)' if prim['decision'][c] == 'SUPPORTED' else 'n/a'}" for c, v in ok.items()), ""]
    L += ["## Success and energy per run (primary pricing)", "", "| cell | arm | n instances x seeds | success | energy per run (fJ) |", "|---|---|---|---|---|"]
    for cell, c in prim["cells"].items():
        for arm, o in c["obs"].items():
            L.append(f"| {cell} | {arm} | {c['n_instances']} x {c['n_seeds']} | {o.get('success', float('nan')):.2f} | {o.get('e_final', float('nan')):.3g} |")
    if prim["notes"]:
        L += ["", "Notes: " + "; ".join(prim["notes"])]
    Path(a.out).write_text("\n".join(L) + "\n")
    Path(a.out).with_suffix(".json").write_text(json.dumps({"primary": prim, "sensitivities": sens_out}, indent=1, default=float))
    print("\n".join(L[:22]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
