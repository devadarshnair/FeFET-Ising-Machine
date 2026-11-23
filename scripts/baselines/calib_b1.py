"""P4.02: B1 (Yin 2024 MESA) calibration vs Yin, R1 algorithm level. Design and tolerance: prereg/calib/P4.02.md.

MESA (golden restart arm "mesa", Count_max = K n) vs plain SA (arm "none") on the same shared single-flip machine,
same geometric schedule, same seeds. Yin's "flip a few bits" perturbation is NOT used (shared single-flip machine;
yin_mesa.B1Cfg.perturb_bits is recorded only). One job = one (graph, arm, seed) run, each well under 1 h; jobs are
resumable (an existing row file is skipped) and run in a process pool.

Usage:
  python -I scripts/baselines/calib_b1.py --prereg prereg/calib/P4.02.md --jobs 16 [--attempt 1|2]
  python -I scripts/baselines/calib_b1.py --prereg prereg/calib/P4.02.md --smoke      (not scored)
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for sub in ("scripts/golden", "scripts/problems", "scripts/baselines"):
    sys.path.insert(0, str(REPO / sub))

import instances as gi  # noqa: E402
import maxcut  # noqa: E402
import tim_golden as tg  # noqa: E402
from restart import RestartCfg  # noqa: E402

GRAPHS = ([f"G{i}" for i in range(1, 18)] + [f"G{i}" for i in range(22, 27)] + [f"G{i}" for i in range(43, 48)]
          + ["G48", "G49", "G50"])
T1_GRAPHS = ("G48", "G49", "G50")
T2_GRAPHS = ("G1", "G2", "G3", "G4", "G5")
SWEEPS = 300
SEEDS = 20
SEED_TAG = 20261115
T_SAMPLES = 32
T1_PAPER, T1_TOL = 27.0, 10.0
T2_PAPER, T2_TOL = 2.0, 0.5
TARGET_FRAC = 0.99
BOOT = 2000
ARMS_ATTEMPT = {1: ("sa", "mesa_k2"), 2: ("sa", "mesa_k1_e10", "mesa_k4_e10")}  # P4.02a amendment
OUT = REPO / "sim/out/calib_b1"


@functools.lru_cache(maxsize=None)
def load_graph(name: str) -> maxcut.MaxCut:
    return maxcut.load_gset(name)


def edges_of(g: maxcut.MaxCut) -> list[tuple[int, int, int]]:
    return [(int(i), int(j), int(w)) for (i, j), w in zip(g.edges, g.weights)]


def temperatures(d: np.ndarray, P: np.ndarray, seed: int) -> tuple[float, float]:
    """Aramon App. A rule: T_start = p85, T_end = p05 of nonzero single-flip |dE| over random states."""
    rng = np.random.default_rng([SEED_TAG, 99, seed])
    dE = []
    for _ in range(T_SAMPLES):
        x = rng.integers(0, 2, len(d))
        dE.append(np.abs(d + P @ x))
    dE = np.concatenate(dE)
    dE = dE[dE > 0]
    return float(np.percentile(dE, 85)), float(np.percentile(dE, 5))


def build(name: str, seed: int, steps: int) -> tuple[tg.Instance, int]:
    g = load_graph(name)
    d, P = gi.maxcut_qubo(g.n, edges_of(g))
    t_hi, t_lo = temperatures(d, P, GRAPHS.index(name) if name in GRAPHS else 0)
    inst = gi.qubo_instance(d, P, seed=gi.mix_seed(SEED_TAG, GRAPHS.index(name) if name in GRAPHS else 99, seed),
                            steps=steps, t_start=t_hi, t_end=t_lo, deoff=0)
    n_pad = 1 << (g.n - 1).bit_length()
    return tg.pad_instance(inst, n_pad), g.n


ARM_RE = re.compile(r"mesa_k(\d+)(?:_e(\d+))?$")


def restart_for(arm: str, n: int) -> RestartCfg:
    if arm == "sa":
        return RestartCfg(arm="none")
    return RestartCfg(arm="mesa", K=int(ARM_RE.match(arm).group(1)) * n)


def epoch_sweeps(arm: str) -> int | None:
    """Per-epoch cooling length in sweeps (amendment P4.02a); None = registered whole-run schedule (attempt 1)."""
    m = ARM_RE.match(arm)
    return int(m.group(2)) if m and m.group(2) else None


def epoch_schedule(inst: tg.Instance, n: int, sweeps: int) -> tuple[tg.Instance, int]:
    """Amendment P4.02a: geometric T0 -> T_end within each MESA epoch of `sweeps` sweeps, then held at T_end.

    The whole-run alpha of attempt 1 cools T0 -> T_end over 300 sweeps, but MESA resets T := T0 every Count_max
    stagnant steps (~2n), so the attempt-1 MESA arm never left T ~ T0 (148 restarts in 300 sweeps, a hot walk)."""
    t_lo = int(round(inst.t0 * (inst.alpha / gi.TWO32) ** (inst.steps - 1)))
    alpha = gi.alpha_reg(inst.t0, max(t_lo, 1), sweeps * n)
    return dataclasses.replace(inst, alpha=alpha), max(t_lo, 1)


def run_job(job: tuple[str, str, int, int, str]) -> str:
    name, arm, seed, sweeps, out = job
    path = Path(out) / "runs" / f"{name}_{arm}_{seed}.json"
    if path.exists():
        return "skip"
    t0 = time.time()
    g_n = load_graph(name).n
    inst, n = build(name, seed, sweeps * g_n)
    es = epoch_sweeps(arm)
    t_floor = 0
    if es is not None:
        inst, t_floor = epoch_schedule(inst, n, es)
    m = tg.Machine(inst, restart=restart_for(arm, n))
    curve = []
    for _ in range(sweeps):
        for _ in range(n):
            m.step()
            if m.temp < t_floor:
                m.temp = t_floor
        curve.append(int(m.best_f))
    cut = load_graph(name).cut(m.best_x[:n])
    assert cut == curve[-1], "golden objective != cut"
    row = dict(graph=name, arm=arm, seed=seed, n=n, sweeps=sweeps, curve=curve, restarts=len(m.restart.events),
               wall_s=round(time.time() - t0, 2))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(row))
    os.replace(tmp, path)
    return "done"


def jobs_for(attempt: int, graphs, seeds: int, sweeps: int, out: Path) -> list:
    js = [(g, a, s, sweeps, str(out)) for g in graphs for a in ARMS_ATTEMPT[attempt] for s in range(seeds)]
    return sorted(js, key=lambda j: -load_graph(j[0]).n)


# ------------------------------------------------------------------------------------------------ evaluation
def final_cuts(rows, g, arm) -> np.ndarray:
    return np.array([r["curve"][-1] for r in rows if r["graph"] == g and r["arm"] == arm], float)


def curves(rows, g, arm) -> np.ndarray:
    return np.array([r["curve"] for r in rows if r["graph"] == g and r["arm"] == arm], float)


def t1_value(cuts: dict) -> float:
    return max(100.0 * (cuts[g]["mesa"].mean() - cuts[g]["sa"].mean()) / cuts[g]["sa"].mean() for g in cuts)


def tts(curv: np.ndarray, target: float) -> float:
    """min_t t * R99(p(t)) in sweeps; inf if never reached."""
    p = (curv >= target).mean(axis=0)
    best = math.inf
    for t, pt in enumerate(p, start=1):
        if pt <= 0:
            continue
        r99 = 1.0 if pt >= 1 else math.log(0.01) / math.log(1 - pt)
        best = min(best, t * max(r99, 1.0))
    return best


def t2_value(cv: dict, targets: dict) -> float:
    ratios = []
    for g in cv:
        a, b = tts(cv[g]["sa"], targets[g]), tts(cv[g]["mesa"], targets[g])
        if math.isinf(b):
            continue
        if math.isinf(a):
            return math.inf
        ratios.append(a / b)
    return float(np.exp(np.mean(np.log(ratios)))) if ratios else math.nan


def boot_sd(fn, data: dict, rng) -> float:
    vals = []
    for _ in range(BOOT):
        res = {g: {a: v[rng.integers(0, len(v), len(v))] for a, v in arms.items()} for g, arms in data.items()}
        vals.append(fn(res))
    vals = np.array(vals, float)
    vals = vals[np.isfinite(vals)]
    return float(vals.std(ddof=1)) if len(vals) > 1 else math.nan


def verdict(value: float, sigma: float, paper: float, tol: float) -> bool:
    return math.isfinite(value) and abs(value - paper) <= max(tol, sigma if math.isfinite(sigma) else 0.0)


def evaluate(rows: list, mesa_arm: str, t1_graphs, t2_graphs) -> dict:
    rng = np.random.default_rng([SEED_TAG, 7])
    c1 = {g: {"sa": final_cuts(rows, g, "sa"), "mesa": final_cuts(rows, g, mesa_arm)} for g in t1_graphs}
    v1 = t1_value(c1)
    s1 = boot_sd(t1_value, c1, rng)
    cv = {g: {"sa": curves(rows, g, "sa"), "mesa": curves(rows, g, mesa_arm)} for g in t2_graphs}
    targets = {g: TARGET_FRAC * (load_graph(g).best_known or math.inf) for g in t2_graphs}
    v2 = t2_value(cv, targets)
    s2 = boot_sd(lambda d: t2_value(d, targets), cv, rng)
    return {"arm": mesa_arm,
            "T1": dict(value=v1, sigma=s1, passed=verdict(v1, s1, T1_PAPER, T1_TOL),
                       per_graph={g: 100 * (c1[g]["mesa"].mean() / c1[g]["sa"].mean() - 1) for g in c1}),
            "T2": dict(value=v2, sigma=s2, passed=verdict(v2, s2, T2_PAPER, T2_TOL),
                       tts={g: [tts(cv[g]["sa"], targets[g]), tts(cv[g]["mesa"], targets[g])] for g in cv})}


def load_rows(out: Path) -> list:
    return [json.loads(p.read_text()) for p in sorted((out / "runs").glob("*.json"))]


def prereg_sha(path: Path) -> str:
    """sha256 of the prereg; refuses to score if the file differs from its committed version."""
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
        out = a.out or REPO / "sim/out/calib_b1_smoke"
        graphs, seeds, sweeps, t1g, t2g = ("G1", "G43", "G48"), 2, 2, ("G48",), ("G1",)
    else:
        out = a.out or OUT
        graphs, seeds, sweeps, t1g, t2g = GRAPHS, SEEDS, SWEEPS, T1_GRAPHS, T2_GRAPHS
    if a.attempt == 2:
        graphs = sorted(set(t1g) | set(t2g))
    js = jobs_for(a.attempt, graphs, seeds, sweeps, out)
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, st in enumerate(pool.imap_unordered(run_job, js), 1):
            print(f"[{i}/{len(js)}] {st} {time.time() - t0:.0f}s", flush=True)
    rows = load_rows(out)
    tag = "SMOKE (not scored)" if a.smoke else "RESULT"
    results = []
    for arm in ARMS_ATTEMPT[a.attempt][1:]:
        ev = evaluate(rows, arm, t1g, t2g)
        results.append(ev)
        for t in ("T1", "T2"):
            r = ev[t]
            print(f"{tag} P4.02 {t} {'PASS' if r['passed'] else 'FAIL'} value={r['value']:.4g} "
                  f"sigma={r['sigma']:.3g} arm={arm} attempt={a.attempt} prereg_sha256={sha[:12]}")
    amendment = a.prereg.with_name("P4.02a_amendment.md")
    amend_sha = hashlib.sha256(amendment.read_bytes()).hexdigest() if amendment.exists() else None
    print(f"{tag} amendment_sha256={(amend_sha or 'none')[:12]}")
    (out / f"result_attempt{a.attempt}.json").write_text(json.dumps(
        dict(prereg_sha256=sha, amendment_sha256=amend_sha, smoke=a.smoke, attempt=a.attempt, results=results), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
