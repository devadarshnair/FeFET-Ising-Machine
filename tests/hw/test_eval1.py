"""EVAL-1: a 0 %-success comparator (ETS = inf, ratio 0) is not an energy win when the post-hoc switch is on."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts/testing"))
import evalcommon as ev  # noqa: E402

C = {"ets_ratio": 0.0, "d_success": 0.7, "d_success_ci": (0.5, 0.9), "ets_ci": (0.0, 0.0)}


def test_default_keeps_the_frozen_label():
    assert ev.energy_verdict(C, 0.0) == "win"


def test_switch_labels_zero_comparator_not_evaluable(monkeypatch):
    monkeypatch.setattr(ev, "ZERO_COMPARATOR_NOT_EVALUABLE", True)
    assert ev.energy_verdict(C, 0.0) == "not evaluable"
    assert ev.energy_verdict({**C, "ets_ratio": 0.5, "ets_ci": (0.3, 0.8)}, 0.001) == "win"
