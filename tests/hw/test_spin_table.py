"""P5.03: spin counts equal the qubo-bridge matrix sizes (SAT and colouring, bridge run read-only via `python -I`
from a scratch dir), Max-Cut counts equal the G-set headers, and every row carries a fit flag per machine."""
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.problems import maxcut as mc  # noqa: E402
from scripts.problems import spin_table as st  # noqa: E402
from scripts.problems.colouring import Colouring  # noqa: E402
from scripts.problems.maxsat import MaxSat  # noqa: E402

BRIDGE = ROOT.parents[1] / "sw_ref_wt/qubo"

RUNNER = '''
import json, sys
sys.path.insert(0, sys.argv[1])
from histmem.instances.external.cnf import MaxSat
from histmem.instances.external.dimacs_col import Colouring
spec = json.load(open(sys.argv[2]))
out = []
for s in spec:
    f = MaxSat("b", s["nv"], s["clauses"], s["w"]) if s["kind"] == "sat" else Colouring("b", s["n"], s["edges"], s["k"])
    (I, J, V), c, c0 = f.to_qubo()
    out.append(len(c))
json.dump(out, open(sys.argv[3], "w"))
'''


def bridge_spec(problem):
    if isinstance(problem, MaxSat):
        return {"kind": "sat", "nv": problem.nv, "clauses": problem.clauses,
                "w": [None if w is None else float(w) for w in problem.weights]}
    return {"kind": "col", "n": problem.n, "k": problem.k, "edges": problem.edges.tolist()}


def bridge_sizes(problems, tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "run.py").write_text(RUNNER)
    (scratch / "spec.json").write_text(json.dumps([bridge_spec(p) for p in problems]))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1"}
    subprocess.run([sys.executable, "-I", "run.py", str(BRIDGE), "spec.json", "out.json"], cwd=scratch, env=env,
                   check=True)
    return json.loads((scratch / "out.json").read_text())


def test_sat_and_colouring_counts_equal_bridge(tmp_path):
    rows = [(f, p, lv) for f, p, lv in st.problem_instances() if isinstance(p, (MaxSat, Colouring))]
    assert rows
    sizes = bridge_sizes([p for _, p, _ in rows], tmp_path)
    for (family, problem, logical), size in zip(rows, sizes):
        spins = st.table_row(family, problem, logical)["spins"]
        assert spins == size, problem.name
        assert problem.n_vars == size, problem.name


def test_maxcut_counts_equal_gset_headers():
    for name in ("G1", "G6", "G11", "G14"):
        header_n = int(Path(mc.GSET_DIR / name).read_text().split()[0])
        assert st.table_row("maxcut", mc.load_gset(name), header_n)["spins"] == header_n


def test_extra_spins_and_logical_counts_add_up():
    for row in st.build_table():
        assert row["logical_vars"] + row["extra_spins"] == row["spins"], row["instance"]


def test_every_row_has_fit_flag_per_machine(tmp_path):
    out = tmp_path / "spin_table.csv"
    st.write_table(out)
    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(st.build_table())
    allowed = {"fits", "does_not_fit"}
    for row in rows:
        for machine in ("fit_ours", "fit_b1", "fit_b2", "fit_b3"):
            flag = row[machine]
            assert flag in allowed or flag.startswith("tiled:"), (row["instance"], machine)


def test_fit_flags_follow_capacities():
    for row in st.build_table():
        spins = row["spins"]
        assert (row["fit_ours"] == "fits") == (spins <= st.OURS_SPINS)
        assert (row["fit_b2"] == "fits") == (spins <= st.B2_VARS)
        if spins > st.B1_TILE:
            assert row["fit_b1"] == f"tiled:{row['b1_tiles']}"
            assert row["b1_tiles"] == int(np.ceil(spins / st.B1_TILE)) ** 2


def test_coupling_bits_cover_range():
    for row in st.build_table():
        bound = max(abs(row["coupling_min"]), abs(row["coupling_max"]))
        assert bound < 2 ** (row["coupling_bits"] - 1)
