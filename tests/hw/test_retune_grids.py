"""Stage 1 re-tune grids (internal review item 9.3.2): every arm gets 12 configurations that change its parameters AND its trajectory."""
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import machines as mc  # noqa: E402
import run_h8 as rh  # noqa: E402
import s1_retune_grids as g  # noqa: E402
from cost_model import CostModel  # noqa: E402


def _spec(label, family, key, over, sweeps=1.0):
    a = SimpleNamespace(label=label, family=family, phase="main", cond="ideal", mit="none", c2c=0.5, sweeps=sweeps, ours_tile_rows=0)
    s = rh.make_spec(a, key, 0)
    return dataclasses.replace(s, tag=10, inst_index=1500 + int(key.lstrip("G")) % 1000, cfg={**s.cfg, **over})


def test_scaled_temps_default_is_identity():
    assert mc.scaled_temps((6.0, 1.0), {}) == (6.0, 1.0)
    assert mc.scaled_temps((6.0, 1.0), {"t_hi_mult": 1.5, "t_lo_mult": 0.25}) == (9.0, 0.25)


@pytest.mark.parametrize("label", list(g.GRIDS))
def test_twelve_configs_per_arm(label):
    assert len(g.GRIDS[label]) == 12


@pytest.mark.parametrize("cell", [("p3n480", "2101"), ("p4n480", "2201"), ("maxcut", "G43")])
@pytest.mark.parametrize("label", list(g.GRIDS))
def test_every_config_has_distinct_effective_parameters(label, cell):
    fam, key = cell
    eff = [tuple(sorted(mc.effective_params(_spec(label, fam, key, o)).items())) for o in g.GRIDS[label]]
    assert len(set(eff)) == 12, eff


def test_old_pct_lo_axis_was_inert_on_colouring():
    a = mc.effective_params(_spec("B3_v2", "p3n480", "2101", {"pct_hi": 90, "pct_lo": 5, "knob": 1.0}))
    b = mc.effective_params(_spec("B3_v2", "p3n480", "2101", {"pct_hi": 90, "pct_lo": 10, "knob": 1.0}))
    assert a == b


@pytest.mark.parametrize("label", list(g.GRIDS))
def test_every_config_changes_the_trajectory(label):
    sig = set()
    for o in g.GRIDS[label]:
        sw = 2.0 if label in ("B3_v2", "ours_none") else 30.0      # kick arms need stalls before K / L can act
        r = mc.execute(_spec(label, "p3n480", "2101", o, sweeps=sw), CostModel())
        sig.add((tuple(r["curve"]), r["flips"], r["best_E"], r.get("restarts")))
    assert len(sig) == 12
