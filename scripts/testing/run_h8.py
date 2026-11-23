"""H8 runner: one job = one (phase, arm label, family, device condition) block of (instance, seed) runs -> one JSON of raw records.

Nothing is scored here. Condition 'ideal' = no variation and no mitigation (the machine on a perfect device); 'nominal' = every stochastic variation
term at x1 with the arm's chosen mitigation (plan_h8.ARMS[label].mit); 'vx<k>' / 'drift<d>' = the stress points (variation_v2.point), with an
explicit --mit and --c2c share. Run tokens: "instance/lo-hi" (seed range). A job is resumable (an existing output is skipped).

  python -I scripts/testing/run_h8.py --id ID --phase main --label ours_kc2_i11 --family p3n240 --cond nominal --mit wv+diff+cal \\
         --runs 1101/0-4,1102/0-4 --sweeps 150 --out sim/out/hw/h8 [--smoke]
  python -I scripts/testing/run_h8.py --smoke-h8 [--out DIR]     every job type once (1 sweep) under the real ids + the real report barrier
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[1] / "scripts" / "baselines"))
import plan as pl  # noqa: E402
import plan_h8 as p8  # noqa: E402
import h8_instances as h8i  # noqa: E402

REPO = p8.REPO


def kind_of(family: str) -> str:
    return "maxcut" if family == "maxcut" else "colouring"


def resolve_cfg(label: str, family: str) -> dict:
    """Config of an arm label: s2:<key> (Stage 2 tuned selection), bv2:<key> (BASELINES_V2 selection), kc2c (fairness-arm hook)."""
    kind = kind_of(family)
    if label.startswith("sw."):
        return {}
    src = p8.ARMS[label].cfg
    if src == "kc2c":
        c = p8.kc2c_cfg(kind)
        if c is None:
            raise SystemExit(f"REFUSED: the tuned ours.kc2c selection is not in the tree ({p8.KC2C_PENDING}); the fairness arm cannot run yet")
        return c
    tag, _, key = src.partition(":")
    path = REPO / (p8.TUNED_S2 if tag == "s2" else p8.TUNED_BV2)
    return json.loads(path.read_text())["tuned"][kind][key]


def inst_index(family: str, inst: str) -> int:
    if family == "maxcut":
        return p8.INST_BASE + int(inst[1:])
    if family in h8i.PLANTED:
        return p8.INST_BASE + int(inst) - p8.PLANTED_SEED0[3 if family.startswith("p3") else 4]
    return p8.INST_BASE + list(h8i.GRAPHS).index(inst)


def parse_runs(s: str) -> list[tuple[str, int]]:
    out = []
    for tok in s.split(","):
        inst, rr = tok.split("/")
        lo, hi = (int(v) for v in rr.split("-"))
        out += [(inst, r) for r in range(lo, hi + 1)]
    return out


def pert_of(cond: str) -> dict | None:
    import variation_v2 as v2
    if cond == "ideal":
        return None
    return v2.point("vx1" if cond == "nominal" else cond).as_dict()


def make_spec(a, inst: str, r: int) -> pl.Spec:
    if a.label.startswith("sw."):
        arm, cfg = a.label, ({"iters_per_vertex": int(a.sweeps) if a.phase != "ref" else p8.TABU_REF_IPV} if a.label == "sw.tabucol" else {})
    else:
        arm, cfg = p8.ARMS[a.label].arm, resolve_cfg(a.label, a.family)
    return pl.Spec(study="h8", phase=a.phase, family=a.family, instance=inst, r=r, arm=arm, cfg=cfg, sweeps=a.sweeps, pert=pert_of(a.cond),
                   inst_index=inst_index(a.family, inst), tag=p8.SEED_TAG)


def execute_one(spec: pl.Spec, a) -> dict:
    import machines as ma
    from cost_model import CostModel
    if spec.arm.startswith("b1y."):
        import b1_native as bn
        rec = bn.execute(spec)
        rec["spec"] = dataclasses.asdict(spec)
        return rec
    mit = None
    if a.cond != "ideal" and not spec.arm.startswith("sw.") and spec.arm.split(".")[0] != "b3":
        import variation_v2 as v2
        mit = v2.Mitigation.parse(a.mit)
    import variation_v2 as v2
    v2.OURS_TILE_ROWS = getattr(a, "ours_tile_rows", 0) or None
    with _c2c(a.c2c):
        rec = ma.execute(spec, CostModel(), mit)
    if mit is not None:
        import variation_v2 as v2
        mc = v2.mitigation_cost(rec, mit, CostModel())
        rec["mit_cost"] = {k: v for k, v in mc.items() if k != "items"}
        rec["mit"] = mit.label
    return rec


class _c2c:
    def __init__(self, share: float):
        import variation_v2 as v2
        self.cm = v2.c2c_share(share)

    def __enter__(self):
        return self.cm.__enter__()

    def __exit__(self, *e):
        return self.cm.__exit__(*e)


def git_head() -> dict:
    import subprocess

    def g(*x):
        return subprocess.run(["git", "-C", str(REPO), *x], capture_output=True, text=True).stdout.strip()
    return {"head": g("rev-parse", "HEAD"), "dirty": bool(g("status", "--porcelain", "--untracked-files=no"))}


def atomic_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":"), default=float))
    os.replace(tmp, path)


def run_job(a) -> int:
    out = Path(a.out) / "h8" / f"{a.id}.json"
    if out.exists():
        print(f"skip {a.id} (exists)")
        return 0
    t0 = time.time()
    recs = [execute_one(make_spec(a, inst, r), a) for inst, r in parse_runs(a.runs)]
    meta = {"label": a.label, "phase": a.phase, "family": a.family, "cond": a.cond, "mit": a.mit, "c2c": a.c2c, "sweeps": a.sweeps}
    atomic_json(out, {"id": a.id, "h8": meta, "args": {k: v for k, v in vars(a).items() if k not in ("smoke", "smoke_h8", "smoke_all", "tier", "with_kc2c")}, "git": git_head(),
                      "wall_s": round(time.time() - t0, 1), "records": recs})
    print(f"{a.id}: {len(recs)} runs, {time.time() - t0:.0f} s")
    return 0


def check_record(r: dict) -> list[str]:
    if r["desc"]["kind"] == "sw":
        return [] if math.isfinite(r["best_E"]) else ["bad software best_E"]
    bad = []
    if "price" in r:
        p = r["price"]
        if not all(math.isfinite(v) for v in (p["e_total"], p["time_ns"], p["a_total"])):
            bad.append("non-finite price")
        if abs(p["e_total"] - math.fsum(p["blocks"].values())) > 1e-9 * max(1.0, p["e_total"]):
            bad.append("blocks != total")
    if r.get("array_writes"):
        bad.append("array writes")
    if "curve" in r and len(r["curve"]) != len(r["curve_t"]):
        bad.append("curve")
    if r["spec"]["pert"] and r["desc"]["kind"] in ("ours", "b1") and "mit_cost" not in r:
        bad.append("mitigated record without mit_cost")
    return bad


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id")
    ap.add_argument("--phase", default="main")
    ap.add_argument("--label")
    ap.add_argument("--family")
    ap.add_argument("--cond", default="ideal")
    ap.add_argument("--mit", default="none")
    ap.add_argument("--c2c", type=float, default=p8.C2C_DEFAULT)
    ap.add_argument("--runs")
    ap.add_argument("--sweeps", type=float, default=pl.SWEEPS)
    ap.add_argument("--out", default=p8.OUT)
    ap.add_argument("--ours-tile-rows", type=int, default=0, help="R13: simulate ours as row tiles of this many rows (0 = legacy one column, H8)")
    ap.add_argument("--smoke", action="store_true", help="mark a smoke job (no effect on the computation; the record is a normal H8 record)")
    ap.add_argument("--smoke-h8", action="store_true")
    ap.add_argument("--tier", choices=("core", "full"), default="core", help="--smoke-h8: smoke only the job types of this tier")
    ap.add_argument("--with-kc2c", action="store_true", help="--smoke-h8: include the fairness-arm types (stub selection if the real one is absent)")
    ap.add_argument("--smoke-all", action="store_true", help="smoke gate: run every type even if its declared rss exceeds free memory (cloud)")
    return ap


def _rss_run(argv: list[str], timeout_s: int = 900) -> tuple[int, float, str]:
    """Run one job command as the dispatcher does (own process) and return (rc, peak RSS GB of that process, tail of its output)."""
    import subprocess
    import tempfile
    with tempfile.TemporaryFile("w+") as log:
        p = subprocess.Popen([sys.executable, "-I", str(HERE / "run_h8.py"), *argv], cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                             env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "NUMBA_CACHE_DIR": str(REPO / "sim/out/numba_cache"),
                                  "H8_KC2C_SMOKE_STUB": "1"})
        _, status, ru = os.wait4(p.pid, 0)
        rc = os.waitstatus_to_exitcode(status)
        log.seek(0)
        return rc, ru.ru_maxrss / 1048576.0, log.read()[-400:]


def mem_available_gb() -> float:
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable"):
            return int(ln.split()[1]) / 1048576.0
    return 0.0


def smoke_h8(out: Path, tier: str = "core", with_kc2c: bool = False) -> int:
    """Gate smoke of ONE tier (core gate: core job types only; full gate: full types): one job per distinct H8 job type (gen_jobs_h8.smoke_types(tier);
    the fairness arm only if its selection exists or --with-kc2c, then via a stub selection) run as its OWN
    process through its own smoke command, with peak RSS checked against the job's declared rss; then the REAL report barrier on the smoke dir.
    Fails on any bad record, missing/empty output, peak RSS above the declared value, or an empty report. A type whose declared rss does not fit
    in this machine's free memory is SKIPPED with a message (never silently); the cloud gate (128 GB) runs them all (--smoke-all)."""
    import shlex
    import gen_jobs_h8 as g8
    import evaluate_h8 as ev8
    import shutil
    p8.FORCE_KC2C = with_kc2c
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    fails, skipped, types = 0, [], g8.smoke_types(tier)
    avail = mem_available_gb()
    for j in types:
        if j.mode == "all":
            continue
        argv = shlex.split(j.smoke.replace("$PY -I scripts/testing/run_h8.py ", "", 1))
        argv[argv.index("--out") + 1] = str(out)
        name = f"{j.phase:5s} {j.cell.label:20s} {j.cell.family:9s} {j.cell.cond:9s} {j.cell.mit:16s}"
        if j.rss > avail - 1.5 and "--smoke-all" not in sys.argv:
            skipped.append(j.id)
            print(f"SMOKE-H8 {name} SKIP (declared {j.rss:.1f} GB > {avail - 1.5:.1f} GB free here)", flush=True)
            continue
        t0 = time.time()
        rc, peak, tail = _rss_run(argv)
        bad = []
        try:
            a = make_parser().parse_args(argv)
            doc = json.loads((out / "h8" / f"{a.id}.json").read_text())
            bad = [b for r in doc["records"] for b in check_record(r)] or ([] if doc["records"] else ["no records"])
        except Exception as e:                      # noqa: BLE001 - report every failing type, keep going
            bad = [f"{type(e).__name__}: {e} | rc={rc} {tail.strip()[-160:]}"]
        if rc != 0 and not bad:
            bad = [f"rc={rc}"]
        if peak > j.rss:
            bad.append(f"peak RSS {peak:.2f} GB > declared {j.rss:.1f} GB")
        fails += bool(bad)
        print(f"SMOKE-H8 {name} {'ok' if not bad else 'FAIL ' + ';'.join(bad)} rss {peak:.2f}/{j.rss:.1f} GB {time.time() - t0:.1f}s", flush=True)
    print(f"SMOKE-H8 tier {tier} job types: {len(types) - 1}, run: {len(types) - 1 - len(skipped)}, skipped for memory: {len(skipped)}, failures: {fails}")
    try:
        # the smoke jobs are one pair each: the barrier must still read every file (D7) and report non-empty tables
        rep = ev8.evaluate(str(out), B=20, smoke=True, sensitivities=False, tier=tier)
        assert rep["n_files_read"] == rep["n_files"] > 0, (rep["n_files_read"], rep["n_files"], rep["unread_files"][:5])
        assert any(rep["cells"].values()), "report_h8 produced no cell table (raw dir mismatch?)"
        md = ev8.markdown(rep)
        assert md.count("## ") >= 4, "report_h8 markdown is empty"
        (out / "h8_report_smoke.json").write_text(json.dumps(rep, indent=1, default=float))
        (out / "h8_report_smoke.md").write_text(md)
        print(f"SMOKE-H8 barrier report_h8: ok ({rep['n_files_read']} files read, non-empty)", flush=True)
    except Exception as e:                          # noqa: BLE001
        print(f"SMOKE-H8 barrier FAIL {type(e).__name__}: {e}", flush=True)
        fails += 1
    return 1 if fails else 0


def main() -> int:
    a = make_parser().parse_args()
    if a.smoke_h8:
        return smoke_h8(Path(a.out) if a.out != p8.OUT else REPO / "sim/out/hw/h8_smoke", a.tier, a.with_kc2c)
    return run_job(a)


if __name__ == "__main__":
    sys.exit(main())
