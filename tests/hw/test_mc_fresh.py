"""MC-1: fresh G-set-like Max-Cut generator, best-found reference, plumbing into machines (family maxcut, keys R<seed>)."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import machines as mc  # noqa: E402
import mc_fresh as mf  # noqa: E402
from scripts.problems import maxcut as mcut  # noqa: E402


def _h(g):
    return hashlib.sha256(repr(sorted(map(tuple, np.asarray(g.edges).tolist()))).encode()).hexdigest()


def test_statistics_match_g43_47():
    g = mf.graph("R5001")
    assert (g.n, len(g.edges)) == (1000, 9990) and set(np.asarray(g.weights)) == {1.0}
    try:
        ref = mcut.load_gset("G43")
    except Exception:
        pytest.skip("G-set files not present")
    assert (ref.n, ref.m) == (g.n, len(g.edges))


def test_fresh_graphs_are_distinct_and_disjoint_from_every_used_gset():
    fresh = {_h(mf.graph(f"R{5000 + i}")) for i in range(1, 6)}
    assert len(fresh) == 5
    used = []
    for name in [f"G{i}" for i in range(1, 55)]:
        try:
            used.append(_h(mcut.load_gset(name)))
        except Exception:
            continue
    assert not fresh & set(used)


def test_polish_reaches_a_local_optimum_and_never_lowers_the_cut():
    g = mf.graph("R5001", n=60, m=200)
    rng = np.random.default_rng(0)
    x = rng.integers(0, 2, g.n)
    y = mf.polish(g, x)
    assert mf.cut_of(g, y) >= mf.cut_of(g, x)
    for i in range(g.n):
        z = y.copy()
        z[i] ^= 1
        assert mf.cut_of(g, z) <= mf.cut_of(g, y)


def test_best_found_and_reference_plumbing(tmp_path, monkeypatch):
    r = mf.best_found("R5001", restarts=2, sweeps=50, n=60, m=200)
    assert r["best_cut"] == max(r["cuts"]) > 0
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps({"R5001": {"best_cut": 9000}}))
    monkeypatch.setattr(mf, "REF_JSON", ref)
    assert mc.bks_cut("R5001") == 9000 and mc.bks_cut("R5002") is None
    assert mc.bks_cut("G43") == mcut.best_known("G43")


def test_machines_map_fresh_keys_as_maxcut():
    mq = mc.mapped("maxcut", "R5001")
    assert mq.spins == 1000
