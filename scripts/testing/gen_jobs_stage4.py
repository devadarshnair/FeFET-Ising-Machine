"""Stage 4 (H7, prereg/hw/H7_scaleup.md DRAFT) job enumeration = the single source for jobs_stage4.tsv and the H7 budget.

Phases: test (H7 TEST: hardware arms + software references) + ref (TabuCol 20x, solvability) + var (H7-V variation) -> report_h7
(barrier, runs only when every earlier row has a done marker). No tuning phase: every config is a frozen Stage 2/3 selection.
Per-run seconds: local timings (16 Nov IST, loaded WSL, 960-spin p3n960 at 3 sweeps scaled to 150) x 1.5 margin x
plan.CLOUD_OVER_LOCAL, scaled to other sizes by spins x padded lanes (field cost per step ~ lanes). Jobs <= CHUNK_TARGET_S.

Usage: python -I scripts/testing/gen_jobs_stage4.py --tsv PATH | --summary
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan as pl  # noqa: E402
import plan_h7 as p7  # noqa: E402
from gen_jobs_stage3 import Job, _merge  # noqa: E402

CHUNK_TARGET_S = 1500
OUT = "sim/out/hw/stage4"
RSS_GB = {"ours": 1.0, "b1": 1.2, "b3": 0.8, "sw": 0.6}
LOCAL_S_960 = {"ours.kc2.fs.i11": 46.0, "ours.none.fs": 35.0, "b1.none.fs": 174.0, "b1.mesa.fs": 149.0, "b3.b3": 27.0,
               "sw.dsatur": 2.0, "sw.tabucol": 2.0, "sw.sa": 3.0}
MARGIN = 1.5
PERT_FACTOR = 26.3 / 18.2       # Stage 2 measured perturbed / unperturbed ours (Max-Cut)
REF_FACTOR = p7.TABU_REF_IPV / p7.TABU_IPV
GATE_CPU_H = 12.0
TAIL_FACTOR = 1.15
RS_PER_VCPU_H = 2.01
CAP_RS = 150                    # spend cap for Stage 4 (about Rs 180 left)


def s_per_run(arm: str, family: str, inst: str, pert: bool = False, ref: bool = False, sweeps: int = p7.SWEEPS) -> float:
    s = p7.spins(family, inst)
    lanes = max(4, 1 << (s - 1).bit_length())
    base = LOCAL_S_960[arm] * MARGIN * pl.CLOUD_OVER_LOCAL
    scale = 1.0 if arm.startswith("sw.") else s * lanes / (960 * 1024)
    return max(0.5, base * scale * (PERT_FACTOR if pert else 1.0) * (REF_FACTOR if ref else 1.0) * sweeps / p7.SWEEPS)


def _make(prefix, study, phase, arm, family, toks, secs_each, extra) -> list[Job]:
    per = max(1, int(CHUNK_TARGET_S // max(secs_each, 1e-3)))
    m = arm.split(".")[0]
    return [Job(f"{prefix}_{k // per:03d}", study, phase, arm, family, _merge(toks[k:k + per]), secs_each * len(toks[k:k + per]), extra,
                rss=RSS_GB[m], n_runs=len(toks[k:k + per]), out=OUT) for k in range(0, len(toks), per)]


def test_jobs() -> list[Job]:
    jobs = []
    for fam in p7.FAMILIES:
        for unit in ([None] if fam != "dimacs" else p7.TEST_SET[fam]):        # dimacs: one budget per graph -> jobs per graph
            insts = p7.TEST_SET[fam] if unit is None else [unit]
            for a in p7.test_arms(fam, unit):
                seeds = 1 if a.arm == "sw.dsatur" else p7.test_seeds(fam)    # DSATUR is deterministic: one run per instance
                toks = [("h7", i, r) for i in insts for r in range(seeds)]
                S = p7.sweeps_of(fam, unit)
                secs = max(s_per_run(a.arm, fam, i, sweeps=S) for i in insts)
                sw = f" --sweeps {S}" if S != p7.SWEEPS else ""
                tag = fam if unit is None else f"{fam}_{unit}"
                jobs += _make(f"x7_{a.label}_{tag}", "h7", "test", a.arm, fam, toks, secs, f"--h7-cfg {a.cfg}{sw}")
    return jobs


def ref_jobs() -> list[Job]:
    jobs = []
    a = p7.SW_REF
    for fam in p7.FAMILIES:
        toks = [("h7", i, r) for i in p7.TEST_SET[fam] for r in range(p7.TABU_REF_SEEDS)]
        jobs += _make(f"r7_{a.label}_{fam}", "h7", "ref", a.arm, fam, toks, s_per_run(a.arm, fam, p7.TEST_SET[fam][0], ref=True),
                      f"--h7-cfg {a.cfg}")
    return jobs


def var_jobs() -> list[Job]:
    jobs = []
    for fam in p7.V_FAMILIES:
        insts = p7.TEST_SET[fam][:p7.V_INSTANCES]
        for a in p7.V_ARMS:
            for pt in p7.v_points():
                toks = [("h7", i, r) for i in insts for r in range(p7.V_SEEDS)]
                jobs += _make(f"v7_{a.label}_{fam}_{pt.pid}", "h7v", "var", a.arm, fam, toks,
                              s_per_run(a.arm, fam, insts[0], pert=True), f"--h7-cfg {a.cfg} --point {pt.pid}")
    return jobs


def barrier(job_id: str, command: str) -> Job:
    return Job(job_id, "", "", "", "", [], 60, command, mode="all", rss=1.5)


def all_jobs() -> list[Job]:
    ev = "$PY -I scripts/testing/evaluate_h7.py"
    par = sorted(test_jobs() + ref_jobs() + var_jobs(), key=lambda j: -j.secs)
    return par + [barrier("report_h7", f"{ev} --raw {OUT} --out {OUT}/h7_report.json")]


def smoke_types() -> list[Job]:
    seen, out = set(), []
    for j in all_jobs():
        if j.mode == "all" or j.runs[0].split("/")[1] != p7.TEST_SET[j.family][0]:
            continue                # smoke every arm on the family's first instance, so the smoke barrier sees complete instances
        key = (j.study, j.phase, j.arm, j.family if j.family == "dimacs" else j.family[:2], "--point" in j.extra.split())
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
             "# Stage 4 (H7, DRAFT prereg until frozen by commit). mode par = one process per slot; all = barrier (report_h7). LPT order."]
    for j in jobs:
        est = max(1, math.ceil(j.secs / 60))
        tmo = 60 if j.mode == "all" else max(60, math.ceil(est * 2.5) + 5)
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
