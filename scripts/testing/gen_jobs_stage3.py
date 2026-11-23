"""Stage 3 (H6, prereg/hw/H6_followup.md) job enumeration = the single source for jobs_stage3.tsv and the H6 budget.

Phases (barriers are 'all' rows): tune (restart-threshold sweep on the H6 TUNE split) -> select_h6 -> test (H6 TEST split) + h5
-> report_h6. Per-run seconds: Stage 2 measured cloud times (plan_h6.S_PER_RUN) and, for col3p/col4p, a local timing mapped with
plan.CLOUD_OVER_LOCAL. Jobs are planned at <= CHUNK_TARGET_S.

Usage: python -I scripts/testing/gen_jobs_stage3.py --tsv PATH | --summary
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan as pl  # noqa: E402
import plan_h6 as p6  # noqa: E402

CHUNK_TARGET_S = 1500
OUT = "sim/out/hw/stage3"
RSS_GB = {"ours": 0.8, "b1": 0.9, "b3": 0.7, "b2": 0.4}
RUN_PY = "$PY -I scripts/testing/run_cell.py"
# col3p / col4p (120 spins, 128 lanes): local runner s/run at 150 sweeps (scripts/testing/run_cell.py, 16 Nov IST, loaded WSL host)
LOCAL_COL_S = {"ours": 2.0, "b1": 3.6, "b3": 1.2}   # measured 1.33 / 2.40 / 0.77 s (col4p, 2 runs) x 1.5 margin
GATE_CPU_H = 12.0              # setup (conda eda + verilator) + Stage 0 gate (tests/hw incl. RTL spot check, smoke_all, H6 smoke), 32 vCPU wall
TAIL_FACTOR = 1.15             # packing/tail inefficiency on 32 vCPU
RS_PER_VCPU_H = 2.01


@dataclass
class Job:
    id: str
    study: str
    phase: str
    arm: str
    family: str
    runs: list
    secs: float
    extra: str = ""
    mode: str = "par"
    rss: float = 0.8
    n_runs: int = 0
    out: str = OUT                  # raw-output directory of this job (Stage 4 passes its own; never inherit another stage's)

    def command_argv(self) -> list[str]:
        return (["--id", self.id, "--study", self.study, "--phase", self.phase, "--arm", self.arm, "--family", self.family,
                 "--runs", ",".join(self.runs), "--out", self.out] + self.extra.split())

    def command(self) -> str:
        if self.mode == "all":
            return self.extra
        return f"{RUN_PY} " + " ".join(self.command_argv())


def machine_of(arm: str) -> str:
    return pl.Arm.parse(arm).machine


def s_per_run(arm: str, family: str, sweeps: float = p6.SWEEPS, pert: bool = False) -> float:
    a = pl.Arm.parse(arm)
    m = a.machine
    if m == "b2":
        return pl.seconds_per_run("b2", "qkp", sweeps, pert)
    if family == "maxcut":
        key = ("ours_pert" if pert else "ours_i11" if a.tweak == "i11" else "ours") if m == "ours" else m
        base = p6.S_PER_RUN[(key, "maxcut")]
        if pert and m == "b1":
            base *= p6.S_PER_RUN[("ours_pert", "maxcut")] / p6.S_PER_RUN[("ours", "maxcut")]   # B1 perturbed: not measured; ours' ratio
    else:
        base = LOCAL_COL_S[m] * pl.CLOUD_OVER_LOCAL
    return base * sweeps / p6.SWEEPS


def _merge(toks: list[tuple]) -> list[str]:
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


def _make(prefix, study, phase, arm, family, toks, secs_each, extra) -> list[Job]:
    per = max(1, int(CHUNK_TARGET_S // max(secs_each, 1e-3)))
    jobs = []
    for k in range(0, len(toks), per):
        ch = toks[k:k + per]
        jobs.append(Job(f"{prefix}_{k // per:03d}", study, phase, arm, family, _merge(ch), secs_each * len(ch), extra,
                        rss=RSS_GB[machine_of(arm)], n_runs=len(ch)))
    return jobs


def tune_jobs() -> list[Job]:
    import json
    t2 = json.loads((pl_repo() / p6.TUNED_STAGE2).read_text())["tuned"]
    jobs = []
    for fam in p6.FAMILIES:
        for arm in p6.SWEEP_ARMS:
            base = t2["colouring" if fam.startswith("col") else fam][p6.SWEEP_BASE[arm]]
            for c in p6.sweep_configs(pl.Arm.parse(arm).restart, base):
                toks = [("h6", i, r) for i in p6.TUNE_SET[fam] for r in range(p6.TUNE_SEEDS)]
                jobs += _make(f"t6_{arm}_{fam}_{c['cid']}", "h6", "tune", arm, fam, toks, s_per_run(arm, fam),
                              f"--h6-cfg grid:{arm}@{c['cid']}")
    return jobs


def test_jobs() -> list[Job]:
    jobs = []
    for fam in p6.FAMILIES:
        for a in p6.test_arms(fam):
            toks = [("h6", i, r) for i in p6.TEST_SET[fam] for r in range(p6.TEST_SEEDS[fam])]
            sw = f" --sweeps {a.sweeps}" if a.sweeps != p6.SWEEPS else ""
            jobs += _make(f"x6_{a.label}_{fam}", "h6", "test", a.arm, fam, toks, s_per_run(a.arm, fam, a.sweeps),
                          f"--h6-cfg {a.cfg}{sw}")
    return jobs


def h5_jobs() -> list[Job]:
    jobs = []
    fam = p6.H5_FAMILY
    insts = p6.TEST_SET[fam][:p6.H5_INSTANCES]
    for a in p6.H5_ARMS + (p6.H5_B1,):
        for pt in p6.h5_arm_points(a):
            toks = [("h6", i, r) for i in insts for r in range(p6.H5_SEEDS)]
            jobs += _make(f"h56_{a.label}_{pt.pid}", "h6h5", "h5", a.arm, fam, toks, s_per_run(a.arm, fam, pert=True),
                          f"--h6-cfg {a.cfg} --point {pt.pid}")
    L = pl.H5_B2_PROPOSALS
    for pid in pl.H5_B2_POINTS:
        toks = [("h6", i, r) for i in pl.TEST_SET["qkp"][:p6.H5_B2_INSTANCES]
                for r in range(p6.H5_B2_R0, p6.H5_B2_R0 + p6.H5_B2_SEEDS)]
        jobs += _make(f"h56_b2_{pid}", "h6h5", "h5", "b2.b2", "qkp", toks, s_per_run("b2.b2", "qkp", L, True),
                      f"--h6-cfg tuned:b2.b2@{L} --point {pid} --proposals {L}")
    return jobs


def pl_repo() -> Path:
    return HERE.parents[1]


def barrier(job_id: str, command: str) -> Job:
    return Job(job_id, "", "", "", "", [], 60, command, mode="all", rss=1.0)


def all_jobs() -> list[Job]:
    def lpt(js):
        return sorted(js, key=lambda j: -j.secs)
    ev = "$PY -I scripts/testing/evaluate_h6.py"
    return (lpt(tune_jobs())
            + [barrier("select_h6", f"{ev} --select --raw {OUT} --out {OUT}/h6_sweep.json")]
            + lpt(test_jobs() + h5_jobs())
            + [barrier("report_h6", f"{ev} --report --raw {OUT} --out {OUT}/h6_report.json")])


def smoke_types() -> list[Job]:
    seen, out = set(), []
    for j in all_jobs():
        if j.mode == "all":
            continue
        ex = j.extra.split()
        key = (j.phase, j.arm, j.family, ex[1].split("@")[0] if ex else "", "--point" in ex, "--sweeps" in ex)
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out


def budget() -> dict:
    tot: dict = {}
    for j in all_jobs():
        if j.mode == "par":
            tot[j.phase] = tot.get(j.phase, 0.0) + j.secs / 3600
    jobs_h = sum(tot.values())
    billed = jobs_h * TAIL_FACTOR + GATE_CPU_H
    return {"cpu_h_by_phase": {k: round(v, 2) for k, v in tot.items()}, "jobs_cpu_h": round(jobs_h, 2),
            "billed_vcpu_h_incl_gate": round(billed, 1), "rs": round(billed * RS_PER_VCPU_H), "wall_h_32vcpu": round(billed / 32, 2)}


def write_tsv(path: Path) -> int:
    jobs = all_jobs()
    lines = ["# id\tmode\trss_gb\test_min\ttimeout_min\tcommand (run in the worktree; $PY, $NP expanded by run_job.sh)",
             "# Stage 3 (H6). mode par = one process per slot; all = barrier run alone (select_h6, report_h6). LPT order per phase."]
    for j in jobs:
        est = max(1, math.ceil(j.secs / 60))
        tmo = 30 if j.mode == "all" else max(60, math.ceil(est * 2.5) + 5)
        lines.append(f"{j.id}\t{j.mode}\t{j.rss}\t{est}\t{tmo}\t{j.command()}")
    path.write_text("\n".join(lines) + "\n")
    return len(jobs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.tsv:
        print(f"wrote {write_tsv(a.tsv)} rows to {a.tsv}")
    if a.summary:
        js = [j for j in all_jobs() if j.mode == "par"]
        print(budget(), "jobs", len(js), "max job min", round(max(j.secs for j in js) / 60, 1))


if __name__ == "__main__":
    main()
