"""B1_yin (scripts/baselines/b1_native.py; P4_v2 amendment 1): Yin's move set and MESA v2 rules as a priced harness machine."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "scripts" / "baselines", ROOT / "scripts" / "testing", ROOT):
    sys.path.insert(0, str(p))

import b1_native as bn  # noqa: E402
import yin_mesa as b1  # noqa: E402
from instances import maxcut_qubo, random_graph  # noqa: E402


def _prob(n=24, seed=3):
    d, P = maxcut_qubo(n, random_graph(n, 0.4, seed))
    return np.asarray(d, np.int64), np.asarray(P, np.int64)


def test_best_state_matches_reported_objective_and_curve_monotone():
    d, P = _prob()
    cps = np.arange(1, 24 * 50 + 1, 24)
    cps[-1] = 24 * 50
    for arm in ("sa", "mesa"):
        cfg = bn.NativeCfg(arm, 4.0, 0.2, count_max=12, epoch_sweeps=3)
        bf, x, st, bc = bn.run(d, P, 50, cfg, 7, cps)
        assert bf == int(d @ x + x @ P @ x // 2) == bc[-1]
        assert (np.diff(bc) >= 0).all() and (np.diff(st[:, 0]) > 0).all() and st[-1, 0] == 24 * 50


def test_one_proposal_per_iteration_few_bits():
    d, P = _prob()
    cfg = bn.NativeCfg("sa", 1e6, 1e6)          # hot: almost every proposal accepted
    _, _, st, _ = bn.run(d, P, 20, cfg, 1, np.array([24 * 20]))
    it, acc, accbits, _, _, drawbits = st[-1]
    assert it == 480 and acc > 0.95 * it and 1.8 * it < drawbits < 2.2 * it and accbits <= 3 * acc


def test_mesa_epochs_wait_for_cooling():
    d, P = _prob()
    cfg = bn.NativeCfg("mesa", 4.0, 0.2, count_max=1, epoch_sweeps=5)
    _, _, st, _ = bn.run(d, P, 100, cfg, 2, np.array([2400]))
    assert 0 < st[-1, bn.S_EPOCHS] <= 100 // 5


def test_same_kernel_as_r1_native_run():
    """b1_native._run and yin_mesa._yin_run implement the same algorithm: same seed -> same best objective."""
    d, P = _prob(30, 5)
    for arm in ("sa", "mesa"):
        a = b1.yin_native_run(d, P, 40, 3.0, 0.2, arm, 11, count_max=60, epoch_sweeps=4)[0]
        b = bn.run(d, P, 40, bn.NativeCfg(arm, 3.0, 0.2, count_max=60, epoch_sweeps=4), 11, np.array([1200]))[0]
        assert a == b


def test_counters_rule():
    c = bn.counters_from([100, 40, 70, 2, 5, 190], n=32, adc_bits=6)
    assert c["array_reads"] == c["field_reads"] == c["lut_reads"] == 100
    assert c["cycles"] == 100 * (3 + 1 + 6) and c["restarts"] == 2 and c["best_updates"] == 5
    assert c["rng_draws"] == 200 + 190 and c["reg_writes"] == 200 + 70 + 80 + 2 * 35 + 5


def test_equal_rule_grids():
    import plan as pl
    for arm in ("sa", "mesa"):
        g = bn.grid(arm)
        assert len(g) == 8 and {(c["pct_hi"], c["pct_lo"]) for c in g} == set(pl.PCT_PAIRS)


def test_harness_record_prices_and_evaluates():
    import evalcommon as ev
    import plan as pl
    from cost_model import CostModel
    spec = pl.Spec(study="h7", phase="test", family="p3n240", instance="801", r=0, arm="b1y.mesa", cfg=bn.grid("mesa")[0],
                   sweeps=3, inst_index=300, tag=7)
    rec = bn.execute(spec)
    ra = ev.run_arrays(rec, CostModel())
    assert rec["desc"]["kind"] == "b1" and rec["desc"]["native"] == "yin" and len(rec["snaps"]) == pl.N_CHECKPOINTS
    assert np.isfinite(ra.e_total) and ra.e_total > 0 and ra.ecum[-1] == pytest.approx(ra.e_total)
    assert rec["price"]["blocks"]["array"] > 0 and rec["price"]["blocks"]["adc"] > 0
