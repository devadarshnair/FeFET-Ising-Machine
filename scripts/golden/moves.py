"""Round-2 move prototypes (DEFAULT OFF; not wired into tim_golden.Machine, no RTL counterpart).

A lean exact-integer replica of the I11 plateau walk (accept uniformly among moves with gain >= 0) plus the Kc2
stall kick (K stall steps without improving the epoch best -> flip L random spins), extended with optional moves:

  swap   one-hot SWAP: for a group (vertex) with set lane i and unset lane j, flip both in one step. Exact pair gain
         from the two lane fields: g_ij = g_i + g_j - s_i s_j P_ij  (s = +1 for 0->1, -1 for 1->0), P_ij = 2A known.
  fkick  feasible kick: the Kc2 kick recolours L random groups (clear the set lane, set a random other lane) instead of
         flipping L random spins, so the kick never pays the one-hot penalty.
  pair   Max-Cut edge pair flip: flip both ends of an edge (i, j) when g_i + g_j - s_i s_j P_ij >= 0.

Energy convention: minimise E = d.x + x.P.x/2 (+offset); gain g = -dE. Field h = d + P x; dE_i = (1 - 2 x_i) h_i.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MoveCfg:
    K: int = 0                 # stall window (0 = 0.25 n)
    L: int = 10                # kick size
    swap: bool = False
    fkick: bool = False
    pair: bool = False
    swap_when_stuck: bool = False   # swaps join the pool only when no single flip has gain > 0


def run(d, P, offset, steps, seed, cfg: MoveCfg, k: int = 0, edges=None, target=None):
    """Return (best_E, step_reached_target or -1, kicks). k = one-hot group size (0 = no groups)."""
    rng = np.random.default_rng(seed)
    n = len(d)
    x = np.zeros(n, np.int64)
    h = d.astype(np.int64).copy()
    E = int(offset)
    best = E
    hit = -1
    K = cfg.K or max(1, n // 4)
    stall, epoch = 0, E
    kicks = 0
    G = n // k if k else 0
    if cfg.pair:
        eu, ev = edges[:, 0], edges[:, 1]
        pw = P[eu, ev]

    def flip(i):
        nonlocal E
        s = 1 - 2 * x[i]
        E += int(s * h[i])
        x[i] ^= 1
        h[:] += s * P[:, i]

    for t in range(steps):
        g = -(1 - 2 * x) * h
        cands = []                                   # (kind, flat index array)
        sing = np.flatnonzero(g >= 0)
        pool_n = sing.size
        sw = None
        if cfg.swap and k and (not cfg.swap_when_stuck or not (g > 0).any()):
            X = x.reshape(G, k)
            gg = g.reshape(G, k)
            # pair (i set, j unset) in the same group: g_i + g_j - (-1)(+1) P_ij = g_i + g_j + P_ij, P_ij = 2A
            pij = P[0, 1]
            m = (X[:, :, None] == 1) & (X[:, None, :] == 0)
            sg = gg[:, :, None] + gg[:, None, :] + pij
            sw = np.flatnonzero((m & (sg >= 0)).ravel())
            pool_n += sw.size
        pr = None
        if cfg.pair:
            s = 1 - 2 * x
            pg = g[eu] + g[ev] - s[eu] * s[ev] * pw
            pr = np.flatnonzero(pg >= 0)
            pool_n += pr.size
        if pool_n:
            r = int(rng.integers(pool_n))
            if r < sing.size:
                flip(int(sing[r]))
            else:
                r -= sing.size
                if sw is not None and r < sw.size:
                    f = int(sw[r]); v, rem = divmod(f, k * k); a, b = divmod(rem, k)
                    flip(v * k + a); flip(v * k + b)
                else:
                    r -= 0 if sw is None else sw.size
                    e = int(pr[r]); flip(int(eu[e])); flip(int(ev[e]))
        if E < best:
            best = E
            if target is not None and E <= target and hit < 0:
                hit = t
                break
        if E < epoch:
            epoch, stall = E, 0
        else:
            stall += 1
        if stall >= K:
            kicks += 1
            if cfg.fkick and k:
                for v in rng.choice(G, size=min(cfg.L, G), replace=False):
                    row = x[v * k:(v + 1) * k]
                    on = np.flatnonzero(row)
                    for c in on:
                        flip(v * k + int(c))
                    c = int(rng.integers(k))
                    flip(v * k + c)
            else:
                for i in rng.choice(n, size=min(cfg.L, n - 1), replace=False):
                    flip(int(i))
            epoch, stall = E, 0
            if E < best:
                best = E
    return best, hit, kicks
