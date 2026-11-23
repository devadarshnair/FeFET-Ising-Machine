"""P4.05: HyCiM D-QUBO gap diagnosis (prereg/calib/P4.05.md; hypotheses docs/hw/lit/hycim_dqubo.md).

Stages (one invocation runs all, resumable; each job = one (instance, arm, run config, block of 10 initial states)):
  diag-A  C1 (L = 1000 proposals) and C2 (L = 1000 sweeps) on the 5 registered instances, both arms.
  diag-B  winning reading W (from diag-A only) with H4 consistent init (C3) and H5 T0 multipliers 1e-3, 1e-5 (C4, C5).
  full    best registered cell B (from the diagnosis only) on all 40 instances -> RESULT P4.05 PASS|FAIL.
Readings: per-run, per-init (best of the init's 100 runs). Scorers (H3): best (best feasible seen), final, minE.
A job row stores, per scorer, the number of successful runs of each initial state.

Usage: python -I scripts/baselines/dqubo_diag.py --prereg prereg/calib/P4.05.md --jobs 16 [--smoke]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts/baselines"))

import hycim as hc  # noqa: E402

DIAG = ("jeu_100_25_1.txt", "jeu_100_50_1.txt", "jeu_100_75_1.txt", "jeu_100_100_1.txt", "jeu_100_25_2.txt")
N_INIT, N_RUNS, BLOCK = 100, 100, 10
PAPER, BAND_D, BAND_F = 10.75, (5.75, 15.75), (93.54, 100.0)
SCORERS = ("best", "final", "minE")
READINGS = ("run", "init")
# config = (length mode, D-QUBO init, D-QUBO T0 multiplier)
C1 = ("prop1000", "bernoulli", 1e-4)
C2 = ("sweep1000", "bernoulli", 1e-4)
OUT = REPO / "sim/out/dqubo_diag"


def length(inst: hc.Inst, arm: str, mode: str) -> int:
    if mode == "prop1000":
        return 1000
    if mode == "sweep1000":
        return 1000 * (inst.n + (inst.C if arm == "dqubo" else 0))
    if mode.startswith("smoke"):
        return int(mode[5:])
    raise ValueError(mode)


def sig(arm: str, cfg: tuple) -> tuple:
    """The filter arm ignores the D-QUBO-only knobs (init, T0 multiplier), so its runs are shared across them."""
    return (cfg[0], "-", 0.0) if arm == "filter" else cfg


def key(name: str, arm: str, cfg: tuple, block: int) -> str:
    s = sig(arm, cfg)
    return f"{name[:-4]}_{arm}_{s[0]}_{s[1]}_{s[2]:g}_b{block}"


def run_job(job) -> str:
    name, arm, cfg, block, out, n_runs = job
    path = Path(out) / "runs" / (key(name, arm, cfg, block) + ".json")
    if path.exists():
        return "skip"
    t0 = time.time()
    inst = hc.load(name)
    opt = json.loads(hc.OPTIMA.read_text())["instances"][name]["value"]
    idx, ai, si = hc.INSTANCES.index(name), hc.ARMS.index(arm), hc.SCHEDULES.index("S4")
    mode, init, mult = sig(arm, cfg)
    L = length(inst, arm, mode)
    T0 = hc.t0_for(inst, arm, "S4", hc.seed_of(idx, ai, si, 99), dqubo_mult=mult if arm == "dqubo" else hc.DQUBO_T0_S4)
    T = hc.temps("S4", T0, L)
    pswap = hc.PSWAP_V3 if arm == "filter" else 0.0
    counts = {s: [] for s in SCORERS}
    for k in range(block * BLOCK, (block + 1) * BLOCK):
        x0, y0 = hc.initial_state(inst, arm, hc.seed_of(idx, ai, 0, k), init if arm == "dqubo" else "bernoulli")
        ok = {s: 0 for s in SCORERS}
        for r in range(n_runs):
            best, _, final, minE = hc.run_one(inst, arm, T, x0, y0, hc.seed_of(idx, ai, si, k, r, L), pswap)
            for s, v in zip(SCORERS, (best, final, minE)):
                ok[s] += int(v >= 0.95 * opt)
        for s in SCORERS:
            counts[s].append(ok[s])
    row = dict(instance=name, arm=arm, sig=list(sig(arm, cfg)), block=block, L=L, T0=T0, n_runs=n_runs,
               counts=counts, wall_s=round(time.time() - t0, 2))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(row))
    os.replace(tmp, path)
    return "done"


def run_jobs(names, cfgs, out, jobs, n_init, n_runs) -> None:
    js = sorted({(nm, arm, sig(arm, c), b) for nm in names for c in cfgs for arm in hc.ARMS
                 for b in range(n_init // BLOCK)})
    js = [(nm, arm, c, b, str(out), n_runs) for nm, arm, c, b in js]
    t0 = time.time()
    with Pool(jobs) as pool:
        for i, st in enumerate(pool.imap_unordered(run_job, js), 1):
            print(f"[{i}/{len(js)}] {st} {time.time() - t0:.0f}s", flush=True)


def rate(out, names, arm, cfg, reading, scorer, n_init) -> float:
    """Percent success over the instances (mean of per-instance rates), from the job rows."""
    per = []
    for nm in names:
        c = []
        for b in range(n_init // BLOCK):
            row = json.loads((Path(out) / "runs" / (key(nm, arm, cfg, b) + ".json")).read_text())
            c += row["counts"][scorer]
            n_runs = row["n_runs"]
        c = np.array(c)
        per.append(c.mean() / n_runs if reading == "run" else (c > 0).mean())
    return 100.0 * float(np.mean(per))


def in_band(d: float, f: float) -> bool:
    return BAND_D[0] <= d <= BAND_D[1] and BAND_F[0] <= f <= BAND_F[1]


def cells(out, names, cfgs, n_init) -> list:
    rows = []
    for c in cfgs:
        for rd in READINGS:
            for sc in SCORERS:
                d = rate(out, names, "dqubo", c, rd, sc, n_init)
                f = rate(out, names, "filter", c, rd, sc, n_init)
                rows.append(dict(cfg=list(c), reading=rd, scorer=sc, dqubo=d, filter=f, in_band=in_band(d, f)))
    return rows


def winning_reading(out, names, n_init) -> tuple:
    cand = [(C1, "init"), (C2, "run"), (C2, "init")]
    return min(cand, key=lambda cr: abs(rate(out, names, "dqubo", cr[0], cr[1], "best", n_init) - PAPER))


def prereg_sha(path: Path) -> str:
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
    ap.add_argument("--smoke", action="store_true", help="tiny lengths/counts, separate out dir, not scored")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    sha = prereg_sha(a.prereg)
    global C1, C2
    if a.smoke:
        out = a.out or REPO / "sim/out/dqubo_diag_smoke"
        C1, C2 = ("smoke200", "bernoulli", 1e-4), ("smoke2000", "bernoulli", 1e-4)
        diag, full, n_init, n_runs = DIAG[:2], DIAG[:3], BLOCK, 3
    else:
        out = a.out or OUT
        diag, full, n_init, n_runs = DIAG, hc.INSTANCES, N_INIT, N_RUNS
    tag = "SMOKE (not scored)" if a.smoke else "RESULT"
    run_jobs(diag, [C1, C2], out, a.jobs, n_init, n_runs)
    W, w_reading = winning_reading(out, diag, n_init)
    extra = [(W[0], "consistent", W[2]), (W[0], W[1], 1e-3), (W[0], W[1], 1e-5)]
    run_jobs(diag, extra, out, a.jobs, n_init, n_runs)
    table = cells(out, diag, [C1, C2] + extra, n_init)
    for r in table:
        print(f"{tag} P4.05 DIAG cfg={r['cfg']} reading={r['reading']} scorer={r['scorer']} "
              f"dqubo={r['dqubo']:.2f} filter={r['filter']:.2f} in_band={r['in_band']}")
    pool_ = [r for r in table if r["in_band"]] or table
    B = min(pool_, key=lambda r: abs(r["dqubo"] - PAPER))
    run_jobs(full, [tuple(B["cfg"])], out, a.jobs, n_init, n_runs)
    d = rate(out, full, "dqubo", tuple(B["cfg"]), B["reading"], B["scorer"], n_init)
    f = rate(out, full, "filter", tuple(B["cfg"]), B["reading"], B["scorer"], n_init)
    ok = in_band(d, f)
    label = ("reproduced only under the best-of-100 reading" if ok and B["reading"] == "init" else
             "reproduced" if ok else f"D-QUBO not reproduced under {len(table)} registered interpretations")
    print(f"{tag} P4.05 {'PASS' if ok else 'FAIL'} dqubo={d:.2f} filter={f:.2f} cfg={B['cfg']} "
          f"reading={B['reading']} scorer={B['scorer']} instances={len(full)} label=\"{label}\" "
          f"prereg_sha256={sha[:12]}")
    (Path(out) / "result.json").write_text(json.dumps(dict(
        prereg_sha256=sha, smoke=a.smoke, winning_reading=[list(W), w_reading], diag=table, best=B,
        full=dict(dqubo=d, filter=f, passed=ok, label=label, instances=len(full))), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
