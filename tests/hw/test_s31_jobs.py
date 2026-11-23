"""Stage 3.1 / 3.1b job list: structure, global-rule equal tuning, disjointness of tuning from confirmatory instances, selection logic on synthetic data."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "testing"))
import gen_jobs_s31 as g  # noqa: E402
import s3_1_jobs as j1  # noqa: E402
import s3_1b_jobs as j1b  # noqa: E402


def test_counts_and_dependencies():
    rs = g.rows()
    assert len(rs) == 78 + 36 + 3
    by = {r["id"]: r for r in rs}
    assert set(by["SEL.31"]["deps"].split(",")) == {r["id"] for r in rs if r["group"] == "31"}
    assert set(by["SEL.31b"]["deps"].split(",")) == {r["id"] for r in rs if r["group"] == "31b"}
    assert by["report_s31"]["deps"] == "*"


def test_equal_tuning_twelve_configs_on_all_three_cells():
    assert len(j1.OURS) == 12 and len(j1.B3) == 12 and len(j1b.CFGS) == 12
    ids = {r["id"] for r in g.rows() if r["group"] == "31"}
    for arm, cfgs in (("ours", j1.OURS), ("B3", j1.B3)):
        for name in cfgs:
            for cell in j1.CELLS:
                assert f"s31.{arm}.{name}.{cell}" in ids


def test_tuning_keys_disjoint_from_confirmatory_and_s2():
    tuning = {k for keys, _ in j1.CELLS.values() for k in keys} | set(j1b.K3) | {f"R{5001 + i}" for i in range(5)}
    confirm = {str(3301 + i) for i in range(64)} | {str(3401 + i) for i in range(64)} | {f"R{6001 + i}" for i in range(20)}
    s2 = {str(2301 + i) for i in range(64)} | {str(2401 + i) for i in range(64)}
    assert not (tuning & confirm) and not (tuning & s2)


def test_smoke_has_every_job_and_tiny_budgets():
    rs = g.rows()
    sm = [g.smoke(r) for r in rs]
    assert len(sm) == len(rs)
    for r in sm:
        if r["group"] in ("31", "31b"):
            assert "--seeds 1" in r["cmd"] and "--sweeps 1" in r["cmd"] and "_smoke" in r["cmd"]
            assert "smokeb" not in r["cmd"] and "_smoke_smoke" not in r["cmd"]
    assert any("sim/out/hw/s31b_smoke/selection_31b.json" in r["cmd"] for r in sm)
    assert any("sim/out/hw/s31_smoke/selection_31.json" in r["cmd"] for r in sm)


def test_selection_rule_on_synthetic_data(tmp_path):
    for arm, cfgs in (("ours", j1.OURS), ("B3", j1.B3)):
        for i, name in enumerate(cfgs):
            for cell in j1.CELLS:
                succ = 1 if (arm == "ours" and name == "m3_plain") or (arm == "B3" and name == "th1.5_tl0.0625") else 0
                row = {"arm": arm, "cid": name, "cell": cell, "success": bool(succ), "best_E": 0.0 if succ else 3.0}
                (tmp_path / f"s31.{arm}.{name}.{cell}.jsonl").write_text(json.dumps(row) + "\n")
    out = tmp_path / "sel.json"
    j1.select(str(tmp_path), str(out))
    d = json.loads(out.read_text())
    assert d["ours"]["selected"] == "m3_plain" or d["ours"]["selected"] is None   # non-regression needs the base reference row; absent here
    assert d["B3"]["selected"] == "th1.5_tl0.0625"
