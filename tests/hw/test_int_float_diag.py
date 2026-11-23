"""P2.08: DiagMachine with no float factor is bit-exact to Machine; each factor runs and stays finite."""
import numpy as np
import pytest

import instances as gi
import int_float_diag as dg
import tim_golden as tg


def _inst(rule, q=8):
    raw = gi.d5c_make_instance(200, 16, 5000)
    gsh = 3 if rule != "hw" else int(np.log2(q))
    return raw, gi.d5c_to_tim(raw, rule=rule, T0=3.0, T_min=0.05, budget=400, seed=100, lam=0.25, dE_off=0.5,
                              Q=q, gsh=gsh)


@pytest.mark.parametrize("rule", ["hw", "penalty", "filter"])
def test_no_factor_is_bit_exact(rule):
    _, inst = _inst(rule)
    ref = tg.Machine(inst).run(steps=400).trace[:-1]
    m = dg.DiagMachine(inst, (), 1.0, 1.0, 1.0)
    assert [m.step() for _ in range(400)] == ref


@pytest.mark.parametrize("floats", [("lut",), ("lam",), ("temp",), ("eoff",), dg.FACTORS])
def test_factor_runs(floats):
    raw, inst = _inst("hw")
    lam_f, deoff_f = dg.float_registers(raw, dict(lam=0.25, dE_off=0.5), "hw", 8, 3)
    m = dg.DiagMachine(inst, floats, lam_f, deoff_f, (0.05 / 3.0) ** (1 / 399))
    m.temp_f = 3.0 * float(np.abs(raw["d"]).mean()) * 8 * 65536
    r = m.run(steps=400, keep_trace=False)
    assert r.best_f > 0


def test_float_lambda_close_to_register():
    raw, inst = _inst("hw")
    lam_f, _ = dg.float_registers(raw, dict(lam=0.25, dE_off=0.5), "hw", 8, 3)
    assert abs(lam_f - inst.lam) <= 0.5
