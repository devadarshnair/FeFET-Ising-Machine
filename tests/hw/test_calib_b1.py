"""P4.02: calib_b1 pipeline pieces (no scored run)."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import calib_b1 as cb  # noqa: E402


def test_instance_list_matches_prereg():
    assert len(cb.GRAPHS) == 30 and len(set(cb.GRAPHS)) == 30
    ns = {cb.load_graph(g).n for g in cb.GRAPHS}
    assert min(ns) == 800 and max(ns) == 3000
    assert set(cb.T1_GRAPHS) <= set(cb.GRAPHS) and set(cb.T2_GRAPHS) <= set(cb.GRAPHS)


def test_restart_arms():
    assert cb.restart_for("sa", 800).arm == "none"
    r = cb.restart_for("mesa_k4", 800)
    assert (r.arm, r.K) == ("mesa", 3200)


def test_build_pads_and_temperatures():
    inst, n = cb.build("G1", 0, 800)
    assert n == 800 and inst.n == 1024 and int(inst.lane_en.sum()) == 800
    assert inst.deoff == 0 and inst.geom == 1


def test_tts():
    c = np.array([[0, 1, 1], [0, 0, 1]], float)       # p = 0, .5, 1
    assert cb.tts(c, 1) == min(2 * math.log(0.01) / math.log(0.5), 3)
    assert math.isinf(cb.tts(np.zeros((2, 3)), 1))


def test_t2_inf_when_sa_never_reaches():
    cv = {"g": {"sa": np.zeros((2, 3)), "mesa": np.ones((2, 3))}}
    assert math.isinf(cb.t2_value(cv, {"g": 1}))


def test_t1_and_verdict():
    cuts = {"g": {"sa": np.array([100.0, 100.0]), "mesa": np.array([127.0, 127.0])}}
    assert abs(cb.t1_value(cuts) - 27) < 1e-9
    assert cb.verdict(37, 0, 27, 10) and not cb.verdict(37.1, 0, 27, 10) and cb.verdict(40, 13.5, 27, 10)
    assert not cb.verdict(math.inf, 0, 2, 0.5)


def test_run_job_row(tmp_path):
    assert cb.run_job(("G1", "mesa_k2", 0, 1, str(tmp_path))) == "done"
    assert cb.run_job(("G1", "mesa_k2", 0, 1, str(tmp_path))) == "skip"
    rows = cb.load_rows(tmp_path)
    assert len(rows) == 1 and len(rows[0]["curve"]) == 1 and rows[0]["curve"][0] > 0


def test_epoch_arm_parsing():
    assert cb.epoch_sweeps("mesa_k2") is None
    assert cb.epoch_sweeps("mesa_k4_e10") == 10
    assert cb.restart_for("mesa_k4_e10", 800).K == 3200


def test_epoch_schedule_reaches_t_end_within_epoch():
    inst, n = cb.build("G1", 0, 300 * 800)
    ep, t_floor = cb.epoch_schedule(inst, n, 10)
    t_after = ep.t0 * (ep.alpha / 2**32) ** (10 * n - 1)
    assert abs(t_after - t_floor) / t_floor < 0.01
    assert t_floor < inst.t0 / 5


def test_attempt1_mesa_restarts_every_count_max_regression():
    """Root cause of the attempt-1 failure: whole-run cooling + T := T0 on each restart keeps MESA at T ~ T0, so
    the best never improves and a restart fires every Count_max = 2n steps."""
    inst, n = cb.build("G1", 0, 300 * 800)
    m = cb.tg.Machine(inst, restart=cb.restart_for("mesa_k2", n))
    m.run(20 * n, keep_trace=False)
    assert len(m.restart.events) >= 8
    assert m.temp > 0.9 * inst.t0 * (inst.alpha / 2**32) ** (2 * n)
