"""P5.02: copies of the qubo-bridge MaxSAT / colouring mappings equal the bridge (called read-only via
`python -I` from a scratch dir, never imported here) and obey the energy/violation identities by brute force."""
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.problems.colouring import Colouring  # noqa: E402
from scripts.problems.maxsat import MaxSat  # noqa: E402

BRIDGE = ROOT.parents[1] / "sw_ref_wt/qubo"

RUNNER = '''
import json, sys
sys.path.insert(0, sys.argv[1])
import numpy as np
from histmem.instances.external.cnf import MaxSat
from histmem.instances.external.dimacs_col import Colouring
spec = json.load(open(sys.argv[2]))
out = {}
for i, s in enumerate(spec):
    f = MaxSat(f"s{i}", s["nv"], s["clauses"], s["w"]) if s["kind"] == "sat" else Colouring(f"c{i}", s["n"], s["edges"], s["k"])
    (I, J, V), c, c0 = f.to_qubo()
    out[f"I{i}"], out[f"J{i}"], out[f"V{i}"], out[f"c{i}"], out[f"c0{i}"] = I, J, V, c, np.array(c0)
np.savez(sys.argv[3], **out)
'''


def dense(qubo, n):
    (I, J, V), c, _ = qubo
    M = np.zeros((n, n))
    np.add.at(M, (np.minimum(I, J), np.maximum(I, J)), V)
    return M + np.diag(c)


def instances(rng):
    out = []
    for t in range(50):
        if t % 2 == 0:
            nv, m = int(rng.integers(3, 6)), int(rng.integers(2, 5))
            cls = []
            for _ in range(m):
                k = int(rng.integers(1, 5))
                v = rng.choice(nv, size=min(k, nv), replace=False) + 1
                cls.append([int(a) * int(rng.choice([-1, 1])) for a in v])
            w = [float(rng.integers(1, 4)) if rng.random() < 0.3 else None for _ in cls]
            if sum(max(0, len(c) - 2) for c in cls) + nv > 12:
                cls = [c for c in cls if len(c) <= 3]
            out.append({"kind": "sat", "nv": nv, "clauses": cls, "w": w if len(cls) == len(w) else [1.0] * len(cls)})
        else:
            n, k = int(rng.integers(3, 5)), int(rng.integers(2, 4))
            pairs = [(a, b) for a in range(n) for b in range(a + 1, n) if rng.random() < 0.6] or [(0, 1)]
            out.append({"kind": "col", "n": n, "k": k, "edges": pairs})
    return out


def build(s):
    if s["kind"] == "sat":
        return MaxSat("t", s["nv"], s["clauses"], s["w"])
    return Colouring("t", s["n"], s["edges"], s["k"])


def test_matches_bridge_and_identities(tmp_path):
    spec = instances(np.random.default_rng(7))
    assert len(spec) == 50
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "run.py").write_text(RUNNER)
    (scratch / "spec.json").write_text(json.dumps(spec))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1"}
    subprocess.run([sys.executable, "-I", "run.py", str(BRIDGE), "spec.json", "out.npz"], cwd=scratch, env=env,
                   check=True)
    ref = np.load(scratch / "out.npz")
    for i, s in enumerate(spec):
        f = build(s)
        q = f.to_qubo()
        n = f.n_vars
        assert n <= 12
        assert np.array_equal(dense(q, n), dense(((ref[f"I{i}"], ref[f"J{i}"], ref[f"V{i}"]), ref[f"c{i}"], 0), n))
        assert float(q[2]) == float(ref[f"c0{i}"])
        M, c0 = dense(q, n), q[2]
        if s["kind"] == "sat":
            best = {}
            for bits in itertools.product((0, 1), repeat=n):
                x = np.array(bits)
                E = float(x @ M @ x + c0)
                key = bits[:f.nv]
                best[key] = min(best.get(key, 1e18), E)
            for key, E in best.items():
                u = f.unsat(np.array(key))
                wts = f._weights(None)
                assert abs(E - sum(w for w, b in zip(wts, u) if b)) < 1e-9
        else:
            for bits in itertools.product((0, 1), repeat=n):
                x = np.array(bits)
                E = float(x @ M @ x + c0)
                X = x.reshape(f.n, f.k)
                d = f.decode(x)
                assert abs(E - (float(((1 - X.sum(1)) ** 2).sum()) + d["conflicts"])) < 1e-9
                if d["feasible"]:
                    assert abs(E - d["conflicts"]) < 1e-9
