"""Stage 1 runner (DRAFT, tuning-only): one job per process. Modes:
  run    --id ID --stage S --arm A --cid C --label L --family F --cell CELL --cond ideal|nominal --mit M --shares X --keys K1,K2 --seeds N --k K --tile T
         [--cfg k=v,...] [--sel REF] [--sweeps S] --out FILE.jsonl      one JSONL row per (instance, seed): best_E, target, success
  gate   --id ID --out FILE.json [--smoke]       R13 identity gate: fresh ideal vs tiled-256 nominal runs of the same specs; rc 1 on any difference
  select --stage 1a|2 --dir DIR --out FILE.json  registered selection rule on the JSONL files in DIR
  report --dir DIR --out FILE.md                 tables (success, Wilson 95 %) + gate + selections
Selection references (--sel): <stage>:<arm>:<col|gk>:<rank> (stage 1a) or 2:ours:final|final_gk (stage 2); the file is DIR/selection_<stage>.json.
Stage 1 is tuning-only: instances are tag-10 fresh planted keys and G43-47 (P4.02-used). Nothing here is confirmatory.
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))

TUNE_TAG = 10
ARM_ORDER = ("ours", "B3", "kc2c", "none_B1")


def sweeps_of(family: str, key: str = "") -> float:
    if family == "dimacs8":                     # H8 rule: max(150, 150 x spins / 240), cap 600 (named DIMACS-style graphs)
        import machines as ma
        return float(min(600, max(150, round(150 * ma.mapped(family, key).spins / 240))))
    if family == "maxcut" or family.endswith("n240") or family == "p4n120":
        return 150.0
    return float(min(600, max(150, round(150 * int(family[3:]) / 240))))


def inst_index(key: str) -> int:
    return 1500 + (int(key) if key.isdigit() else int(key.lstrip("GR"))) % 1000


def inst_index_for(tag: int, key: str) -> int:
    """Spec.inst_index by tag: 10 = tuning (1500 + key % 1000); 11 = Stage 2 (frozen: 700 + key - 2300); 12 = Stage 3.2 (2000 + numeric part of the key)."""
    if tag == TUNE_TAG:
        return inst_index(key)
    if tag == 11:
        return 700 + int(key) - 2300
    if tag == 13:                                # Stage C: planted numeric keys, Max-Cut R keys, named DIMACS-style graphs (index in h8_instances.GRAPHS)
        if key.isdigit():
            return 3000 + int(key)
        import h8_instances as h8i
        return 6000 + list(h8i.GRAPHS).index(key) if key in h8i.GRAPHS else 3000 + int(key.lstrip("GR"))
    return 2000 + int(key.lstrip("GR"))


def parse_cfg(s: str) -> dict:
    out = {}
    for kv in filter(None, s.split(",")):
        k, _, v = kv.partition("=")
        if v in ("true", "false"):
            out[k] = v == "true"
        else:
            try:
                out[k] = json.loads(v)
            except ValueError:
                out[k] = v                       # bare string (e.g. cc=burst)
    return out


def target_of(family: str, key: str) -> float:
    if family == "maxcut":
        import evalcommon as ev
        import plan as pl
        try:
            return -pl.MAXCUT_TARGET_FRAC * float(ev.best_known_cut(key))
        except Exception:                       # fresh R<seed> graph without a built reference: success undefined, screening uses mean best_E
            return float("-inf")
    return 0.0


def load_sel(ref: str, outdir: Path) -> dict:
    parts = ref.split(":")
    d = json.loads((outdir / f"selection_{parts[0]}.json").read_text())
    if parts[0] == "1a":
        return d["arms"][parts[1]][parts[2]][int(parts[3])]
    return d["final"][parts[2]] if parts[2] in d["final"] else d[parts[2]]


def do_run(a) -> int:
    import run_h8 as rh
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg_over = {}
    if a.sel:
        sel_stage = a.sel.split(":")[0]
        d = json.loads((out.parent / f"selection_{sel_stage}.json").read_text())
        if a.id.startswith("1e.") and not d.get("stage2_go", True) and not a.sweeps:      # a smoke (--sweeps given) always runs
            out.write_text("")
            print(f"SKIPPED {a.id}: stage2_go is false in selection_{sel_stage}.json (Stage 1 gate not passed)")
            return 0
        ent = load_sel(a.sel, out.parent)
        cfg_over.update(ent["cfg_over"])
        a.cid = ent["cid"] if a.cid.startswith("top") or a.cid.endswith("_sel") else a.cid
    cfg_over.update(parse_cfg(a.cfg))
    from variation_v2 import vx
    import variation_v2 as v2
    v2.OURS_TILE_ROWS = a.tile or None
    cond = a.cond if (a.k == 1.0 or a.cond == "ideal") else f"vx{a.k:g}"
    if a.l0sigma != 1.0:                        # C2C_ESTIMATE bracket: scale only the level-0 sigma(Vth)
        orig_sig = v2.sigma_vth
        v2.sigma_vth = lambda k_: orig_sig(k_) * (a.l0sigma if k_ == 0 else 1.0)
    t0 = time.time()
    n = 0
    recs = []
    with open(out, "w") as fh:
        for share in (float(x) for x in a.shares.split(",")):
            for key in a.keys.split(","):
                tgt = target_of(a.family, key)
                sweeps = float(a.sweeps) if a.sweeps else sweeps_of(a.family, key)
                for r in range(a.seeds):
                    ns = SimpleNamespace(label=a.label, family=a.family, phase="main", cond=cond, mit=a.mit, c2c=share, sweeps=sweeps, ours_tile_rows=a.tile)
                    spec = rh.make_spec(ns, key, r)
                    spec = dataclasses.replace(spec, tag=a.tag, inst_index=inst_index_for(a.tag, key), cfg={**spec.cfg, **cfg_over})
                    rec = rh.execute_one(spec, ns)
                    if a.records:
                        recs.append(rec)
                    fh.write(json.dumps({"id": a.id, "stage": a.stage, "arm": a.arm, "cid": a.cid, "label": a.label, "cell": a.cell, "family": a.family, "cond": cond, "mit": a.mit,
                                         "share": share, "k": a.k, "tile": a.tile, "inst": key, "r": r, "best_E": rec["best_E"], "target": tgt, "success": rec["best_E"] <= tgt,
                                         "flips": rec["flips"], "restarts": rec.get("restarts"), "cfg_over": cfg_over, "sweeps": sweeps}) + "\n")
                    fh.flush()
                    n += 1
    if a.records:
        Path(a.records).mkdir(parents=True, exist_ok=True)
        (Path(a.records) / f"{a.id}.json").write_text(json.dumps({"id": a.id, "arm": a.arm, "cid": a.cid, "cell": a.cell, "cond": cond, "mit": a.mit, "shares": a.shares, "family": a.family, "tag": a.tag, "records": recs}, default=float))
    print(f"{a.id}: {n} runs, {time.time() - t0:.0f} s")
    return 0


def do_gate(a) -> int:
    """R13 identity: fresh ideal and tiled-256 nominal runs of the same registered ours_kc2_i11 spec; identical best_E and energy curve required."""
    import run_h8 as rh
    import variation_v2 as v2
    fam = a.family or ("p3n480" if a.smoke else "p3n960")      # smoke exercises the same code path (tiled nominal, 2 tiles) at a size the local machine can hold
    sweeps = 1.0 if a.smoke else sweeps_of(fam)
    rows = []
    for r in range(2):
        res = {}
        for name, cond, mit, tile in (("ideal", "ideal", "none", 0), ("tiled_nominal", "nominal", "wv+diff+cal", 256)):
            v2.OURS_TILE_ROWS = tile or None
            ns = SimpleNamespace(label="ours_kc2_i11", family=fam, phase="main", cond=cond, mit=mit, c2c=0.5, sweeps=sweeps, ours_tile_rows=tile)
            spec = dataclasses.replace(rh.make_spec(ns, a.key, r), tag=a.tag, inst_index=inst_index_for(a.tag, a.key))
            res[name] = rh.execute_one(spec, ns)
        i, t = res["ideal"], res["tiled_nominal"]
        rows.append({"r": r, "family": fam, "best_E_ideal": i["best_E"], "best_E_tiled_nominal": t["best_E"], "curve_identical": list(i["curve"]) == list(t["curve"]),
                     "flips_ideal": i["flips"], "flips_tiled": t["flips"]})
        print(json.dumps(rows[-1]), flush=True)
    ok = all(x["curve_identical"] and x["best_E_ideal"] == x["best_E_tiled_nominal"] for x in rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"id": a.id, "pass": ok, "smoke": a.smoke, "rows": rows,
                                       "rule": "nominal (tiled 256, wv+diff+cal, share 0.5) == ideal at the gate size; a difference STOPS every noisy 960-class job and is reported"}, indent=1))
    print("GATE", "PASS" if ok else "FAIL (difference reported; dependants will not run)")
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------------------------ statistics / selection
def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def newcombe(k1: int, n1: int, k2: int, n2: int):
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = k1 / n1 - k2 / n2
    return d, d - math.sqrt((k1 / n1 - l1) ** 2 + (u2 - k2 / n2) ** 2), d + math.sqrt((u1 - k1 / n1) ** 2 + (k2 / n2 - l2) ** 2)


def read_rows(d: str) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        rows += [json.loads(x) for x in open(f) if x.strip()]
    return rows


def agg(rows: list[dict], keyf):
    g: dict = {}
    for r in rows:
        e = g.setdefault(keyf(r), {"n": 0, "k": 0, "sumE": 0.0, "cfg_over": r["cfg_over"], "order": len(g)})
        e["n"] += 1
        e["k"] += int(r["success"])
        e["sumE"] += r["best_E"]
    return g


def rank(g: dict) -> list:
    return sorted(g.items(), key=lambda kv: (-kv[1]["k"] / kv[1]["n"], kv[1]["sumE"] / kv[1]["n"], kv[1]["order"]))


def is_round2(r: dict) -> bool:
    return r["id"].split(".")[3:4] in (["top0"], ["top1"], ["top2"], ["top3"], ["ref"]) or r["cell"] == "p3n960" and r["stage"] == "1a"


def do_select(a) -> int:
    rows = read_rows(a.dir)
    out = {"stage": a.stage, "rule": "highest pooled success; ties lower mean best_E; ties grid order (prereg/hw/S1_tuning_grids.json)"}
    if a.stage == "1a":
        arms = {}
        r1 = [r for r in rows if r["stage"] == "1a" and r["cell"] in ("p3n480", "gk")]
        for arm in ARM_ORDER:
            arms[arm] = {}
            for kind, cells in (("col", ("p3n480",)), ("gk", ("gk",))):
                sub = [r for r in r1 if r["arm"] == arm and r["cell"] in cells and r["cid"] != "ref" and not r["cid"].endswith("_ref_H8")]
                g = agg(sub, lambda r: r["cid"])
                arms[arm][kind] = [{"cid": cid, "cfg_over": e["cfg_over"], "success": e["k"] / e["n"], "n": e["n"], "mean_best_E": e["sumE"] / e["n"]} for cid, e in rank(g)[:4]]
                arms[arm][kind + "_all"] = {cid: {"k": e["k"], "n": e["n"]} for cid, e in g.items()}
        out["arms"] = arms
    else:
        d1 = json.loads((Path(a.dir) / "selection_1a.json").read_text())
        r2 = [r for r in rows if r["stage"] == "1a" and r["cell"] == "p3n960" and r["arm"] == "ours"]
        g2 = agg(r2, lambda r: r["cid"])
        ref = g2.get("ref")
        ranked = [(c, e) for c, e in rank(g2) if c != "ref"]
        best = ranked[0] if ranked else None
        gate = {"p3n960": None, "gk": None}
        if best and ref:
            d, lo, hi = newcombe(best[1]["k"], best[1]["n"], ref["k"], ref["n"])
            gate["p3n960"] = {"best_cid": best[0], "success": best[1]["k"] / best[1]["n"], "ref_success": ref["k"] / ref["n"], "diff": d, "newcombe_lo": lo, "pass": d >= 0.15 and lo > 0}
        gkall = d1["arms"]["ours"]["gk_all"]
        gk_best = d1["arms"]["ours"]["gk"][0] if d1["arms"]["ours"]["gk"] else None
        refgk = gkall.get("c0_K1")
        if gk_best and refgk:
            d, lo, hi = newcombe(round(gk_best["success"] * gk_best["n"]), gk_best["n"], refgk["k"], refgk["n"])
            gate["gk"] = {"best_cid": gk_best["cid"], "success": gk_best["success"], "ref_success": refgk["k"] / refgk["n"], "diff": d, "newcombe_lo": lo, "pass": d >= 0.25 and lo > 0}
        go = bool((gate["p3n960"] or {}).get("pass") or (gate["gk"] or {}).get("pass"))
        # 1b variants on p3n480 (ours rank-1 config + R6/R5): choose the best variant only if it beats `base` by >= +0.10
        b1 = agg([r for r in rows if r["stage"] == "1b" and r["cell"] == "p3n480"], lambda r: r["cid"])
        variant = None
        if "base" in b1 and len(b1) > 1:
            cand = [(c, e) for c, e in rank(b1) if c != "base"]
            if cand and cand[0][1]["k"] / cand[0][1]["n"] - b1["base"]["k"] / b1["base"]["n"] >= 0.10:
                variant = cand[0]
        col1 = d1["arms"]["ours"]["col"][0] if d1["arms"]["ours"]["col"] else {"cid": "ref", "cfg_over": {"kick_c": 0, "knob": 2}}
        bestcfg = next((e["cfg_over"] for c, e in ranked[:1]), col1["cfg_over"]) if ranked else col1["cfg_over"]
        final = {"cid": (best[0] if best else col1["cid"]) + ("+" + variant[0] if variant else ""), "cfg_over": {**bestcfg, **(variant[1]["cfg_over"] if variant else {})}}
        gkfin = {"cid": (gk_best or {"cid": "ref"})["cid"], "cfg_over": (gk_best or {"cfg_over": {"kick_c": 0, "knob": 1}})["cfg_over"]}
        # baselines: rank-1 of round 1 (already in selection_1a)
        out.update({"final": {"final": final, "final_gk": gkfin}, "stage2_go": go, "gate": gate, "variant_1b": variant[0] if variant else None,
                    "note": "B3 / none_B1 / kc2c selections are the rank-1 entries of selection_1a.json (1e reads them via --sel 1a:<arm>:<col|gk>:0)"})
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k in ("stage", "stage2_go", "gate")}))
    return 0


def do_report(a) -> int:
    rows = read_rows(a.dir)
    L = ["# Stage 1 report (DRAFT, tuning-only; not confirmatory)", f"{len(rows)} run rows read from {a.dir}", ""]
    g: dict = {}
    for r in rows:
        key = (r["stage"], r["cell"], r["arm"], r["cid"], r["cond"], r["mit"], r["share"], r["tile"])
        e = g.setdefault(key, [0, 0])
        e[0] += int(r["success"])
        e[1] += 1
    L += ["| stage | cell | arm | cid | cond | mit | share | tile | success | n | Wilson 95 % |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(g, key=lambda x: tuple(str(i) for i in x)):
        k, n = g[key]
        lo, hi = wilson(k, n)
        L.append("| " + " | ".join(str(x) for x in key) + f" | {k / n:.2f} | {n} | [{lo:.2f}, {hi:.2f}] |")
    for f in sorted(glob.glob(os.path.join(a.dir, "0.5*.json"))):
        d = json.loads(Path(f).read_text())
        L += ["", f"## R13 gate ({Path(f).name}): {'PASS' if d['pass'] else 'FAIL'} (smoke={d['smoke']})", f"rows: {d['rows']}"]
    for f in sorted(glob.glob(os.path.join(a.dir, "1c.fmc.*.json"))):
        d = json.loads(Path(f).read_text())
        L.append(f"- {Path(f).name}: mean error {d['mean']:.3f}, sd {d['sd']:.3f}, nonzero {d['frac_nonzero']:.3f}, neg/pos {d['frac_neg']:.3f}/{d['frac_pos']:.3f}")
    for f in sorted(glob.glob(os.path.join(a.dir, "selection_*.json"))):
        d = json.loads(Path(f).read_text())
        L += ["", f"## Selection {Path(f).name}", "```", json.dumps({k: v for k, v in d.items() if k != "arms"} if "arms" not in d else {k: {kk: vv[:2] if isinstance(vv, list) else None for kk, vv in v.items()} for k, v in d["arms"].items()}, indent=1)[:4000], "```"]
    Path(a.out).write_text("\n".join(L) + "\n")
    print(f"report: {len(g)} cells, {len(rows)} rows")
    return 0 if rows or a.allow_empty else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="mode", required=True)
    r = sp.add_parser("run")
    for n in ("id", "stage", "arm", "cid", "label", "family", "cell", "cond", "mit", "shares", "keys", "out"):
        r.add_argument("--" + n, required=True)
    r.add_argument("--seeds", type=int, required=True)
    r.add_argument("--k", type=float, default=1.0)
    r.add_argument("--tile", type=int, default=0)
    r.add_argument("--cfg", default="")
    r.add_argument("--sel", default="")
    r.add_argument("--sweeps", default="")
    r.add_argument("--tag", type=int, default=TUNE_TAG, help="Spec.tag: 10 = tuning (Stage 1), 11 = Stage 2 confirmatory")
    r.add_argument("--keep-sel", action="store_true")
    r.add_argument("--l0sigma", type=float, default=1.0, help="multiplier of the level-0 sigma(Vth) (C2C_ESTIMATE tail bracket: 1.0 = 0.15 V model, 1.33 = 0.20 V)")
    r.add_argument("--records", default="", help="directory: also dump the full run records (curve, snaps, price) for ETS evaluation")
    g = sp.add_parser("gate")
    g.add_argument("--id", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--family", default="")
    g.add_argument("--key", default="2101")
    g.add_argument("--tag", type=int, default=TUNE_TAG)
    s = sp.add_parser("select")
    s.add_argument("--stage", required=True)
    s.add_argument("--dir", required=True)
    s.add_argument("--out", required=True)
    p = sp.add_parser("report")
    p.add_argument("--dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--allow-empty", action="store_true")
    a = ap.parse_args(argv)
    return {"run": do_run, "gate": do_gate, "select": do_select, "report": do_report}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main())
