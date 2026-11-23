"""P1.12 -> canonical table: the rows char_v1 measures are in the table with their char_v1 values and no placeholder flag."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "golden"))

import check_char  # noqa: E402
import cost_model as cm  # noqa: E402

CHAR = Path(__file__).resolve().parents[2] / "circuit" / "char_v1.csv"


def _char():
    return {(r["key"], r["param"]): float(r["value"]) for r in csv.DictReader(open(CHAR, newline=""))}


def test_char_v1_schema():
    assert check_char.check(str(CHAR)) == []


def test_measured_rows_replace_placeholders():
    t, c = cm.canonical_table(), _char()
    assert t["e_array_cell_read"]["value"] == pytest_approx((c[("e_read_fJ", "level=0")] + c[("e_read_fJ", "level=7")]) / 2)
    assert t["e_adc_conv_bit"]["value"] == pytest_approx(c[("e_adc_per_bit_fJ", "bits=8")])
    for k in ("e_array_cell_read", "e_adc_conv_bit", "e_cim_write_l0", "e_cim_write_l7", "n_l0_attempts_bin", "n_l0_attempts_3bit"):
        assert t[k]["placeholder"] == 0 and "char_v1" in t[k]["source"]


def test_level0_verify_costs_more_than_as_measured():
    m = cm.CostModel()
    on, off = m.program_cost(1000, 600, True), m.program_cost(1000, 600, False)
    assert on["e_program_fJ"] > off["e_program_fJ"] and on["t_program_us"] > off["t_program_us"] and off["attempts_l0"] == 1.0


def pytest_approx(x):
    import pytest
    return pytest.approx(x, rel=1e-3)
