"""MC-1: fresh Max-Cut instances, G-set-like (rudy rnd_graph statistics of G43-G47: 1000 nodes, 9990 edges, unit weights), with a
best-found reference cut (no BKS exists for a fresh graph).

Keys "R<seed>" (seed >= 5000; tests/hw/test_mc_fresh.py checks content-disjointness from the G-set graphs used before). The machines
use them as family "maxcut" (machines.mapped / bks_cut dispatch on the "R" prefix), so every runner and evaluator works unchanged.
Success rule (author decision EP-D2, proposed): cut >= 0.99 x best-found, where best-found = the best cut of REF_RESTARTS independent SA
runs of REF_SWEEPS sweeps each (dwave-samplers on the machines' mapped QUBO), polished by 1-flip descent. After a study, the reference
must be raised to the best cut ANY arm found (post-hoc max), and reported both ways.

  python scripts/testing/mc_fresh.py build R5001 R5002 ... [--restarts 8 --sweeps 4000]   # writes/updates REF_JSON
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE, REPO, REPO / "scripts" / "golden", REPO / "scripts" / "baselines"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

N_NODES, N_EDGES = 1000, 9990
REF_JSON = REPO / "docs" / "hw" / "mc_fresh" / "reference.json"
REF_RESTARTS, REF_SWEEPS = 8, 4000
SUCCESS_FRAC = 0.99


def is_fresh(key: str) -> bool:
    return key.startswith("R") and key[1:].isdigit()


def graph(key: str, n: int = N_NODES, m: int = N_EDGES):
    from scripts.problems import maxcut as mcut
    assert is_fresh(key), key
    g = mcut.random_graph(n, m, seed=int(key[1:]))
    g.name = key
    return g


def mapped(key: str, n: int = N_NODES, m: int = N_EDGES):
    from scripts.problems import load as ld
    g = graph(key, n, m)
    return ld.from_problem("maxcut", g, g.n)


def cut_of(g, x) -> int:
    E = np.asarray(g.edges)
    w = np.asarray(g.weights, float)
    return int(round(float((w * (x[E[:, 0]] != x[E[:, 1]])).sum())))


def polish(g, x):
    """1-flip descent to a local optimum of the cut (exact integer gains)."""
    n = g.n
    adj = [[] for _ in range(n)]
    for (u, v), w in zip(g.edges, g.weights):
        adj[u].append((v, w))
        adj[v].append((u, w))
    x = np.asarray(x, np.int64).copy()
    improved = True
    while improved:
        improved = False
        for i in range(n):
            gain = sum(w if x[j] == x[i] else -w for j, w in adj[i])
            if gain > 0:
                x[i] ^= 1
                improved = True
    return x


def best_found(key: str, restarts: int = REF_RESTARTS, sweeps: int = REF_SWEEPS, n: int = N_NODES, m: int = N_EDGES) -> dict:
    import sw_colouring as sw
    g = graph(key, n, m)
    mq = mapped(key, n, m)
    best, cuts = -1, []
    for r in range(restarts):
        x = sw.sa_qubo(mq.d, mq.P, mq.offset, sweeps, 90000 + 97 * r + int(key[1:]))["x"][:g.n]
        c = cut_of(g, polish(g, x))
        cuts.append(c)
        best = max(best, c)
    return {"best_cut": best, "cuts": cuts, "restarts": restarts, "sweeps": sweeps, "n": n, "m": m,
            "method": "max over SA restarts (dwave-samplers, mapped QUBO) + 1-flip polish"}


def reference(key: str) -> int | None:
    if not REF_JSON.exists():
        return None
    d = json.loads(REF_JSON.read_text())
    return d.get(key, {}).get("best_cut")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build",))
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--restarts", type=int, default=REF_RESTARTS)
    ap.add_argument("--sweeps", type=int, default=REF_SWEEPS)
    ap.add_argument("--out", default=str(REF_JSON))
    a = ap.parse_args(argv)
    out = Path(a.out)
    d = json.loads(out.read_text()) if out.exists() else {}
    for k in a.keys:
        d[k] = best_found(k, a.restarts, a.sweeps)
        print(k, d[k]["best_cut"], d[k]["cuts"], flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(d, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
