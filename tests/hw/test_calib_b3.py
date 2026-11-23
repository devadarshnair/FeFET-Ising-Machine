"""P4.04: evaluator pieces of scripts/baselines/calib_b3.py on synthetic rows (no scored data)."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "baselines"))

import calib_b3 as cb  # noqa: E402


def test_tts_opt():
    assert cb.tts_opt([], 5) == math.inf
    assert cb.tts_opt([10, 20, 30], 3) == 30.0                      # all hit: t at the last hit
    assert cb.tts_opt([5], 50) == pytest.approx(5 * math.log(0.01) / math.log(1 - 1 / 50))


def _rows(kind, sizes, base):
    rows = []
    for n in sizes:
        for i in range(4):
            for arm in ("off", "on"):
                t = int(base * 10 ** (0.002 * n))                    # every run hits at t: TTS = t
                rows.append(dict(kind=kind, n=n, inst=i, arm=arm, attempt=1, runs=2, iters=10 ** 6,
                                 best=[7, 7], best_step=[t, t], boost=[n * 0.9, n * 0.8]))
    return rows


def test_evaluate_recovers_slope():
    sizes = (64, 128, 256)
    res = cb.evaluate(_rows("bimodal", sizes, 1000) + _rows("gaussian", sizes, 1000), 1, sizes)
    assert res["T1"]["value"] == pytest.approx(0.002, rel=0.02) and res["T1"]["passed"]
    assert res["T2"]["passed"] and res["T3"]["value"] == pytest.approx(1.0) and res["T3"]["passed"]
    assert res["T4"]["passed"] and res["T4"]["excluded"] == 0


def test_offset_rate():
    assert cb.offset_rate(10.0, "off") == 0 and cb.offset_rate(10.0, "on") == 2 and cb.offset_rate(1.0, "on") == 1
