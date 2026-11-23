"""Stage 3.2 job list (gen_jobs_s32.py): keys equal the exclusion-tested instance set; gate first; both B3 comparators; cost guards; evaluator rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "testing"))
import gen_jobs_s32 as g  # noqa: E402
import s3_instances as s3  # noqa: E402


def test_job_keys_equal_the_tested_instance_set():
    inst = s3.s3_instances()
    for cell in ("p3n480", "p4n480", "p3n960", "maxcut"):
        used = {k for r in g.rows() if r["kind"] == "run" and r["cell"] == cell for k in r["keys"]}
        assert used == set(inst[cell]) and len(used) == s3.S3_COUNTS[cell]


def test_gate_first_and_large_tiled_jobs_depend_on_it():
    rs = g.rows()
    assert rs[0]["id"] == g.GATE_ID
    big = [r for r in rs if r["kind"] == "run" and r["tile"] and r["cell"] in ("p3n960", "maxcut")]
    assert big and all(r["deps"] == g.GATE_ID for r in big)


def test_both_b3_comparators_on_every_primary_cell():
    ids = {(r["arm"], r["cell"]) for r in g.rows() if r["kind"] == "run"}
    for cell in s3.S3_COUNTS:
        assert {("ours_stack", cell), ("B3_sel", cell), ("B3_h8", cell)} <= ids


def test_selected_configurations_are_the_stage31_selections():
    assert g.CFG["ours_stack"]["esc_step"] == 1 and g.CFG["ours_stack"]["knob"] == 0.25 and g.CFG["ours_stack"]["sim_refresh"] == 200 and "adaptive_m" not in g.CFG["ours_stack"]
    assert g.CFG["B3_sel"]["t_hi_mult"] == 2.5 and g.CFG["B3_sel"]["t_lo_mult"] == 0.0625
    assert g.MIT["ours_stack"].endswith("scr8")


def test_worst_case_cost_on_16_vcpu_within_cap():
    assert (20 + 8 + 12 + 215 + 6) / 60 * 32.14 <= 150
    assert g.cost(g.rows())[16]["expected_rs"] <= 150


def test_evaluator_decision_rule_and_pricing_defaults():
    import evaluate_s3 as e3
    assert e3.BASE["margin"] == 0.10 and e3.BASE["ours_attrs"]["t1_lcor_k"] == 0 and e3.BASE["strip_scr"] and "t6" in e3.BASE["b3"]
    assert "margin -1 pp" in e3.SENS and "hardware estimates x2" in e3.SENS and "Max-Cut target 0.995" in e3.SENS
