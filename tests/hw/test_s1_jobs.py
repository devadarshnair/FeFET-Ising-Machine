"""Stage 1 job list (gen_jobs_s1.py): structure, fairness and cost guards."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "testing"))
import gen_jobs_s1 as g  # noqa: E402


def rows():
    return g.build()


def test_gate_is_first_and_gates_every_noisy_960_job():
    rs = rows()
    assert rs[0].id == g.GATE_ID
    noisy = [r for r in rs if r.kind == "run" and r.cond == "nominal" and r.cell in g.GATED]
    assert noisy and all(g.GATE_ID in r.deps.split(",") for r in noisy)


def test_every_arm_has_equal_round1_config_counts():
    rs = [r for r in rows() if r.kind == "run" and r.stage == "1a" and r.rnd == 1]
    n = Counter()
    for r in rs:
        n[(r.arm, r.cell, r.cid)] += 0
    per = Counter((a, c) for a, c, _ in n)
    for cell in ("p3n480", "gk"):
        for arm in ("B3", "kc2c", "none_B1"):
            assert per[(arm, cell)] == 12
        assert 8 <= per[("ours", cell)] <= 12       # ours: 12 labels, aliases of equal L run once


def test_round2_counts_equal():
    import re
    base = {re.sub(r"\.p\d\d$", "", r.id): r.arm for r in rows() if r.stage == "1a" and r.rnd == 2 and ".top" in r.id}
    assert Counter(base.values()) == {"ours": 4, "B3": 4, "kc2c": 4, "none_B1": 4}


def test_dependencies_are_acyclic_and_schedule_completes_within_budget():
    rs = rows()
    sim = g.sim_makespan(rs)
    assert sim["makespan_min"] < 150
    assert g.cost(rs)["rs"] <= 125


def test_gk_rows_are_labelled_tuning_only():
    assert all("TUNING-ONLY" in r.needs for r in rows() if r.cell == "gk" and r.stage in ("1b", "1d"))


def test_smoke_covers_every_job_type():
    rs = rows()
    sm = g.smoke_rows(rs)
    types = lambda xs: {(r.kind, r.arm, r.label, r.mit, r.cond, r.cell, r.tile, r.k, tuple(sorted(r.cfg_over)), bool(r.sel)) for r in xs}  # noqa: E731
    assert types(sm) == types(rs)
