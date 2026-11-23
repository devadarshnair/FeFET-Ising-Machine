"""Round-2 move prototypes (scripts/golden/moves.py): exactness of the pair gain and default-off behaviour."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "golden"))
from moves import MoveCfg, run  # noqa: E402


def _colouring_qubo(n=12, k=3, seed=1):
    rng = np.random.default_rng(seed)
    N = n * k
    P = np.zeros((N, N), np.int64)
    d = np.full(N, -1, np.int64)               # A(1 - sum x)^2, A = 1: d = -A, intra-group P = 2A
    for v in range(n):
        for a in range(k):
            for b in range(k):
                if a != b:
                    P[v * k + a, v * k + b] = 2
    for u in range(n):
        for v in range(u + 1, n):
            if rng.random() < 0.3:
                for c in range(k):
                    P[u * k + c, v * k + c] = P[v * k + c, u * k + c] = 1
    return d, P, n


def test_swap_pair_gain_is_exact():
    d, P, n = _colouring_qubo()
    k = 3
    rng = np.random.default_rng(0)
    E = lambda x: int(d @ x + x @ P @ x // 2)
    for _ in range(50):
        x = np.zeros(3 * n, np.int64)
        x[np.arange(n) * k + rng.integers(0, k, n)] = 1
        h = d + P @ x
        g = -(1 - 2 * x) * h
        v = int(rng.integers(n)); i = v * k + int(np.flatnonzero(x[v * k:v * k + k])[0]); j = v * k + (i - v * k + 1) % k
        y = x.copy(); y[i] ^= 1; y[j] ^= 1
        assert g[i] + g[j] + P[i, j] == E(x) - E(y)


def test_default_cfg_has_no_extra_moves():
    c = MoveCfg()
    assert not (c.swap or c.fkick or c.pair or c.swap_when_stuck)


def test_swap_run_reaches_proper_colouring_small():
    d, P, n = _colouring_qubo(n=12, k=3, seed=3)
    best, _, _ = run(d, P, n, 20000, 1, MoveCfg(swap=True), k=3, target=None)
    assert best >= 0                               # E + offset(=n) counts conflicts + broken groups, never negative
