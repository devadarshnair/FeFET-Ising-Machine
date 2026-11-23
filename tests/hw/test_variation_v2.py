"""VARIATION_V2 (scripts/testing/variation_v2.py): physics model, mitigation switches, costs, harness plumbing."""
import csv
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import machines as mc  # noqa: E402
import plan as pl  # noqa: E402
import variation_v2 as v2  # noqa: E402
from cim_field import CimCfg, CimField  # noqa: E402
from cost_model import CostModel  # noqa: E402

COST = CostModel()
NEEDS_QKP = pytest.mark.skipif(not v2.qkp_available(), reason="QKP benchmark data (09_next_phase/benchmarks/qkp_billionnet_soutif + "
                               "optima.json) not found from this checkout; set HW_PROJECT_ROOT or HW_QKP_DIR/HW_QKP_OPTIMA")
TUNED = v2._tuned()["colouring"]
ARMS = {"ours": ("ours.kc2.fs.i11", "ours.kc2.i10.i11"), "b1": ("b1.none.fs", "b1.none"), "b1bs": ("b1bs.none.fs", "b1.none")}


def spec(machine, pert=None, sweeps=8, family="col3p", inst="501", r=0):
    arm, tk = ARMS[machine]
    return pl.Spec(study="t", phase="t", family=family, instance=inst, r=r, arm=arm, cfg=TUNED[tk], sweeps=sweeps,
                   pert=pert, inst_index=400, tag=v2.SEED_TAG)


def same(a, b):
    return a["curve"] == b["curve"] and a["flips"] == b["flips"] and a["best_E"] == b["best_E"] \
        and a["price"]["e_total"] == b["price"]["e_total"]


# ------------------------------------------------------------------ cell physics
def test_transfer_samples_reproduce_char_v1():
    rows = list(csv.DictReader(open(REPO / "circuit" / "cim" / "cim_cell_v1.csv")))
    d = np.genfromtxt(v2.MC_CSV, delimiter=",", names=True)
    for k in range(8):
        i = d["i_read_nA"][d["level"] == k]
        assert len(i) == 200
        assert i.std(ddof=1) == pytest.approx(float(rows[k]["i_sigma_nA"]), rel=1e-4)


def test_transfer_monotone_and_nominal():
    tr = v2.transfer()
    g = np.linspace(-0.6, 0.6, 241)
    for k in range(8):
        i = tr.current(k, g)
        assert np.all(np.diff(i) <= 1e-12) and np.all(i > 0) and np.all(i <= v2.I_SAT_CAP_NA)
    assert tr.current(7, 0.0) == pytest.approx(99.15, rel=2e-3)
    assert tr.current(0, 0.0) < 0.1


def test_drift_shift_signs():
    p = pl.Perturb("d", drift_v_dec=0.02)
    assert v2.drift_shift(0, p) < 0 < v2.drift_shift(7, p)
    assert v2.drift_shift(0, pl.Perturb("n")) == 0.0


def test_program_ideal_exact_and_cost():
    lv = np.array([[0, 7, 3], [7, 0, 0]])
    p = v2.program_cells(lv, False, v2.vx(0), v2.Mitigation(model="v2"), np.random.default_rng(0))
    assert np.allclose(p["i_op"] / v2.transfer().unit_ml, lv)
    c = v2.program_cost([p], False)
    cell = v2.transfer().cell
    assert c["e_program_fJ"] == pytest.approx(3 * cell[0]["e_write_fJ"] + 2 * cell[7]["e_write_fJ"] + cell[3]["e_write_fJ"])
    assert c["pulses_per_cell"] == 1.0


def test_write_verify_level0_and_multilevel():
    rng = np.random.default_rng(1)
    mit = v2.Mitigation(model="v2", wv=True)
    tr = v2.transfer()
    p0 = v2.program_cells(np.zeros(4000, int), True, pl.Perturb("n"), mit, rng)
    open_ = v2.program_cells(np.zeros(4000, int), True, pl.Perturb("n"), v2.Mitigation(model="v2"), rng)
    thr = mit.wv_window * tr.unit_bin
    assert np.mean(p0["i_op"] < thr) > 0.99 > np.mean(open_["i_op"] < thr) - 0.0     # verify removes most of the tail
    assert p0["i_op"].std() < open_["i_op"].std()
    assert p0["pulses"][0] >= 4000 and p0["verifies"][0] == p0["pulses"][0]
    p3 = v2.program_cells(np.full(2000, 3), False, pl.Perturb("n"), mit, rng)
    err = np.abs(p3["i_op"] / tr.target(3, False) - 1)
    assert np.mean(err < mit.wv_window) > 0.95
    assert p3["pulses"][3] > 2000                         # ISPP pulses + C2C redraws are charged


# ------------------------------------------------------------------ switches off = bit-exact
@pytest.mark.parametrize("machine", ["ours", "b1"])
def test_v1_mitigation_is_legacy_bit_exact(machine):
    s = spec(machine, pert=pl.H5_POINTS[0].as_dict())
    a = mc.execute(s, COST)
    b = mc.execute(s, COST, v2.Mitigation())
    assert same(a, b)


@pytest.mark.parametrize("machine", ["ours", "b1", "b1bs"])
@pytest.mark.parametrize("mit", ["none", "wv", "diff", "cal", "r3", "bin", "wv+diff+cal+r3"])
def test_v2_ideal_device_bit_exact_to_unperturbed(machine, mit):
    base = mc.execute(spec(machine), COST)
    r = mc.execute(spec(machine, pert=v2.vx(0).as_dict()), COST, v2.Mitigation.parse(mit))
    assert same(base, r)


def test_mitigation_parse_roundtrip_and_v1_guard():
    for lab in ("none", "wv", "wv0.02+diff", "diff+cal+r3", "wv+diff+cal+bin"):
        assert v2.Mitigation.parse(lab).label == lab
    with pytest.raises(AssertionError):
        v2.Mitigation(model="v1", diff=True)
    with pytest.raises(AssertionError):
        v2.Mitigation(model="v2", reads=2)


# ------------------------------------------------------------------ column engine
def _cf(counts, binary, mit, pert, adc=lambda r: (1, 255), tile=None, seed=0):
    nr = counts.shape[-1]
    w = (1 << np.arange(counts.shape[1])) if binary else np.array([1])
    return v2.ColumnField(counts, binary, tile or nr, w, pert, mit, np.random.default_rng(seed), adc)


def test_column_engine_matches_cimfield_rounding():
    rng = np.random.default_rng(3)
    P = rng.integers(-15, 16, (40, 40))
    np.fill_diagonal(P, 0)
    d = np.zeros(40, np.int64)
    cim = CimField(CimCfg(adc_bits=4, w_bits=4), P, d)        # LSB > 1: rounding active
    planes = np.arange(4)
    counts = np.stack([(np.maximum(P, 0)[None] >> planes[:, None, None]) & 1, (np.maximum(-P, 0)[None] >> planes[:, None, None]) & 1])
    cf = _cf(counts, True, v2.Mitigation(model="v2"), v2.vx(0), adc=lambda r: (cim.lsb, cim.top))
    for _ in range(20):
        x = rng.integers(0, 2, 40)
        assert np.array_equal(np.rint(cf.field_delta(x)).astype(np.int64), cim.field(x))


def test_diff_and_calib_cancel_common_leakage():
    rng = np.random.default_rng(4)
    n = 200
    bits = (rng.random((2, 1, 8, n)) < 0.3).astype(int)
    x = np.ones(n, int)
    exact = bits.sum(-1)[..., None]
    out = {}
    for lab in ("none", "diff+cal"):
        mit = v2.Mitigation.parse(lab)
        cf = _cf(bits, True, mit, v2.vx(0))
        m0 = 0.01                                             # 1 nA per OFF cell: 200 active rows x 0.7 -> 1.4 counts
        cf.A = cf.A + m0 * (cf.V == 0)
        cf.A_cal = cf.A
        if mit.diff:
            cf.B = cf.B + m0 * (cf.V == 1)
            cf.B_cal = cf.B
            cf._calibrate(np.ones(1))
        cf.reset_sums()
        out[lab] = cf.column_codes(x)
    assert np.any(out["none"] != exact)
    assert np.array_equal(out["diff+cal"], exact)


def test_calibration_removes_adc_offsets():
    rng = np.random.default_rng(5)
    bits = (rng.random((2, 1, 64, 64)) < 0.4).astype(int)
    pert = pl.Perturb("m", dev=0.0, write=0.0, read=0.0, mismatch=4.0)     # 1 LSB offsets, nothing else
    x = rng.integers(0, 2, 64)
    exact = (bits * x).sum(-1)[..., None]
    raw = _cf(bits, True, v2.Mitigation(model="v2"), pert, seed=9).column_codes(x)
    cal = _cf(bits, True, v2.Mitigation(model="v2", calib=True), pert, seed=9).column_codes(x)
    assert np.mean(raw != exact) > 0.2
    assert np.array_equal(cal, exact)


def test_redundant_reads_reduce_dynamic_errors():
    rng = np.random.default_rng(6)
    bits = (rng.random((2, 1, 64, 128)) < 0.5).astype(int)
    pert = pl.Perturb("r", dev=0.0, write=0.0, mismatch=0.0, read=60.0)     # dynamic noise only, ~0.4 count rms
    x = np.ones(128, int)
    exact = bits.sum(-1)[..., None]
    err = {}
    for R in (1, 3, 5):
        cf = _cf(bits, True, v2.Mitigation(model="v2", reads=R), pert, seed=2)
        err[R] = np.mean([np.mean(cf.column_codes(x) != exact) for _ in range(10)])
    assert err[1] > err[3] > err[5]


def test_adc_clipping_is_simulated():
    bits = np.ones((2, 1, 4, 16), int)
    cf = _cf(bits, True, v2.Mitigation(model="v2"), v2.vx(0), adc=lambda r: (1, 7))
    assert cf.column_codes(np.ones(16, int)).max() == 7


# ------------------------------------------------------------------ costs
def _rec(machine, mit="none", k=1.0):
    s = spec(machine, pert=v2.vx(k).as_dict())
    r = mc.execute(s, COST, v2.Mitigation.parse(mit))
    return r


def test_cost_off_is_zero_and_reads_triple():
    r = _rec("ours")
    c0 = v2.mitigation_cost(r, v2.Mitigation.parse("none"), COST)
    assert c0["d_run_fJ"] == 0 and c0["d_area_um2"] == 0 and c0["e_run_fJ"] == r["price"]["e_total"]
    r3 = _rec("ours", "r3")
    c3 = v2.mitigation_cost(r3, v2.Mitigation.parse("r3"), COST)
    b = r3["price"]["blocks"]
    assert c3["d_run_fJ"] >= 2 * (b["array"] + b["adc"])
    assert c3["d_time_ns"] > 0


def test_cost_diff_and_calib_charge_area_and_once():
    r = _rec("b1", "diff+cal")
    c = v2.mitigation_cost(r, v2.Mitigation.parse("diff+cal"), COST)
    assert c["d_area_um2"] > r["price"]["area"]["array"]
    assert c["e_once_fJ"] > r["prog_v2"]["e_program_fJ"]
    assert r["prog_v2"]["cells"] == 2 * mc.execute(spec("b1", pert=v2.vx(1).as_dict()), COST,
                                                   v2.Mitigation.parse("none"))["prog_v2"]["cells"]


def test_b3_has_no_overhead():
    s = pl.Spec(study="t", phase="t", family="col3p", instance="501", r=0, arm="b3.b3", cfg=TUNED["b3.b3"], sweeps=4,
                inst_index=400, tag=8)
    r = mc.execute(s, COST)
    c = v2.mitigation_cost(r, v2.Mitigation.parse("wv+diff+cal+r3"), COST)
    assert c["d_run_fJ"] == 0 and c["e_once_fJ"] == 0


def test_b1bs_fs_bits_are_bitplane_sums():
    r = mc.execute(spec("b1bs"), COST)
    assert r["desc"]["adc_bits_fs"] <= 6                     # 32-row binary tile column: max 32 -> <= 6 bits


# ------------------------------------------------------------------ B2
@NEEDS_QKP
@pytest.mark.parametrize("mit", ["none", "bin", "diff", "wv+diff+bin"])
def test_b2_filter_ideal_exact(mit):
    hc = v2.hycim()
    inst = hc.load("jeu_100_25_1.txt")
    x = hc.feasible_random(inst, np.random.default_rng(0))
    f = v2.b2_filter_v2(inst, v2.vx(0), v2.Mitigation.parse(mit), np.random.default_rng(0), x)
    assert np.allclose(f["w_eff"], inst.w) and f["cref"] == pytest.approx(inst.C + 0.5) and f["sigma"] == 0


@NEEDS_QKP
def test_b2_v2_run_and_cost():
    r = v2.run_job({"machine": "b2", "family": "jeu_100_25_1.txt", "point": "vx0", "mit": "bin", "r": 0})
    assert r["quality"] > 0.9 and r["cost"]["d_area_um2"] > 0


# ------------------------------------------------------------------ harness plumbing
def test_grid_and_points():
    for m, n in (("ours", 920), ("b1", 1060), ("b2", 530), ("b3", 20)):
        jobs = v2.grid(m)
        assert len(jobs) == n and len({v2.job_key(j) for j in jobs}) == n
    assert v2.point("vx0").ideal and v2.point("drift0.02").drift_v_dec == 0.02 and v2.point("t_d2d").write == 0


def test_vmc_family_and_reference():
    mq = mc.mapped("vmc120", "1")
    assert mq.spins == 120
    assert v2.vmc_reference("vmc120", "1") > 0.7 * 480


def test_smoke_job_ours_runs():
    r = v2.run_job({"machine": "ours", "family": "col3p", "point": "vx1", "mit": "wv+diff+cal", "r": 0})
    assert set(r) >= {"success", "quality", "cost", "prog_v2"} and r["cost"]["overhead_pct"] > 0


@NEEDS_QKP
def test_b2_calibration_uses_the_shared_rule():
    j = {"machine": "b2", "family": "jeu_100_25_1.txt", "point": "vx0", "mit": "cal", "r": 0}
    r = v2.run_job(j)
    import hycim_b2 as hb2
    L = 10_000
    cc = v2.calib_cost(COST, cols=1, bits=hb2.CMP_BITS, conversions=L, cells_per_col=100 * hb2.ROWS + hb2.ROWS * hb2.COLS)
    assert r["cost"]["items"]["calib_fJ"] == pytest.approx(cc["run_fJ"])
    assert r["cost"]["d_area_um2"] == pytest.approx(cc["area_um2"])


def test_qkp_paths_resolve_or_skip_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("HW_QKP_DIR", str(tmp_path))
    monkeypatch.setenv("HW_QKP_OPTIMA", str(tmp_path / "missing.json"))
    hc = v2.hycim()
    assert hc.QKP_DIR.is_dir() or not v2.qkp_available()
    monkeypatch.delenv("HW_QKP_DIR")
    monkeypatch.delenv("HW_QKP_OPTIMA")


def test_c2c_share_context_and_effect():
    lv = np.zeros(3000, int)
    rng = lambda: np.random.default_rng(7)          # noqa: E731
    mit = v2.Mitigation(model="v2", wv=True)
    with v2.c2c_share(0.0):
        a = v2.program_cells(lv, True, pl.Perturb("n"), mit, rng())
    assert v2._C2C[0] == v2.C2C_SHARE
    with v2.c2c_share(0.75):
        b = v2.program_cells(lv, True, pl.Perturb("n"), mit, rng())
    thr = mit.wv_window * v2.transfer().unit_bin
    assert np.mean(b["i_op"] < thr) > np.mean(a["i_op"] < thr)     # no C2C part: re-erase cannot remove the D2D tail


def test_calib_cost_rule():
    c = v2.calib_cost(COST, cols=10, bits=6, conversions=1000, cells_per_col=32)
    assert c["run_fJ"] == pytest.approx(1000 * COST.v("e_adc_conv_bit"))
    assert c["once_fJ"] > 0 and c["area_um2"] > 0


def test_wilson_and_newcombe():
    lo, hi = v2.wilson(0, 60)
    assert lo == 0 and 0.05 < hi < 0.07
    lo, hi = v2.wilson(10, 20)
    assert lo < 0.5 < hi
    d, lo, hi = v2.newcombe_diff(60, 60, 60, 60)
    assert d == 0 and lo < 0 < hi and lo > -0.07


def test_stat_grid_design():
    for m in ("ours", "b1"):
        jobs = v2.grid_stat(m)
        assert len({v2.job_key(j) for j in jobs}) == len(jobs)
        dec = [j for j in jobs if j["point"] == "vx1" and j["mit"] == "wv+diff+cal" and j["c2c"] == v2.C2C_SHARE]
        for f, insts in v2.STAT_INST.items():
            fj = [j for j in dec if j["family"] == f]
            assert {j["inst"] for j in fj} == set(insts) and len(fj) == 3 * v2.DEC_SEEDS
        assert {j["c2c"] for j in jobs} == set(v2.C2C_GRID)
    b2 = v2.grid_stat("b2")
    assert all(j["proposals"] == 100_000 for j in b2) and len({j["inst"] for j in b2}) == 3
    assert {j["point"] for j in v2.grid_stat("ours_i7v2")} == {f"vx{k:g}" for k in v2.K_GRID}


def test_restoring_selection_rule():
    rows = []
    for f in ("a", "b", "c", "d"):          # four families x 60 runs, as the grid
        rows.append(dict(machine="m", family=f, point="vx0", mit="none", c2c=0.5, k=60, n=60, overhead_pct=0, e_once_fJ=0, d_area_pct=0))
        rows.append(dict(machine="m", family=f, point="vx1", mit="cheap", c2c=0.5, k=50, n=60, overhead_pct=5, e_once_fJ=0, d_area_pct=0))
        rows.append(dict(machine="m", family=f, point="vx1", mit="good", c2c=0.5, k=60, n=60, overhead_pct=30, e_once_fJ=0, d_area_pct=0))
    res = v2.restoring(rows, "m")
    assert [r["mit"] for r in res] == ["good"]                        # 50/60 vs 60/60 per family: significantly worse, not restoring
    same = [dict(r, k=39 if r["point"] == "vx0" or r["mit"] == "good" else 20) for r in rows]
    assert [r["mit"] for r in v2.restoring(same, "m")] == ["good"]    # identical counts at p = 0.65 restore (pooled margin)


def test_script_and_import_share_module_state():
    """Run as a script (__main__), the module must be the one machines.py imports, else the C2C share set by the harness is lost."""
    import subprocess
    code = ("import runpy, sys\n"
            "sys.argv = ['v']\n"
            "try:\n    runpy.run_path('scripts/testing/variation_v2.py', run_name='__main__')\n"
            "except SystemExit:\n    pass\n"
            "import variation_v2\n"
            "assert variation_v2.__name__ == '__main__', variation_v2.__name__\n"
            "print('shared')\n")
    out = subprocess.run([sys.executable, "-I", "-c", code], cwd=REPO, capture_output=True, text=True)
    assert "shared" in out.stdout, out.stderr


# ------------------------------------------------------------------ R13 tiled LSB-1 ours simulator
@pytest.fixture
def tiled():
    old = v2.OURS_TILE_ROWS
    v2.OURS_TILE_ROWS = 256
    yield
    v2.OURS_TILE_ROWS = old


@pytest.mark.parametrize("mit", ["none", "wv+diff+cal"])
def test_r13_tiled_ideal_device_bit_exact_to_unperturbed(tiled, mit):
    s = dict(family="p3n480", inst="1101", sweeps=2)
    base = mc.execute(spec("ours", **s), COST)
    r = mc.execute(spec("ours", pert=v2.vx(0).as_dict(), **s), COST, v2.Mitigation.parse(mit))
    assert same(base, r) and r["desc"]["sim_tile_rows"] == 256


def test_r13_tiled_sim_is_inactive_at_one_tile_and_by_default(tiled):
    r = mc.execute(spec("ours", pert=v2.vx(1).as_dict()), COST, v2.Mitigation.parse("wv+diff+cal"))
    assert "sim_tile_rows" not in r["desc"]                              # n_act <= 256: the legacy column, unchanged
    v2.OURS_TILE_ROWS = None
    r = mc.execute(spec("ours", pert=v2.vx(1).as_dict(), family="p3n480", inst="1101", sweeps=2), COST, v2.Mitigation.parse("wv"))
    assert "sim_tile_rows" not in r["desc"]


def test_r13_tiled_columns_have_per_tile_adc_and_offsets(tiled):
    b = mc.build(spec("ours", pert=v2.vx(1).as_dict(), family="p3n480", inst="1101", sweeps=2), COST, 10, v2.Mitigation.parse("wv"))
    cf = b.m.cim.cf
    assert cf.nb == 2 and cf.tile == 256 and cf.off.shape[-1] == 2
    assert cf.adc(0)[0] == 1 and cf.adc(0)[1] <= b.m.cim.inner.top
