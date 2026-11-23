"""P3.06: widened d (12 bit) / P (10 bit) ranges and the G-set degree table (FIXES R11)."""
import csv
import sys
from pathlib import Path

import numpy as np
import pytest

import gen_tests as gt
import instances as gi
import tim_golden as tg

REPO = Path(__file__).resolve().parents[2]


def test_degree_table_max_is_589():
    assert gt.gset_max_degree() == 589
    rows = list(csv.DictReader(open(REPO / "scripts/problems/gset_degree_table.csv")))
    assert len(rows) == 71


def test_gset800_hub_fits_and_runs_without_overflow():
    n, edges = gt.gset800_like(589)
    d, P = gi.maxcut_qubo(n, edges)
    assert d.max() == 589 and d.max() > 127          # did not fit the old 8-bit bias
    inst = tg.pad_instance(gi.qubo_instance(d, P, seed=1, steps=40, t_start=40.0, t_end=5.0, deoff=2), 1024)
    inst.check_widths()
    tg.Machine(inst).run()                            # asserts |h| < 2^17 on every step


@pytest.mark.parametrize("bad", ("d_hi", "d_lo", "p_hi", "p_lo"))
def test_out_of_range_rejected(bad):
    d, P = gi.random_qubo(8, 1, 3, 3)
    d, P = d.copy(), P.copy()
    if bad == "d_hi": d[0] = 2048
    if bad == "d_lo": d[0] = -2049
    if bad == "p_hi": P[0, 1] = P[1, 0] = 512
    if bad == "p_lo": P[0, 1] = P[1, 0] = -513
    inst = gi.qubo_instance(d, P, seed=1, steps=3, t_start=2.0, t_end=None, deoff=0)
    with pytest.raises(AssertionError):
        inst.check_widths()


@pytest.mark.parametrize("edge", ("d", "p"))
def test_range_edges_accepted(edge):
    d, P = gi.random_qubo(8, 1, 3, 3)
    d, P = d.copy(), P.copy()
    if edge == "d": d[0], d[1] = 2047, -2048
    else: P[0, 1] = P[1, 0] = 511; P[2, 3] = P[3, 2] = -512
    gi.qubo_instance(d, P, seed=1, steps=3, t_start=2.0, t_end=None, deoff=0).check_widths()
