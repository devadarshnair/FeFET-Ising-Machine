"""Published software colouring baselines for H7 (prereg/hw/H7_scaleup.md section 4). Own implementations from the papers:

- DSATUR: Brelaz, "New methods to color the vertices of a graph", CACM 22(4), 1979. Exact rule: pick the uncoloured vertex of
  maximum saturation degree (distinct colours among neighbours), ties by largest degree in the uncoloured subgraph, then lowest
  index; give it the smallest feasible colour.
- TabuCol: Hertz & de Werra, Computing 39, 1987, with the tabu tenure of Galinier & Hao, J. Comb. Optim. 3, 1999:
  tt = L + 0.6 * |conflicting vertices|, L uniform in 0..9; best non-tabu 1-move among conflicting vertices (ties at random),
  aspiration when the move gives a new best. Fixed k; objective = number of monochromatic edges.
- SA: dwave-samplers SimulatedAnnealingSampler (D-Wave reference SA, version pinned in setup.sh) on the same penalty QUBO the
  machines get, default beta range, num_sweeps = the machines' sweep budget.
Pure functions; no machine model.
"""
from __future__ import annotations

import numpy as np


def adjacency(n: int, edges) -> list[np.ndarray]:
    adj = [[] for _ in range(n)]
    for u, v in np.asarray(edges, np.int64).reshape(-1, 2):
        adj[u].append(v)
        adj[v].append(u)
    return [np.array(sorted(set(a)), np.int64) for a in adj]


def dsatur(n: int, edges) -> np.ndarray:
    adj = adjacency(n, edges)
    col = -np.ones(n, np.int64)
    sat = [set() for _ in range(n)]
    deg_unc = np.array([len(a) for a in adj])
    for _ in range(n):
        unc = np.flatnonzero(col < 0)
        key = [(-len(sat[v]), -deg_unc[v], v) for v in unc]
        v = unc[min(range(len(unc)), key=lambda i: key[i])]
        c = 0
        while c in sat[v]:
            c += 1
        col[v] = c
        for w in adj[v]:
            sat[w].add(c)
            deg_unc[w] -= 1
    return col


def conflicts(edges, col) -> int:
    E = np.asarray(edges, np.int64).reshape(-1, 2)
    return int(np.sum(col[E[:, 0]] == col[E[:, 1]]))


def fold_to_k(n: int, edges, col: np.ndarray, k: int) -> np.ndarray:
    """Recolour vertices with colour >= k (in index order) to their least-conflicting colour < k (DSATUR at a fixed k)."""
    adj = adjacency(n, edges)
    col = col.copy()
    for v in np.flatnonzero(col >= k):
        cnt = np.bincount(col[adj[v]][col[adj[v]] < k], minlength=k)
        col[v] = int(np.argmin(cnt))
    return col


def _csr(n: int, edges):
    adj = adjacency(n, edges)
    ptr = np.zeros(n + 1, np.int64)
    ptr[1:] = np.cumsum([len(a) for a in adj])
    nbr = np.concatenate(adj) if ptr[-1] else np.zeros(0, np.int64)
    return ptr, nbr


def tabucol(n: int, edges, k: int, iters: int, seed: int, col0: np.ndarray | None = None) -> dict:
    """TabuCol (see module docstring); numba kernel, random draws from one numpy stream (reproducible per seed)."""
    rng = np.random.default_rng(seed)
    ptr, nbr = _csr(n, edges)
    col = rng.integers(0, k, n).astype(np.int64) if col0 is None else np.asarray(col0, np.int64).copy()
    best_f, best_col, it, best_it = _tabucol_kernel(ptr, nbr, n, k, int(iters), col, int(rng.integers(0, 2**31 - 1)))
    return {"best_conflicts": int(best_f), "colour": best_col, "iters": int(it), "best_iter": int(best_it)}


def _kernel_impl(ptr, nbr, n, k, iters, col, seed):
    np.random.seed(seed)
    gamma = np.zeros((n, k), np.int64)
    for v in range(n):
        for e in range(ptr[v], ptr[v + 1]):
            gamma[v, col[nbr[e]]] += 1
    f = 0
    for v in range(n):
        f += gamma[v, col[v]]
    f //= 2
    best_f, best_col, best_it = f, col.copy(), 0
    tabu = np.zeros((n, k), np.int64)
    n_conf = 0
    it = 0
    big = 1 << 40
    while it < iters and best_f > 0:
        it += 1
        dmin, cnt, mv, mc = big, 0, -1, -1
        n_conf = 0
        for v in range(n):
            g0 = gamma[v, col[v]]
            if g0 == 0:
                continue
            n_conf += 1
            for c in range(k):
                if c == col[v]:
                    continue
                dl = gamma[v, c] - g0
                if tabu[v, c] >= it and not (f + dl < best_f):
                    continue
                if dl < dmin:
                    dmin, cnt, mv, mc = dl, 1, v, c
                elif dl == dmin:                     # uniform choice among ties (reservoir sampling)
                    cnt += 1
                    if np.random.randint(0, cnt) == 0:
                        mv, mc = v, c
        if mv < 0:
            continue
        old = col[mv]
        f += dmin
        col[mv] = mc
        for e in range(ptr[mv], ptr[mv + 1]):
            w = nbr[e]
            gamma[w, old] -= 1
            gamma[w, mc] += 1
        tabu[mv, old] = it + np.random.randint(0, 10) + int(0.6 * n_conf)
        if f < best_f:
            best_f, best_col, best_it = f, col.copy(), it
    return best_f, best_col, it, best_it


try:
    import numba as _nb
    _tabucol_kernel = _nb.njit(cache=False)(_kernel_impl)
except ImportError:                          # pragma: no cover - the pinned env has numba
    _tabucol_kernel = _kernel_impl


def sa_qubo(d: np.ndarray, P: np.ndarray, offset: int, sweeps: int, seed: int) -> dict:
    """dwave-samplers SA on f(x) = d.x + sum_{i<j} P_ij x_i x_j + offset (the machines' mapped QUBO), one read."""
    from dwave.samplers import SimulatedAnnealingSampler
    iu, ju = np.nonzero(np.triu(P, 1))
    Q = {(int(i), int(i)): float(d[i]) for i in range(len(d))}
    Q.update({(int(i), int(j)): float(P[i, j]) for i, j in zip(iu, ju)})
    ss = SimulatedAnnealingSampler().sample_qubo(Q, num_reads=1, num_sweeps=int(sweeps), seed=int(seed) & 0x7FFFFFFF)
    x = np.array([ss.first.sample[i] for i in range(len(d))], np.int64)
    return {"x": x, "energy": float(ss.first.energy) + offset}
