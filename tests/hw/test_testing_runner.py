"""Testing-phase runner and evaluators (scripts/testing). Synthetic and tiny-instance checks only: no scored data is read."""
import dataclasses
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "testing"))
sys.path.insert(0, str(REPO / "scripts" / "golden"))
sys.path.insert(0, str(REPO / "scripts" / "baselines"))

import evalcommon as ev  # noqa: E402
import evaluate_h2 as h2  # noqa: E402
import evaluate_h3 as h3  # noqa: E402
import evaluate_h5 as h5  # noqa: E402
import gen_jobs_stage2 as gj  # noqa: E402
import machines as ma  # noqa: E402
import plan as pl  # noqa: E402
import pricing as pr  # noqa: E402
import run_cell as rc  # noqa: E402
from cost_model import CostModel  # noqa: E402

COST = CostModel()
COLD = (0.3, 0.05)          # cold temperatures so I10 actually skips reads on a tiny instance


def spec(arm, family="colouring", inst="301", r=0, sweeps=20, cfg=None, study="h2", phase="test", **kw):
    a = pl.Arm.parse(arm)
    kind = "b3" if a.machine == "b3" else "b2" if a.machine == "b2" else a.restart
    c = cfg or pl.default_config(kind).as_dict()
    return pl.Spec(study, phase, family, inst, r, arm, cfg=c, sweeps=sweeps, inst_index=pl.TEST_SET[family].index(inst) if family != "qkp" else 0, **kw)


@pytest.fixture
def cold(monkeypatch):
    monkeypatch.setattr(ma, "_temps_cached", lambda *a: COLD)


# ------------------------------------------------------------------------------------------------------------------ plan
def test_design_counts():
    assert len(pl.grid("kc2")) == len(pl.grid("none")) == len(pl.grid("da_offset")) == len(pl.grid("b3")) == len(pl.grid("b2")) == 8
    assert pl.H3_CELLS == 3600 and len(pl.H3_TRAJ) == 20 and len(pl.H5_POINTS) == 24
    for fam in ("maxcut", "maxsat", "colouring"):
        assert not set(pl.TEST_SET[fam]) & set(pl.TUNE_SET[fam])
    assert (len(pl.TEST_SET["maxcut"]), len(pl.TUNE_SET["maxcut"]), len(pl.TEST_SET["qkp"]), len(pl.TUNE_SET["qkp"])) == (10, 4, 30, 10)
    assert not set(pl.TEST_SET["qkp"]) & set(pl.TUNE_SET["qkp"])


def test_h5_points_not_evaluable_and_duplicates():
    assert {p.pid for p in pl.H5_POINTS if not p.evaluable} == {"corner_SS", "corner_FF"}
    assert set(pl.H5_DUPLICATES) == {"write_x1", "read_x1", "drift_0.0", "mismatch_x1"}


def test_arm_key_roundtrip():
    for a in pl.h2_arms("maxcut"):
        assert pl.Arm.parse(a.key) == a
    assert pl.Arm.parse("b1.mesa.published").tweak == "published"


# ------------------------------------------------------------------------------------------------------------------ sign
def test_machine_energy_is_minus_cut(monkeypatch):
    """The golden machine maximises f; the mapped QUBO is a minimisation form, so E = -cut must hold for the best state."""
    from scripts.problems import load as ld
    from scripts.problems import maxcut as mcut
    g = mcut.torus_pm1(6, 1)
    mq = ld.from_problem("maxcut", g, g.n)
    monkeypatch.setattr(ma, "mapped", lambda f, k: mq)
    ma.quantised.cache_clear()
    ma._temps_cached.cache_clear()
    sp = spec("ours.kc2.i7i10", "maxcut", "G1", sweeps=40)
    steps = int(sp.sweeps * mq.spins)
    b = ma.build(sp, COST, steps)
    for _ in range(steps):
        b.m.step()
        b.m.counters.steps.pop()
    cut = g.cut(b.m.best_x[:g.n])
    assert ma._energy(b, b.m) == -cut
    assert cut >= 1                      # a real cut, not the all-zero start state
    ma.quantised.cache_clear()
    ma._temps_cached.cache_clear()


# ------------------------------------------------------------------------------------------------------------ determinism
def test_seeds_common_across_arms_and_distinct_across_runs():
    a = spec("ours.kc2.i7i10", r=3)
    b = spec("b1.mesa", r=3)
    assert ma.seed_of(a) == ma.seed_of(b)
    assert ma.seed_of(a) != ma.seed_of(spec("ours.kc2.i7i10", r=4))
    assert ma.seed_of(a) != ma.seed_of(dataclasses.replace(a, tag=1))


def test_run_is_deterministic():
    r1, r2 = ma.execute(spec("ours.mesa.i10")), ma.execute(spec("ours.mesa.i10"))
    assert r1["curve"] == r2["curve"] and r1["price"]["e_total"] == r2["price"]["e_total"]


# ---------------------------------------------------------------------------------------------------------- I10 pricing
@pytest.mark.parametrize("full,alone,restart", [("ours.kc2.i7i10", "ours.kc2.i7", "kc2"), ("ours.none.i10", "ours.none.off", "none"),
                                                ("ours.mesa.i7i10", "ours.mesa.i7", "mesa")])
def test_unskip_reconstruction(cold, full, alone, restart):
    """Counters of an I10-simulated run with the skipped reads put back equal the counters of the run without I10 (exact at sigma 0)."""
    a, b = ma.execute(spec(full)), ma.execute(spec(alone))
    assert a["skipped_reads"] > 0 and b["skipped_reads"] == 0
    assert a["curve"] == b["curve"]
    assert a["snaps"][-1]["c_ns"] == b["snaps"][-1]["c"]
    assert a["price_noskip"]["e_total"] == pytest.approx(b["price"]["e_total"], rel=1e-12)
    assert a["price"]["e_total"] < b["price"]["e_total"]


def test_snapshots_monotone_and_priced():
    r = ma.execute(spec("ours.kc2.i7i10"))
    cyc = [s["c"]["cycles"] for s in r["snaps"]]
    assert cyc == sorted(cyc) and len(r["snaps"]) == pl.N_CHECKPOINTS and r["snaps"][-1]["t"] == r["steps"]
    assert rc.check_record(r) == [] and r["array_writes"] == 0 and r["prog"]["e_program_fJ"] > 0


# ------------------------------------------------------------------------------------------------------------ all machines
@pytest.mark.parametrize("arm", ["b1.none", "b1.da_offset", "b1.mesa", "b1.kc2", "b1bs.mesa", "b1.mesa.published", "b3.b3",
                                 "ours.kc2.i7i10.i11", "ours.none.off", "ours.da_offset.i7"])
def test_each_machine_arm_runs(arm):
    kind = {"b1.mesa.published": "mesa", "b3.b3": "b3"}.get(arm, pl.Arm.parse(arm).restart)
    r = ma.execute(spec(arm, cfg=pl.grid(kind)[3].as_dict()))
    assert rc.check_record(r) == [] and math.isfinite(r["best_E"])
    if arm.endswith("none") or arm.endswith("none.off"):
        assert r["restarts"] == 0


def test_b1_restart_blocks_follow_arm():
    none = ma.execute(spec("b1.none"))["price"]["blocks"]["restart"]
    kc2 = ma.execute(spec("b1.kc2"))["price"]["blocks"]["restart"]
    mesa = ma.execute(spec("b1.mesa"))["price"]["blocks"]["restart"]
    assert none == 0 and 0 < kc2 < mesa


def test_b2_qkp_runs():
    name = pl.TEST_SET["qkp"][0]
    s = pl.Spec("h2", "test", "qkp", name, 0, "b2.b2", cfg=pl.grid("b2")[0].as_dict(), proposals=2000)
    r = ma.execute(s)
    assert r["best_profit"] > 0 and rc.check_record(r) == [] and r["price"]["e_total"] > 0


# ------------------------------------------------------------------------------------------------------------ H3 / H5 hooks
def test_sigma_and_adc_axes_change_trajectory_not_counters_schema():
    a = ma.execute(spec("ours.kc2.i7", sweeps=30))
    b = ma.execute(spec("ours.kc2.i7", sweeps=30, sigma_mult=5.0, adc_delta=-2))
    assert a["desc"]["adc_bits"] - 2 == b["desc"]["adc_bits"] and a["snaps"][-1]["c"].keys() == b["snaps"][-1]["c"].keys()


def test_ideal_point_equals_unperturbed_run_and_has_no_false_events():
    """NoisyRestartUnit at zero readout error must be the golden restart arm; no false stalls or resets can occur.
    Power off: with I7 the low-bit ADC itself is a readout error (measured energy != true energy), which is intended."""
    ideal = pl.H5_POINTS[1]
    assert ideal.pid == "dev_x0"
    for restart in ("kc2", "mesa"):
        base = ma.execute(spec(f"ours.{restart}.off", sweeps=60))
        pert = ma.execute(spec(f"ours.{restart}.off", sweeps=60, pert=ideal.as_dict()))
        assert base["curve"] == pert["curve"] and base["restarts"] == pert["restarts"]
        fs = pert["false_stall"]
        assert fs["false_stalls"] == 0 and fs["false_resets"] == 0


def test_perturbation_applies_identically_to_b1_and_ours():
    pt = next(p for p in pl.H5_POINTS if p.pid == "dev_x4")
    for arm in ("ours.kc2.i7", "b1.mesa"):
        base = ma.execute(spec(arm, sweeps=30, pert=pl.H5_POINTS[1].as_dict()))
        noisy = ma.execute(spec(arm, sweeps=30, pert=pt.as_dict()))
        assert base["curve"] != noisy["curve"] or base["restarts"] != noisy["restarts"]
        assert noisy["array_writes"] == 0


def test_every_h5_point_runs_on_ours():
    for pt in pl.H5_POINTS:
        if pt.evaluable:
            r = ma.execute(spec("ours.kc2.i7", sweeps=3, pert=pt.as_dict()))
            assert rc.check_record(r) == [], pt.pid


def test_false_stall_counts_exist_under_noise():
    pt = next(p for p in pl.H5_POINTS if p.pid == "combined")
    r = ma.execute(spec("ours.kc2.i7", sweeps=80, pert=pt.as_dict()))
    fs = r["false_stall"]
    assert set(fs) == {"stalls", "false_stalls", "resets", "false_resets"} and fs["false_stalls"] <= fs["stalls"]
    assert fs["false_resets"] <= fs["resets"]


# ------------------------------------------------------------------------------------------------------------ H3 pricing
@pytest.mark.parametrize("arm", ["ours.kc2.i7i10", "b1.mesa", "b3.b3"])
def test_h3_components_are_exactly_linear(arm):
    """Every H3 cost-only cell is a dot product of the per-row components: it must equal pricing with the scaled table."""
    r = ma.execute(spec(arm))
    sn = r["snaps"][-1]
    v, t = h3.comps_at(r["desc"], sn["c"], sn["t"], sn["flips"])
    for read, arc, rng_, clk in ((0.2, 3.0, 0.3, 2.0), (5.0, 0.5, 3.0, 0.5)):
        w = h3.cell_weights(read, arc, rng_, clk)
        scale = {"e_array_cell_read": read * arc, "e_adc_conv_bit": arc, "e_adc_bias_step": arc, "e_rng_draw": rng_, "t_clk": clk,
                 "e_sram_read_bit": arc}
        p = pr.price(r["desc"], sn["c"], sn["t"], sn["flips"], CostModel(scale=scale))
        assert float(v @ w) == pytest.approx(p["e_total"], rel=1e-9)
        assert t * clk == pytest.approx(p["time_ns"], rel=1e-9)


def test_b1_rebits_equals_rerun_costs_when_adc_exact():
    """B1 with a 32-row tile has an exact ADC for >= 6 bits: +2 bits only scales the ADC conversion bits (8 -> 10) and the SAR cycles."""
    r = ma.execute(spec("b1.mesa"))
    c = r["snaps"][-1]["c"]
    c2, d2 = pr.b1_rebits(c, r["desc"], 2)
    p = pr.price(r["desc"], c, r["steps"], r["snaps"][-1]["flips"], COST)
    p2 = pr.price(d2, c2, r["steps"], r["snaps"][-1]["flips"], COST)
    assert p2["blocks"]["adc"] == pytest.approx(p["blocks"]["adc"] * 10 / 8) and p2["time_ns"] > p["time_ns"]
    c0, d0 = pr.b1_rebits(c, r["desc"], 0)
    assert pr.price(d0, c0, r["steps"], r["snaps"][-1]["flips"], COST)["e_total"] == p["e_total"]


# ---------------------------------------------------------------------------------------------------------- job generator
def test_jobs_unique_chunked_and_complete():
    jobs = gj.all_jobs()
    par = [j for j in jobs if j.mode == "par"]
    assert len({j.id for j in jobs}) == len(jobs)
    assert max(j.secs for j in par) <= 1.1 * gj.CHUNK_TARGET_S or max(len(j.runs) for j in par if j.secs > gj.CHUNK_TARGET_S) == 1
    assert [j.id for j in jobs if j.mode == "all"] == ["select_tuned", "freeze_h2"]
    # every test run of every arm appears exactly once
    n_test = sum(j.n_runs for j in jobs if j.phase == "test" and j.family == "maxcut" and j.arm == "ours.kc2.i7i10")
    assert n_test == 10 * 10
    n_tune = sum(j.n_runs for j in jobs if j.phase == "tune" and j.family == "maxsat" and j.arm == "b1.mesa")
    assert n_tune == 8 * 4 * 2


def test_tsv_roundtrip(tmp_path):
    p = tmp_path / "j.tsv"
    n = gj.write_tsv(p)
    rows = [ln.split("\t") for ln in p.read_text().splitlines() if not ln.startswith("#")]
    assert len(rows) == n and all(len(r) == 6 for r in rows)
    assert all(int(r[3]) <= 30 for r in rows if r[1] == "par"), "every chunk planned under 30 min"
    assert all(int(r[4]) >= int(r[3]) for r in rows)


def test_run_tokens_and_tuned_resolution(tmp_path):
    runs = rc.parse_runs("@tuned/G1/0-2,mesa_p85_5_k2/G6/1-1")
    assert runs[0] == ("@tuned", "G1", 0) and len(runs) == 4
    tuned = {"tuned": {"maxcut": {"ours.kc2.i7i10": pl.grid("kc2")[2].as_dict(), "ours.kc2.i10": pl.grid("kc2")[5].as_dict(),
                                  "b2.b2@10000": pl.grid("b2")[0].as_dict()}}}
    assert rc.resolve_cfg("@tuned", "ours.kc2.i7", "maxcut", 0, tuned, None)["cid"] == pl.grid("kc2")[2].cid
    assert rc.resolve_cfg("@tuned", "ours.kc2.off", "maxcut", 0, tuned, None)["cid"] == pl.grid("kc2")[5].cid
    assert rc.tuned_key("b2.b2", 10000) == "b2.b2@10000"


def test_h3_skipped_when_h2_gate_failed(tmp_path):
    (tmp_path / "frozen.json").write_text(json.dumps({"gate_pass": False}))
    argv = ["--id", "h3x", "--study", "h3", "--phase", "h3", "--arm", "@ours_best", "--family", "maxcut", "--runs", "@frozen/G1/0-0",
            "--out", str(tmp_path)]
    a = rc.make_parser().parse_args(argv)
    assert rc.run_job(a, None, {"gate_pass": False}) == 0
    assert "skipped" in json.loads((tmp_path / "h3" / "h3x.json").read_text())


def test_runner_refuses_test_without_tuned(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_cell.py", "--id", "t", "--phase", "test", "--arm", "ours.kc2.i7i10", "--family", "colouring",
                                      "--runs", "@tuned/301/0-0", "--out", str(tmp_path)])
    assert rc.main() == 2


def test_job_file_resume(tmp_path):
    argv = ["--id", "j1", "--study", "h2", "--phase", "test", "--arm", "b3.b3", "--family", "colouring", "--runs", "@default/301/0-1",
            "--sweeps", "3", "--out", str(tmp_path)]
    a = rc.make_parser().parse_args(argv)
    rc.run_job(a, None, None)
    f = tmp_path / "h2" / "j1.json"
    d = json.loads(f.read_text())
    assert len(d["records"]) == 2 and d["git"]["head"]
    before = f.stat().st_mtime_ns
    rc.run_job(a, None, None)
    assert f.stat().st_mtime_ns == before                        # resumed = skipped


# --------------------------------------------------------------------------------------------------------------- statistics
def test_r99_tts_ets():
    p = np.array([[0.0, 0.5, 1.0]])
    r = ev.r99(p)
    assert np.isinf(r[0, 0]) and r[0, 1] == pytest.approx(math.log(0.01) / math.log(0.5)) and r[0, 2] == 1.0
    t = np.array([[1.0, 2.0, 3.0]])
    tts, ets = ev.tts_ets(p, t, 10 * t)
    assert tts[0] == pytest.approx(min(2.0 * r[0, 1], 3.0)) and ets[0] == pytest.approx(10 * tts[0])
    assert np.isinf(ev.tts_ets(np.zeros((1, 3)), t, t)[0][0])


def test_holm_and_loss_point():
    assert ev.holm({"a": 0.01, "b": 0.04, "c": 0.5}) == {"a": 0.03, "b": 0.08, "c": 0.5}
    assert h5.loss_point([1, 2, 4], [1.0, 0.95, 0.5], 1.0) == pytest.approx(2 + (0.95 - 0.9) / (0.95 - 0.5) * 2)
    assert math.isinf(h5.loss_point([1, 2, 4], [1.0, 0.95, 0.92], 1.0))


def fake_arm(name, ets_scale, succ_p, I=8, S=8, K=10, seed=0, area=1.0):
    """Synthetic ArmData: success probability grows linearly to succ_p, energy grows linearly scaled by ets_scale."""
    rng = np.random.default_rng(seed)
    u = rng.random((I, S))
    k = np.arange(1, K + 1)
    succ = (u[:, :, None] < succ_p * k / K) & (rng.random((I, S, K)) >= 0)         # same u for every arm (paired)
    succ = np.maximum.accumulate(succ, axis=2)
    ecum = np.broadcast_to(k * ets_scale, (I, S, K)).astype(float)
    return ev.ArmData(name, [str(i) for i in range(I)], succ, ecum, ecum.copy(), succ[:, :, -1], np.zeros((I, S)), np.zeros((I, S, K)),
                      area, np.zeros((I, S)), np.zeros((I, S)))


def test_contrast_win_tie_loss():
    base = fake_arm("b", 1.0, 0.8)
    arms = {"b": base, "win": fake_arm("win", 0.5, 0.8), "same": fake_arm("same", 1.0, 0.8), "worse": fake_arm("worse", 2.0, 0.8),
            "fewer": fake_arm("fewer", 0.5, 0.4)}
    bs = ev.boot_stats(arms, B=400)
    names = {n: ev.contrast(bs, n, "b") for n in ("win", "same", "worse", "fewer")}
    hp = ev.holm({n: c["p_ets_lt1"] for n, c in names.items()})
    assert ev.energy_verdict(names["win"], hp["win"]) == "win"
    assert ev.energy_verdict(names["same"], hp["same"]) == "tie"
    assert ev.energy_verdict(names["worse"], hp["worse"]) == "loss"
    assert ev.energy_verdict(names["fewer"], hp["fewer"]) != "win"          # cheaper but lower success: no win
    assert ev.area_verdict(0.9) == "win" and ev.area_verdict(1.0) == "tie" and ev.area_verdict(1.2) == "loss"


def test_win_margin_is_five_percent():
    base, a97, a94 = fake_arm("b", 1.0, 0.9), fake_arm("a97", 0.97, 0.9), fake_arm("a94", 0.94, 0.9)
    bs = ev.boot_stats({"b": base, "a97": a97, "a94": a94}, B=200)
    c97, c94 = ev.contrast(bs, "a97", "b"), ev.contrast(bs, "a94", "b")
    assert ev.energy_verdict(c97, 0.0) != "win" and ev.energy_verdict(c94, 0.0) == "win"


# -------------------------------------------------------------------------------------------------------------- H2 selection
def tune_rec(arm, fam, inst, cid, best_E, e, r=0, cfg=None):
    return {"spec": {"phase": "tune", "arm": arm, "family": fam, "instance": inst, "cfg": {"cid": cid, "pct_hi": 85}, "proposals": 0, "r": r},
            "best_E": best_E, "price": {"e_total": e}}


def test_select_tuned_uses_gap_then_energy(tmp_path):
    (tmp_path / "h2").mkdir()
    recs = []
    for arm in ("b1.none", "b1.da_offset", "b1.mesa", "b1.kc2", "ours.none.i10", "ours.da_offset.i10", "ours.mesa.i10", "ours.kc2.i10"):
        for fam in ("maxcut", "maxsat"):
            inst = "G6" if fam == "maxcut" else "2001"
            lo = {"b1.mesa": -3000.0, "ours.kc2.i10": -3000.0}.get(arm, -2900.0)
            recs += [tune_rec(arm, fam, inst, "good", lo, 5.0), tune_rec(arm, fam, inst, "tie_cheaper", lo, 4.0),
                     tune_rec(arm, fam, inst, "bad", lo + 50, 1.0)]
    (tmp_path / "h2" / "t.json").write_text(json.dumps({"records": recs}))
    out = h2.select_tuned(tmp_path)
    assert out["tune_table"]["maxcut"]["b1.mesa"]["_selected"] == "tie_cheaper"          # equal gap -> lower energy; 'bad' cheaper but worse
    assert out["rung3_best"]["b1"]["maxcut"] == "mesa" and out["rung3_best"]["ours_global"] == "kc2"
    assert out["tuned"]["maxcut"]["b1.mesa"]["cid"] == "tie_cheaper"


def test_gate_and_full_design_rules():
    def c(energy):
        return {"energy": energy}
    rep = {f: {"contrasts": {"ours_kc2_i10 vs 3_B1_best": c("win" if f == "maxcut" else "tie"),
                             "ours_kc2_i7 vs 3_B1_best": c("win")}, "arms": {}} for f in h2.HEADLINE}
    g = h2.gate(rep, {})
    assert g["pass"] and g["winning_arms"] == ["ours_kc2_i7"]
    rep["maxsat"]["contrasts"]["ours_kc2_i7 vs 3_B1_best"] = c("loss")
    assert not h2.gate(rep, {})["pass"] and "not a hardware win" in h2.gate(rep, {})["statement"]


def test_full_design_removes_tweaks_that_do_not_pay():
    tuned = {"rung3_best": {"ours_global": "kc2"}}
    def fam(i10, i7):
        return {"contrasts": {"ours_kc2_i10 vs ours_kc2_off": {"energy": i10}, "ours_kc2_i7 vs ours_kc2_off": {"energy": i7}},
                "arms": {"ours_kc2_off": {"ets": 10.0}, "ours_kc2_i10": {"ets": 8.0}, "ours_kc2_i7": {"ets": 7.0}, "ours_kc2_i7i10": {"ets": 5.0}}}
    rep = {"maxcut": fam("win", "win"), "maxsat": fam("win", "win")}
    assert h2.full_design(rep, tuned)["full"] == "ours_kc2_i7i10"
    rep = {"maxcut": fam("win", "tie"), "maxsat": fam("win", "win")}          # I7 fails in one family: removed, pair removed
    assert h2.full_design(rep, tuned)["candidates"] == ["ours_kc2_off", "ours_kc2_i10"]


# ---------------------------------------------------------------------------------------------------- H3 / H5 decision rules
def fake_cells(win_fraction, ratios=None):
    """The full 3600-cell grid with a fixed B1 ratio (0.5), except the cells listed in `ratios` {(read, sigma, adc_delta): ratio}."""
    import itertools
    cells = []
    for rd, arc, dl, sg, rn, ck in itertools.product(pl.H3_READ_E, pl.H3_ARRAY_ADC, pl.H3_ADC_DELTA, pl.H3_SIGMA, pl.H3_RNG, pl.H3_CLOCK):
        r = (ratios or {}).get((rd, sg, dl), 0.5) if (arc, rn, ck) == (1.0, 1.0, 1.0) else 0.5
        cells.append({"read": rd, "arc": arc, "adc_delta": dl, "sigma": sg, "rng": rn, "clock": ck,
                      "vs_b1": {"ratio": r, "win": r <= 0.95}, "vs_b3": {"ratio": 0.5, "win": True}})
    return cells


def test_h3_break_even_and_win_fraction():
    cells = fake_cells(1.0)
    assert h3.win_fractions(cells) == {"vs_b1": 1.0, "vs_b3": 1.0}
    be = h3.break_even(cells)
    assert all(math.isinf(v) for v in be.values())
    cells = fake_cells(1.0, {(5.0, 1.0, 0): 1.2})                              # B1 wins back at read x5
    assert h3.break_even(cells)["read"] == 5.0
    cells = fake_cells(1.0, {(1.0, 1.0, 1): 1.0})                              # lost one ADC bit away: factor 2
    assert h3.break_even(cells)["adc_delta"] == 2.0


def test_h3_win_lost_exactly_at_factor_2_does_not_pass():
    cells = fake_cells(1.0, {(2.0, 1.0, 0): 1.0})                              # ratio reaches 1 at read x2: win does not survive factor 2
    be = h3.break_even(cells)["read"]
    assert be == 2.0 and not h3.survives_factor_2(be)
    cells = fake_cells(1.0, {(5.0, 1.0, 0): 1.2})                              # first lost at x5: survives factor 2
    assert h3.survives_factor_2(h3.break_even(cells)["read"])
    assert h3.survives_factor_2(math.inf)


def test_h5_axes_cover_registered_points():
    used = {p for ax in h5.AXES.values() for _, p in ax} | set(h5.SINGLE)
    sim = {p.pid for p in pl.H5_POINTS if p.evaluable and p.pid not in pl.H5_DUPLICATES and p.pid != "dev_x0"}
    assert sim <= used | {"nominal"}


def test_h5_loss_point_table():
    tab = {("a", p): np.full((3, 3), v) for p, v in (("nominal", 1.0), ("dev_x2", 0.95), ("dev_x4", 0.5))}
    out = h5.boot_loss_points(tab, "a", 50, np.random.default_rng(0))
    assert out["dev"]["point"] == pytest.approx(2 + 0.05 / 0.45 * 2)


# ------------------------------------------------------------------------------------- end-to-end evaluator on tiny real runs
def test_family_report_on_tiny_runs(tmp_path):
    """The H2 ladder machinery runs end to end on tiny real records (colouring, 2 sweeps); verdict values are meaningless here."""
    insts = pl.TEST_SET["colouring"][:2]
    out = tmp_path / "h2"
    out.mkdir()
    recs = []
    tuned = {"rung3_best": {"b1": {"colouring": "mesa"}, "ours_global": "kc2"}, "tuned": {"colouring": {}}}
    for fam_label, (arm, variant, src) in h2.spec_of_label(tuned, "colouring").items():
        kind = "b3" if arm.startswith("b3") else pl.Arm.parse(arm).restart
        for i in insts:
            for r in range(3):
                s = spec(arm, "colouring", i, r, sweeps=2)
                s.phase = "test"
                recs.append(ma.execute(s, COST))
    (out / "t.json").write_text(json.dumps({"records": recs}))
    tg = {i: {"E_ref": 0.0, "E_target": 2.0} for i in insts}
    rep = h2.family_report(tmp_path, tuned, "colouring", tg, COST, B=100)
    assert "ours_kc2_i7i10 vs 3_B1_best" in rep["contrasts"] and "B3" in rep["arms"]
    c = rep["contrasts"]["ours_kc2_i7 vs ours_kc2_off"]
    assert c["energy"] in ("win", "tie", "loss", "inconclusive", "not evaluable") and 0 <= c["holm_p"] <= 1
    assert "gap@50%E_B1" in rep["quality"]["B3"] and "gap@25%steps" in rep["quality"]["B3"]


def test_b1_adc_is_exact_from_six_bits():
    """H3 collapses the B1 ADC-bit axis to cost-only: the 32-row tile ADC is exact for 6, 7 and 8 bits, so trajectories are equal."""
    import yin_mesa as ym
    from instances import maxcut_qubo, qubo_instance, random_graph
    d, P = maxcut_qubo(48, random_graph(48, 0.2, 3))
    inst = qubo_instance(d, P, seed=5, steps=400, t_start=3.0, t_end=0.1, deoff=0)
    best = []
    for bits in (6, 7, 8):
        m = ym.b1_machine(inst, ym.B1Cfg(adc_bits=bits))
        best.append((m.run(400, keep_trace=True).trace[:-1], m.best_f))
    assert best[0] == best[1] == best[2]


def _write(tmp, study, name, recs):
    (tmp / study).mkdir(parents=True, exist_ok=True)
    (tmp / study / f"{name}.json").write_text(json.dumps({"records": recs}))


def test_h3_evaluator_end_to_end_on_tiny_grid(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "H3_SIGMA", (1.0, 2.0))
    monkeypatch.setattr(pl, "H3_ADC_DELTA", (-1, 0))
    monkeypatch.setattr(pl, "H3_READ_E", (1.0, 5.0))
    monkeypatch.setattr(pl, "H3_ARRAY_ADC", (1.0, 2.0))
    monkeypatch.setattr(pl, "H3_RNG", (1.0, 3.0))
    monkeypatch.setattr(pl, "H3_CLOCK", (1.0, 2.0))
    monkeypatch.setattr(pl, "H3_INSTANCES", 2)
    monkeypatch.setattr(pl, "H3_SEEDS", 2)
    insts = pl.TEST_SET["colouring"][:2]
    recs = []
    for sg in pl.H3_SIGMA:
        for dl in pl.H3_ADC_DELTA:
            for i in insts:
                for r in range(2):
                    recs.append(ma.execute(spec("ours.kc2.i7", inst=i, r=r, sweeps=2, sigma_mult=sg, adc_delta=dl, study="h3", phase="h3"), COST))
        for i in insts:
            for r in range(2):
                recs.append(ma.execute(spec("b1.mesa", inst=i, r=r, sweeps=2, sigma_mult=sg, study="h3", phase="h3"), COST))
    _write(tmp_path, "h3", "a", recs)
    b3 = [ma.execute(spec("b3.b3", inst=i, r=r, sweeps=2), COST) for i in insts for r in range(2)]
    frozen = {"colouring": {"ours_best": {"arm": "ours.kc2.i7"}, "b1_tuned": {"arm": "b1.mesa"}}, "gate_pass": True}
    tg = {i: {"E_ref": 0.0, "E_target": 3.0} for i in insts}
    out = h3.evaluate_family(tmp_path, frozen, "colouring", b3, tg, B=30)
    assert len(out["cells"]) == 2 ** 6 and len(out["traj"]) == 4
    c = out["cells"][0]
    assert set(c["vs_b1"]) == {"ratio", "ci", "win"} and isinstance(c["vs_b3"]["win"], bool)
    assert set(h3.break_even(out["cells"])) == {"read", "arc", "rng", "clock", "sigma", "adc_delta"}
    assert set(h3.win_fractions(out["cells"])) == {"vs_b1", "vs_b3"}


def test_h5_evaluator_end_to_end_on_tiny_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "H5_INSTANCES", {"colouring": 2})
    monkeypatch.setattr(pl, "H5_SEEDS", 2)
    pts = {p.pid: p for p in pl.H5_POINTS}
    insts = pl.TEST_SET["colouring"][:2]
    recs = []
    for arm in h5.MACHINES.values():
        for pid in ("nominal", "dev_x2", "dev_x4", "dev_x0"):
            for i in insts:
                for r in range(2):
                    recs.append(ma.execute(spec(arm, inst=i, r=r, sweeps=3, pert=pts[pid].as_dict(), study="h5", phase="h5"), COST))
    _write(tmp_path, "h5", "a", recs)
    res = h5.evaluate(tmp_path, B=30)
    fam = res["families"]["colouring"]
    assert "dev" in fam["loss_points"]["ours_kc2"] and "ets_ratio" in fam["kc2_vs_mesa"]["dev_x2"]
    assert set(fam["nominal_escalation"]) <= {"kc2", "mesa", "none"} and "corners (SS, FF)" in res["not_evaluable"]
    assert fam["points"]["ours.kc2.i7|nominal"]["array_writes"] == 0


@pytest.mark.parametrize("arm,kw", [("ours.kc2.i7i10", {}), ("ours.mesa.i7", {"sigma_mult": 3.0}), ("ours.da_offset.off", {}),
                                    ("b1.mesa", {}), ("b1.kc2", {"sigma_mult": 2.0})])
def test_fast_cim_is_bit_identical(monkeypatch, cold, arm, kw):
    """The incremental column sums (fastcim.py) must reproduce the parent's full products exactly: same machine trace line by line,
    including kc2 kicks, MESA reloads, I7 precision changes, seeded read noise and the B1 row tiles."""
    traces = []
    for fast in (True, False):
        monkeypatch.setattr(ma, "FAST_CIM", fast)
        sp = spec(arm, sweeps=25, **kw)
        steps = int(sp.sweeps * ma.mapped(sp.family, sp.instance).spins)
        b = ma.build(sp, COST, steps)
        lines = []
        for _ in range(steps):
            lines.append(b.m.step())
            b.m.counters.steps.pop()
        traces.append((lines, b.m.best_f, b.m.restart.events[:]))
    assert traces[0] == traces[1]
    assert traces[0][2] or pl.Arm.parse(arm).restart == "da_offset", "restart path exercised"


# ---------------------------------------------------------------------------------------- H5 completion: T7, B2, corners
def _h5pt(pid):
    return next(p for p in pl.H5_POINTS if p.pid == pid)


def test_sign_magnitude_arm_parses_and_reuses_the_base_tuned_key():
    a = pl.Arm.parse("ours.kc2.i7.sm")
    assert (a.machine, a.restart, a.power, a.tweak) == ("ours", "kc2", "i7", "sm") and a.key == "ours.kc2.i7.sm"
    assert rc.tuned_key("ours.kc2.i7.sm") == rc.tuned_key("ours.kc2.i7") == "ours.kc2.i7i10"


def test_sign_magnitude_halves_programmed_cells_and_lowers_static_variance():
    base = ma.execute(spec("ours.kc2.i7", sweeps=3, pert=_h5pt("dev_x4").as_dict()), COST)
    sm = ma.execute(spec("ours.kc2.i7.sm", sweeps=3, pert=_h5pt("dev_x4").as_dict()), COST)
    assert rc.check_record(sm) == [] and sm["array_writes"] == 0
    assert sm["prog"]["e_program_fJ"] < base["prog"]["e_program_fJ"]
    b1 = ma.build(spec("ours.kc2.i7", sweeps=3, pert=_h5pt("dev_x4").as_dict()), COST, 100)
    b2 = ma.build(spec("ours.kc2.i7.sm", sweeps=3, pert=_h5pt("dev_x4").as_dict()), COST, 100)
    assert np.abs(b2.pert_wrap.dP).sum() < np.abs(b1.pert_wrap.dP).sum()      # one cell per magnitude bit, not two
    assert b2.pert_wrap.dP.shape == b1.pert_wrap.dP.shape


def test_sign_magnitude_at_ideal_point_equals_base_arm():
    ideal = _h5pt("dev_x0").as_dict()
    a = ma.execute(spec("ours.kc2.off", sweeps=30, pert=ideal), COST)
    b = ma.execute(spec("ours.kc2.off.sm", sweeps=30, pert=ideal), COST)
    assert a["curve"] == b["curve"]


QKP = pl.TEST_SET["qkp"][0]


def _b2spec(pid, L=3000, r=0):
    return pl.Spec("h5", "h5", "qkp", QKP, r, "b2.b2", cfg=pl.grid("b2")[0].as_dict(), proposals=L, pert=_h5pt(pid).as_dict())


def test_b2_ideal_point_equals_unperturbed_filter_run():
    s = _b2spec("dev_x0")
    plain = ma.execute(dataclasses.replace(s, pert=None), COST)
    ideal = ma.execute(s, COST)
    assert ideal["best_profit"] == plain["best_profit"] and ideal["rejected"] == plain["rejected"]
    assert ideal["false_accept_states"] == 0


def test_b2_perturbation_is_applied_to_the_filter_and_true_feasibility_is_checked():
    s = _b2spec("dev_x4", L=4000)
    inst = ma.hc.load(QKP)
    wI, cref = ma.b2_effective_filter(inst, pl.Perturb(**s.pert), np.random.default_rng(1))
    assert not np.allclose(wI, inst.w) and cref != inst.C + 0.5
    r = ma.execute(s, COST)
    assert rc.check_record(r) == [] and r["array_writes"] == 0 and r["best_profit"] >= 0
    again = ma.execute(s, COST)
    assert again["best_profit"] == r["best_profit"]                           # deterministic


def test_b2_points_are_the_registered_analogue_ones():
    assert set(pl.H5_B2_POINTS) <= {p.pid for p in pl.H5_POINTS if p.evaluable and p.pid not in pl.H5_DUPLICATES}
    jobs = [j for j in gj.all_jobs() if j.arm == "b2.b2" and j.phase == "h5"]
    assert {j.extra.split()[1] for j in jobs} == set(pl.H5_B2_POINTS)
    assert all(f"--proposals {pl.H5_B2_PROPOSALS}" in j.extra for j in jobs)
    assert sum(j.n_runs for j in jobs) == len(pl.H5_B2_POINTS) * pl.H5_B2_INSTANCES * pl.H5_SEEDS


def test_t7_jobs_cover_every_simulated_point_and_families():
    jobs = [j for j in gj.all_jobs() if j.arm == "ours.kc2.i7.sm"]
    pts = {p.pid for p in pl.H5_POINTS if p.evaluable and p.pid not in pl.H5_DUPLICATES}
    for fam, n_inst in pl.H5_INSTANCES.items():
        got = {j.extra.split()[1] for j in jobs if j.family == fam}
        assert got == pts
        assert sum(j.n_runs for j in jobs if j.family == fam) == len(pts) * n_inst * pl.H5_SEEDS


def test_corner_points_emit_an_explicit_not_evaluable_record(tmp_path):
    jobs = [j for j in gj.all_jobs() if j.id.endswith("_not_evaluable")]
    assert sorted(j.id for j in jobs) == ["h5_corner_FF_not_evaluable", "h5_corner_SS_not_evaluable"]
    j = jobs[0]
    argv = ["--id", j.id, "--study", "h5", "--phase", "h5", "--arm", j.arm, "--family", j.family, "--runs", j.runs[0], "--out", str(tmp_path),
            *j.extra.split()]
    assert rc.run_job(rc.make_parser().parse_args(argv), None, None) == 0
    doc = json.loads((tmp_path / "h5" / f"{j.id}.json").read_text())
    assert doc["records"] == [] and doc["point"] == "corner_SS" and doc["not_evaluable"] == pl.CORNER_REASON
    assert h5.not_evaluable_points(tmp_path) == {"corner_SS": pl.CORNER_REASON}


def test_h5_evaluator_reports_b2_t7_and_corner_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "H5_INSTANCES", {"colouring": 2})
    monkeypatch.setattr(pl, "H5_SEEDS", 2)
    pts = {p.pid: p for p in pl.H5_POINTS}
    insts = pl.TEST_SET["colouring"][:2]
    recs = []
    for arm in list(h5.MACHINES.values()) + [h5.T7_ARM]:
        for pid in ("nominal", "dev_x2", "dev_x4", "dev_x0"):
            for i in insts:
                for r in range(2):
                    recs.append(ma.execute(spec(arm, inst=i, r=r, sweeps=3, pert=pts[pid].as_dict(), study="h5", phase="h5"), COST))
    b2recs = [ma.execute(dataclasses.replace(_b2spec(pid, L=500, r=r)), COST) for pid in ("nominal", "dev_x4") for r in range(2)]
    _write(tmp_path, "h5", "a", recs + b2recs)
    (tmp_path / "h5" / "corner.json").write_text(json.dumps({"id": "c", "point": "corner_SS", "not_evaluable": pl.CORNER_REASON, "records": []}))
    res = h5.evaluate(tmp_path, B=30)
    t7 = res["families"]["colouring"]["t7_sign_magnitude_extra"]
    assert t7["arm"] == h5.T7_ARM and "dev" in t7["loss_points"] and any(k.startswith(h5.T7_ARM) for k in t7["points"])
    assert "ours.kc2.i7.sm" not in res["families"]["colouring"]["loss_points"]            # not in the machine comparison
    assert set(res["b2_qkp"]) <= {"nominal", "dev_x4"} and res["not_evaluable"]["corner records written by the runner"] == ["corner_SS"]
    assert res["not_evaluable"]["corners (SS, FF)"] == pl.CORNER_REASON


def test_smoke_all_uses_the_machines_sign_convention():
    """smoke_all fed the minimisation QUBO straight into the maximising golden machine; it now feeds (-d, -P) like the runner."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import smoke_all as sa
    from scripts.problems import load as ld
    from scripts.problems import maxcut as mcut
    g = mcut.torus_pm1(6, 1)
    mq = ld.from_problem("maxcut", g, g.n)
    qz = ld.quantise(mq, ld.QUANT["ours"])
    d, P, _ = sa.pad_pow2(mq, qz)
    assert (d[:mq.spins] == -qz.d).all() and (P[:mq.spins, :mq.spins] == -qz.P).all()
    for row in (sa.run_ours(mq, "maxcut", "kc2", False, True, 600, COST), sa.run_b1(mq, "maxcut", True, 600, COST),
                sa.run_b3(mq, "maxcut", 600, COST)):
        assert row["best_energy"] < 0, row["machine"]           # E = -cut of a real cut (was +cut-like, i.e. the worst cut, before)
        assert row["best_energy"] >= -g.n * g.n
    assert sa.machine_energy(mq, 7) == -7 + mq.offset
