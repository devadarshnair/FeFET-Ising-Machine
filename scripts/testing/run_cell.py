"""Testing-phase runner: one job = one study/arm/family block of runs -> one JSON of raw per-run records.

A record carries the spec, the best-so-far curve, 40 cumulative counter snapshots (so energy at any step and every H3 cost-only
re-scale can be recomputed), the priced totals at the nominal cost table, programming cost, area, restarts, array writes and (H5)
the false-stall counts. Nothing is scored here: no target, no contrast, no verdict (evaluate_h2/h3/h5.py do that, later).

Run tokens: "cfg/instance/rlo-rhi" (cfg = a grid id, @default, @tuned (tuned.json), @frozen (frozen.json)); a job is resumable
(an existing output is skipped). Usage:
  python -I scripts/testing/run_cell.py --id ID --study h2 --phase test --arm ours.kc2.i7i10 --family maxcut \\
         --runs @tuned/G1/0-9,@tuned/G2/0-9 --out sim/out/hw/stage2 [--sweeps S] [--proposals L] [--sigma M --adc D] [--point PID]
  python -I scripts/testing/run_cell.py --smoke [--out DIR]       every job type once, 1 sweep, no data kept in the repo
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan as pl  # noqa: E402
import machines as ma  # noqa: E402

REPO = ma.REPO
POWER_FOR_TUNED = {"i7": "i7i10", "off": "i10"}      # frozen-config sims reuse the config tuned on the H2 simulation arm


def git_head() -> dict:
    def g(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout.strip()
    return {"head": g("rev-parse", "HEAD"), "dirty": bool(g("status", "--porcelain", "--untracked-files=no"))}


def tuned_key(arm: str, proposals: int = 0) -> str:
    a = pl.Arm.parse(arm)
    if a.tweak == "sm":                                     # T7 sign-magnitude extra arm reuses the Kc2 config tuned on the base arm
        a = dataclasses.replace(a, tweak="")
    if a.machine == "ours" and a.power in POWER_FOR_TUNED:
        a = dataclasses.replace(a, power=POWER_FOR_TUNED[a.power])
    k = a.key
    return f"{k}@{proposals}" if a.machine == "b2" else k


def find_config(arm: str, cid: str) -> dict:
    a = pl.Arm.parse(arm)
    kind = "b3" if a.machine == "b3" else "b2" if a.machine == "b2" else a.restart
    return next(c for c in pl.grid(kind) if c.cid == cid).as_dict()


def resolve_cfg(cid: str, arm: str, family: str, proposals: int, tuned: dict | None, frozen_cfg: dict | None) -> dict:
    a = pl.Arm.parse(arm)
    if cid == "@default":
        return pl.default_config(a.restart).as_dict()
    if cid == "@tuned":
        if tuned is None:                                   # smoke only: first grid point stands in
            return find_config(arm, pl.grid("b3" if a.machine == "b3" else "b2" if a.machine == "b2" else a.restart)[0].cid)
        return tuned["tuned"][family][tuned_key(arm, proposals)]
    if cid == "@frozen":
        return frozen_cfg
    return find_config(arm, cid)


def parse_runs(s: str) -> list[tuple[str, str, int]]:
    out = []
    for tok in s.split(","):
        cid, inst, rr = tok.split("/")
        lo, hi = (int(v) for v in rr.split("-"))
        out += [(cid, inst, r) for r in range(lo, hi + 1)]
    return out


def inst_index(family: str, inst: str) -> int:
    if inst in pl.TEST_SET[family]:
        return pl.TEST_SET[family].index(inst)
    return 100 + pl.TUNE_SET[family].index(inst)


def h6_cfg(src: str, family: str, out: Path) -> dict:
    """H6 config sources (plan_h6): tuned:<arm key> (Stage 2 tuned.json; col3p/col4p use the colouring entry), sweep:<arm> (the
    H6 restart-sweep selection, h6_sweep.json written by the select barrier), b1mesa_epoch, grid:<restart>:<cid> (sweep grid)."""
    import plan_h6 as p6
    t2 = json.loads((REPO / p6.TUNED_STAGE2).read_text())["tuned"]
    fam2 = "colouring" if family.startswith("col") else family
    kind, _, rest = src.partition(":")
    if kind == "tuned":
        return t2[fam2][rest]
    if kind == "b1mesa_epoch":
        return dict(t2[fam2]["b1.mesa"], cid=f"b1mesa_epoch_K{p6.B1_MESA_EPOCH_KNOB:g}", knob=p6.B1_MESA_EPOCH_KNOB, epoch_sweeps=p6.EPOCH_SWEEPS)
    if kind == "grid":
        arm, cid = rest.split("@")
        return next(c for c in p6.sweep_configs(pl.Arm.parse(arm).restart, t2[fam2][p6.SWEEP_BASE[arm]]) if c["cid"] == cid)
    if kind == "sweep":
        sel = out / "h6_sweep.json"
        if not sel.exists():
            raise SystemExit(f"REFUSED: {sel} missing (run the select_h6 barrier first)")
        return json.loads(sel.read_text())["selected"][family][rest]
    raise ValueError(src)


def h7_cfg(src: str) -> dict:
    """H7 config sources (plan_h7): tuned:<Stage 2 colouring arm key>, b1mesa_epoch (Stage 3 B1_mesa_epoch), sw:<algo>[:<iters/vertex>]."""
    import plan_h7 as p7
    kind, _, rest = src.partition(":")
    if kind == "sw":
        return p7.sw_cfg(src)
    t2 = json.loads((REPO / p7.TUNED_STAGE2).read_text())["tuned"]["colouring"]
    if kind == "tuned":
        return t2[rest]
    if kind == "b1mesa_epoch":
        return dict(t2["b1.mesa"], cid=f"b1mesa_epoch_K{p7.B1_MESA_EPOCH_KNOB:g}", knob=p7.B1_MESA_EPOCH_KNOB, epoch_sweeps=p7.EPOCH_SWEEPS)
    raise ValueError(src)


def build_specs(a, tuned: dict | None, frozen: dict | None) -> list[pl.Spec]:
    specs = []
    if getattr(a, "h7_cfg", ""):
        import plan_h7 as p7
        pert = next(p for p in pl.H5_POINTS if p.pid == a.point).as_dict() if a.point else None
        cfg = h7_cfg(a.h7_cfg)
        for _, inst, r in parse_runs(a.runs):
            specs.append(pl.Spec(study=a.study, phase=a.phase, family=a.family, instance=inst, r=r, arm=a.arm, cfg=cfg,
                                 sweeps=a.sweeps, pert=pert, inst_index=p7.inst_index(a.family, inst), tag=p7.SEED_TAG))
        return specs
    if getattr(a, "h6_cfg", ""):
        import plan_h6 as p6
        pert = next(p for p in pl.H5_POINTS if p.pid == a.point).as_dict() if a.point else None
        for _, inst, r in parse_runs(a.runs):
            cfg = h6_cfg(a.h6_cfg, a.family, Path(a.out))
            specs.append(pl.Spec(study=a.study, phase=a.phase, family=a.family, instance=inst, r=r, arm=a.arm, cfg=cfg,
                                 sweeps=a.sweeps, pert=pert, proposals=a.proposals,
                                 inst_index=p6.inst_index(a.family, inst) if a.family != "qkp" else 0, tag=p6.SEED_TAG))
        return specs
    arm = a.arm
    frozen_cfg = None
    if arm in ("@ours_best", "@b1_tuned"):
        f = frozen[a.family][arm[1:]]
        arm, frozen_cfg = f["arm"], f["cfg"]
    pert = next(p for p in pl.H5_POINTS if p.pid == a.point).as_dict() if a.point else None
    for cid, inst, r in parse_runs(a.runs):
        cfg = resolve_cfg(cid, arm, a.family, a.proposals, tuned, frozen_cfg)
        specs.append(pl.Spec(study=a.study, phase=a.phase, family=a.family, instance=inst, r=r, arm=arm, cfg=cfg,
                             sweeps=a.sweeps, sigma_mult=a.sigma, adc_delta=a.adc, pert=pert, proposals=a.proposals,
                             inst_index=inst_index(a.family, inst) if a.family != "qkp" else 0,
                             tag=1 if a.phase == "ref" else 0))
    return specs


def atomic_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    os.replace(tmp, path)


def run_job(a, tuned, frozen) -> int:
    out = Path(a.out) / a.study / f"{a.id}.json"
    if out.exists():
        print(f"skip {a.id} (exists)")
        return 0
    if a.phase == "h3" and frozen is not None and not frozen.get("gate_pass", False):
        atomic_json(out, {"id": a.id, "skipped": "H3 is not run: the H2 gate did not pass (frozen.json gate_pass false)"})
        print(f"{a.id}: H3 skipped (H2 gate not passed)")
        return 0
    pt = next((p for p in pl.H5_POINTS if p.pid == a.point), None) if a.point else None
    if pt is not None and not pt.evaluable:
        atomic_json(out, {"id": a.id, "point": pt.pid, "not_evaluable": pl.CORNER_REASON, "records": []})
        print(f"{a.id}: point {pt.pid} not evaluable ({pl.CORNER_REASON})")
        return 0
    cost = ma.CostModel()
    t0 = time.time()
    recs = [ma.execute(s, cost) for s in build_specs(a, tuned, frozen)]
    atomic_json(out, {"id": a.id, "args": {k: v for k, v in vars(a).items() if k not in ("smoke",)}, "git": git_head(),
                      "wall_s": round(time.time() - t0, 1), "records": recs})
    print(f"{a.id}: {len(recs)} runs, {time.time() - t0:.0f} s")
    return 0


def check_record(r: dict) -> list[str]:
    bad = []
    if not all(math.isfinite(v) for v in (r["price"]["e_total"], r["price"]["time_ns"], r["price"]["a_total"])):
        bad.append("non-finite price")
    if abs(r["price"]["e_total"] - math.fsum(r["price"]["blocks"].values())) > 1e-9 * max(1.0, r["price"]["e_total"]):
        bad.append("blocks != total")
    if r["array_writes"]:
        bad.append("array writes")
    if "curve" in r and len(r["curve"]) != len(r["curve_t"]):
        bad.append("curve")
    return bad


def smoke(out: Path) -> int:
    import gen_jobs_stage2 as gj
    types = gj.smoke_types()
    fails = 0
    for t in types:
        j = t["job"]
        argv = ["--id", "smoke_" + j.id, "--study", j.study, "--phase", j.phase, "--arm", j.arm, "--family", j.family,
                "--runs", t["first_run"], "--out", str(out)]
        extra = j.extra.split()
        if "--sweeps" in extra:
            extra[extra.index("--sweeps") + 1] = "1"
        argv += extra + ([] if "--sweeps" in extra else ["--sweeps", "1"])
        if "--proposals" in extra:
            argv[argv.index("--proposals") + 1] = "1000"
        a = make_parser().parse_args(argv)
        frozen = {a.family: {"ours_best": {"arm": "ours.kc2.i7i10", "cfg": pl.default_config("kc2").as_dict()},
                             "b1_tuned": {"arm": "b1.mesa", "cfg": pl.default_config("mesa").as_dict()}}, "gate_pass": True}
        t0 = time.time()
        try:
            run_job(a, None, frozen)
            doc = json.loads((out / a.study / f"smoke_{j.id}.json").read_text())
            bad = [b for r in doc.get("records", []) for b in check_record(r)]
            if not doc.get("records") and not doc.get("not_evaluable") and not doc.get("skipped"):
                bad.append("no records")
        except Exception as e:                      # noqa: BLE001 - report every failing job type, keep going
            bad = [f"{type(e).__name__}: {e}"]
        fails += bool(bad)
        print(f"SMOKE {j.phase:5s} {j.arm:22s} {j.family:9s} {j.extra[:28]:28s} {'ok' if not bad else 'FAIL ' + ';'.join(bad)} "
              f"{time.time() - t0:.1f}s", flush=True)
    print(f"SMOKE job types: {len(types)}, failures: {fails}")
    return 1 if fails else 0


def smoke_h6(out: Path) -> int:
    """Stage 3 gate smoke: one job per distinct H6 job type at 1 sweep (proposals 1000), a dummy h6_sweep.json (first grid point)."""
    import gen_jobs_stage3 as g3
    import plan_h6 as p6
    t2 = json.loads((REPO / p6.TUNED_STAGE2).read_text())["tuned"]
    sel = {f: {arm: p6.sweep_configs(pl.Arm.parse(arm).restart, t2["colouring" if f.startswith("col") else f][p6.SWEEP_BASE[arm]])[0]
               for arm in p6.SWEEP_ARMS} for f in p6.FAMILIES}
    out.mkdir(parents=True, exist_ok=True)
    (out / "h6_sweep.json").write_text(json.dumps({"selected": sel, "smoke": True}))
    fails, types = 0, g3.smoke_types()
    for j in types:
        argv = j.command_argv()
        argv[argv.index("--out") + 1] = str(out)
        argv[argv.index("--id") + 1] = "smoke_" + j.id
        cid, inst, rr = j.runs[0].split("/")
        lo = rr.split("-")[0]
        argv[argv.index("--runs") + 1] = f"{cid}/{inst}/{lo}-{lo}"
        if "--sweeps" in argv:
            argv[argv.index("--sweeps") + 1] = "1"
        else:
            argv += ["--sweeps", "1"]
        if "--proposals" in argv:
            argv[argv.index("--proposals") + 1] = "1000"
        a = make_parser().parse_args(argv)
        t0 = time.time()
        try:
            run_job(a, None, None)
            doc = json.loads((out / a.study / f"smoke_{j.id}.json").read_text())
            bad = [b for r in doc.get("records", []) for b in check_record(r)] or ([] if doc.get("records") else ["no records"])
        except Exception as e:                      # noqa: BLE001
            bad = [f"{type(e).__name__}: {e}"]
        fails += bool(bad)
        print(f"SMOKE-H6 {j.phase:6s} {j.arm:24s} {j.family:7s} {j.extra[:40]:40s} {'ok' if not bad else 'FAIL ' + ';'.join(bad)} "
              f"{time.time() - t0:.1f}s", flush=True)
    print(f"SMOKE-H6 job types: {len(types)}, failures: {fails}")
    fails += smoke_h6_barriers(out)
    return 1 if fails else 0


def check_any(r: dict) -> list[str]:
    if r["desc"]["kind"] == "sw":
        return [] if math.isfinite(r["best_E"]) and r["best_E"] >= 0 else ["bad software best_E"]
    return check_record(r)


def smoke_h7(out: Path) -> int:
    """Stage 4 gate smoke: one job per distinct H7 job type at 1 sweep (software: tiny budgets), under the REAL job ids, then the real
    report_h7 barrier command with its raw dir pointed at the smoke dir. Fails if the barrier writes an empty report."""
    import shlex
    import gen_jobs_stage4 as g4
    import evaluate_h7 as ev7
    out.mkdir(parents=True, exist_ok=True)
    fails, types = 0, g4.smoke_types()
    for j in types:
        argv = j.command_argv()
        argv[argv.index("--out") + 1] = str(out)
        cid, inst, rr = j.runs[0].split("/")
        lo = rr.split("-")[0]
        argv[argv.index("--runs") + 1] = f"{cid}/{inst}/{lo}-{lo}"
        argv += ["--sweeps", "1"]
        if "sw:tabucol" in j.extra:
            argv[argv.index("--h7-cfg") + 1] = "sw:tabucol:1"
        a = make_parser().parse_args(argv)
        t0 = time.time()
        try:
            run_job(a, None, None)
            doc = json.loads((out / a.study / f"{j.id}.json").read_text())
            bad = [b for r in doc.get("records", []) for b in check_any(r)] or ([] if doc.get("records") else ["no records"])
        except Exception as e:                      # noqa: BLE001
            bad = [f"{type(e).__name__}: {e}"]
        fails += bool(bad)
        print(f"SMOKE-H7 {j.phase:5s} {j.arm:18s} {j.family:7s} {j.extra[:44]:44s} {'ok' if not bad else 'FAIL ' + ';'.join(bad)} "
              f"{time.time() - t0:.1f}s", flush=True)
    print(f"SMOKE-H7 job types: {len(types)}, failures: {fails}")
    try:
        bar = next(j for j in g4.all_jobs() if j.mode == "all")
        cmd = shlex.split(bar.command().replace("$PY ", "", 1).replace(g4.OUT, str(out)))
        assert cmd[:2] == ["-I", "scripts/testing/evaluate_h7.py"], cmd
        assert ev7.main([*cmd[2:], "--boot", "20"]) == 0
        rep_path = Path(cmd[cmd.index("--out") + 1])
        rep = json.loads(rep_path.read_text())
        assert any(rep["families"].values()), "report_h7 produced no family table (raw dir mismatch?)"
        assert rep_path.with_suffix(".md").read_text().count("## ") >= 3, "report_h7 markdown is empty"
        print("SMOKE-H7 barrier report_h7: ok (non-empty report)", flush=True)
    except Exception as e:                      # noqa: BLE001
        print(f"SMOKE-H7 barrier FAIL {type(e).__name__}: {e}", flush=True)
        fails += 1
    return 1 if fails else 0


def smoke_h6_barriers(out: Path) -> int:
    """Run the select_h6 and report_h6 barriers (evaluate_h6) end to end on the smoke records, renamed to the job ids they expect.
    Returns 1 on any exception, so a broken barrier stops the gate instead of stopping Stage 3 after the compute is done."""
    import shutil
    import evaluate_h6 as ev6
    bar = out / "barrier"
    shutil.rmtree(bar, ignore_errors=True)
    for study in ("h6", "h6h5"):
        (bar / study).mkdir(parents=True)
        for f in sorted((out / study).glob("smoke_*.json")):
            if "_h6_sweep" not in f.name:
                shutil.copy(f, bar / study / f.name.removeprefix("smoke_"))
    try:
        sel = ev6.select(str(bar))
        assert sel["selected"], "select_h6 produced no selection"
        (bar / "h6_sweep.json").write_text(json.dumps(sel, default=float))
        rep = ev6.evaluate(str(bar), B=20)
        assert rep["h5"], "report_h6 produced no H5 table"
        ev6.markdown(rep)
        print("SMOKE-H6 barriers select_h6 / report_h6: ok", flush=True)
        return 0
    except Exception as e:                      # noqa: BLE001
        print(f"SMOKE-H6 barriers FAIL {type(e).__name__}: {e}", flush=True)
        return 1


def make_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id")
    ap.add_argument("--study", default="h2")
    ap.add_argument("--phase", default="test")
    ap.add_argument("--arm")
    ap.add_argument("--family")
    ap.add_argument("--runs")
    ap.add_argument("--out", default="sim/out/hw/stage2")
    ap.add_argument("--sweeps", type=float, default=pl.SWEEPS)
    ap.add_argument("--proposals", type=int, default=0)
    ap.add_argument("--sigma", type=float, default=0.0)
    ap.add_argument("--adc", type=int, default=0)
    ap.add_argument("--point", default="")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--h6-cfg", default="", help="H6 config source (plan_h6); makes the job an H6 job (seed tag 6)")
    ap.add_argument("--smoke-h6", action="store_true", help="every Stage 3 (H6) job type once, 1 sweep")
    ap.add_argument("--h7-cfg", default="", help="H7 config source (plan_h7); makes the job an H7 job (seed tag 7)")
    ap.add_argument("--smoke-h7", action="store_true", help="every Stage 4 (H7) job type once, 1 sweep, + report barrier")
    ap.add_argument("--smoke-h8", action="store_true", help="every H8 (full study) job type once, 1 sweep, + report barrier (delegates to run_h8.py)")
    return ap


def main() -> int:
    a = make_parser().parse_args()
    root = Path(a.out)
    if a.smoke_h8:
        import run_h8
        return run_h8.smoke_h8(Path(a.out) if a.out != "sim/out/hw/stage2" else REPO / "sim/out/hw/h8_smoke")
    if a.smoke_h7:
        return smoke_h7(Path(a.out) if a.out != "sim/out/hw/stage2" else REPO / "sim/out/hw/stage4_smoke")
    if a.smoke_h6:
        return smoke_h6(Path(a.out) if a.out != "sim/out/hw/stage2" else REPO / "sim/out/hw/stage3_smoke")
    if a.smoke:
        return smoke(Path(a.out) if a.out != "sim/out/hw/stage2" else REPO / "sim/out/hw/stage2_smoke")
    tuned = json.loads((root / "tuned.json").read_text()) if (root / "tuned.json").exists() else None
    frozen = json.loads((root / "frozen.json").read_text()) if (root / "frozen.json").exists() else None
    if a.phase == "test" and a.runs and "@tuned" in a.runs and tuned is None:
        print("REFUSED: tuned.json missing (run select_tuned first)")
        return 2
    return run_job(a, tuned, frozen)


if __name__ == "__main__":
    sys.exit(main())
