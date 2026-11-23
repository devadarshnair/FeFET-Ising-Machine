"""P5.04: one mapped QUBO for every machine config; quantisation loss reported."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.problems import load as ld  # noqa: E402

MACHINES = ("ours", "b1", "b2", "b3")


@pytest.mark.parametrize("family", sorted(ld.FAMILIES))
def test_identical_hash_and_spins_across_machines(family):
    insts = ld.FAMILIES[family](10)
    assert len(insts) == 10 and len({m.sha256() for m in insts}) == 10
    for mq in insts:
        cfgs = ld.machine_configs(mq)
        assert set(cfgs) == set(MACHINES)
        assert {c.mapped_sha256 for c in cfgs.values()} == {mq.sha256()}
        assert {c.spins for c in cfgs.values()} == {mq.spins}


def test_hash_is_content_sensitive():
    mq = ld.FAMILIES["maxsat"](1)[0]
    P = mq.P.copy()
    P[0, 1] += 1
    P[1, 0] += 1
    assert ld.MappedQubo(mq.name, mq.family, mq.d, P, mq.offset, mq.logical_vars).sha256() != mq.sha256()


@pytest.mark.parametrize("family", sorted(ld.FAMILIES))
def test_energy_matches_problem(family):
    rng = np.random.default_rng(3)
    for mq in ld.FAMILIES[family](3):
        x = rng.integers(0, 2, mq.spins)
        assert mq.energy(x) == int(mq.d @ x + x @ np.triu(mq.P, 1) @ x + mq.offset)


def test_quantisation_lossless_when_in_range_and_reported_otherwise():
    mq = ld.FAMILIES["maxcut"](1)[0]  # +-1 weights: couplings +-2 fit every machine
    assert all(c.quant.loss["lossless"] for c in ld.machine_configs(mq).values())
    big = ld.MappedQubo("big", "maxsat", np.array([0, 5000, 0, 0]), np.array([[0, 900, 0, 0], [900, 0, 0, 0],
                        [0, 0, 0, 3], [0, 0, 3, 0]]), 0, 4)
    cfgs = ld.machine_configs(big)
    assert not cfgs["ours"].quant.loss["lossless"] and cfgs["ours"].quant.scale < 1
    assert cfgs["ours"].quant.loss["rel_rms_energy_error"] >= 0
    assert not cfgs["b1"].quant.loss["lossless"] and cfgs["b3"].quant.loss["lossless"]


def test_ours_instance_valid_and_padded():
    mq = ld.FAMILIES["colouring"](1)[0]
    inst = ld.machine_config("ours", mq).instance
    inst.check_widths()
    assert inst.n & (inst.n - 1) == 0 and int(inst.lane_en.sum()) == mq.spins


def test_machine_arms():
    mq = ld.FAMILIES["maxcut"](1)[0]
    cfgs = ld.machine_configs(mq)
    assert cfgs["ours"].arms == ("none", "da_offset", "kc2") and cfgs["b1"].arms == ("mesa",)
    assert cfgs["b3"].arms == ("da_offset",) and cfgs["b2"].arms == ("hycim",)


def test_qkp_same_object_for_b2_and_ours():
    import hycim as hc
    rng = np.random.default_rng(1)
    n = 32
    P = np.triu(rng.integers(0, 50, (n, n)), 1)
    inst = hc.Inst("synth", rng.integers(1, 100, n), P, rng.integers(1, 50, n), 300)
    mq = ld.load_qkp(inst)
    x = rng.integers(0, 2, n)
    assert mq.energy(x) == -int(round(inst.profit(x)))
    cfgs = ld.machine_configs(mq)
    assert {c.mapped_sha256 for c in cfgs.values()} == {mq.sha256()}
    assert cfgs["b2"].instance.C == 300


def test_report_written(tmp_path):
    rows = ld.write_report(tmp_path / "q.csv")
    assert len(rows) == 3 * 10 * 4 and all("rel_rms_energy_error" in r for r in rows)
