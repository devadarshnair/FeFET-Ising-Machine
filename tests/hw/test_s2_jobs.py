"""Stage 2 job list (gen_jobs_s2.py): keys equal the exclusion-tested instance set; gate first; cost guards."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "testing"))
import gen_jobs_s2 as g  # noqa: E402
import s2_instances as s2  # noqa: E402


def test_job_keys_equal_the_tested_instance_set():
    inst = s2.s2_instances()
    for r in g.rows():
        if r["kind"] == "run":
            assert set(r["keys"]) <= set(inst[r["cell"]]), r["id"]
    for cell in ("p3n480", "p4n480"):
        used = {k for r in g.rows() if r["kind"] == "run" and r["cell"] == cell for k in r["keys"]}
        assert used == set(inst[cell]) and len(used) == 64


def test_gate_first_and_nominal_480_tiled_jobs_depend_on_it():
    rs = g.rows()
    assert rs[0]["id"] == g.GATE_ID
    tiled = [r for r in rs if r["kind"] == "run" and r["tile"]]
    assert tiled and all(r["deps"] == g.GATE_ID for r in tiled)


def test_both_b3_comparators_and_primary_cells_present():
    ids = {(r["arm"], r["cell"], r["cond"]) for r in g.rows() if r["kind"] == "run"}
    for cell in ("p3n480", "p4n480"):
        assert {("B3_sel", cell, "ideal"), ("B3_h8", cell, "ideal"), ("ours_new", cell, "nominal"), ("B1_sel", cell, "nominal")} <= ids


def test_worst_case_cost_on_16_vcpu_within_cap():
    c = g.cost(g.rows())
    assert c[16]["expected_rs"] <= 150
    worst = (20 + 18 + 205 + 5) / 60 * 32.14           # go_s2 caps: set-up 20, gate 18, hard 205 (deadline 190 + 15), collect 5
    assert worst <= 150
