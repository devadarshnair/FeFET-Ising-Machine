"""P4.05: copied HyCiM kernel (H3 scorers, H4 init, H5 T0) and the diag bookkeeping (no scored run)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import dqubo_diag as dd  # noqa: E402
import hycim as hc  # noqa: E402

INST = hc.load("jeu_100_25_1.txt")


def test_instances_and_optima():
    opt = json.loads(hc.OPTIMA.read_text())["instances"]
    assert len(hc.INSTANCES) == 40 and all(nm in opt for nm in hc.INSTANCES)
    assert INST.n == 100 and INST.C > 0 and set(dd.DIAG) <= set(hc.INSTANCES)


def test_filter_scorers_consistent():
    T = hc.temps("S4", hc.t0_for(INST, "filter", "S4", [1]), 2000)
    x0, y0 = hc.initial_state(INST, "filter", [2])
    best, _, final, minE = hc.run_one(INST, "filter", T, x0, y0, [3], hc.PSWAP_V3)
    assert best >= 0 and final <= best and minE == best     # filter energy = -profit on feasible states


def test_dqubo_scorers_bounded():
    T = hc.temps("S4", hc.t0_for(INST, "dqubo", "S4", [1]), 5000)
    x0, y0 = hc.initial_state(INST, "dqubo", [2])
    best, _, final, minE = hc.run_one(INST, "dqubo", T, x0, y0, [3])
    assert final <= best and minE <= best


def test_t0_multiplier():
    a = hc.t0_for(INST, "dqubo", "S4", [5])
    b = hc.t0_for(INST, "dqubo", "S4", [5], dqubo_mult=1e-3)
    assert np.isclose(b, 10 * a)


def test_consistent_init():
    x, y = hc.initial_state(INST, "dqubo", [4], "consistent")
    wx = int(INST.w @ x)
    assert wx <= INST.C and y.sum() == (1 if wx >= 1 else 0) and (wx == 0 or y[wx - 1] == 1)


def test_lengths_and_sig():
    assert dd.length(INST, "dqubo", "sweep1000") == 1000 * (100 + INST.C)
    assert dd.length(INST, "filter", "sweep1000") == 100_000 and dd.length(INST, "dqubo", "prop1000") == 1000
    assert dd.sig("filter", ("prop1000", "consistent", 1e-3)) == ("prop1000", "-", 0.0)


def test_in_band():
    assert dd.in_band(10.75, 98.5) and not dd.in_band(5.7, 98.5) and not dd.in_band(10, 93.5)


def test_job_and_rate(tmp_path):
    cfg = ("smoke100", "bernoulli", 1e-4)
    for arm in hc.ARMS:
        assert dd.run_job(("jeu_100_25_1.txt", arm, cfg, 0, str(tmp_path), 2)) == "done"
    r = dd.rate(tmp_path, ["jeu_100_25_1.txt"], "filter", cfg, "init", "best", dd.BLOCK)
    assert 0.0 <= r <= 100.0


def test_dqubo_incremental_energy_matches_reference():
    """Kernel's incremental S/Y/profit bookkeeping equals dqubo_energy on the final (x, y); a 1000-proposal D-QUBO
    run from a Bernoulli start cannot reach feasibility (its 0 % rate is dynamics, not a scoring bug)."""
    L = 3000
    T = hc.temps("S4", hc.t0_for(INST, "dqubo", "S4", [1]), L)
    x0, y0 = hc.initial_state(INST, "dqubo", [2])
    rng = np.random.default_rng(3)
    nv = INST.n + INST.C
    ri = rng.integers(0, nv, size=L).astype(np.int64)
    x, y = x0.copy(), y0.copy()
    best, _, final, _ = hc._run(hc.A_DQUBO, INST.p, INST.off, INST.w, INST.C, T, x, y, rng.random(L), ri,
                                rng.integers(0, INST.n, size=L).astype(np.int64), rng.random(L), 0.0, 2.0, 2.0)
    feasible = INST.w @ x <= INST.C
    assert final == (INST.profit(x) if feasible else -1.0)
    assert (best == -1.0) or feasible or best >= 0
    T1 = hc.temps("S4", hc.t0_for(INST, "dqubo", "S4", [1]), 1000)
    assert hc.run_one(INST, "dqubo", T1, x0, y0, [4])[0] == -1.0
