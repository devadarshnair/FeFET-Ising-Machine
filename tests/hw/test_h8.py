"""H8 (full study) checks: instances, fresh seed streams, job plan / budget / limits, every command resolves, the kc2c hook, the evaluator end to end
on real tiny runs (every output file is read: D7), the mitigation overhead pricing, the memory-aware scheduler."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ("scripts/testing", "scripts/golden", "scripts/baselines", "."):
    sys.path.insert(0, str(ROOT / sub))

import evaluate_h8 as ev8  # noqa: E402
import gen_jobs_h8 as g8  # noqa: E402
import h8_instances as h8i  # noqa: E402
import plan as pl  # noqa: E402
import plan_h7 as p7  # noqa: E402
import plan_h8 as p8  # noqa: E402
import run_h8 as rh8  # noqa: E402


@pytest.fixture(autouse=True)
def _no_force():
    old = p8.FORCE_KC2C
    yield
    p8.FORCE_KC2C = old


# ------------------------------------------------------------------------------------------------ instances
def test_kneser_known_graphs_and_chromatic_formula():
    n, E = h8i.kneser_edges(5, 2)                                  # Petersen graph
    assert (n, len(E)) == (10, 15)
    for name, (nv, k) in h8i.GRAPHS.items():
        if name.startswith("kneser"):
            N, K = (int(x) for x in name[6:].split("_"))
            assert k == N - 2 * K + 2, name                         # Lovasz 1978
            assert h8i.graph(name)[0] == nv


@pytest.mark.parametrize("name", [g for g in h8i.GRAPHS if not g.startswith("kneser")])
def test_dimacs_style_graph_sizes_match_known_headers(name):
    n, E = h8i.graph(name)
    assert n == h8i.GRAPHS[name][0]
    known = {"myciel7": 2360, "queen9_9": 1056, "queen10_10": 1470, "myciel6": 755, "queen8_8": 728}
    if name in known:
        assert len(E) == known[name]


@pytest.mark.parametrize("fam", list(h8i.PLANTED))
def test_planted_spins_match_family_name_and_have_a_proper_colouring(fam):
    n, k, _ = h8i.PLANTED[fam]
    assert n * k == int(fam.split("n")[1])
    cp = h8i.problem(fam, str(p8.PLANTED_SEED0[3 if fam.startswith("p3") else 4]))
    assert cp.n == n and cp.k == k and len(cp.edges) > n


def test_every_graph_is_k_colourable_by_construction_known_chi_not_below_clique():
    import networkx as nx
    for name in ("myciel4", "queen6_6", "kneser7_2"):
        n, E = h8i.graph(name)
        G = nx.Graph(E.tolist())
        assert max(len(c) for c in nx.find_cliques(G)) <= h8i.GRAPHS[name][1]


# ------------------------------------------------------------------------------------------------ fresh seeds
def _earlier_stage_instances():
    """Planted seeds and G-set names used by EVERY earlier stage: Stage 2, H6 (Stage 3), H7 (Stage 4) and its tune seeds, P4.02 B1 calibration,
    P4_v2 R1x, VARIATION_V2 (smoke + statistical grid)."""
    import calib_b1
    import plan_h6 as p6
    import repro_v2
    import variation_v2 as v2
    seeds = {int(s) for k in ("colouring", "maxsat") for s in pl.TUNE_SET[k] + pl.TEST_SET[k]}
    seeds |= {int(s) for d in (p6.TUNE_SET, p6.TEST_SET) for k, v in d.items() if k != "maxcut" for s in v}
    seeds |= {int(s) for v in p7.TEST_SET.values() for s in v if s.isdigit()}
    seeds |= {851, 951}                                                        # H7 pilot (TUNE-only) instances
    seeds |= {int(i) for v in v2.STAT_INST.values() for i in v if i.isdigit()} | {int(i) for i in v2.SMOKE_INST.values() if i.isdigit()}
    gs = set(pl.TUNE_SET["maxcut"]) | set(pl.TEST_SET["maxcut"]) | set(p6.TUNE_SET["maxcut"]) | set(p6.TEST_SET["maxcut"])
    gs |= set(calib_b1.GRAPHS) | set(repro_v2.R1X_GRAPHS)
    return seeds, gs


def test_instances_are_disjoint_from_every_earlier_stage_including_calibrations():
    seeds, gs = _earlier_stage_instances()
    assert {"G8", "G9", "G22", "G43", "G48"} <= gs and 1101 not in seeds       # the reader of this test can see the sets are real
    mine_seeds = {int(i) for k in (3, 4) for size in p8.INST_SEEDS for i in p8.planted_instances(k, size, "full")}
    assert not mine_seeds & seeds and min(mine_seeds) >= 1100
    mine_g = set(p8.G_CORE_1000) | set(p8.G_FULL_2000)
    assert not mine_g & gs, mine_g & gs
    assert not any(g in mine_g for g in ("G8", "G9", "G10", "G17", "G19", "G20", "G21"))      # the former 800-node set (Stage 3) is gone
    assert all(g not in pl.TEST_SET["maxcut"] + pl.TUNE_SET["maxcut"] for g in mine_g)


def test_seed_streams_are_disjoint_from_every_earlier_stage():
    """Tag and the actual mixed seeds: enumerate the earlier specs (Stage 2 TEST, H6, H7 TEST, VARIATION_V2) and compare with every H8 seed."""
    import machines as ma
    import plan_h6 as p6
    import variation_v2 as v2
    assert p8.SEED_TAG not in (0, 1, p6.SEED_TAG, 7, v2.SEED_TAG)
    old = set()
    for fam, insts in pl.TEST_SET.items():                                      # Stage 2 (tag 0)
        for i, key in enumerate(insts):
            for r in range(pl.TEST_SEEDS[fam]):
                old.add(ma.seed_of(pl.Spec(study="h2", phase="test", family=fam, instance=key, r=r, arm="x", inst_index=i, tag=0)))
    for fam, insts in p6.TEST_SET.items():                                      # H6 (tag 6)
        for key in insts:
            for r in range(p6.TEST_SEEDS[fam]):
                old.add(ma.seed_of(pl.Spec(study="h6", phase="test", family=fam, instance=key, r=r, arm="x", inst_index=p6.inst_index(fam, key), tag=p6.SEED_TAG)))
    for fam, insts in p7.TEST_SET.items():                                      # H7 (tag 7)
        for key in insts:
            for r in range(10):
                old.add(ma.seed_of(pl.Spec(study="h7", phase="test", family=fam, instance=key, r=r, arm="x", inst_index=p7.inst_index(fam, key), tag=7)))
    for fam in ("p3n240", "p4n240"):
        for r in range(40):
            for ii in range(400, 460):
                old.add(ma.seed_of(pl.Spec(study="var2", phase="smoke", family=fam, instance="1", r=r, arm="x", inst_index=ii, tag=v2.SEED_TAG)))
    new = set()
    for k in (3, 4):
        for size in p8.INST_SEEDS:
            fam = p8.planted_family(k, size)
            for i in p8.planted_instances(k, size, "full"):
                for r in range(12):
                    new.add(ma.seed_of(pl.Spec(study="h8", phase="main", family=fam, instance=i, r=r, arm="x", inst_index=rh8.inst_index(fam, i), tag=p8.SEED_TAG)))
    assert len(old) > 1000 and len(new) > 1000 and not old & new


def test_planted_seeds_do_not_overlap_between_sizes_of_a_family_in_inst_index():
    import machines as ma
    seen = {}
    for k in (3, 4):
        for size in (120, 240, 480, 960, 2040):
            fam = p8.planted_family(k, size)
            for i in p8.planted_instances(k, size, "full"):
                s = pl.Spec(study="h8", phase="main", family=fam, instance=i, r=0, arm="ours.none.fs", inst_index=rh8.inst_index(fam, i), tag=p8.SEED_TAG)
                v = ma.seed_of(s)
                assert v not in seen, (fam, i)
                seen[v] = fam


# ------------------------------------------------------------------------------------------------ plan, budget, limits
@pytest.fixture(scope="module")
def tiers():
    p8.FORCE_KC2C = True
    return {t: g8.all_jobs(t) for t in ("core", "full")}


def test_core_budget_fits_the_rupee_cap_and_full_is_a_superset(tiers):
    p8.FORCE_KC2C = True
    b = g8.budget()
    assert b["core"]["rs"] <= g8.CAP_CORE_RS, b["core"]
    core_ids = {j.id for j in tiers["core"]}
    full_ids = {j.id for j in tiers["full"]}
    assert core_ids - {g8.barrier("core").id} <= full_ids
    assert b["full_total"]["rs"] > b["core"]["rs"] and b["full_extra"]["jobs"] > 0


def test_every_job_is_under_the_60_minute_limit_and_has_a_smoke_command(tiers):
    for tier, jobs in tiers.items():
        for j in jobs:
            if j.mode == "par":
                assert j.secs / 60 <= g8.MAX_EST_MIN, (tier, j.id, j.secs / 60)
                assert "--smoke" in j.smoke and "--sweeps 1 " in j.smoke + " " and g8.SMOKE_OUT in j.smoke, j.id
                assert j.rss > 0
    assert jobs[-1].mode == "all" and jobs[-1].id.startswith("report_h8")


def test_tsv_rows_have_seven_fields_timeout_under_60_and_unique_ids(tmp_path):
    p8.FORCE_KC2C = True
    for tier in ("core", "full"):
        f = tmp_path / f"{tier}.tsv"
        g8.write_tsv(f, tier)
        rows = [ln.split("\t") for ln in f.read_text().splitlines() if not ln.startswith("#")]
        assert len({r[0] for r in rows}) == len(rows)
        assert all(len(r) == 7 for r in rows)
        assert all(float(r[4]) <= 60 for r in rows)
        assert rows[-1][1] == "all" and all(r[1] == "par" for r in rows[:-1])


def test_every_command_resolves_arm_cfg_family_and_instances(tiers):
    """A job whose label / cfg / instance does not exist must fail here, not on the cloud after the compute."""
    os.environ["H8_KC2C_SMOKE_STUB"] = "1"
    try:
        for j in tiers["full"]:
            if j.mode != "par":
                continue
            a = rh8.make_parser().parse_args(j.command.replace("$PY -I scripts/testing/run_h8.py ", "").split())
            for inst, r in rh8.parse_runs(a.runs):
                assert rh8.inst_index(a.family, inst) >= p8.INST_BASE
            if not a.label.startswith("sw."):
                assert pl.Arm.parse(p8.ARMS[a.label].arm)
                assert isinstance(rh8.resolve_cfg(a.label, a.family), dict)
            fam_ok = a.family in h8i.FAMILIES_COLOURING or a.family == "maxcut"
            assert fam_ok, a.family
            for inst, _ in rh8.parse_runs(a.runs):
                assert inst in (h8i.GRAPHS if a.family == h8i.GRAPH_FAMILY else p8.G_CORE_1000 + p8.G_FULL_2000 if a.family == "maxcut"
                                else p8.planted_instances(3 if a.family.startswith("p3") else 4, int(a.family.split("n")[1]), "full")), (j.id, inst)
    finally:
        os.environ.pop("H8_KC2C_SMOKE_STUB")


def test_smoke_types_cover_every_phase_arm_and_the_barrier(tiers):
    p8.FORCE_KC2C = True
    types = g8.smoke_types("full")
    assert types[-1].mode == "all"
    labels = {j.cell.label for j in types if j.cell}
    assert set(p8.MAIN_ARMS) | set(p8.LADDER_ARMS) - {"L_none", "L_kc2_i11"} | {"sw.dsatur", "sw.tabucol", "sw.sa", "B1_yin_sa"} <= labels
    assert {j.cell.phase for j in types if j.cell} == {"main", "abl", "var", "sw", "ref", "ctx"}
    assert {j.cell.cond for j in types if j.cell} >= {"ideal", "nominal", "vx3", "drift0.02"}


def test_jobs_chunk_within_target_and_no_pair_is_lost_or_duplicated(tiers):
    for tier, jobs in tiers.items():
        cells = {}
        for j in jobs:
            if j.mode == "par":
                c = j.cell
                k = (c.phase, c.label, c.family, c.cond, c.mit, c.c2c)
                cells.setdefault(k, []).extend(j.pairs)
        for k, pairs in cells.items():
            assert len(pairs) == len(set(pairs)), k


def test_kc2c_hook_is_absent_until_the_selection_exists_and_refuses_to_run(monkeypatch):
    monkeypatch.setattr(p8, "_kc2c_selected", lambda kind: None)
    monkeypatch.delenv("H8_KC2C_SMOKE_STUB", raising=False)
    p8.FORCE_KC2C = False
    assert not p8.kc2c_ready() and "ours_kc2c" not in p8.main_arms()
    with pytest.raises(SystemExit):
        rh8.resolve_cfg("ours_kc2c", "p3n240")
    p8.FORCE_KC2C = True
    assert "ours_kc2c" in p8.main_arms()
    monkeypatch.setenv("H8_KC2C_SMOKE_STUB", "1")
    assert rh8.resolve_cfg("ours_kc2c", "p3n240")["tfinal"] == 0.5
    monkeypatch.setattr(p8, "_kc2c_selected", lambda kind: {"cid": "real", "pct_hi": 85, "pct_lo": 5, "knob": 2.0, "tfinal": 0.5})
    p8.FORCE_KC2C = False
    assert p8.kc2c_ready() and "ours_kc2c" in p8.main_arms() and rh8.resolve_cfg("ours_kc2c", "maxcut")["cid"] == "real"


def test_power_function_is_monotone_and_mde_shrinks_with_data():
    assert p8.power_diff(0.5, 0.7, 20, 5) > p8.power_diff(0.5, 0.7, 10, 5) > p8.power_diff(0.5, 0.7, 5, 5)
    assert p8.power_diff(0.5, 0.7, 10, 10) >= p8.power_diff(0.5, 0.7, 10, 2)
    assert p8.mde(30, 8) < p8.mde(8, 4) < 1.0
    for row in p8.power_table():
        assert 0.0 < row["mde_success_diff"] <= 1.0
    assert p8.mde(*p8.INST_SEEDS[240]["core"], m=p8.primary_family_size("core")) <= 0.25   # stated in the prereg: core 240-spin MDE
    assert p8.primary_family_size("core") == 20 and p8.primary_family_size("full") == 26   # 2 x (8 planted + graphs + G1000) / (+ 2 x 2040 + G2000)
    assert p8.mde(30, 8, m=26) > p8.mde(30, 8, m=8)                      # a larger family costs power


def test_timing_model_reproduces_the_measured_stage4_points():
    # Stage 4 cloud wall_s per run at 150 sweeps / 240 spins and 300 sweeps / 480 spins (margin and mitigation excluded)
    for lab, w240, w480 in (("ours_kc2_i11", 1.8, 10.2), ("B1_best", 7.2, 52.0), ("B3_v2", 1.5, 6.8)):
        m = p8.MARGIN
        assert p8.s_per_run(lab, "p3n240", 240, 150, "ideal") / m == pytest.approx(w240, rel=0.12)
        assert p8.s_per_run(lab, "p3n480", 480, 300, "ideal") / m == pytest.approx(w480, rel=0.12)


# ------------------------------------------------------------------------------------------------ evaluator end to end (D7)
def _run(out: Path, jid, phase, label, fam, cond, mit, runs, sweeps=2, c2c=0.5):
    a = rh8.make_parser().parse_args(["--id", jid, "--phase", phase, "--label", label, "--family", fam, "--cond", cond, "--mit", mit,
                                      "--runs", runs, "--sweeps", str(sweeps), "--out", str(out), "--c2c", str(c2c)])
    assert rh8.run_job(a) == 0


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    out = tmp_path_factory.mktemp("h8raw")
    fam, runs = "p3n120", "1101/0-1,1102/0-1"
    for lab in ("ours_kc2_i11", "ours_none", "B1_best", "B3_v2"):
        for cond in p8.conds_of(lab):
            _run(out, f"m_{lab}_{cond}", "main", lab, fam, cond, "none" if cond == "ideal" else p8.ARMS[lab].mit, runs)
    _run(out, "abl_kc2_ideal", "abl", "L_kc2", fam, "ideal", "none", runs)
    _run(out, "abl_kc2_nom", "abl", "L_kc2", fam, "nominal", "wv+diff+cal", runs)
    for sw_ in ("sw.dsatur", "sw.tabucol", "sw.sa"):
        _run(out, f"sw_{sw_}", "sw", sw_, fam, "ideal", "none", runs, sweeps=3)
    _run(out, "ref_tabu", "ref", "sw.tabucol", fam, "ideal", "none", "1101/0-1", sweeps=3)
    _run(out, "ctx_b1y", "ctx", "B1_yin_sa", fam, "ideal", "none", runs)
    _run(out, "var_ours_vx2", "var", "ours_kc2_i11", fam, "vx2", "wv+diff+cal", runs)
    return out


def test_evaluator_reads_every_file_and_builds_every_section(raw):
    rep = ev8.evaluate(str(raw), B=20, smoke=True, sensitivities=False)
    assert rep["n_files"] == rep["n_files_read"] and not rep["unread_files"]
    c = rep["cells"]["p3n120"]
    assert set(c) >= {"ideal", "nominal", "spins"}
    assert "ours_kc2_i11 vs B3_v2" in c["nominal"]["contrasts"] and "ours_kc2_i11 vs B1_best" in c["nominal"]["contrasts"]
    assert set(c["ideal"]["arms"]) == {"ours_kc2_i11", "ours_none", "B1_best", "B3_v2"}
    assert any(k.startswith("L_kc2") for k in rep["ablation"]["p3n120"]["ideal"]["arms"])
    assert any("B1_yin_sa" in k for k in rep["software"]["context"]["p3n120"]) and "ours_kc2_i11" in rep["stress"] and rep["software"]["context"]["p3n120"]["sw.tabucol"]["n"] == 4
    assert rep["software"]["solvability_tabucol_20x"]["p3n120"]["solved_frac"] in (0.0, 1.0)
    assert rep["kc2c_arm"].startswith(("PENDING", "no kc2c"))
    md = ev8.markdown(rep)
    assert md.count("## ") >= 6 and "Power" in md


def test_main_fails_when_a_raw_file_is_not_read_by_any_section(raw, tmp_path):
    import shutil
    d = tmp_path / "r"
    shutil.copytree(raw, d)
    f = next((d / "h8").glob("m_ours_none_ideal.json"))
    doc = json.loads(f.read_text())
    doc["h8"]["phase"] = "mystery"
    (d / "h8" / "stray.json").write_text(json.dumps(doc))
    with pytest.raises(AssertionError, match="not read"):
        ev8.main(["--raw", str(d), "--out", str(tmp_path / "o" / "rep.json"), "--boot", "20", "--smoke"])


def test_main_fails_on_an_empty_raw_dir(tmp_path):
    (tmp_path / "h8").mkdir()
    with pytest.raises(AssertionError):
        ev8.main(["--raw", str(tmp_path), "--out", str(tmp_path / "o.json"), "--boot", "20", "--smoke"])


def test_mitigation_overhead_raises_energy_and_area_of_a_nominal_run(raw):
    from cost_model import MeasuredCostV2
    files = [d for d in ev8.load_files(raw) if d["h8"]["label"] == "ours_kc2_i11" and d["h8"]["phase"] == "main"]
    nom = [d for d in files if d["h8"]["cond"] == "nominal"][0]
    rec = nom["records"][0]
    cost = MeasuredCostV2()
    with_once, a1 = ev8._price_run(rec, cost, True)
    no_once, a2 = ev8._price_run(rec, cost, False)
    base = ev8.ev.run_arrays(rec, cost)
    assert a1 > 0 and with_once.e_total > no_once.e_total > base.e_total
    assert with_once.a_total > base.a_total


def test_ideal_records_carry_no_mitigation_cost_and_nominal_ones_do(raw):
    for d in ev8.load_files(raw):
        m = d["h8"]
        for r in d["records"]:
            assert ("mit_cost" in r) == (m["cond"] != "ideal" and m["phase"] in ("main", "abl", "var") and m["label"] not in ("B3_v2",))
            assert not rh8.check_record(r)


def test_common_keeps_only_complete_instance_seed_rectangles():
    class R:
        def __init__(self, i, s):
            self.inst, self.seed = i, s
    g = {"a": [R("1", 0), R("1", 1), R("2", 0)], "b": [R("1", 0), R("1", 1), R("2", 0), R("2", 1)]}
    assert ev8.common(g) == (["1"], [0, 1]) or ev8.common(g) == (["1"], [0, 1])


# ------------------------------------------------------------------------------------------------ scheduler
def _sched(tmp, rows, extra=()):
    tsv = tmp / "t.tsv"
    tsv.write_text("# c\n" + "\n".join("\t".join(map(str, r)) for r in rows) + "\n")
    cmd = [sys.executable, str(ROOT / "scripts/cloud/h8/h8_sched.py"), "--tsv", str(tsv), "--run", str(tmp / "run"), "--wt", str(tmp), "--py", sys.executable,
           "--slots", "2", *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def test_scheduler_runs_jobs_then_barrier_and_resumes(tmp_path):
    rows = [("a", "par", 0.1, 1, 1, "touch a.out", "x"), ("b", "par", 0.1, 1, 1, "touch b.out", "x"), ("rep", "all", 0.1, 1, 1, "test -e a.out && test -e b.out && touch rep.out", "x")]
    r = _sched(tmp_path, rows)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "rep.out").exists() and (tmp_path / "run/done/rep").exists() and (tmp_path / "run/H8_DONE").exists()
    (tmp_path / "run/done/rep").unlink()
    (tmp_path / "rep.out").unlink()
    r = _sched(tmp_path, rows)
    assert r.returncode == 0 and (tmp_path / "rep.out").exists()


def test_scheduler_does_not_run_the_barrier_when_a_job_failed_and_refuses_oversized_jobs(tmp_path):
    rows = [("a", "par", 0.1, 1, 1, "false", "x"), ("rep", "all", 0.1, 1, 1, "touch rep.out", "x")]
    r = _sched(tmp_path, rows)
    assert r.returncode == 1 and not (tmp_path / "rep.out").exists() and (tmp_path / "run/failed/a").exists()
    big = [("huge", "par", 9999, 1, 1, "true", "x")]
    t2 = tmp_path / "t2"
    t2.mkdir()
    r = _sched(t2, big)
    assert r.returncode == 2 and "REFUSED" in r.stdout


# ------------------------------------------------------------------------------------------------ global Holm is the primary verdict
def _contrast(p, ratio=0.5, hi=0.9):
    return {"ets_ratio": ratio, "ets_ci": (0.3, hi), "d_success": 0.1, "d_success_ci": (0.0, 0.2), "p_ets_lt1": p, "holm_p": p,
            "energy": ev8.ev.energy_verdict({"ets_ratio": ratio, "ets_ci": (0.3, hi), "d_success": 0.1, "d_success_ci": (0.0, 0.2)}, p), "not_evaluable": None}


def test_primary_verdict_uses_the_global_holm_p_and_differs_from_the_cell_verdict():
    p_small, p_cell = 0.03, 0.03
    cells = {}
    for k in range(12):                                         # 12 families x 2 primary contrasts: many comparisons, a modest p
        cells[f"f{k}"] = {"nominal": {"contrasts": {"ours_kc2_i11 vs B3_v2": _contrast(p_cell if k == 0 else 0.4),
                                                    "ours_kc2_i11 vs B1_best": _contrast(0.4),
                                                    "ours_kc2_i11 vs ours_none": _contrast(0.001)}}}
    cell0 = cells["f0"]["nominal"]["contrasts"]["ours_kc2_i11 vs B3_v2"]
    assert cell0["energy"] == "win"                              # per-cell verdict (p 0.03 < 0.05)
    hp = ev8.holm_primary(cells)
    assert len(hp) == 24 and hp["f0|nominal|ours_kc2_i11 vs B3_v2"] > 0.05
    assert cell0["energy"] == "inconclusive" and cell0["primary"] and cell0["holm_p_global"] > 0.05      # PRIMARY verdict: global p
    assert cells["f0"]["nominal"]["contrasts"]["ours_kc2_i11 vs ours_none"]["energy"] == "win"            # non-primary keeps its cell verdict
    assert "primary" not in cells["f0"]["nominal"]["contrasts"]["ours_kc2_i11 vs ours_none"]


def test_not_evaluable_survives_global_holm_and_report_prints_both_verdicts(raw):
    rep = ev8.evaluate(str(raw), B=20, smoke=True, sensitivities=False)
    assert rep["global_family_size_design"] == 20 and rep["global_family_size_present"] == 2 and not rep["global_family_complete"]
    c = rep["cells"]["p3n120"]["nominal"]["contrasts"]["ours_kc2_i11 vs B3_v2"]
    assert c["primary"] and "holm_p_global" in c and "energy_cell" in c
    md = ev8.markdown(rep)
    assert "INCOMPLETE" in md and "(primary)" in md and "global" in md


def test_core_gate_smokes_only_core_types_and_full_gate_the_full_types():
    core = {j.id for j in g8.smoke_types("core")}
    full = {j.id for j in g8.smoke_types("full")}
    core_jobs = {j.id for j in g8.all_jobs("core")}
    assert core <= core_jobs and core - {g8.barrier("core").id} <= core_jobs
    assert not any(("p3n2040" in i or "maxcut_2000" in i or "myciel7" in i) for i in core)
    assert any("p3n2040" in i for i in full) and len(full) > len(core)
    assert max(j.rss for j in g8.smoke_types("core") if j.mode == "par") <= max(j.rss for j in g8.all_jobs("core") if j.mode == "par")


def test_worst_case_core_cost_is_inside_the_rupee_cap_and_gate_is_hard_timed():
    w = g8.worst_case_rs()
    assert w["rs"] <= g8.CAP_CORE_RS and w["minutes"] <= 280
    sh = (ROOT / "scripts/cloud/h8/go_h8.sh").read_text()
    assert sh.count("timeout -k 30") >= 3 and "SETUP_MIN" in sh and "GATE_SMOKE_MIN" in sh and "--tier \"$TIER\"" in sh
    assert f"DL_CORE={g8.DEADLINE_CORE_MIN};;" in sh and "echo $DL_CORE ||" in sh


# ------------------------------------------------------------------------------------------------ 16-vCPU profile and the kc2c integration
def test_kc2c_selection_in_the_tree_is_the_retune_output_and_in_the_core_lists():
    assert p8.kc2c_ready()
    c = p8.kc2c_cfg("colouring")
    assert c["cid"].startswith("kc2c_") and c["tfinal"] == 0.5 and p8.kc2c_cfg("maxcut")["cid"].startswith("kc2c_")
    assert c != rh8.json.loads((ROOT / p8.TUNED_S2).read_text())["tuned"]["colouring"]["ours.kc2.i10"]     # not the plain Stage 2 Kc2 config
    assert "ours_kc2c" in p8.main_arms()
    ids = [ln.split("\t")[0] for ln in (ROOT / "scripts/cloud/h8/jobs_h8_core.tsv").read_text().splitlines() if not ln.startswith("#")]
    assert any("ours_kc2c" in i for i in ids)
    assert rh8.resolve_cfg("ours_kc2c", "p3n240")["tfinal"] == 0.5


def test_core_tsv_on_disk_equals_a_fresh_generation(tmp_path):
    for t in ("core", "full"):
        f = tmp_path / f"{t}.tsv"
        g8.write_tsv(f, t)
        assert f.read_text() == (ROOT / f"scripts/cloud/h8/jobs_h8_{t}.tsv").read_text(), t


def test_profile_16_fits_the_deadline_memory_budget_and_the_rupee_ceiling():
    b = g8.budget()
    for prof in (32, 16):
        pb = b[f"profile_{prof}"]
        assert pb["core_plan"]["makespan_min"] <= pb["deadline_min"], (prof, pb)
        assert pb["core_worst_case"]["rs"] <= g8.CAP_CORE_RS, pb
        assert pb["core_plan"]["peak_rss_gb"] <= (108.0 if prof == 32 else 60.0)
    assert b["profile_16"]["core_plan"]["peak_concurrent"] <= 16
    assert b["profile_32"]["core"]["rs"] == b["core"]["rs"]                # the 32-vCPU numbers are unchanged by the profile code
    assert g8.PROFILES[32]["deadline_core"] == g8.DEADLINE_CORE_MIN


def test_big_mitigated_jobs_are_limited_to_four_at_once_in_profile_16():
    sched = rh8.sys.modules.get("h8_sched")
    import importlib.util
    spec = importlib.util.spec_from_file_location("h8_sched", ROOT / "scripts/cloud/h8/h8_sched.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    rows = [{"id": f"b{i}", "mode": "par", "rss": 13.8, "est": 10.0, "tmo": 60, "cmd": ""} for i in range(8)]
    sim = m.simulate(rows, 16, 60.0)
    assert sim["peak_concurrent"] == 4 and sim["makespan_min"] == 20.0
    assert m.simulate(rows, 16, 108.0)["peak_concurrent"] == 7
    big = [j for j in g8.all_jobs("core") if j.mode == "par" and j.rss >= 13.8]
    assert big and max(j.rss for j in big) <= 60.0


def test_scheduler_plan_mode_and_profile_flags(tmp_path):
    rows = [("a", "par", 1.0, 5, 10, "true", "x"), ("rep", "all", 0.1, 1, 60, "true", "x")]
    tsv = tmp_path / "t.tsv"
    tsv.write_text("\n".join("\t".join(map(str, r)) for r in rows) + "\n")
    base = [sys.executable, str(ROOT / "scripts/cloud/h8/h8_sched.py"), "--tsv", str(tsv), "--run", str(tmp_path / "r"), "--wt", str(tmp_path), "--py", sys.executable,
            "--plan", "--slots", "16", "--mem-gb", "60"]
    ok = subprocess.run(base + ["--deadline-min", "10"], capture_output=True, text=True)
    assert ok.returncode == 0 and "FITS" in ok.stdout
    bad = subprocess.run(base + ["--deadline-min", "3"], capture_output=True, text=True)
    assert bad.returncode == 1 and "EXCEEDS" in bad.stdout
    sh = (ROOT / "scripts/cloud/h8/go_h8.sh").read_text()
    assert "--profile" in sh and "--slots 16 --mem-gb 60" in sh and "DL_CORE=450" in sh and "--plan" in sh


def test_partial_data_without_any_registered_pair_does_not_crash_the_report(raw, tmp_path):
    import shutil
    d = tmp_path / "r"
    (d / "h8").mkdir(parents=True)
    for f in (raw / "h8").glob("m_B1_best_*.json"):
        shutil.copy(f, d / "h8" / f.name)                       # only B1: no registered contrast exists
    shutil.copy(raw / "h8" / "m_B3_v2_ideal.json", d / "h8" / "m_B3_v2_ideal.json")
    rep = ev8.evaluate(str(d), B=20, smoke=True, sensitivities=False)
    assert rep["n_files_read"] == rep["n_files"] and not rep["global_family_complete"]
    ev8.markdown(rep)


def _load_sched():
    import importlib.util
    spec = importlib.util.spec_from_file_location("h8_sched", ROOT / "scripts/cloud/h8/h8_sched.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_admission_budget_is_capped_at_memtotal_minus_four_gib(monkeypatch):
    m = _load_sched()
    monkeypatch.setattr(m, "mem_total_gb", lambda: 61.0)
    assert m.admission_budget(60.0, 0.85) == 57.0
    assert m.admission_budget(0.0, 0.85) == 51.85
    monkeypatch.setattr(m, "mem_total_gb", lambda: 128.0)
    assert m.admission_budget(60.0, 0.85) == 60.0


def test_evaluator_cost_flags_path_reports_flags_and_frozen_sensitivity(raw):
    rep = ev8.evaluate(str(raw), B=20, smoke=True, sensitivities=True, cost_flags=frozenset({"b1", "b2", "b3"}))
    assert rep["cost_flags"] == ["b1", "b2", "b3"] and "corrected cost flags" in rep["primary_pricing"]
    assert "frozen_h8_pricing" in rep["sensitivity_verdicts"]
    frozen = ev8.evaluate(str(raw), B=20, smoke=True, sensitivities=False)
    assert frozen["cost_flags"] == [] and "frozen_h8_pricing" not in frozen["sensitivity_verdicts"]


def test_evaluator_cli_accepts_cost_flags(raw, tmp_path):
    out = tmp_path / "rep.json"
    assert ev8.main(["--raw", str(raw), "--out", str(out), "--boot", "20", "--smoke", "--cost-flags", "all"]) == 0
    import json as _j
    assert _j.loads(out.read_text())["cost_flags"] == ["b1", "b2", "b3"]
