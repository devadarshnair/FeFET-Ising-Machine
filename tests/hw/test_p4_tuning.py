"""P4-1: the Stage 1b re-tune can be planned for p4n480 on its own tuning keys (2201-2208), same grids and rule."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import s1b_retune as sb  # noqa: E402


def test_p4_plan(tmp_path):
    out = tmp_path / "jobs.tsv"
    try:
        assert sb.main(["--cell", "p4n480", "plan", str(out)]) == 0
        lines = out.read_text().splitlines()
        assert lines and all("--family p4n480" in l and "--keys 2201,2202" in l and ".p4n480\\t" not in l for l in lines)
        assert all(l.split("\t")[0].endswith(".p4n480") for l in lines)
        assert sb.main(["--cell", "p4n480", "check"]) == 0
    finally:
        sb.set_cell("p3n480")


def test_default_cell_unchanged(tmp_path):
    out = tmp_path / "jobs.tsv"
    sb.main(["plan", str(out)])
    assert all("--family p3n480" in l for l in out.read_text().splitlines())
