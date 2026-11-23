"""H2 evaluator: tuning selection, freeze for H3/H5, and the registered ladder/headline decision rules (prereg/hw/H2_ablation.md
sections 2, 4, 5, 6). NOT run on real data at the time of writing; pointed at the Stage 2 raw directory only after tagging.

  --select --raw DIR --out tuned.json     frozen configs from the TUNING runs only (mean normalised gap at end of budget; ties by energy)
  --freeze --raw DIR --out frozen.json    H2 verdicts -> gate_pass and the ours-best / B1-tuned arms for H3 and H5
  --report --raw DIR --out report.json    full ladder + headline tables (+ markdown next to it)

Rungs per family (arm labels): 1 B1 published | 2a-2d B1 none/DA/MESA/Kc2 | 2' ours none/DA/MESA/Kc2 (power off) | 3 best of
2a-2d (B1) and the tuning-selected restart arm of ours | 4a +I10 | 4b +I7 alone, then I7+I10 only if each passes alone | 4c +I11 |
5 full design = surviving variants, lowest summed log ETS99 on Max-Cut and MaxSAT | side: B1 bit-sliced; B3. I10 variants are priced
from the I10-simulated trajectories (exactly equal at sigma = 0; verified by test_unskip_reconstruction). Rung 4d (I3) runs on the
knapsack family only and 4e (I5) only if I11 fails: neither is in the default job list. Rung 6 (TCAM-lite) is off.
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
from cost_model import CostModel  # noqa: E402

HEADLINE = ("maxcut", "maxsat")
OURS_VARIANTS = ("off", "i10", "i7", "i7i10")


# ------------------------------------------------------------------------------------------------------------- tuning
def _tune_ref(recs: list[dict]) -> dict:
    """E_ref per (family, instance) for the tuning gap: Max-Cut best-known, else the best energy over ALL tuning runs of the
    instance (self-referenced, tuning data only; test data is never used for selection)."""
    ref: dict = {}
    for r in recs:
        s = r["spec"]
        if "best_E" not in r:
            continue
        k = (s["family"], s["instance"])
        ref[k] = min(ref.get(k, math.inf), r["best_E"])
    for (fam, inst) in list(ref):
        if fam == "maxcut":
            ref[(fam, inst)] = -float(ev.best_known_cut(inst))
    return ref


def _qkp_gap(r: dict) -> float:
    import hycim as hc
    opt = json.loads(hc.OPTIMA.read_text())["instances"][r["spec"]["instance"]]["value"]
    return (opt - r["best_profit"]) / opt


def select_tuned(raw: str | Path) -> dict:
    recs = ev.load_records(raw, "h2", "tune")
    ref = _tune_ref(recs)
    table: dict = {}
    for r in recs:
        s = r["spec"]
        key = s["arm"] + (f"@{s['proposals']}" if s["arm"].startswith("b2") else "")
        gap = _qkp_gap(r) if "best_profit" in r else ev.gap_of(np.array([r["best_E"]]), ref[(s["family"], s["instance"])])[0]
        table.setdefault(s["family"], {}).setdefault(key, {}).setdefault(s["cfg"]["cid"], []).append((gap, r["price"]["e_total"], s["cfg"]))
    tuned, tune_table = {}, {}
    for fam, arms in table.items():
        for key, cfgs in arms.items():
            rows = {cid: (float(np.mean([g for g, _, _ in v])), float(np.mean([e for _, e, _ in v])), v[0][2]) for cid, v in cfgs.items()}
            best = min(rows, key=lambda c: (round(rows[c][0], 12), rows[c][1]))      # lower gap; ties -> lower energy
            tuned.setdefault(fam, {})[key] = rows[best][2]
            tune_table.setdefault(fam, {})[key] = {cid: [g, e] for cid, (g, e, _) in rows.items()} | {"_selected": best}
    rung3 = {"b1": {}, "ours_global": None}
    for fam in pl.FAMILIES:
        if fam not in tune_table:
            continue
        cand = {r: tune_table[fam].get(f"b1.{r}") for r in pl.RESTARTS}
        if all(cand.values()):
            rung3["b1"][fam] = min(cand, key=lambda r: (_sel(cand[r])[0], _sel(cand[r])[1]))
    tot = {}
    for r in pl.RESTARTS:
        gs = [_sel(tune_table[f][f"ours.{r}.i10"])[0] for f in HEADLINE if f in tune_table and f"ours.{r}.i10" in tune_table[f]]
        if len(gs) == len(HEADLINE):
            tot[r] = sum(gs)
    if tot:
        rung3["ours_global"] = min(tot, key=tot.get)
    return {"tuned": tuned, "rung3_best": rung3, "tune_table": tune_table, "grid": {"configs_per_arm": 8, "tune_runs_per_config": 8}}


def _sel(rows: dict) -> tuple[float, float]:
    s = rows["_selected"]
    return rows[s][0], rows[s][1]


# ------------------------------------------------------------------------------------------------------------- ladder
def spec_of_label(tuned: dict, fam: str) -> dict:
    """label -> (sim arm key, pricing variant ('' = as simulated), cfg-source key)."""
    b1best = tuned["rung3_best"]["b1"][fam]
    ob = tuned["rung3_best"]["ours_global"]
    L = {"1_B1_published": ("b1.mesa.published", "", "@default"),
         "2a_B1_none": ("b1.none", "", "b1.none"), "2b_B1_da": ("b1.da_offset", "", "b1.da_offset"),
         "2c_B1_mesa": ("b1.mesa", "", "b1.mesa"), "2d_B1_kc2": ("b1.kc2", "", "b1.kc2"),
         "3_B1_best": (f"b1.{b1best}", "", f"b1.{b1best}"), "side_B1_bitsliced": ("b1bs.mesa", "", "b1bs.mesa"),
         "B3": ("b3.b3", "", "b3.b3")}
    for r in pl.RESTARTS:
        L[f"2p_ours_{r}"] = (f"ours.{r}.i10", "off", f"ours.{r}.i10")
    for v in OURS_VARIANTS:
        sim = "i10" if v in ("off", "i10") else "i7i10"
        L[f"ours_{ob}_{v}"] = (f"ours.{ob}.{sim}", v, f"ours.{ob}.{sim}")
        L[f"ours_kc2_i11_{v}"] = (f"ours.kc2.{sim}.i11", v, f"ours.kc2.{sim}.i11")
    return L


def _recs_for(by_arm: dict, arm: str, fam: str) -> list[dict]:
    return by_arm.get((arm, fam), [])


def build_arms(raw: str | Path, tuned: dict, fam: str, tg: dict, cost) -> dict[str, ev.ArmData]:
    recs = ev.load_records(raw, "h2", "test")
    by: dict = {}
    for r in recs:
        by.setdefault((r["spec"]["arm"], r["spec"]["family"]), []).append(r)
    out = {}
    for label, (arm, variant, _) in spec_of_label(tuned, fam).items():
        rs = _recs_for(by, arm, fam)
        if rs:
            out[label] = ev.arm_data(label, rs, tg, cost, noskip=variant in ("off", "i7"))
    return out


def family_report(raw, tuned: dict, fam: str, tg: dict, cost, B: int = ev.N_BOOT) -> dict:
    arms = build_arms(raw, tuned, fam, tg, cost)
    ob = tuned["rung3_best"]["ours_global"]
    base = f"ours_{ob}_off"
    pairs = [("2d_B1_kc2", "2c_B1_mesa"), ("2p_ours_kc2", "2p_ours_mesa"),
             (f"ours_{ob}_i10", base), (f"ours_{ob}_i7", base), (f"ours_{ob}_i7i10", base),
             ("ours_kc2_i11_off", "ours_kc2_off"), ("ours_kc2_i11_i10", "ours_kc2_i10"),
             ("ours_kc2_i11_i7", "ours_kc2_i7"), ("ours_kc2_i11_i7i10", "ours_kc2_i7i10")]
    vs_b1 = [lab for lab in arms if lab.startswith(("2p_ours", "ours_")) or lab in ("B3",)]
    contrasts = {f"{a} vs {b}": (a, b) for a, b in pairs if a in arms and b in arms}
    contrasts |= {f"{lab} vs 3_B1_best": (lab, "3_B1_best") for lab in vs_b1 if "3_B1_best" in arms and lab != "B3"}
    if "B3" in arms:
        contrasts |= {f"{lab} vs B3": (lab, "B3") for lab in vs_b1 if lab != "B3"}
    bs = ev.boot_stats(arms, B)
    res = {k: ev.contrast(bs, a, b) for k, (a, b) in contrasts.items()}
    hp = ev.holm({k: v["p_ets_lt1"] for k, v in res.items()})
    for k, v in res.items():
        v["holm_p"] = hp[k]
        v["energy"] = ev.energy_verdict(v, hp[k])
        v["quality"] = ev.quality_verdict(v)
        if k == "2d_B1_kc2 vs 2c_B1_mesa":                  # H2 section 1, 6: rung 2d is reported as a win or a tie, never a loss
            v["rung_2d_vs_2c"] = "win" if v["energy"] == "win" else "tie (not better)"
        a, b = contrasts[k]
        v["area_ratio"] = arms[a].area / arms[b].area
        v["area"] = ev.area_verdict(v["area_ratio"])
    quality = {lab: {f"gap@{int(f * 100)}%steps": float(a.curve_gap[:, :, max(0, int(round(f * a.curve_gap.shape[2])) - 1)].mean())
                     for f in (0.25, 0.5, 1.0)} for lab, a in arms.items()}
    if "3_B1_best" in arms:                      # fixed energy budgets: 25 / 50 / 100 % of the B1-tuned full-run energy, per instance
        full = arms["3_B1_best"].ecum[:, :, -1].mean(axis=1)
        for lab, a in arms.items():
            quality[lab].update({f"gap@{int(f * 100)}%E_B1": ev.gap_at_energy(a, f * full) for f in (0.25, 0.5, 1.0)})
    return {"arms": {lab: bs["__obs__"][lab] | {"area_um2": a.area} for lab, a in arms.items()}, "contrasts": res, "quality": quality,
            "n_instances": len(next(iter(arms.values())).instances) if arms else 0}


def full_design(rep: dict, tuned: dict) -> dict:
    """Surviving tweaks: I10 / I7 kept only if each wins alone vs ours-base; the pair only if both; I11 variants only if they win
    against their non-I11 counterpart. Choose the candidate with the lowest summed log ETS99 over the headline families."""
    ob = tuned["rung3_best"]["ours_global"]
    surv = {"off": True, "i10": True, "i7": True}
    for fam in HEADLINE:
        c = rep[fam]["contrasts"]
        surv["i10"] &= c.get(f"ours_{ob}_i10 vs ours_{ob}_off", {}).get("energy") == "win"
        surv["i7"] &= c.get(f"ours_{ob}_i7 vs ours_{ob}_off", {}).get("energy") == "win"
    cands = ["off"] + [v for v in ("i10", "i7") if surv[v]] + (["i7i10"] if surv["i10"] and surv["i7"] else [])
    labels = [f"ours_{ob}_{v}" for v in cands]
    for v in cands:
        ok = all(rep[fam]["contrasts"].get(f"ours_kc2_i11_{v} vs ours_kc2_{v}", {}).get("energy") == "win" for fam in HEADLINE)
        if ok:
            labels.append(f"ours_kc2_i11_{v}")
    score = {}
    for lab in labels:
        vals = [rep[f]["arms"].get(lab, {}).get("ets", math.inf) for f in HEADLINE]
        score[lab] = sum(math.log(v) for v in vals) if all(math.isfinite(v) and v > 0 for v in vals) else math.inf
    best = min(score, key=score.get) if score else None
    return {"candidates": labels, "score_sum_log_ets99": score, "full": best}


def gate(rep: dict, full: dict) -> dict:
    """H2 gate: full machine or at least one rung beats B1-tuned by the win margin on ETS99 on >= 2 families (Max-Cut and MaxSAT)."""
    wins: dict = {}
    for fam in HEADLINE:
        for k, v in rep[fam]["contrasts"].items():
            if k.endswith(" vs 3_B1_best") and v["energy"] == "win":
                wins.setdefault(k.split(" vs ")[0], []).append(fam)
    both = sorted(a for a, f in wins.items() if set(f) >= set(HEADLINE))
    text = ("H2 gate PASS: " + ", ".join(both)) if both else ("H2 gate FAIL: a restart rule is not a hardware win over a tuned "
                                                              "FeFET CiM annealer; the phase stops before H4")
    return {"pass": bool(both), "winning_arms": both, "wins_by_arm": wins, "statement": text}


def b2_report(raw, cost) -> dict:
    """B2 on QKP, reported on its own (ours is not run on QKP by default): success at 0.99 x optimum, ETS per success, energy, area."""
    import hycim as hc
    recs = ev.load_records(raw, "h2", "test")
    opt = json.loads(hc.OPTIMA.read_text())["instances"]
    out = {}
    for L in pl.QKP_LENGTHS:
        rs = [r for r in recs if r["spec"]["arm"].startswith("b2") and r["spec"]["proposals"] == L]
        if not rs:
            continue
        ok = np.array([r["best_profit"] >= pl.QKP_TARGET_FRAC * opt[r["spec"]["instance"]]["value"] for r in rs])
        e = np.array([r["price"]["e_total"] for r in rs])
        p = float(ok.mean())
        out[str(L)] = {"runs": len(rs), "success": p, "energy_fJ_per_run": float(e.mean()),
                       "ets99_fJ": float(e.mean() * ev.r99(np.array([p]))[0]), "area_um2": rs[0]["price"]["a_total"]}
    return out


def evaluate(raw, tuned: dict, B: int = ev.N_BOOT) -> dict:
    cost = CostModel()
    ref = ev.load_records(raw, "ref")
    rep = {}
    for fam in pl.FAMILIES:
        tg = ev.targets(fam, pl.TEST_SET[fam], ref)
        rep[fam] = family_report(raw, tuned, fam, tg, cost, B)
    full = full_design(rep, tuned)
    return {"families": rep, "full_design": full, "gate": gate(rep, full), "b2_qkp": b2_report(raw, cost),
            "tuned": tuned["tuned"], "rung3_best": tuned["rung3_best"], "tuning_table": tuned["tune_table"],
            "stand_in_label": "stand-in BSIM4 / FreePDK45 models, ratios only, absolute numbers carry about x2 uncertainty"}


def freeze(raw, tuned: dict, B: int = ev.N_BOOT) -> dict:
    rep = evaluate(raw, tuned, B)
    full = rep["full_design"]["full"]
    out = {"gate_pass": rep["gate"]["pass"], "statement": rep["gate"]["statement"], "full_design": full}
    ob = tuned["rung3_best"]["ours_global"]
    for fam in pl.FAMILIES:
        lab = full or f"ours_{ob}_off"
        arm, variant, src = spec_of_label(tuned, fam)[lab]
        sim_arm = arm if variant not in ("off", "i7") else arm.replace(".i10", ".off").replace(".i7i10", ".i7")
        cfg = tuned["tuned"][fam][src]
        b1arm = spec_of_label(tuned, fam)["3_B1_best"]
        out[fam] = {"ours_best": {"arm": sim_arm, "cfg": cfg}, "b1_tuned": {"arm": b1arm[0], "cfg": tuned["tuned"][fam][b1arm[2]]}}
    return out


def markdown(rep: dict) -> str:
    lines = ["# H2 report (generated by evaluate_h2.py; stand-in model labels apply to every table)", "", rep["gate"]["statement"], ""]
    for fam, fr in rep["families"].items():
        lines += [f"## {fam}", "| contrast | ETS99 ratio [CI] | Holm p | success diff [CI] | energy | area | quality |", "|---|---|---|---|---|---|---|"]
        for k, v in fr["contrasts"].items():
            lines.append(f"| {k} | {v['ets_ratio']:.3f} [{v['ets_ci'][0]:.3f}, {v['ets_ci'][1]:.3f}] | {v['holm_p']:.3f} | "
                         f"{v['d_success']:+.3f} [{v['d_success_ci'][0]:+.3f}, {v['d_success_ci'][1]:+.3f}] | {v['energy']} | "
                         f"{v['area']} ({v['area_ratio']:.2f}) | {v['quality']} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--select", action="store_true")
    g.add_argument("--freeze", action="store_true")
    g.add_argument("--report", action="store_true")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=ev.N_BOOT)
    ap.add_argument("--tuned")
    a = ap.parse_args()
    raw, out = Path(a.raw), Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.select:
        res = select_tuned(raw)
    else:
        tuned = json.loads(Path(a.tuned or raw / "tuned.json").read_text())
        res = freeze(raw, tuned, a.boot) if a.freeze else evaluate(raw, tuned, a.boot)
        if a.report:
            out.with_suffix(".md").write_text(markdown(res))
    out.write_text(json.dumps(res, indent=1, default=float))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
