"""BASELINES_V2 (prereg/calib/P4_v2_reproduction.md): fast DA kernels vs the golden B3, B3 v2 schedule knob, MESA v2 rules
(epoch cooling, hold, trap counter only after cooling = K >= epoch, few-bit kick), native Yin kernel, harness hooks."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "baselines"))
sys.path.insert(0, str(ROOT / "scripts" / "testing"))
sys.path.insert(0, str(ROOT))

import fujitsu_da as da  # noqa: E402
import yin_mesa as b1  # noqa: E402
from instances import maxcut_qubo, qubo_instance, random_graph, temp_reg  # noqa: E402


def sk(n=16, i=0, kind="bimodal"):
    return da.sk_qubo(n, i, kind)


def brute_max(d, P):
    n = len(d)
    X = ((np.arange(1 << n)[:, None] >> np.arange(n)) & 1).astype(np.int64)
    f = X @ d + 0.5 * np.einsum("ki,ij,kj->k", X, P, X)
    return int(round(f.max()))


# ------------------------------------------------------------------------------------------------ B3 fast kernels
def test_da_anneal_reaches_ground_state_small_sk():
    d, P = sk(12, 3)
    best, when = da.da_anneal(d, P, 40.0, 0.5, 3000, 20, seed=7)
    assert best.max() == brute_max(d, P) and (when <= 3000).all()


def test_da_kernel_matches_golden_b3_distribution():
    """Same algorithm, float Metropolis vs the golden LUT: mean best over runs agrees within 3 % of |f*|, and both find the
    ground state of a 14-spin SK at about the same rate (+-0.25)."""
    d, P = sk(14, 1)
    fstar = brute_max(d, P)
    steps, runs = 600, 60
    fast, _ = da.da_anneal(d, P, 40.0, 1.0, steps, runs, seed=11)
    gold = []
    for r in range(runs):
        inst = qubo_instance(d, P, seed=1000 + r, steps=steps, t_start=40.0, t_end=None, deoff=0)
        m = da.b3_machine(inst, da.B3Cfg(schedule="lin_beta", t_high=40.0, t_low=1.0), counters=False)
        m.run(keep_trace=False)
        gold.append(m.best_f)
    gold = np.array(gold)
    assert abs(fast.mean() - gold.mean()) <= 0.03 * abs(fstar)
    assert abs((fast == fstar).mean() - (gold == fstar).mean()) <= 0.25


def test_da_const_t_boost_limits():
    """Aramon Eqs. 1-3: Pp / Ps -> N at low T and -> 1 at high T."""
    d, P = sk(16, 2)
    pp, ps = da.da_const_t(d, P, 0.05, 2000, 500, seed=3)
    assert pp / ps > 0.95 * 16
    pp, ps = da.da_const_t(d, P, 1e5, 200, 200, seed=3)
    assert pp / ps < 1.01


def test_jeffreys_tts():
    assert da.jeffreys_tts(0, 50, 100) > 100 * 50          # never solved: finite but large (posterior mean 1/102)
    assert da.jeffreys_tts(50, 50, 100) == 100.0           # R99 floored at one run
    assert da.jeffreys_tts(10, 50, 100) == pytest.approx(100 * np.log(0.01) / np.log(1 - 10.5 / 51))


def test_aramon_table1_units():
    assert da.aramon_table1("bimodal") == (40.0, 4.0)
    assert da.aramon_table1("gaussian") == pytest.approx((20.0, 1.0))


# ------------------------------------------------------------------------------------------------ B3 v2 knob
def test_b3v2_t_final_matches_ours_half_schedule():
    th, tl = 6.0, 1.0
    assert da.b3v2_t_final(th, tl, 1.0) == tl
    # ours 'none' at schedule fraction 0.5: geometric T_start -> T_end over half the run, continued for the other half
    assert da.b3v2_t_final(th, tl, 0.5) == pytest.approx(tl * (tl / th))
    cfg = da.b3v2_cfg(th, tl, 0.5)
    assert cfg.offset_rate == 0 and cfg.schedule == "lin_beta" and cfg.t_low == pytest.approx(1 / 6)
    with pytest.raises(AssertionError):
        da.b3v2_t_final(th, tl, 0.7)


def test_harness_grids_are_eight_configs_each():
    import plan as pl
    for r in ("b3v2", "mesa2", "none", "kc2", "mesa", "b3", "b2"):
        g = pl.grid(r)
        assert len(g) == 8 and len({c.cid for c in g}) == 8
        if r != "b2":
            assert {(c.pct_hi, c.pct_lo) for c in g} == set(pl.PCT_PAIRS)


def _spec(arm, knob, fam="p3n240", inst="801", sweeps=2):
    import plan as pl
    cfg = dict(pl.Config("x", 85, 5, knob).as_dict())
    return pl.Spec(study="h7", phase="test", family=fam, instance=inst, r=0, arm=arm, cfg=cfg, sweeps=sweeps, inst_index=300, tag=7)


def test_harness_b3v2_offset_off_lin_beta():
    import machines as M
    from cost_model import CostModel
    b = M.build(_spec("b3.b3v2", 0.5), CostModel(), 100)
    assert b.m.b3.offset_rate == 0 and b.m.b3.schedule == "lin_beta" and b.m.deoff == 0
    assert b.desc["offset_rate"] == 0 and b.desc["t_final"] < b.m.b3.t_high
    rec = M.drive(_spec("b3.b3v2", 0.5), CostModel())
    assert rec["price"]["blocks"]["restart"] == 0.0


def test_harness_b1_mesa2_unit_and_pricing():
    import machines as M
    from cost_model import CostModel
    b = M.build(_spec("b1.mesa2", 1.0), CostModel(), 480)
    assert isinstance(b.m.restart, b1.MesaV2Unit) and b.m.deoff == 0
    assert b.desc["restart"] == "mesa" and b.desc["mesa_variant"] == "v2"
    assert b.m.restart.epoch_steps == b1.MESA2_EPOCH_SWEEPS * 240 and b.m.restart.K == 240


# ------------------------------------------------------------------------------------------------ MESA v2 (A2 lock-in)
def _mesa2(n=24, K=1, steps=4000, epoch_sweeps=2, seed=5):
    d, P = maxcut_qubo(n, random_graph(n, 0.3, seed))
    inst = qubo_instance(d, P, seed=0xBEEF + seed, steps=steps, t_start=4.0, t_end=0.2, deoff=0)
    return b1.b1_mesa2_machine(inst, b1.B1Cfg(count_max=K), 0.2, epoch_sweeps=epoch_sweeps), n


def test_mesa2_epoch_cools_to_floor_then_holds():
    m, n = _mesa2(K=10 ** 9)
    temps = []
    for _ in range(6 * n):
        m.step()
        temps.append(m.temp)
    floor = temp_reg(0.2)
    assert temps[0] > 2 * floor and min(temps) == floor
    assert all(t == floor for t in temps[2 * n:])          # epoch length 2 sweeps, then held (never below T_end)


@pytest.mark.parametrize("K", [1, 3])
def test_mesa2_never_restarts_before_the_epoch_has_cooled(K):
    """A2: K >= epoch is structural: even K = 1 cannot end an epoch before E sweeps have passed."""
    m, n = _mesa2(K=K)
    m.run(keep_trace=False)
    ev = m.restart.events
    assert ev, "MESA v2 never restarted"
    gaps = np.diff([0] + ev)
    assert (gaps >= 2 * n - 1).all()                        # alpha reaches T_end after E n - 1 multiplications


def test_mesa2_restart_resets_t0_and_kicks_few_bits_from_best():
    m, n = _mesa2(K=2)
    seen = 0
    for _ in range(4000):
        best_before = m.best_x.copy()
        if m.restart.events and m.restart.events[-1] == m.t:
            pass
        m.step()
        if m.restart.events and m.restart.events[-1] == m.t:
            seen += 1
            assert m.temp == m.inst.t0 and m.eoff == 0
            assert 1 <= int((m.x != best_before).sum()) <= b1.MESA2_KICK_MAX
    assert seen > 0 and set(m.restart.kicks) <= {1, 2, 3}


def test_old_whole_run_mesa_regression_documented():
    """P4.02 attempt-1 bug (whole-run cooling + T := T0 reset) stays reproducible in the legacy arm, and MESA v2 is not it:
    legacy restarts every Count_max steps from the start; v2's first restart is after the epoch."""
    from restart import RestartCfg
    from tim_golden import Machine
    n = 24
    d, P = maxcut_qubo(n, random_graph(n, 0.3, 5))
    inst = qubo_instance(d, P, seed=0xBEEF + 5, steps=4000, t_start=4.0, t_end=0.2, deoff=0)
    old = Machine(inst, restart=RestartCfg(arm="mesa", K=n))
    old.run(keep_trace=False)
    assert old.restart.events[0] < 4000 // 4                # legacy: restarts while the whole-run schedule is still hot
    m, _ = _mesa2(K=n, epoch_sweeps=4)
    m.run(keep_trace=False)
    assert m.restart.events[0] >= 4 * n + n // 2             # v2: cool one epoch (4n), then trapped steps


# ------------------------------------------------------------------------------------------------ native Yin kernel
def test_yin_native_sa_finds_max_cut_small():
    n = 14
    d, P = maxcut_qubo(n, random_graph(n, 0.4, 3))
    fstar = brute_max(d, P)
    hits = [b1.yin_native_run(d, P, 400, 3.0, 0.1, "sa", s)[0] == fstar for s in range(10)]
    assert np.mean(hits) >= 0.8


def test_yin_native_mesa_epochs_respect_cooling_and_curve_monotone():
    n = 20
    d, P = maxcut_qubo(n, random_graph(n, 0.4, 4))
    best, curve, epochs, _ = b1.yin_native_run(d, P, 300, 3.0, 0.1, "mesa", 1, count_max=1, epoch_sweeps=10)
    assert 0 < epochs <= 300 // 10                          # count_max = 1 still waits for each 10-sweep epoch to cool
    assert (np.diff(curve) >= 0).all() and curve[-1] == best == brute_max(d, P)


def test_yin_native_multi_bit_delta_exact():
    """The incremental m-bit dE of the kernel equals the objective difference: f recomputed from best x == reported best f."""
    n = 30
    d, P = maxcut_qubo(n, random_graph(n, 0.5, 9))
    for mode in ("sa", "mesa"):
        for s in range(5):
            best, curve, _, x = b1.yin_native_run(d, P, 40, 4.0, 0.3, mode, s, count_max=5, epoch_sweeps=3)
            assert best == int(d @ x + x @ P @ x // 2) and best == curve[-1]


# ------------------------------------------------------------------------------------------------ A7 own clock
def _rows(tmp_path, b3_lane):
    p = tmp_path / "rows.csv"
    p.write_text("key,block,kind,unit,value,band_lo_x,band_hi_x,source,placeholder\n"
                 f"tt_t_lane_path_b3,time,time,ns per cycle,{b3_lane},0.8,1.5,test,0\n"
                 "tt_t_lane_path_ours_rerun,time,time,ns per cycle,2.4,0.8,1.5,test,0\n"
                 "tt_a_lane_b3,digital,area,um2,1000,0.8,1.5,test,0\n")
    return p


@pytest.mark.parametrize("b3_lane", [3.0, 50.0])
def test_own_clock_rules(tmp_path, b3_lane):
    import baseline_clock as bc
    from cost_model import MeasuredCost
    k = bc.OwnClockCost(rows=_rows(tmp_path, b3_lane))
    ref = MeasuredCost()
    lane = max(k.blocks["tt_t_lane_path"]["value"], k.blocks["tt_t_rng_path"]["value"])
    for n in (64, 256, 1024):
        assert k.t_clk_at(n, "ours") == ref.t_clk_at(n, "ours")
        assert k.t_clk_at(n, "b3") == pytest.approx(max(ref.t_clk_at(n, "ours"), b3_lane))
        assert k.t_clk_at(n, "b1") == pytest.approx(lane)          # Yin: no select tree


def test_own_clock_b1_pays_tile_sum_cycles(tmp_path):
    import baseline_clock as bc
    k = bc.OwnClockCost(rows=_rows(tmp_path, 3.0))
    c = {"cycles": 1000, "array_reads": 100}
    one = k.at({"kind": "b1", "n_act": 32, "n_pad": 32})
    eight = k.at({"kind": "b1", "n_act": 240, "n_pad": 256})       # 8 row tiles -> 3 extra cycles per read
    assert one.time_ns(c) == pytest.approx(1000 * one.v("t_clk"))
    assert eight.time_ns(c) == pytest.approx((1000 + 3 * 100) * eight.v("t_clk"))
