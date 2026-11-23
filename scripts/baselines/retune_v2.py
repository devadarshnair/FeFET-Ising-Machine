"""P4_v2 R5 (equal-rule re-tuning of b3.b3v2 and b1.mesa2) and R6 (Stage 4 240-spin colouring TEST re-run of those arms).
prereg/calib/P4_v2_reproduction.md sections 5, R5, R6.

  retune_v2.py tune  [--chunk i/k]   8 configs x Stage 2 TUNE_SET x TUNE_SEEDS per (arm, family); records in the Stage 2 format
  retune_v2.py select                 select_tuned rule; E_ref = best over ALL Stage 2 tuning runs of the instance + these runs
  retune_v2.py test  [--chunk i/k]   p3n240 / p4n240 TEST, Stage 4 seeds, with the R5 colouring selection
  retune_v2.py eval                   RESULT P4v2 R6 + success table vs the frozen Stage 4 records
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts" / "testing"))
sys.path.insert(0, str(REPO))
import plan as pl  # noqa: E402
import plan_h7 as p7  # noqa: E402
import repro_v2 as rv  # noqa: E402

OUT = REPO / "sim/out/hw/baselines_v2"
STAGE2_RAW = REPO / "sim/out/hw/stage2"
STAGE4_RAW = REPO / "sim/out/hw/stage4"
ARMS = ("b3.b3v2", "b1.mesa2")                       # first offload (pinned da4e16c): job lists of these two arms must not move
FAITHFUL = ("b1y.sa", "b1y.mesa")                    # B1_yin (b1_native.py), added by P4_v2 amendment 1
FAIR = ("ours.kc2c",)                               # review fix: ours Kc2 with B3 v2's T_final knob (K fixed at Stage 2's 2n)
ALL_ARMS = ARMS + FAITHFUL + FAIR
TUNE_KEY = {"ours.kc2c": "ours.kc2.i10"}             # spec arm used in tuning (Stage 2 power mode); test runs the H7 fs key
R6_FAMILIES = ("p3n240", "p4n240")
BIG_FAMILIES = ("p3n480", "p4n480", "dimacs")         # cloud job C-R6-480 (BASELINES_V2 section 5)
H7_KEY = {"b3.b3v2": "b3.b3v2", "b1.mesa2": "b1.mesa2.fs", "b1y.sa": "b1y.sa", "b1y.mesa": "b1y.mesa", "ours.kc2c": "ours.kc2.fs"}


def configs(arm: str) -> list[dict]:
    if arm == "ours.kc2c":                           # 4 shared pairs x T_final in {T_end, T_end^2/T_start}; K = 2n (Stage 2 colouring)
        return [dict(cid=f"kc2c_p{hi}_{lo}_t{t:g}", pct_hi=hi, pct_lo=lo, knob=2.0, tfinal=float(t), sched="", pswap=0)
                for hi, lo in pl.PCT_PAIRS for t in (1.0, 0.5)]
    if arm.startswith("b1y."):
        import b1_native as bn
        return bn.grid(arm.split(".")[1])
    return [c.as_dict() for c in pl.grid(pl.Arm.parse(arm).restart)]


def tune_jobs(arms=ARMS) -> list[tuple]:
    return [(a, f, c["cid"]) for a in arms for f in pl.FAMILIES for c in configs(a)]


def test_jobs(arms=ARMS, families=R6_FAMILIES, per_seed=False) -> list[tuple]:
    out = []
    for a in arms:
        for f in families:
            for i in p7.TEST_SET[f]:
                if per_seed:
                    out += [(a, f, i, r) for r in range(p7.test_seeds(f))]
                else:
                    out.append((a, f, i))
    return out


def _execute(spec):
    if spec.arm.startswith("b1y."):
        import b1_native as bn
        return bn.execute(spec)
    import machines as M
    from cost_model import CostModel
    return M.execute(spec, CostModel())


def _inst_index(family, inst):
    import run_cell as rc
    return rc.inst_index(family, inst)


def run_tune_job(job) -> list[dict]:
    arm, fam, cid = job
    cfg = next(c for c in configs(arm) if c["cid"] == cid)
    recs = []
    for inst in pl.TUNE_SET[fam]:
        for r in range(pl.TUNE_SEEDS):
            spec = pl.Spec(study="h2", phase="tune", family=fam, instance=inst, r=r, arm=TUNE_KEY.get(arm, arm), cfg=cfg, sweeps=pl.SWEEPS,
                           inst_index=_inst_index(fam, inst), tag=0)
            recs.append(_execute(spec))
    return recs


def run_test_job(job, tuned: dict) -> list[dict]:
    arm, fam, inst = job[:3]
    cfg = tuned["colouring"][TUNE_KEY.get(arm, arm)]
    seeds = [job[3]] if len(job) > 3 else range(p7.test_seeds(fam))
    sweeps = p7.sweeps_of(fam, inst) if fam == "dimacs" else p7.sweeps_of(fam)
    recs = []
    for r in seeds:
        spec = pl.Spec(study="h7", phase="test", family=fam, instance=inst, r=r, arm=H7_KEY[arm], cfg=cfg,
                       sweeps=sweeps, inst_index=p7.inst_index(fam, inst), tag=p7.SEED_TAG)
        recs.append(_execute(spec))
    return recs


def _path(kind: str, job) -> Path:
    return OUT / kind / "h2" / ("_".join(map(str, job)) + ".json") if kind == "tune" else \
        OUT / kind / "h7" / ("_".join(map(str, job)) + ".json")


def run(kind: str, chunk: str, arms=ARMS, families=R6_FAMILIES, per_seed=False, smoke=False) -> int:
    sha = rv.prereg_sha()
    i, k = map(int, chunk.split("/"))
    js = tune_jobs(arms) if kind == "tune" else test_jobs(arms, families, per_seed)
    tp = OUT / "tune" / "tuned.json"
    tuned = json.loads(tp.read_text())["tuned"] if kind == "test" and tp.exists() else None
    if kind == "test" and tuned is None and not smoke:
        raise SystemExit(f"{tp} missing: run select first")
    if smoke:                                         # one job, 1-sweep budget, separate dir, never scored
        return smoke_one(kind, js[i - 1], tuned)
    for idx, j in enumerate(js):
        if idx % k != i - 1:
            continue
        p = _path(kind, j)
        if p.exists():
            continue
        t0 = time.time()
        recs = run_tune_job(j) if kind == "tune" else run_test_job(j, tuned)
        rv._write(p, {"records": recs, "prereg_sha256": sha, "wall_s": round(time.time() - t0, 1)})
        print(f"done {p.name} {time.time() - t0:.0f} s", flush=True)
    return 0


def select() -> dict:
    import evalcommon as ev
    import evaluate_h2 as e2
    old = ev.load_records(STAGE2_RAW, "h2", "tune")
    new = ev.load_records(OUT / "tune", "h2", "tune")
    for arm in sorted({r["spec"]["arm"] for r in new}):
        got = sum(r["spec"]["arm"] == arm for r in new)
        src = {v: k for k, v in TUNE_KEY.items()}.get(arm, arm)
        assert got == len(tune_jobs((src,))) * 4 * pl.TUNE_SEEDS, f"tuning of {arm} incomplete: {got} records"
    ref = e2._tune_ref(old + new)
    table: dict = {}
    for r in new:
        s = r["spec"]
        gap = ev.gap_of(np.array([r["best_E"]]), ref[(s["family"], s["instance"])])[0]
        table.setdefault(s["family"], {}).setdefault(s["arm"], {}).setdefault(s["cfg"]["cid"], []).append(
            (gap, r["price"]["e_total"], s["cfg"]))
    tuned, tt = {}, {}
    for fam, arms in table.items():
        for key, cfgs in arms.items():
            rows = {cid: (float(np.mean([g for g, _, _ in v])), float(np.mean([e for _, e, _ in v])), v[0][2]) for cid, v in cfgs.items()}
            assert len(rows) == 8
            best = min(rows, key=lambda c: (round(rows[c][0], 12), rows[c][1]))
            tuned.setdefault(fam, {})[key] = rows[best][2]
            tt.setdefault(fam, {})[key] = {cid: [g, e] for cid, (g, e, _) in rows.items()} | {"_selected": best}
    out = {"tuned": tuned, "tune_table": tt, "rule": "P4_v2 s.5: 8 configs, Stage 2 TUNE_SET, TUNE_SEEDS, select_tuned rule; "
           "E_ref over Stage 2 + P4_v2 tuning runs", "prereg_sha256": rv.prereg_sha()}
    (OUT / "tune" / "tuned.json").write_text(json.dumps(out, indent=1))
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def stage4_success(label: str, fam: str) -> float | None:
    import glob
    vals = []
    for f in glob.glob(str(STAGE4_RAW / "h7" / f"x7_{label}_{fam}_*.json")):
        vals += [r["best_E"] <= 0 for r in json.loads(Path(f).read_text())["records"]]
    return float(np.mean(vals)) if vals else None


def evaluate() -> dict:
    import evalcommon as ev
    recs = ev.load_records(OUT / "test", "h7", "test")
    res = {}
    fams = sorted({r["spec"]["family"] for r in recs})
    for arm in ALL_ARMS:
        for fam in fams:
            rs = [r for r in recs if r["spec"]["arm"] == H7_KEY[arm] and r["spec"]["family"] == fam]
            k = sum(r["best_E"] <= 0 for r in rs)
            res[f"{arm}@{fam}"] = dict(n=len(rs), success=k / len(rs) if rs else None, wilson95=wilson(k, len(rs)),
                                       mean_conflicts=float(np.mean([r["best_E"] for r in rs])) if rs else None)
    for lab in ("ours_kc2_i11", "ours_none", "B1_best", "B1_mesa_epoch", "B3"):
        for fam in fams:
            res[f"stage4:{lab}@{fam}"] = stage4_success(lab, fam)
    complete = all(res[f"b3.b3v2@{f}"]["n"] == p7.test_seeds(f) * len(p7.TEST_SET[f]) for f in R6_FAMILIES)
    ok = any((res[f"b3.b3v2@{f}"]["success"] or 0) >= 0.10 and res[f"b3.b3v2@{f}"]["wilson95"][0] > 0 for f in R6_FAMILIES)
    v = ("PASS" if ok else "FAIL") if complete else "INCOMPLETE"
    print(f"RESULT P4v2 R6 {v} prereg_sha256={rv.prereg_sha()[:16]}", flush=True)
    res["verdict"] = v
    (OUT / "r6_result.json").write_text(json.dumps(res, indent=1, default=float))
    return res


def smoke_one(kind: str, job, tuned) -> int:
    """Executes one job at a 1-sweep budget into sim/out/hw/baselines_v2/smoke/ (checks imports, configs, record format)."""
    import evalcommon as ev
    arm, fam = job[0], job[1]
    if kind == "tune":
        cfg = next(c for c in configs(arm) if c["cid"] == job[2])
    else:
        cfg = (tuned or {}).get("colouring", {}).get(TUNE_KEY.get(arm, arm)) or configs(arm)[0]
    inst = pl.TUNE_SET[fam][0] if kind == "tune" else job[2]
    spec = pl.Spec(study="h7", phase="smoke", family=fam, instance=inst, r=0, arm=H7_KEY[arm], cfg=cfg, sweeps=1,
                   inst_index=_inst_index(fam, inst) if kind == "tune" else p7.inst_index(fam, inst), tag=p7.SEED_TAG)
    rec = _execute(spec)
    ra = ev.run_arrays(rec, __import__("cost_model").CostModel())
    assert len(rec["curve"]) == len(rec["curve_t"]) and math.isfinite(ra.e_total) and ra.e_total > 0
    rv._write(OUT / "smoke" / ("_".join(map(str, job)) + ".json"), {"records": [rec]})
    print(f"SMOKE ok {kind} {job} best_E={rec['best_E']} e_total={ra.e_total:.3g}", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("tune", "select", "test", "eval"))
    ap.add_argument("--chunk", default="1/1")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--families", default=",".join(R6_FAMILIES))
    ap.add_argument("--per-seed", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="run job number i of --chunk i/k at 1 sweep (not scored)")
    a = ap.parse_args(argv)
    if a.cmd in ("tune", "test"):
        return run(a.cmd, a.chunk, tuple(a.arms.split(",")), tuple(a.families.split(",")), a.per_seed, a.smoke)
    if a.cmd == "select":
        print(json.dumps(select()["tuned"], indent=1))
        return 0
    evaluate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
