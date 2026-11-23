"""P4.04: B3 (Fujitsu DA) calibration against Aramon et al. 2019. Registered in prereg/calib/P4.04.md.

Usage: calib_b3.py --prereg prereg/calib/P4.04.md [--jobs J] [--attempt 1|2] [--smoke]
Jobs = (class, n, instance, arm, attempt); each runs all its runs and writes sim/out/calib_b3/runs/<job>.json
(resumable). Then the evaluator prints RESULT lines (SMOKE lines with --smoke: tiny budget, separate dir, not scored).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fujitsu_da as da  # noqa: E402
from instances import mix_seed, qubo_instance  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "sim/out/calib_b3"
CLASSES = ("bimodal", "gaussian")
SIZES = (64, 128, 256)
INSTANCES = 20
RUNS = {1: 50, 2: 25}
ITER_PER_N = {1: 400, 2: 1000}
ARMS = {1: ("off", "on"), 2: ("off",)}
BETA_PAPER = {"bimodal": 0.0021, "gaussian": 0.0019}
WINDOW_FRAC = 0.10
BOOT = 2000
SMOKE = dict(sizes=(16, 32), instances=2, runs=3, iter_per_n=40)


def offset_rate(t_low: float, arm: str) -> int:
    return 0 if arm == "off" else max(1, round(t_low / 4))


def build(kind: str, n: int, i: int):
    d, P = da.sk_qubo(n, i, kind)
    t_low, t_high = da.dE_percentiles(d, P, seed=mix_seed(20261116, CLASSES.index(kind), n, i))
    return d, P, t_low, t_high


def run_job(job) -> str:
    kind, n, i, arm, attempt, runs, iters, out = job
    path = Path(out) / "runs" / f"{kind}_{n}_{i}_{arm}_a{attempt}.json"
    if path.exists():
        return "skip"
    t0 = time.time()
    d, P, t_low, t_high = build(kind, n, i)
    cfg = da.B3Cfg(offset_rate=offset_rate(t_low, arm), schedule="lin_beta", t_high=t_high, t_low=t_low)
    bests, boosts, hit_step = [], [], []
    for r in range(runs):
        seed = mix_seed(20261116, CLASSES.index(kind), n, i, r + (1000 if attempt == 2 else 0))
        inst = qubo_instance(d, P, seed=seed, steps=iters, t_start=t_high, t_end=None, deoff=0)
        m = da.b3_machine(inst, cfg, counters=False)
        m.window = (int(iters * (1 - WINDOW_FRAC)), 0, 0)
        m.run(keep_trace=False)
        bests.append(int(m.best_f))
        hit_step.append(int(m.best_step))
        boosts.append(da.acceptance_boost(m))
    row = dict(kind=kind, n=n, inst=i, arm=arm, attempt=attempt, runs=runs, iters=iters, t_low=t_low, t_high=t_high,
               rate=cfg.offset_rate, best=bests, best_step=hit_step, boost=boosts, wall_s=round(time.time() - t0, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(row))
    os.replace(tmp, path)
    return "done"


def jobs_for(attempt, sizes, instances, runs, iter_per_n, out) -> list:
    js = [(k, n, i, a, attempt, runs, iter_per_n * n, str(out)) for k in CLASSES for n in sizes
          for i in range(instances) for a in ARMS[attempt]]
    return sorted(js, key=lambda j: -j[1])


# ------------------------------------------------------------------------------------------------ evaluation
def tts_table(rows, attempt) -> dict:
    """{(kind, n, arm): [TTS99 per instance]} with E* = best over all rows of the instance (both arms, all attempts)."""
    ref: dict = {}
    for r in rows:
        key = (r["kind"], r["n"], r["inst"])
        ref[key] = max(ref.get(key, -math.inf), max(r["best"]))
    out: dict = {}
    for r in rows:
        if r["attempt"] != attempt:
            continue
        e = ref[(r["kind"], r["n"], r["inst"])]
        hits = [s for b, s in zip(r["best"], r["best_step"]) if b >= e]
        out.setdefault((r["kind"], r["n"], r["arm"]), []).append(tts_opt(hits, r["runs"]))
    return out


def tts_opt(hits: list[int], runs: int) -> float:
    """min over t of t x R99(p(t)); p(t) = fraction of runs whose best-so-far reached E* by iteration t (Sec. IV with
    the anneal length chosen optimally, so a p = 1 budget does not set the TTS); inf if no run reached E*."""
    if not hits:
        return math.inf
    hs = sorted(max(h, 1) for h in hits)
    return min(da.tts99(k / runs, 1) * t if k < runs else float(t) for k, t in enumerate(hs, 1))


def tts80(v) -> float:
    return float(np.percentile(np.array(v, dtype=float), 80, method="higher"))


def beta_fit(tt: dict, kind: str, sizes, arm="off") -> float:
    ys = [tts80(tt[(kind, n, arm)]) for n in sizes]
    if not all(math.isfinite(y) for y in ys):
        return math.inf
    return float(np.polyfit(np.array(sizes, dtype=float), np.log10(ys), 1)[0])


def boot_sd(fn, tt: dict, rng) -> float:
    vals = []
    for _ in range(BOOT):
        res = {k: list(rng.choice(np.array(v, dtype=float), size=len(v))) for k, v in tt.items()}
        v = fn(res)
        if math.isfinite(v):
            vals.append(v)
    return float(np.std(vals)) if len(vals) > 1 else math.nan


def q_value(tt: dict, sizes) -> float:
    rs = []
    for k in CLASSES:
        for n in sizes:
            on, off = tts80(tt.get((k, n, "on"), [math.inf])), tts80(tt.get((k, n, "off"), [math.inf]))
            if math.isfinite(on) and math.isfinite(off):
                rs.append(on / off)
    return float(np.exp(np.mean(np.log(rs)))) if rs else math.nan


def boost_medians(per_inst: dict) -> dict:
    """Median acceptance boost per class over all runs of all instances; NaN runs (no acceptance in the window) dropped."""
    out = {}
    for k, runs in per_inst.items():
        vals = [b for bs in runs for b in bs if b == b]
        out[k] = float(np.median(vals)) if vals else math.nan
    return out


def t4_result(rows, nmax: int, rng) -> dict:
    """T4 (P4.04): per-class median boost over runs and instances, pass iff both >= nmax / 2. sigma = bootstrap over
    instances of the lower class median (the reported value); NaN only if fewer than two finite replicates exist."""
    per_inst = {k: [r["boost"] for r in rows if r["kind"] == k and r["n"] == nmax and r["arm"] == "off"
                    and r["attempt"] == 1] for k in CLASSES}
    med = boost_medians(per_inst)
    excl = sum(1 for runs in per_inst.values() for bs in runs for b in bs if b != b)
    reps = []
    for _ in range(BOOT):
        m = boost_medians({k: [runs[j] for j in rng.integers(0, len(runs), len(runs))] for k, runs in per_inst.items()})
        if all(v == v for v in m.values()):
            reps.append(min(m.values()))
    sigma = float(np.std(reps)) if len(reps) > 1 else math.nan
    ok = all(v == v and v >= nmax / 2 for v in med.values())
    return dict(value=min(med.values()), sigma=sigma, passed=ok, per_class=med, excluded=excl)


def evaluate(rows, attempt, sizes) -> dict:
    rng = np.random.default_rng(20261116)
    tt = tts_table(rows, attempt)
    res = {}
    for t, kind in (("T1", "bimodal"), ("T2", "gaussian")):
        b = beta_fit(tt, kind, sizes)
        lo, hi = BETA_PAPER[kind] / 2, 2 * BETA_PAPER[kind]
        res[t] = dict(value=b, sigma=boot_sd(lambda x, k=kind: beta_fit(x, k, sizes), tt, rng), passed=lo <= b <= hi,
                      band=(lo, hi), tts80={n: tts80(tt[(kind, n, "off")]) for n in sizes})
    if attempt == 1:
        q = q_value(tt, sizes)
        res["T3"] = dict(value=q, sigma=boot_sd(lambda x: q_value(x, sizes), tt, rng), passed=bool(q == q and q >= 0.5))
        res["T4"] = t4_result(rows, max(sizes), rng)
    return res


def load_rows(out: Path) -> list:
    return [json.loads(p.read_text()) for p in sorted((out / "runs").glob("*.json"))]


def prereg_sha(path: Path) -> str:
    """sha256 of the prereg; refuses to run if the file differs from its committed version."""
    rc = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", "HEAD", "--", str(path)]).returncode
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", str(path)],
                             capture_output=True).returncode
    if rc != 0 or tracked != 0:
        raise SystemExit(f"prereg {path} is not committed unchanged; refusing to run")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prereg", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--attempt", type=int, choices=(1, 2), default=1)
    ap.add_argument("--smoke", action="store_true", help="tiny budget, separate out dir, verdicts not scored")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    sha = prereg_sha(a.prereg)
    if a.smoke:
        out = a.out or REPO / "sim/out/calib_b3_smoke"
        sizes, ninst, runs, ipn = SMOKE["sizes"], SMOKE["instances"], SMOKE["runs"], SMOKE["iter_per_n"]
    else:
        out = a.out or OUT
        sizes, ninst, runs, ipn = SIZES, INSTANCES, RUNS[a.attempt], ITER_PER_N[a.attempt]
    js = jobs_for(a.attempt, sizes, ninst, runs, ipn, out)
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, st in enumerate(pool.imap_unordered(run_job, js), 1):
            print(f"[{i}/{len(js)}] {st} {time.time() - t0:.0f}s", flush=True)
    rows = load_rows(out)
    tag = "SMOKE (not scored)" if a.smoke else "RESULT"
    res = evaluate(rows, a.attempt, sizes)
    for t, r in res.items():
        print(f"{tag} P4.04 {t} {'PASS' if r['passed'] else 'FAIL'} value={r['value']:.4g} sigma={r['sigma']:.3g} "
              f"attempt={a.attempt} prereg_sha256={sha[:12]}")
    (out / f"result_attempt{a.attempt}.json").write_text(json.dumps(
        dict(prereg_sha256=sha, smoke=a.smoke, attempt=a.attempt, results=res), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
