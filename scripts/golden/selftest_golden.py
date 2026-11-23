"""Self-tests of the golden model. Run: scripts/run_guarded.sh <python> -I -B scripts/golden/selftest_golden.py

Prints one "PASS <name>" or "FAIL <name>: why" line per test and exits non-zero on any failure. Some tests read
the reference software study code (read only): the D5c instance generator and splitmix64. NUMBA_CACHE_DIR should point into sim/out.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SWREF = Path("$PROJECT/sw_ref")
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

import instances as gi  # noqa: E402
import tim_golden as tg  # noqa: E402


def test_splitmix_known_values():
    # splitmix64 from seed 0 (published values; also equal to the reference software study's splitmix_fill, see test below)
    assert tg.splitmix64_stream(0, 3) == [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]


def test_splitmix_equals_swref():
    sys.path.insert(0, str(SWREF))
    from histmem.fast.kernels import splitmix_fill
    for seed in (0, 1, 0x123456789ABCDEF, (1 << 64) - 1):
        out = np.zeros(8, dtype=np.uint64)
        splitmix_fill(np.uint64(seed), out)
        assert [int(v) for v in out] == tg.splitmix64_stream(seed, 8), hex(seed)


def test_xoshiro_vector_equals_scalar():
    states = tg.seed_states(0xC0FFEE, 5)
    vec = tg.LaneRngs(states)
    scal = [tg.Xoshiro128ss(*s) for s in states]
    for _ in range(500):
        v = vec.next()
        assert [int(a) for a in v] == [g.next() for g in scal]


def test_xoshiro_output_is_function_of_state():
    g = tg.Xoshiro128ss(1, 2, 3, 4)
    # out = rotl(s1*5, 7)*9 with s1 = 2: rotl(10, 7) = 1280, *9 = 11520
    assert g.output() == 11520
    assert g.next() == 11520 and g.s == [7, 0, 1026, 12288]


def test_lut_shape():
    for lab in (8, 10):
        lut = tg.make_lut(lab)
        assert len(lut) == 1 << lab and max(lut) < 4096 and min(lut) >= 0
        assert all(a >= b for a, b in zip(lut, lut[1:]))
    assert tg.make_lut(10)[0] == round(256 * np.log(2048.0))


def test_select_prob():
    for c in range(1, 257):
        probs = [tg.select_prob(c, r) for r in range(c)]
        assert abs(sum(probs) - 1.0) < 1e-12
        assert max(abs(p - 1.0 / c) for p in probs) <= 1.0 / 65536 + 1e-15


def _float_counts(raw, x, Q, w_max):
    """qkp_nb._kernel lines 96-158 in float (dq = w_max / Q), returning (add count, remove count) per item."""
    dq = w_max / Q
    W, C = raw["W"], raw["C"]
    load = W @ x
    sl = C - load
    flo = np.floor(np.maximum(sl, 0) / dq)
    wq = np.floor(W / dq).T
    add = np.maximum(wq - flo[None, :], 0.0).sum(axis=1)
    ov = np.maximum(-sl, 0)
    rem = np.floor(np.minimum(W.T, ov[None, :]) / dq).sum(axis=1)
    return np.where(x == 0, add, 0.0), np.where(x == 1, rem, 0.0)


def test_pricer_counts_equal_float_formula():
    rng = np.random.default_rng(5)
    for (n, m, s) in ((40, 4, 1), (64, 8, 2), (200, 16, 5000)):
        raw = gi.d5c_make_instance(n, m, s)
        for Q in (8, 16):
            inst = gi.d5c_to_tim(raw, rule="hw", T0=3, T_min=0.1, budget=10, seed=0, lam=1.0, dE_off=1.0, Q=Q)
            rows = tg.thermo_rows(inst)
            for frac in (0.1, 0.3, 0.5, 0.8):
                x = (rng.random(n) < frac).astype(np.int64)
                _, _, _, ca, cr = tg.effective_gain(inst, rows, x, inst.d + inst.P @ x, inst.W @ x)
                fa, fr = _float_counts(raw, x, Q, 50)
                assert np.array_equal(ca, fa.astype(np.int64)) and np.array_equal(cr, fr.astype(np.int64))


def test_d5c_generator_port_equals_swref():
    sys.path.insert(0, str(SWREF / "experiments/d5c_qhinge"))
    import qkp_nb
    for n, m, s in ((16, 8, 3), (64, 8, 1), (200, 16, 5000)):
        a, b = qkp_nb.make_instance(n, m, s), gi.d5c_make_instance(n, m, s)
        for k in ("P", "d", "W", "C"):
            assert np.array_equal(np.asarray(a[k]), b[k]), k


def _check_end_state(inst, res):
    x = res.x
    assert np.array_equal(res.h, inst.d + inst.P @ x)
    assert res.f == tg.objective(inst, x)
    if inst.mode == "knap":
        assert np.array_equal(res.load, inst.W @ x)
    assert res.best_f == tg.objective(inst, res.best_x) and tg.feasible(inst, res.best_x)


def test_machine_invariants():
    d, P = gi.random_qubo(32, 1, 20, 30)
    q = gi.qubo_instance(d, P, seed=11, steps=800, t_start=40.0, t_end=1.0, deoff=3)
    res = tg.Machine(q).run()
    _check_end_state(q, res)
    assert res.flips > 100
    raw = gi.d5c_make_instance(32, 8, 2)
    for rule in ("hw", "penalty", "filter"):
        k = gi.d5c_to_tim(raw, rule=rule, T0=3, T_min=0.1, budget=800, seed=1, lam=1.0, dE_off=1.0)
        res = tg.Machine(k).run()
        _check_end_state(k, res)
        assert res.flips > 50


def test_inst_roundtrip():
    raw = gi.d5c_make_instance(16, 8, 3)
    a = gi.d5c_to_tim(raw, rule="hw", T0=2, T_min=0.02, budget=50, seed=0, lam=2.0, dE_off=0.5)
    d, P = gi.maxcut_qubo(8, gi.ring_graph(8))
    b = gi.qubo_instance(d, P, seed=5, steps=20, t_start=2.0, t_end=None, deoff=0)
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        for inst in (a, b):
            path = Path(tmp) / "x.inst"
            tg.write_inst(inst, path)
            back = tg.read_inst(path)
            assert tg.Machine(back).run().trace == tg.Machine(inst).run().trace
            assert tg.cfg_lines(back, 8) == tg.cfg_lines(inst, 8)


def test_transition_matrix_rows_sum_to_one():
    d, P = gi.random_qubo(4, 3, 4, 4, density=1.0)
    inst = gi.qubo_instance(d, P, seed=1, steps=10, t_start=2.0, t_end=None, deoff=0)
    for pick in ("uniform", "first"):
        mat = tg.transition_matrix(inst, pick)
        assert np.allclose(mat.sum(axis=1), 1.0) and mat.min() >= 0


def test_brute_force_ring_and_torus():
    d, P = gi.maxcut_qubo(8, gi.ring_graph(8))
    inst = gi.qubo_instance(d, P, seed=1, steps=1, t_start=1.0, t_end=None, deoff=0)
    assert gi.brute_force_best(inst)[0] == 8
    d, P = gi.maxcut_qubo(16, gi.torus_graph(4, 4))
    inst = gi.qubo_instance(d, P, seed=1, steps=1, t_start=1.0, t_end=None, deoff=0)
    assert gi.brute_force_best(inst)[0] == 32


def main() -> int:
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:  # noqa: BLE001
            fails += 1
            print(f"FAIL {name}: {traceback.format_exc().strip().splitlines()[-1]}")
    print(f"selftest_golden: {len(tests) - fails}/{len(tests)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
