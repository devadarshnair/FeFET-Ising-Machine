"""Stage 2 job enumeration (H2 ladder, H3 grid, H5 variation) = the single source for jobs_stage2.tsv and docs P6.02 budget.

A job = one study / arm / family block of runs (config x instance x seed-block) -> one raw JSON. Runs per job are sized from the
measured timing (plan.LOCAL_RUNNER_US mapped to the Stage 1 cloud chunks, see plan.py) so that every job is planned at <= CHUNK_TARGET_S (a 2x timing error stays
below 1 h). Phase order (barriers are 'all' rows): ref + tune -> select_tuned -> test -> freeze -> h5 + h3.

Usage: python -I scripts/testing/gen_jobs_stage2.py --tsv PATH      write the TSV
       python -I scripts/testing/gen_jobs_stage2.py --summary       CPU-h per sweep (the P6.02 table)
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan as pl  # noqa: E402

CHUNK_TARGET_S = 1500           # < 30 min per job at the measured cloud timing
OUT = "sim/out/hw/stage2"
RSS_GB = {"ours": 0.8, "b1": 0.9, "b1bs": 0.9, "b3": 0.7, "b2": 0.4}
RUN_PY = "$PY -I scripts/testing/run_cell.py"


@dataclass
class Job:
    id: str
    study: str
    phase: str
    arm: str
    family: str
    runs: list                  # tokens "cfg/instance/rlo-rhi"
    secs: float                 # planned seconds (sum)
    extra: str = ""             # additional CLI flags
    mode: str = "par"
    rss: float = 0.8
    n_runs: int = 0

    def command(self) -> str:
        if self.mode == "all":
            return self.extra
        return (f"{RUN_PY} --id {self.id} --study {self.study} --phase {self.phase} --arm {self.arm} --family {self.family} "
                f"--runs {','.join(self.runs)} --out {OUT} {self.extra}").strip()


def machine_of(arm: str) -> str:
    if arm.startswith("@"):
        return {"@ours_best": "ours", "@b1_tuned": "b1"}[arm]
    return pl.Arm.parse(arm).machine


def _chunks(items: list, secs_each: float) -> list[list]:
    per = max(1, int(CHUNK_TARGET_S // max(secs_each, 1e-3)))
    return [items[i:i + per] for i in range(0, len(items), per)]


def _tok(cid: str, inst: str, r: int) -> str:
    return f"{cid}/{inst}/{r}-{r}"


def _merge_tokens(toks: list[tuple]) -> list[str]:
    """(cid, inst, r) in order -> compact "cid/inst/rlo-rhi" tokens (consecutive seeds of one cid/instance merged)."""
    out, cur = [], None
    for cid, inst, r in toks:
        if cur and cur[0] == cid and cur[1] == inst and cur[3] + 1 == r:
            cur[3] = r
        else:
            if cur:
                out.append(cur)
            cur = [cid, inst, r, r]
    if cur:
        out.append(cur)
    return [f"{c}/{i}/{lo}-{hi}" for c, i, lo, hi in out]


def _make(prefix, study, phase, arm, family, toks, secs_each, extra="") -> list[Job]:
    jobs = []
    for k, ch in enumerate(_chunks(toks, secs_each)):
        mach = machine_of(arm)
        jobs.append(Job(f"{prefix}_{k:03d}", study, phase, arm, family, _merge_tokens(ch), secs_each * len(ch), extra,
                        rss=RSS_GB[mach], n_runs=len(ch)))
    return jobs


def s_per_run(arm: str, family: str, sweeps=pl.SWEEPS, perturbed=False) -> float:
    return pl.seconds_per_run(machine_of(arm), family, sweeps, perturbed)


def cfg_ids(arm: str) -> list[str]:
    a = pl.Arm.parse(arm)
    return [c.cid for c in pl.grid("b3" if a.machine == "b3" else "b2" if a.machine == "b2" else a.restart)]


def ref_jobs() -> list[Job]:
    jobs = []
    arm = "ours.kc2.off"
    toks = [("@default", i, r) for i in pl.TEST_SET["maxsat"] for r in range(pl.REF_SEEDS)]
    sw = pl.SWEEPS * pl.REF_SWEEP_MULT
    return _make("ref_maxsat", "ref", "ref", arm, "maxsat", toks, s_per_run(arm, "maxsat", sw), f"--sweeps {sw}")


def tune_jobs() -> list[Job]:
    jobs = []
    for fam in pl.FAMILIES:
        for a in pl.h2_arms(fam):
            toks = [(cid, i, r) for cid in cfg_ids(a.key) for i in pl.TUNE_SET[fam] for r in range(pl.TUNE_SEEDS)]
            jobs += _make(f"tune_{a.key}_{fam}", "h2", "tune", a.key, fam, toks, s_per_run(a.key, fam))
    for L in pl.QKP_LENGTHS:
        toks = [(cid, i, r) for cid in cfg_ids("b2.b2") for i in pl.TUNE_SET["qkp"] for r in range(pl.TUNE_SEEDS)]
        jobs += _make(f"tune_b2.b2_qkp_L{L}", "h2", "tune", "b2.b2", "qkp", toks, s_per_run("b2.b2", "qkp", L), f"--proposals {L}")
    return jobs


def test_jobs() -> list[Job]:
    jobs = []
    for fam in pl.FAMILIES:
        n_seed = pl.TEST_SEEDS[fam]
        for a in pl.h2_arms(fam):
            toks = [("@tuned", i, r) for i in pl.TEST_SET[fam] for r in range(n_seed)]
            jobs += _make(f"test_{a.key}_{fam}", "h2", "test", a.key, fam, toks, s_per_run(a.key, fam))
        toks = [("@default", i, r) for i in pl.TEST_SET[fam] for r in range(n_seed)]
        jobs += _make(f"test_b1.mesa.published_{fam}", "h2", "test", "b1.mesa.published", fam, toks, s_per_run("b1.mesa", fam))
    for L in pl.QKP_LENGTHS:
        toks = [("@tuned", i, r) for i in pl.TEST_SET["qkp"] for r in range(pl.TEST_SEEDS["qkp"])]
        jobs += _make(f"test_b2.b2_qkp_L{L}", "h2", "test", "b2.b2", "qkp", toks, s_per_run("b2.b2", "qkp", L), f"--proposals {L}")
    return jobs


def h5_jobs() -> list[Job]:
    jobs = []
    for fam, n_inst in pl.H5_INSTANCES.items():
        for a in pl.H5_ARMS:
            for pt in pl.H5_POINTS:
                if not pt.evaluable or pt.pid in pl.H5_DUPLICATES:
                    continue
                toks = [("@tuned", i, r) for i in pl.TEST_SET[fam][:n_inst] for r in range(pl.H5_SEEDS)]
                jobs += _make(f"h5_{a.key}_{fam}_{pt.pid}", "h5", "h5", a.key, fam, toks,
                              s_per_run(a.key, fam, perturbed=True), f"--point {pt.pid}")
    return jobs


def h5_extra_jobs() -> list[Job]:
    """T7 sign-magnitude arm (all evaluable non-duplicate points, reported separately); B2 on QKP (device-sigma and read-noise points
    only); one record-only job per non-evaluable point (corners), so the raw directory states why those rows are empty."""
    jobs = []
    for fam, n_inst in pl.H5_INSTANCES.items():
        for a in pl.H5_EXTRA_ARMS:
            for pt in pl.H5_POINTS:
                if not pt.evaluable or pt.pid in pl.H5_DUPLICATES:
                    continue
                toks = [("@tuned", i, r) for i in pl.TEST_SET[fam][:n_inst] for r in range(pl.H5_SEEDS)]
                jobs += _make(f"h5_{a.key}_{fam}_{pt.pid}", "h5", "h5", a.key, fam, toks, s_per_run(a.key, fam, perturbed=True),
                              f"--point {pt.pid}")
    pts = {p.pid: p for p in pl.H5_POINTS}
    L = pl.H5_B2_PROPOSALS
    for pid in pl.H5_B2_POINTS:
        assert pid not in pl.H5_DUPLICATES and pts[pid].evaluable
        toks = [("@tuned", i, r) for i in pl.TEST_SET["qkp"][:pl.H5_B2_INSTANCES] for r in range(pl.H5_SEEDS)]
        jobs += _make(f"h5_b2.b2_qkp_{pid}", "h5", "h5", "b2.b2", "qkp", toks, s_per_run("b2.b2", "qkp", L, perturbed=True),
                      f"--point {pid} --proposals {L}")
    for pt in pl.H5_POINTS:
        if not pt.evaluable:
            jobs.append(Job(f"h5_{pt.pid}_not_evaluable", "h5", "h5", "ours.kc2.i7", "maxcut", [f"@tuned/{pl.TEST_SET['maxcut'][0]}/0-0"], 1.0,
                            f"--point {pt.pid}", rss=RSS_GB["ours"], n_runs=0))
    return jobs


def h3_jobs() -> list[Job]:
    jobs = []
    for fam in ("maxcut", "maxsat"):
        for sel in ("@ours_best", "@b1_tuned"):
            mach = "ours" if sel == "@ours_best" else "b1"
            cells = pl.H3_TRAJ if mach == "ours" else [(0, sg) for sg in pl.H3_SIGMA]     # B1 ADC exact >= 6 bits: delta collapsed
            for dl, sg in cells:
                toks = [("@frozen", i, r) for i in pl.TEST_SET[fam][:pl.H3_INSTANCES] for r in range(pl.H3_SEEDS)]
                jobs += _make(f"h3_{sel[1:]}_{fam}_d{dl}_s{sg:g}", "h3", "h3", sel, fam, toks,
                              s_per_run("ours.x" if mach == "ours" else "b1.mesa", fam), f"--sigma {sg} --adc {dl}")
    return jobs


def barrier(job_id: str, command: str) -> Job:
    return Job(job_id, "", "", "", "", [], 60, command, mode="all", rss=1.0)


def all_jobs() -> list[Job]:
    def lpt(js):
        return sorted(js, key=lambda j: -j.secs)
    ev = f"$PY -I scripts/testing/evaluate_h2.py"
    return (lpt(ref_jobs() + tune_jobs())
            + [barrier("select_tuned", f"{ev} --select --raw {OUT} --out {OUT}/tuned.json")]
            + lpt(test_jobs())
            + [barrier("freeze_h2", f"{ev} --freeze --raw {OUT} --out {OUT}/frozen.json")]
            + lpt(h5_jobs() + h5_extra_jobs() + h3_jobs()))


def sweep_of(job: Job) -> str:
    return {"ref": "H0/ref", "tune": "H2 tune", "test": "H2", "h5": "H5", "h3": "H3"}.get(job.phase, "")


def cpu_hours() -> dict:
    tot: dict = {}
    for j in all_jobs():
        if j.mode == "all":
            continue
        key = {"ref": "ref", "tune": "H2", "test": "H2", "h5": "H5", "h3": "H3"}[j.phase]
        tot[key] = tot.get(key, 0.0) + j.secs / 3600
    return tot


def write_tsv(path: Path) -> int:
    jobs = all_jobs()
    lines = ["# id\tmode\trss_gb\test_min\ttimeout_min\tcommand (run in the worktree; $PY, $NP expanded by run_job.sh)",
             "# mode par = one process per slot, many at once; all = run alone. Order = run order; 'all' rows are barriers "
             "(select_tuned, freeze_h2). LPT order inside each phase."]
    for j in jobs:
        est = max(1, math.ceil(j.secs / 60))
        tmo = 20 if j.mode == "all" else max(60, math.ceil(est * 2.5) + 5)
        lines.append(f"{j.id}\t{j.mode}\t{j.rss}\t{est}\t{tmo}\t{j.command()}")
    path.write_text("\n".join(lines) + "\n")
    return len(jobs)


def smoke_types() -> list[dict]:
    """One representative job per distinct (study, phase, arm, family) / H5 point: the `--smoke` matrix of run_cell."""
    seen, out = set(), []
    for j in all_jobs():
        if j.mode == "all":
            continue
        key = (j.study, j.phase, j.arm, j.family, j.extra.split(" --proposals")[0] if j.phase == "h5" else "")
        if key in seen:
            continue
        seen.add(key)
        out.append({"job": j, "first_run": j.runs[0]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.tsv:
        print(f"wrote {write_tsv(a.tsv)} rows to {a.tsv}")
    if a.summary:
        jobs = [j for j in all_jobs() if j.mode == "par"]
        print({k: round(v, 1) for k, v in cpu_hours().items()}, "total", round(sum(j.secs for j in jobs) / 3600, 1),
              "jobs", len(jobs), "max job min", round(max(j.secs for j in jobs) / 60, 1))


if __name__ == "__main__":
    main()
