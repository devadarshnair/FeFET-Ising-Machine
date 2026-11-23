"""H6 (Stage 3) design checks: I7v2 ADC full scale, fs re-pricing, MESA epoch harness, fresh instances/seeds, budget."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
for sub in ("scripts/testing", "scripts/golden", "."):
    sys.path.insert(0, str(ROOT / sub))

import gen_jobs_stage3 as g3  # noqa: E402
import h6_instances as h6i  # noqa: E402
import plan as pl  # noqa: E402
import plan_h6 as p6  # noqa: E402
from cim_field import CimCfg, CimField, max_column_sum  # noqa: E402


def _rand_P(n=64, seed=1, wmax=7):
    rng = np.random.default_rng(seed)
    P = rng.integers(-wmax, wmax + 1, (n, n)) * (rng.random((n, n)) < 0.2)
    P = np.triu(P, 1)
    return P + P.T


def test_fs_adc_exact_at_bitlen_of_max_column_sum():
    P = _rand_P()
    d = np.zeros(64, np.int64)
    fs = max_column_sum(P, 3)
    cf = CimField(CimCfg(adc_bits=fs.bit_length(), w_bits=3, fs=fs), P, d)
    rng = np.random.default_rng(2)
    for _ in range(50):
        x = rng.integers(0, 2, 64)
        assert np.array_equal(cf.field(x), d + P @ x)
    assert cf.lsb == 1


def test_fs_zero_is_the_v1_full_scale():
    P = _rand_P()
    a = CimField(CimCfg(adc_bits=6, w_bits=3), P, np.zeros(64, np.int64))
    assert a.fs == 64 and a.shift == 1


def test_i7v2_low_bits_error_at_most_one_cell_per_conversion():
    P = _rand_P()
    fs = max_column_sum(P, 3)
    cf = CimField(CimCfg(adc_bits=fs.bit_length() - 1, w_bits=3, fs=fs), P, np.zeros(64, np.int64))
    x = np.random.default_rng(3).integers(0, 2, 64)
    assert np.abs(cf.field(x) - P @ x).max() <= cf.error_bound() and cf.lsb == 2


def test_planted_colouring_has_zero_energy_optimum():
    import machines as ma
    for fam in ("col3p", "col4p"):
        n, k, _ = h6i.FAMILIES[fam]
        mq = ma.mapped(fam, "501")
        rng = np.random.default_rng([20261117, n, k, 501])
        colour = rng.permutation(n) % k
        x = np.zeros(n * k, np.int64)
        x[np.arange(n) * k + colour] = 1
        assert mq.spins == n * k and mq.energy(x) == 0


def test_fresh_instances_and_seed_stream():
    for fam in ("maxcut",):
        used = set(pl.TEST_SET[fam]) | set(pl.TUNE_SET[fam])
        assert not (set(p6.TEST_SET[fam]) | set(p6.TUNE_SET[fam])) & used
    for fam in p6.FAMILIES:
        assert not set(p6.TEST_SET[fam]) & set(p6.TUNE_SET[fam])
    assert p6.SEED_TAG != 0


def test_mesa_epoch_holds_the_floor_and_restarts():
    import machines as ma
    from cost_model import CostModel
    cfg = dict(pl.default_config("mesa").as_dict(), knob=0.125, epoch_sweeps=2)
    spec = pl.Spec("h6", "test", "col3p", "601", 0, "b1.mesa", cfg, sweeps=8, inst_index=250, tag=6)
    b = ma.build(spec, CostModel(), 8 * 120)
    assert b.t_floor > 0
    rec = ma.drive(spec, CostModel())
    assert rec["restarts"] > 0 and rec["desc"]["epoch_sweeps"] == 2


def test_stage3_budget_within_cap():
    bud = g3.budget()
    assert bud["billed_vcpu_h_incl_gate"] <= 60
    assert max(j.secs for j in g3.all_jobs() if j.mode == "par") <= 1800


@pytest.mark.parametrize("arm", ["ours.kc2.i10", "ours.mesa.i10", "ours.da_offset.i10"])
def test_restart_sweep_grid(arm):
    cs = p6.sweep_configs(pl.Arm.parse(arm).restart, pl.default_config("kc2").as_dict())
    assert len(cs) == (12 if "kc2" in arm else 3 if "mesa" in arm else 6) and len({c["cid"] for c in cs}) == len(cs)


# ------------------------------------------------------------------------------------------------ H6 amendment 1
def test_mesa_sweep_k_is_at_least_the_epoch():
    cs = p6.sweep_configs("mesa", pl.default_config("mesa").as_dict())
    assert [c["knob"] for c in cs] == [10.0, 20.0, 40.0] and all(c["knob"] >= p6.EPOCH_SWEEPS for c in cs)
    assert p6.B1_MESA_EPOCH_KNOB >= p6.EPOCH_SWEEPS


@pytest.mark.parametrize("fs", list(range(3, 70)) + [143])
def test_i7v2_low_bits_lsb_at_most_two(fs):
    import machines as ma
    b_hi, b_lo = ma.i7v2_bits(fs)
    cf = CimField(CimCfg(adc_bits=b_lo, w_bits=3, fs=fs), np.zeros((4, 4), np.int64), np.zeros(4, np.int64))
    assert b_hi == fs.bit_length() and cf.lsb <= 2
    assert CimField(CimCfg(adc_bits=b_hi, w_bits=3, fs=fs), np.zeros((4, 4), np.int64), np.zeros(4, np.int64)).lsb == 1


def _h5_rec(inst, best_E, pid):
    return {"spec": {"instance": inst, "pert": {"pid": pid}}, "best_E": best_E}


def test_graded_h5_score_and_loss_point():
    import evaluate_h6 as e6
    tg = {"G8": {"E_ref": -2000.0, "E_target": -1980.0}}
    st = e6.graded_stats("maxcut", [_h5_rec("G8", -1900.0, "nominal"), _h5_rec("G8", -1960.0, "nominal")], tg)
    assert st["cut_frac"] == pytest.approx(0.965) and st["score"] == pytest.approx(0.65)
    row = {pid: {"score": s} for pid, s in (("nominal", 0.6), ("dev_x2", 0.58), ("dev_x4", 0.3))}
    lp = e6.graded_loss_points(row)
    assert 2.0 < lp["dev"] < 4.0 and "read" not in lp


def test_graded_h5_colouring_reports_conflicts():
    import evaluate_h6 as e6
    tg = {"501": {"E_ref": 0.0, "E_target": 0.0}}
    st = e6.graded_stats("col3p", [_h5_rec("501", 2.0, "nominal"), _h5_rec("501", 0.0, "nominal")], tg)
    assert st["conflicts"] == 1.0 and "cut_frac" not in st


def test_h5_b1_subset_and_budget():
    assert {p.pid for p in p6.h5_arm_points(p6.H5_B1)} == set(p6.H5_B1_POINTS)
    assert len(p6.h5_arm_points(p6.H5_ARMS[0])) == 18
    assert g3.budget()["billed_vcpu_h_incl_gate"] <= 60
