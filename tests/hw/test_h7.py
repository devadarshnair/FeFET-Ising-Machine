"""H7 (Stage 4) checks: instance construction and provenance, software baselines vs known optima, the one full-scale ADC cost rule,
fresh seed stream, job plan/budget, evaluator logic."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ("scripts/testing", "scripts/golden", "scripts/baselines", "."):
    sys.path.insert(0, str(ROOT / sub))

import evaluate_h7 as ev7  # noqa: E402
import gen_jobs_stage4 as g4  # noqa: E402
import h7_instances as h7i  # noqa: E402
import plan as pl  # noqa: E402
import plan_h7 as p7  # noqa: E402
import pricing as pr  # noqa: E402
import sw_colouring as sw  # noqa: E402

DIMACS_DIR = ROOT.parents[1] / ("05_external_tools/open_source_implementations/from_local_papers/zenodo_17051903__Garg2025_code/"
                                "extracted/chiraggarg24-Integer_State_Optimization_Framework-014815e/Dataset/graph_coloring_dataset")


# ------------------------------------------------------------------------------------------------ instances
@pytest.mark.parametrize("name", list(p7.DIMACS))
def test_dimacs_construction_matches_header_counts(name):
    n, E = h7i.dimacs_graph(name)
    assert (n, len(E)) == p7.DIMACS[name][:2]
    assert (E[:, 0] < E[:, 1]).all() and len(np.unique(E, axis=0)) == len(E)


@pytest.mark.parametrize("name", list(p7.DIMACS))
def test_dimacs_construction_equals_local_benchmark_file(name):
    f = DIMACS_DIR / f"{name}.col"
    if not f.exists():
        pytest.skip("local DIMACS copy not present (cloud box): header counts are checked separately")
    import networkx as nx
    from scripts.problems.colouring import parse_col
    n, E = h7i.dimacs_graph(name)
    n2, E2, _ = parse_col(f.read_text())
    assert n == n2
    if name.startswith("queen"):
        assert np.array_equal(E, E2)                     # same vertex numbering as DIMACS
    else:
        assert nx.is_isomorphic(nx.Graph(E.tolist()), nx.Graph(E2.tolist()))


def test_myciel3_is_groetzsch():
    n, E = h7i.myciel_edges(3)
    assert (n, len(E)) == (11, 20)


@pytest.mark.parametrize("fam", list(p7.PLANTED))
def test_planted_family_size_and_zero_optimum(fam):
    n, k, _ = p7.PLANTED[fam]
    seed = int(p7.TEST_SET[fam][0])
    cp = h7i.problem(fam, str(seed))
    assert cp.n * cp.k == int(fam.split("n")[1]) == p7.spins(fam, str(seed))
    colour = np.random.default_rng([20261117, n, k, seed]).permutation(n) % k      # the planted colouring (h6 generator)
    import machines as ma
    mq = ma.mapped(fam, str(seed))
    assert mq.energy(cp.encode(colour)) == 0
    assert sw.conflicts(cp.edges, colour) == 0


def test_fresh_seed_stream_and_family_ids():
    assert p7.SEED_TAG not in (0, 1, 6)
    ids = [pl.FAMILY_ID[f] for f in p7.FAMILIES]
    assert len(set(pl.FAMILY_ID.values())) == len(pl.FAMILY_ID) and len(ids) == len(p7.FAMILIES)
    used6 = {str(s) for s in list(range(501, 526)) + list(range(601, 605)) + list(range(701, 705))}
    assert not used6 & {i for f in p7.PLANTED for i in p7.TEST_SET[f]}


# ------------------------------------------------------------------------------------------------ software baselines
def _cycle(n):
    return np.array([(i, (i + 1) % n) for i in range(n)])


PETERSEN = np.array([(i, (i + 1) % 5) for i in range(5)] + [(i, i + 5) for i in range(5)] + [(5 + i, 5 + (i + 2) % 5) for i in range(5)])


@pytest.mark.parametrize("n,edges,chi", [(8, _cycle(8), 2), (9, _cycle(9), 3), (5, np.array([(i, j) for i in range(5) for j in range(i + 1, 5)]), 5),
                                         (10, PETERSEN, 3)])
def test_dsatur_optimal_on_known_graphs(n, edges, chi):
    col = sw.dsatur(n, edges)
    assert sw.conflicts(edges, col) == 0 and col.max() + 1 == chi


@pytest.mark.parametrize("name", ["myciel4", "queen5_5", "queen6_6"])
def test_tabucol_finds_chromatic_colouring(name):
    n, E = h7i.dimacs_graph(name)
    r = sw.tabucol(n, E, p7.DIMACS[name][2], 20000 * n, seed=3)
    assert r["best_conflicts"] == 0 and sw.conflicts(E, r["colour"]) == 0


def test_tabucol_cannot_go_below_chromatic_number():
    n, E = h7i.dimacs_graph("myciel4")
    assert sw.tabucol(n, E, p7.DIMACS["myciel4"][2] - 1, 2000, seed=1)["best_conflicts"] >= 1


def test_tabucol_reproducible():
    n, E = h7i.dimacs_graph("queen6_6")
    a, b = sw.tabucol(n, E, 6, 3000, seed=9), sw.tabucol(n, E, 6, 3000, seed=9)
    assert a["best_conflicts"] == b["best_conflicts"] and np.array_equal(a["colour"], b["colour"])


def test_fold_to_k_keeps_proper_colouring_when_enough_colours():
    col = sw.dsatur(10, PETERSEN)
    assert sw.conflicts(PETERSEN, sw.fold_to_k(10, PETERSEN, col, 3)) == 0


def test_dwave_sa_solves_small_colouring_and_energy_matches_qubo():
    pytest.importorskip("dwave.samplers")
    from scripts.problems import load as ld
    from scripts.problems.colouring import Colouring
    cp = Colouring("c9", 9, _cycle(9), 3, chi=3)
    mq = ld.from_problem("colouring", cp, cp.n)
    r = sw.sa_qubo(mq.d, mq.P, mq.offset, 500, seed=1)
    assert r["energy"] == mq.energy(r["x"]) == 0


# ------------------------------------------------------------------------------------------------ full-scale ADC rule
def test_b1_native_fs_bits():
    P = np.zeros((64, 64), np.int64)
    P[0, :32] = 7                      # one tile column with 32 cells at level 7 -> 224 -> 8 bits
    assert pr.b1_native_fs_bits(P, 32) == 8
    P[:] = 0
    P[0, 1] = P[1, 0] = 2
    assert pr.b1_native_fs_bits(P, 32) == 2
    assert pr.b1_native_fs_bits(np.zeros((8, 8), np.int64), 32) == 1


def _spec(arm, cfg, fam="p4n240", inst="901", sweeps=3):
    return pl.Spec(study="h7", phase="test", family=fam, instance=inst, r=0, arm=arm, cfg=cfg, sweeps=sweeps,
                   inst_index=p7.inst_index(fam, inst), tag=p7.SEED_TAG)


def _cfg(src):
    import run_cell as rc
    return rc.h7_cfg(src)


def test_ours_fs_same_trajectory_as_v1_and_fewer_adc_bits():
    import machines as ma
    a = ma.execute(_spec("ours.kc2.fs.i11", _cfg("tuned:ours.kc2.i10.i11")))
    b = ma.execute(_spec("ours.kc2.off.i11", _cfg("tuned:ours.kc2.i10.i11")))
    assert a["curve"] == b["curve"] and a["best_E"] == b["best_E"]
    assert a["desc"]["adc_bits"] == a["desc"]["fs_col"].bit_length() < b["desc"]["adc_bits"]
    assert a["price"]["blocks"]["adc"] < b["price"]["blocks"]["adc"]


def test_b1_fs_is_a_pricing_rule_on_the_same_trajectory():
    import machines as ma
    from cost_model import CostModel
    a = ma.execute(_spec("b1.none.fs", _cfg("tuned:b1.none")))
    b = ma.execute(_spec("b1.none", _cfg("tuned:b1.none")))
    assert a["curve"] == b["curve"]
    assert a["desc"]["adc_fs"] and a["desc"]["adc_bits_fs"] < 8
    c = b["snaps"][-1]["c"]
    c2, d2 = pr.b1_rebits(c, b["desc"], a["desc"]["adc_bits_fs"] - 8)
    ref = pr.price(d2, c2, b["steps"], b["flips"], CostModel())
    assert abs(a["price"]["e_total"] - ref["e_total"]) < 1e-6 * ref["e_total"]
    assert a["price"]["e_total"] < b["price"]["e_total"]


def test_b3_has_no_adc_and_is_unchanged():
    assert "fs" not in pl.Arm.parse("b3.b3").key


# ------------------------------------------------------------------------------------------------ plan / budget
def test_stage4_budget_within_cap_and_chunks():
    bud = g4.budget()
    assert bud["rs"] <= g4.CAP_RS
    assert max(j.secs for j in g4.all_jobs() if j.mode == "par") <= 1800


def test_job_runs_cover_registered_design_once():
    seen = {}
    for j in g4.all_jobs():
        if j.mode != "par":
            continue
        for tok in j.runs:
            _, inst, rr = tok.split("/")
            lo, hi = map(int, rr.split("-"))
            for r in range(lo, hi + 1):
                key = (j.phase, j.arm, j.family, j.extra, inst, r)
                assert key not in seen
                seen[key] = 1
    n_test = sum(len(p7.TEST_SET[f]) * (1 if a.arm == "sw.dsatur" else p7.test_seeds(f)) for f in p7.FAMILIES for a in p7.test_arms(f))
    assert sum(1 for k in seen if k[0] == "test") == n_test
    assert sum(1 for k in seen if k[0] == "var") == len(p7.V_FAMILIES) * len(p7.V_ARMS) * len(p7.v_points()) * p7.V_INSTANCES * p7.V_SEEDS


def test_v_points_exist_and_are_evaluable():
    assert {p.pid for p in p7.v_points()} == set(p7.V_POINTS)
    assert all(p.evaluable for p in p7.v_points())


def test_smoke_types_cover_every_arm_and_phase():
    st = g4.smoke_types()
    assert {(j.phase, j.arm) for j in st} == {(j.phase, j.arm) for j in g4.all_jobs() if j.mode == "par"}


def test_last_row_is_the_report_barrier(tmp_path):
    g4.write_tsv(tmp_path / "j.tsv")
    rows = [r for r in (tmp_path / "j.tsv").read_text().splitlines() if not r.startswith("#")]
    assert rows[-1].split("\t")[:2] == ["report_h7", "all"] and sum(r.split("\t")[1] == "all" for r in rows) == 1


# ------------------------------------------------------------------------------------------------ evaluator
def test_scale_verdict_largest_contiguous_size():
    def fr(v):
        return {"contrasts": {"ours_kc2_i11 vs B1_best": {"energy": v}}}
    fams = {"p3n240": fr("win"), "p4n240": fr("win"), "p3n480": fr("win"), "p4n480": fr("inconclusive"),
            "p3n960": fr("win"), "p4n960": fr("win")}
    sv = ev7.scale_verdict(fams)
    assert sv["largest_N_L1_holds"] == 240 and set(sv["per_size"]) == set(p7.SIZES)
    fams["p3n240"] = fr("loss")
    assert ev7.scale_verdict(fams)["largest_N_L1_holds"] is None


def test_amendment1_drops_960_everywhere():
    assert p7.SIZES == (240, 480) and "STAGE4_SIZES: 240, 480" in p7.AMENDMENT1.read_text()
    assert not [f for f in p7.FAMILIES if "960" in f]
    jobs = g4.all_jobs()
    assert not [j for j in jobs if "960" in j.family] and any(j.family == "p4n480" for j in jobs)
    assert set(ev7.scale_verdict({})["per_size"]) == {240, 480}


def test_sw_arm_broadcasts_deterministic_records():
    recs = [{"spec": {"instance": i, "r": 0}, "best_E": e} for i, e in (("a", 0.0), ("b", 2.0))]
    a = ev7.sw_arm("SW_dsatur", recs, ["a", "b"], 4)
    assert a.ok_final.shape == (2, 4) and a.ok_final[0].all() and not a.ok_final[1].any()


def test_evaluator_end_to_end_on_tiny_runs(tmp_path):
    import machines as ma
    fam = "p4n240"
    for a in p7.HW_ARMS + p7.SW_ARMS:
        recs = []
        for inst in p7.TEST_SET[fam][:2]:
            for r in range(1 if a.arm == "sw.dsatur" else 2):
                sp = _spec(a.arm, _cfg(a.cfg if "tabucol" not in a.cfg else "sw:tabucol:5"), fam, inst, sweeps=2)
                sp = pl.Spec(**{**sp.__dict__, "r": r})
                rec = ma.execute(sp)
                rec["spec"] = sp.__dict__
                recs.append(rec)
        (tmp_path / "h7").mkdir(exist_ok=True)
        (tmp_path / "h7" / f"x7_{a.label}_{fam}_000.json").write_text(json.dumps({"records": recs}, default=float))
    rep = ev7.evaluate(str(tmp_path), B=30)
    fr = rep["families"][fam]
    assert fr["B1_comparator"] in ("B1_best", "B1_mesa_epoch")
    assert len(fr["contrasts"]) == 4 and all("holm_p" in v for v in fr["contrasts"].values())
    assert set(fr["software_quality"]) == {f"ours_kc2_i11 vs {s}" for s in ev7.SW_REFS}
    assert fr["instances_missing"] == p7.TEST_SET[fam][2:]
    assert set(rep["sensitivity"]) == {"canonical_table", "baseline_lane_path_clock"} and "measured_v1" in rep["primary_pricing"]
    ev7.markdown(rep)


def test_b1_fs_clipping_is_simulated_under_variation():
    import machines as ma
    from cost_model import CostModel
    pert = next(p for p in pl.H5_POINTS if p.pid == "read_x4").as_dict()
    sp = pl.Spec(**{**_spec("b1.none.fs", _cfg("tuned:b1.none")).__dict__, "pert": pert})
    b = ma.build(sp, CostModel(), 10)
    tiles = b.m.cim.inner.tiles if hasattr(b.m.cim, "inner") else b.m.cim.tiles
    for tf in tiles:
        assert tf.cfg.fs == ma.b1_tile_fs(tf) < 32 and tf.fs == tf.cfg.fs
    tf = tiles[0]                                     # a column read at its own full scale cannot exceed it, whatever the noise

    assert tf.top << tf.shift <= 2 * tf.cfg.fs + (1 << tf.shift)
    assert ma.execute(sp)["desc"]["adc_fs"]


# ---- pre-Stage 4 review fixes: output dir (M1), measured_v1 primary pricing (M2), restart unit (M3), clock policy (M4), 0 % comparator
import gen_jobs_stage3 as g3  # noqa: E402
from cost_model import CostModel, MeasuredCost, measured_v1_table  # noqa: E402


def _tokens(cmd):
    return cmd.split()


def test_every_stage4_row_writes_where_report_h7_reads():
    jobs = g4.all_jobs()
    par = [j for j in jobs if j.mode == "par"]
    assert g4.OUT != g3.OUT == "sim/out/hw/stage3"
    assert par and all(_tokens(j.command())[_tokens(j.command()).index("--out") + 1] == g4.OUT for j in par)
    bar = _tokens(jobs[-1].command())
    assert bar[bar.index("--raw") + 1] == g4.OUT and bar[bar.index("--out") + 1].startswith(g4.OUT + "/")


def test_job_files_are_found_by_the_evaluator_under_their_label(tmp_path):
    (tmp_path / "h7").mkdir()
    (tmp_path / "h7v").mkdir()
    for j in g4.all_jobs():
        if j.mode == "par" and j.study == "h7" and j.phase == "test":
            (tmp_path / "h7" / f"{j.id}.json").write_text('{"records": []}')
    for fam in p7.FAMILIES:
        by = ev7.records_by_label(tmp_path, "h7", "x7", fam)
        assert {a.label for a in p7.test_arms(fam)} == set(by), fam


def test_dimacs_budget_scales_per_graph_and_jobs_carry_it():
    S = {i: p7.sweeps_of("dimacs", i) for i in p7.TEST_SET["dimacs"]}
    assert min(S.values()) == p7.SWEEPS and S["myciel6"] > S["queen6_6"] > p7.SWEEPS - 1
    for j in g4.test_jobs():
        if j.family == "dimacs":
            inst = j.runs[0].split("/")[1]
            assert all(r.split("/")[1] == inst for r in j.runs)
            want = p7.sweeps_of("dimacs", inst)
            assert (f"--sweeps {want}" in j.extra) == (want != p7.SWEEPS)
            if "tabucol" in j.arm:
                assert f"sw:tabucol:{want}" in j.extra


def _priced(arm, cost, cfg="tuned:ours.none.i10"):
    import machines as ma
    rec = ma.execute(_spec(arm, _cfg(cfg), "p4n240", "901", sweeps=2))
    s = rec["snaps"][-1]
    return pr.price(rec["desc"], s["c"], s["t"], s["flips"], cost)


def test_clock_policy_per_machine_and_n():
    m = MeasuredCost()
    assert m.t_clk_at(1024, "ours") == pytest.approx(9.1527) and m.t_clk_at(256, "b1") == pytest.approx(5.6386)
    assert m.t_clk_at(256, "ours") < m.t_clk_at(512, "ours") < m.t_clk_at(1024, "ours")
    lane = MeasuredCost(baseline_clock="lane_path")
    assert lane.t_clk_at(1024, "b1") == pytest.approx(2.4056) == lane.t_clk_at(1024, "b3")
    assert lane.t_clk_at(1024, "ours") == m.t_clk_at(1024, "ours")


def test_price_uses_the_machines_own_clock():
    base = CostModel(table=measured_v1_table())
    a = _priced("ours.none.fs", MeasuredCost(), "tuned:ours.none.i10")      # p4n240: n_pad 256
    ref = _priced("ours.none.fs", base, "tuned:ours.none.i10")
    assert a["time_ns"] == pytest.approx(ref["time_ns"] * 5.6386 / 9.1527, rel=1e-6)


def test_kc2_and_mesa_pay_the_measured_restart_unit_none_does_not():
    base, m = CostModel(table=measured_v1_table()), MeasuredCost()
    for arm, cfg, charged in (("ours.kc2.fs.i11", "tuned:ours.kc2.i10.i11", True), ("ours.none.fs", "tuned:ours.none.i10", False),
                              ("b1.mesa.fs", "b1mesa_epoch", True), ("b1.none.fs", "tuned:b1.none", False)):
        a, b = _priced(arm, m, cfg), _priced(arm, base, cfg)
        d_area = a["a_total"] - b["a_total"]
        if charged:
            assert d_area == pytest.approx(37887.0)                      # n_pad 256, measured post-P&R restart_unit
            assert a["blocks"]["leakage"] > b["blocks"]["leakage"] * 0.5 and a["blocks"]["leakage"] != b["blocks"]["leakage"]
        else:
            assert d_area == pytest.approx(0.0)


def test_restart_unit_area_leakage_exact_at_measured_n_and_monotone():
    m = MeasuredCost()
    from cost_model import loglog_interp
    assert loglog_interp(1024, m._pts("tt_a_restart")) == pytest.approx(173681.0)
    assert loglog_interp(512, m._pts("tt_a_restart")) > 37887.0 and loglog_interp(1024, m._pts("tt_p_leak_restart")) == pytest.approx(4482585.0)


def test_zero_percent_comparator_is_never_a_win(tmp_path):
    src = (ROOT / "scripts/testing/evaluate_h7.py").read_text()
    assert "comparator at 0 % success" in src
    assert "never a win" in (ROOT / "prereg/hw/H7_scaleup.md").read_text()


def test_prereg_states_primary_pricing_clock_and_restart_policy():
    t = (ROOT / "prereg/hw/H7_scaleup.md").read_text()
    for s in ("measured_v1", "PRIMARY", "restart_unit", "baseline_lane_path_clock", "canonical"):
        assert s in t
