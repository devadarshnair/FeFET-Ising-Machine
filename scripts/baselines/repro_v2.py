"""P4_v2 reproductions R1-R4 (prereg/calib/P4_v2_reproduction.md). Resumable, chunked jobs; one JSON per job.

  repro_v2.py run  --part R1|R1x|R2|R3|R4 [--chunk i/k]     runs the jobs of a part (R1x = report-only +27 % runs)
  repro_v2.py eval [--parts R1,R2,R3,R4]                   prints RESULT P4v2 lines, writes sim/out/hw/baselines_v2/result.json
Every heavy call goes through ~/research/shared/local job queue (each chunk < 1 h, one process).
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
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import calib_b1 as cb1  # noqa: E402
import fujitsu_da as da  # noqa: E402
import yin_mesa as b1  # noqa: E402
from instances import maxcut_qubo, mix_seed  # noqa: E402

REPO = HERE.parents[1]
PREREG = REPO / "prereg/calib/P4_v2_reproduction.md"
AMEND1 = REPO / "prereg/calib/P4_v2_amendment1.md"
AMEND2 = REPO / "prereg/calib/P4_v2_amendment2.md"
R4B_INIT, R4B_RUNS, R4B_L = 1000, 100, 1000         # amendment 2 B: paper design, iteration = one proposal
OUT = REPO / "sim/out/hw/baselines_v2"
TAG = 20261117

# R1 (Yin SI Fig. S7)
R1_GRAPHS, R1_SCORED = ("G1", "G2", "G3", "G4", "G5"), "G1"
R1_SWEEPS, R1_SEEDS = 1200, 40
R1X_GRAPHS, R1X_SWEEPS, R1X_SEEDS = ("G48", "G49", "G50"), (10, 30, 100), 10
# R2 (Aramon Fig. 2)
R2_N, R2_INST, R2_REP, R2_THERM, R2_MEAS = 64, 20, 2, 100_000, 5_000
R2_T = {"bimodal": (0.1, 0.3, 1, 3, 10, 30, 100, 1000),
        "gaussian": tuple(1e-4 * t for t in (1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6, 1e7, 1e8))}
# R3 (Aramon Sec. VI.B scaling)
R3_SIZES, R3_INST, R3_RUNS, R3_L = (64, 128, 256), 20, 50, (25, 50, 100, 200, 400, 800)
R3_REF_RUNS, R3_REF_L = 10, 4000
BETA_PAPER = {"bimodal": 0.0021, "gaussian": 0.0019}
# R4 (HyCiM filter)
R4_INIT, R4_RUNS, R4_L, R4_L_LITERAL = 100, 10, 100_000, 1000
CLASSES = ("bimodal", "gaussian")


def prereg_sha() -> str:
    return cb1.prereg_sha(PREREG)


def amend1_sha() -> str:
    return cb1.prereg_sha(AMEND1)


# Amendment 1 (R1b, R3x)
R1B_E = (10, 100)
R1B_FRAC = 0.99
R3X_SIZES = (512, 1024)
R3X_SPLIT = 1024            # sizes >= this run grid and reference runs as separate jobs


def _write(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(row))
    os.replace(tmp, path)


def maxcut_problem(name: str):
    g = cb1.load_graph(name)
    d, P = maxcut_qubo(g.n, cb1.edges_of(g))
    return g, np.asarray(d, np.int64), np.asarray(P, np.int64)


# ------------------------------------------------------------------------------------------------ jobs
def jobs(part: str) -> list[tuple]:
    if part == "R1":
        return [(part, g, arm) for g in R1_GRAPHS for arm in ("sa", "mesa")]
    if part == "R1x":
        return [(part, g, s) for g in R1X_GRAPHS for s in R1X_SWEEPS]
    if part == "R2":
        return [(part, k, T) for k in CLASSES for T in R2_T[k]]
    if part == "R3":
        return [(part, k, n, i) for k in CLASSES for n in R3_SIZES for i in range(R3_INST)]
    if part == "R1b":
        return [(part, g, "sa", 0) for g in R1_GRAPHS] + [(part, g, "mesa", e) for g in R1_GRAPHS for e in R1B_E]
    if part == "R3x":
        out = []
        for k in CLASSES:
            for n in R3X_SIZES:
                for i in range(R3_INST):
                    out += [(part, k, n, i, "grid"), (part, k, n, i, "ref")] if n >= R3X_SPLIT else [(part, k, n, i, "all")]
        return out
    if part == "R4b":
        import hycim as hc
        return [(part, nm) for nm in hc.INSTANCES]
    if part == "R4":
        import hycim as hc
        return [(part, nm) for nm in hc.INSTANCES]
    raise ValueError(part)


def job_path(job) -> Path:
    return OUT / job[0] / ("_".join(str(x) for x in job[1:]).replace(".", "p") + ".json")


def run_r1(job) -> dict:
    _, gname, arm = job
    g, d, P = maxcut_problem(gname)
    t0, t_end = cb1.temperatures(d, P, cb1.GRAPHS.index(gname))
    best, curves, epochs = [], [], []
    for s in range(R1_SEEDS):
        f, curve, ep, _ = b1.yin_native_run(d, P, R1_SWEEPS, t0, t_end, arm, mix_seed(TAG, 1, cb1.GRAPHS.index(gname), s))
        best.append(int(f))
        curves.append(curve.tolist())
        epochs.append(int(ep))
    return dict(graph=gname, arm=arm, n=g.n, t0=t0, t_end=t_end, bks=cb1.maxcut.best_known(gname), best=best, curve=curves,
                epochs=epochs)


def run_r1x(job) -> dict:
    _, gname, sweeps = job
    g, d, P = maxcut_problem(gname)
    t0, t_end = cb1.temperatures(d, P, cb1.GRAPHS.index(gname))
    out = {}
    for arm in ("sa", "mesa"):
        out[arm] = [int(b1.yin_native_run(d, P, sweeps, t0, t_end, arm, mix_seed(TAG, 2, cb1.GRAPHS.index(gname), sweeps, s))[0])
                    for s in range(R1X_SEEDS)]
    return dict(graph=gname, sweeps=sweeps, n=g.n, bks=cb1.maxcut.best_known(gname), **out)


def run_r2(job) -> dict:
    _, kind, T = job
    pp, ps = [], []
    for i in range(R2_INST):
        d, P = da.sk_qubo(R2_N, i, kind)
        for rep in range(R2_REP):
            a, b = da.da_const_t(d, P, T, R2_THERM * R2_N, R2_MEAS * R2_N, mix_seed(TAG, 3, CLASSES.index(kind), i, rep))
            pp.append(a)
            ps.append(b)
    return dict(kind=kind, T=T, pp=pp, ps=ps)


def run_r3(job) -> dict:
    _, kind, n, i = job
    d, P = da.sk_qubo(n, i, kind)
    th, tl = da.aramon_table1(kind)
    rows = {}
    for L in R3_L:
        best, _ = da.da_anneal(d, P, th, tl, L * n, R3_RUNS, mix_seed(TAG, 4, CLASSES.index(kind), n, i, L))
        rows[str(L)] = best.tolist()
    ref, _ = da.da_anneal(d, P, th, tl, R3_REF_L * n, R3_REF_RUNS, mix_seed(TAG, 5, CLASSES.index(kind), n, i))
    return dict(kind=kind, n=n, inst=i, th=th, tl=tl, best=rows, ref=ref.tolist())


def run_r4(job) -> dict:
    import hycim as hc
    _, nm = job
    opt = json.loads(hc.OPTIMA.read_text())["instances"][nm]["value"]
    inst, idx = hc.load(nm), hc.INSTANCES.index(nm)
    ai, si = hc.ARMS.index("filter"), hc.SCHEDULES.index("S4")
    out = {}
    for L in (R4_L, R4_L_LITERAL):
        T = hc.temps("S4", hc.t0_for(inst, "filter", "S4", hc.seed_of(idx, ai, si, 99)), L)
        ok = []
        for k in range(R4_INIT):
            x0, y0 = hc.initial_state(inst, "filter", hc.seed_of(idx, ai, 0, k))
            for r in range(R4_RUNS):
                b = hc.run_one(inst, "filter", T, x0, y0, hc.seed_of(idx, ai, si, k, r, L), hc.PSWAP_V3)[0]
                ok.append(bool(b >= 0.95 * opt))
        out[str(L)] = ok
    return dict(instance=nm, opt=opt, success=out)


def run_r1b(job) -> dict:
    _, gname, arm, E = job
    g, d, P = maxcut_problem(gname)
    t0, t_end = cb1.temperatures(d, P, cb1.GRAPHS.index(gname))
    best, curves, epochs = [], [], []
    for s in range(R1_SEEDS):
        f, curve, ep, _ = b1.yin_native_run(d, P, R1_SWEEPS, t0, t_end, arm, mix_seed(TAG, 6, cb1.GRAPHS.index(gname), s),
                                            epoch_sweeps=E or b1.MESA2_EPOCH_SWEEPS)
        best.append(int(f))
        curves.append(curve.tolist())
        epochs.append(int(ep))
    return dict(graph=gname, arm=arm, E=E, n=g.n, bks=cb1.maxcut.best_known(gname), best=best, curve=curves, epochs=epochs)


def run_r3x(job) -> dict:
    _, kind, n, i, which = job
    d, P = da.sk_qubo(n, i, kind)
    th, tl = da.aramon_table1(kind)
    row = dict(kind=kind, n=n, inst=i, th=th, tl=tl, which=which)
    if which in ("grid", "all"):
        row["best"] = {str(L): da.da_anneal(d, P, th, tl, L * n, R3_RUNS, mix_seed(TAG, 4, CLASSES.index(kind), n, i, L))[0].tolist()
                       for L in R3_L}
    if which in ("ref", "all"):
        row["ref"] = da.da_anneal(d, P, th, tl, R3_REF_L * n, R3_REF_RUNS, mix_seed(TAG, 5, CLASSES.index(kind), n, i))[0].tolist()
    return row


def run_r4b(job) -> dict:
    """Amendment 2 B: 1000 initial states x 100 runs x 1000 proposals; per initial state: number of successful runs and whether
    its best run reaches 0.95 opt (Fig. 10 reading)."""
    import hycim as hc
    _, nm = job
    opt = json.loads(hc.OPTIMA.read_text())["instances"][nm]["value"]
    inst, idx = hc.load(nm), hc.INSTANCES.index(nm)
    ai, si = hc.ARMS.index("filter"), hc.SCHEDULES.index("S4")
    T = hc.temps("S4", hc.t0_for(inst, "filter", "S4", hc.seed_of(idx, ai, si, 99)), R4B_L)
    succ_runs, best_ok = [], []
    for k in range(R4B_INIT):
        x0, y0 = hc.initial_state(inst, "filter", hc.seed_of(idx, ai, 0, k, 2))
        cnt, b = 0, -1.0
        for r in range(R4B_RUNS):
            v = hc.run_one(inst, "filter", T, x0, y0, hc.seed_of(idx, ai, si, k, r, R4B_L, 2), hc.PSWAP_V3)[0]
            cnt += v >= 0.95 * opt
            b = max(b, v)
        succ_runs.append(int(cnt))
        best_ok.append(bool(b >= 0.95 * opt))
    return dict(instance=nm, opt=opt, runs_per_init=R4B_RUNS, succ_runs=succ_runs, best_ok=best_ok)


def eval_r4b(rows: list[dict]) -> dict:
    if len(rows) != 40:
        return dict(pass_=None, n=len(rows))
    per_init = 100.0 * float(np.mean([v for r in rows for v in r["best_ok"]]))
    per_run = 100.0 * float(np.sum([sum(r["succ_runs"]) for r in rows])) / (40 * R4B_INIT * R4B_RUNS)
    worst = min(rows, key=lambda r: np.mean(r["best_ok"]))
    return dict(per_init=per_init, per_run=per_run, band=[93.54, 100.0], pass_=93.54 <= per_init <= 100.0,
                worst_instance=[worst["instance"], 100.0 * float(np.mean(worst["best_ok"]))])


RUNNERS = {"R4b": run_r4b, "R1b": run_r1b, "R3x": run_r3x, "R1": run_r1, "R1x": run_r1x, "R2": run_r2, "R3": run_r3, "R4": run_r4}


def _smoke_settings():
    """Tiny budgets for --smoke (job plumbing only; output under OUT/smoke, never evaluated)."""
    global R1_SWEEPS, R1_SEEDS, R3_RUNS, R3_L, R3_REF_L, R3_REF_RUNS, OUT
    R1_SWEEPS, R1_SEEDS, R3_RUNS, R3_L, R3_REF_L, R3_REF_RUNS = 3, 2, 2, (25,), 25, 1
    OUT = OUT / "smoke"


def run_part(part: str, chunk: str = "1/1", index: int | None = None, smoke: bool = False) -> int:
    sha = prereg_sha()
    i, k = map(int, chunk.split("/"))
    alljobs = jobs(part)
    if smoke:
        _smoke_settings()
    todo = [alljobs[index]] if index is not None else [j for idx, j in enumerate(alljobs) if idx % k == i - 1]
    for j in todo:
        p = job_path(j)
        if p.exists():
            continue
        t0 = time.time()
        row = RUNNERS[part](j)
        row.update(prereg_sha256=sha, wall_s=round(time.time() - t0, 1))
        if part in ("R1b", "R3x"):
            row["amend1_sha256"] = amend1_sha()
        if part == "R4b":
            row["amend2_sha256"] = cb1.prereg_sha(AMEND2)
        _write(p, row)
        print(f"done {p.name} {row['wall_s']} s", flush=True)
    return 0


# ------------------------------------------------------------------------------------------------ evaluation
def load(part: str) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((OUT / part).glob("*.json"))]


def tts_curve(curves: np.ndarray, target: float) -> float:
    return cb1.tts(curves, target)


def eval_r1(rows: list[dict]) -> dict:
    by = {(r["graph"], r["arm"]): r for r in rows}
    per = {}
    for g in R1_GRAPHS:
        if (g, "sa") not in by or (g, "mesa") not in by:
            continue
        bks = by[(g, "sa")]["bks"]
        cs = {a: np.array(by[(g, a)]["curve"]) for a in ("sa", "mesa")}
        s = {a: float((cs[a][:, -1] >= bks).mean()) for a in cs}
        t = {a: tts_curve(cs[a], bks) for a in cs}
        ratio = t["sa"] / t["mesa"] if math.isfinite(t["sa"]) and math.isfinite(t["mesa"]) else float("nan")
        per[g] = dict(success_sa=s["sa"], success_mesa=s["mesa"], tts_sa=t["sa"], tts_mesa=t["mesa"], ratio=ratio,
                      mean_cut_sa=float(cs["sa"][:, -1].mean()), mean_cut_mesa=float(cs["mesa"][:, -1].mean()), bks=bks,
                      epochs_mesa_mean=float(np.mean(by[(g, "mesa")]["epochs"])))
    g = per.get(R1_SCORED)
    ok = bool(g and g["success_mesa"] >= 0.90 and g["success_mesa"] >= g["success_sa"] and 1.0 <= g["ratio"] <= 4.0)
    return dict(per_graph=per, pass_=ok if g else None)


def eval_r1x(rows: list[dict]) -> dict:
    return {f"{r['graph']}@{r['sweeps']}": 100.0 * (np.mean(r["mesa"]) - np.mean(r["sa"])) / np.mean(r["sa"]) for r in rows}


def eval_r2(rows: list[dict]) -> dict:
    res = {}
    ok = True
    for k in CLASSES:
        rs = sorted((r for r in rows if r["kind"] == k), key=lambda r: r["T"])
        if len(rs) != len(R2_T[k]):
            return dict(per_class=res, pass_=None)
        R = [float(np.mean(r["pp"]) / np.mean(r["ps"])) if np.mean(r["ps"]) > 0 else float("nan") for r in rs]
        mono = all(R[j + 1] <= R[j] * 1.05 for j in range(len(R) - 1))
        good = R[0] >= 0.9 * R2_N and R[-1] <= 1.2 and mono
        res[k] = dict(T=[r["T"] for r in rs], ratio=R, monotone=mono, pass_=good)
        ok &= good
    return dict(per_class=res, pass_=ok)


def r3_tables(rows: list[dict]) -> dict:
    out = {}
    for k in CLASSES:
        for n in R3_SIZES:
            rs = [r for r in rows if r["kind"] == k and r["n"] == n]
            if len(rs) != R3_INST:
                continue
            tts = {}
            for L in R3_L:
                vals = []
                for r in rs:
                    estar = max(max(max(v) for v in r["best"].values()), max(r["ref"]))
                    b = np.array(r["best"][str(L)])
                    vals.append(da.jeffreys_tts(int((b >= estar).sum()), len(b), L * n))
                tts[L] = np.array(vals)
            lstar = min(R3_L, key=lambda L: tts[L].mean())
            out[(k, n)] = dict(L_star=lstar, tts80=float(np.percentile(tts[lstar], 80)),
                               mean_tts={L: float(v.mean()) for L, v in tts.items()},
                               solved_frac_at_Lstar=None)
    return out


def eval_r3(rows: list[dict]) -> dict:
    tab = r3_tables(rows)
    res, ok = {}, True
    for k in CLASSES:
        pts = [(n, tab[(k, n)]["tts80"]) for n in R3_SIZES if (k, n) in tab]
        if len(pts) != len(R3_SIZES):
            return dict(per_class=res, pass_=None, table={f"{a}_{b}": v for (a, b), v in tab.items()})
        x = np.array([p[0] for p in pts], float)
        y = np.log10([p[1] for p in pts])
        beta = float(np.polyfit(x, y, 1)[0])
        lo, hi = BETA_PAPER[k] / 2, 2 * BETA_PAPER[k]
        res[k] = dict(beta=beta, band=[lo, hi], tts80={int(a): b for a, b in pts}, pass_=lo <= beta <= hi)
        ok &= res[k]["pass_"]
    return dict(per_class=res, pass_=ok, table={f"{a}_{b}": v for (a, b), v in tab.items()})


def eval_r4(rows: list[dict]) -> dict:
    if len(rows) != 40:
        return dict(pass_=None, n=len(rows))
    rate = 100.0 * float(np.mean([s for r in rows for s in r["success"][str(R4_L)]]))
    lit = 100.0 * float(np.mean([s for r in rows for s in r["success"][str(R4_L_LITERAL)]]))
    # amendment 2 A: the paper defines an iteration as one proposal (Sec. 3.1 / 3.4), so the registered outcome is the
    # 1000-proposal rate; the 1000-sweep rate is a labelled alternative reading that the paper text contradicts.
    return dict(rate_paper_definition=lit, sweep_reading_contradicted=rate, band=[93.54, 100.0], pass_=93.54 <= lit <= 100.0,
                pass_under_sweep_reading=93.54 <= rate <= 100.0)


def eval_r1b(rows: list[dict]) -> dict:
    by = {(r["graph"], r["arm"], r["E"]): r for r in rows}
    per, ok_e = {}, []
    for E in R1B_E:
        for g in R1_GRAPHS:
            sa, me = by.get((g, "sa", 0)), by.get((g, "mesa", E))
            if not sa or not me:
                continue
            tgt = R1B_FRAC * sa["bks"]
            cs = {"sa": np.array(sa["curve"]), "mesa": np.array(me["curve"])}
            s = {a: float((cs[a][:, -1] >= tgt).mean()) for a in cs}
            t = {a: tts_curve(cs[a], tgt) for a in cs}
            ratio = t["sa"] / t["mesa"] if math.isfinite(t["sa"]) and math.isfinite(t["mesa"]) else float("nan")
            per[f"{g}@E{E}"] = dict(success_sa=s["sa"], success_mesa=s["mesa"], tts_sa=t["sa"], tts_mesa=t["mesa"], ratio=ratio,
                                     mean_cut_sa=float(cs["sa"][:, -1].mean()), mean_cut_mesa=float(cs["mesa"][:, -1].mean()))
            if g == R1_SCORED:
                q = per[f"{g}@E{E}"]
                if q["success_mesa"] >= 0.90 and q["success_mesa"] >= q["success_sa"] and 1.0 <= q["ratio"] <= 4.0:
                    ok_e.append(E)
    complete = all(f"{R1_SCORED}@E{E}" in per for E in R1B_E)
    return dict(per_graph=per, pass_=(bool(ok_e) if complete else None), passing_E=ok_e)


def eval_r3full(rows: list[dict]) -> dict:
    merged = {}
    for r in rows:
        key = (r["kind"], r["n"], r["inst"])
        m = merged.setdefault(key, dict(kind=r["kind"], n=r["n"], inst=r["inst"]))
        for f in ("best", "ref"):
            if f in r:
                m[f] = r[f]
    full = [m for m in merged.values() if "best" in m and "ref" in m]
    global R3_SIZES
    keep = R3_SIZES
    R3_SIZES = keep + R3X_SIZES
    try:
        return eval_r3(full)
    finally:
        R3_SIZES = keep


EVALS = {"R4b": eval_r4b, "R1b": eval_r1b, "R3full": lambda rows: eval_r3full(rows), "R1": eval_r1, "R2": eval_r2, "R3": eval_r3, "R4": eval_r4}


def evaluate(parts) -> dict:
    sha = prereg_sha()
    res = {}
    for p in parts:
        res[p] = EVALS[p](load("R3") + load("R3x") if p == "R3full" else load(p))
        v = res[p]["pass_"]
        print(f"RESULT P4v2 {p} {'PASS' if v else 'FAIL' if v is not None else 'INCOMPLETE'} prereg_sha256={sha[:16]}", flush=True)
    if "R1" in parts:
        res["R1x_report_only"] = eval_r1x(load("R1x"))
    (OUT / "result.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(res, indent=1, default=float))
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--part", required=True, choices=sorted(RUNNERS))
    r.add_argument("--chunk", default="1/1")
    r.add_argument("--index", type=int, help="run only job number INDEX of the part (0-based)")
    r.add_argument("--smoke", action="store_true", help="tiny budget into OUT/smoke (plumbing check, never scored)")
    e = sub.add_parser("eval")
    e.add_argument("--parts", default="R1,R2,R3,R4")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run_part(a.part, a.chunk, a.index, a.smoke)
    evaluate(a.parts.split(","))
    return 0


if __name__ == "__main__":
    sys.exit(main())
