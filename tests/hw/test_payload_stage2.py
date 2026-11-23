"""Barrier and STAGE0_GREEN handling of the cloud payload's run_stage2.sh, on a throw-away root with fake jobs (no experiment code runs).

The payload lives outside the git tree (00_admin/cloud_cpu/payload); PAYLOAD_DIR overrides the default location, and the tests skip if it is absent.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PAYLOAD = Path(os.environ.get("PAYLOAD_DIR", Path(__file__).resolve().parents[4] / "00_admin/cloud_cpu/payload"))
pytestmark = pytest.mark.skipif(not (PAYLOAD / "run_stage2.sh").exists(), reason="payload directory not available")


@pytest.fixture()
def box(tmp_path):
    root = tmp_path / "md"
    wt = root / "hw_wt/hw-p5b"
    wt.mkdir(parents=True)
    git = ["git", "-C", str(wt)]
    subprocess.run(git + ["init", "-q"], check=True)
    (wt / "f.txt").write_text("x")
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], check=True)
    pay = tmp_path / "payload"
    pay.mkdir()
    for f in ("common.sh", "run_job.sh", "run_stage2.sh"):
        shutil.copy(PAYLOAD / f, pay / f)
    (pay / "collect.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    flag, log = tmp_path / "flag", tmp_path / "barrier_runs"
    rows = ["# header", f"a\tpar\t1\t1\t1\ttest -e {flag}", "b\tpar\t1\t1\t1\ttrue",
            f"bar\tall\t1\t1\t1\techo run >> {log}", "c\tpar\t1\t1\t1\ttrue"]
    (pay / "jobs_stage2.tsv").write_text("\n".join(rows) + "\n")
    env = dict(os.environ, MD_ROOT=str(root), NP="2", PATH=os.environ["PATH"])
    run = root / "00_admin/cloud_cpu_run"
    (run / "done").mkdir(parents=True)
    (run / "SETUP_OK").write_text("ok")
    head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

    def go():
        return subprocess.run(["bash", str(pay / "run_stage2.sh")], env=env, capture_output=True, text=True)
    return dict(go=go, run=run, flag=flag, log=log, head=head)


def test_refuses_without_stage0_green(box):
    assert box["go"]().returncode == 2


def test_refuses_stage0_green_of_another_commit(box):
    (box["run"] / "STAGE0_GREEN").write_text("0" * 40)
    assert box["go"]().returncode == 2


def test_barrier_waits_for_all_earlier_jobs_then_reruns_each_resume(box):
    (box["run"] / "STAGE0_GREEN").write_text(box["head"])
    box["go"]()
    assert not (box["run"] / "done/a").exists() and (box["run"] / "done/b").exists()
    assert not box["log"].exists() and not (box["run"] / "done/bar").exists() and not (box["run"] / "done/c").exists()
    box["flag"].write_text("")                                                   # job a now succeeds
    box["go"]()
    assert box["log"].read_text().count("run") == 1 and (box["run"] / "done/c").exists()
    box["go"]()                                                                  # a plain resume recomputes the barrier from the full data
    assert box["log"].read_text().count("run") == 2
    assert (box["run"] / "STAGE2_DONE").exists()
