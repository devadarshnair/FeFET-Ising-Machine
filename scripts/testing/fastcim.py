"""Exact incremental column sums for the CiM field (a run-time optimisation, not a model change).

cim_field.CimField recomputes pos @ x and neg @ x (w x n x n integer matrix-vector products, ~3 ms at N = 1024) on every read. The
machine changes x by one accepted flip per step (or an L-bit kick / a reload), so the same integer sums can be maintained from the
changed bits: sums += matrix[:, :, changed] @ delta. Integer arithmetic, same ADC (the parent's _adc, same noise draw order), hence
bit-identical fields; tests/hw/test_testing_runner.py compares full machine traces with and without it (ours, B1 tiles, I7, noise).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "golden"))
from cim_field import CimField  # noqa: E402


class FastCimField(CimField):
    @classmethod
    def adopt(cls, cf: CimField) -> CimField:
        cf.__class__ = cls
        cf._xprev = None
        cf._sp = cf._sn = None
        return cf

    def _sums(self, x: np.ndarray):
        j = None if self._xprev is None else np.flatnonzero(x != self._xprev)
        if j is None or j.size > max(8, x.size // 8):
            self._sp, self._sn = self.pos @ x, self.neg @ x
        elif j.size:
            dx = x[j] - self._xprev[j]
            self._sp = self._sp + self.pos[:, :, j] @ dx
            self._sn = self._sn + self.neg[:, :, j] @ dx
        self._xprev = x.copy()
        return self._sp, self._sn

    def field(self, x: np.ndarray) -> np.ndarray:
        x = x.astype(np.int64)
        sp_sum, sn_sum = self._sums(x)
        nz = self._lfsr_noise() if self.cfg.lfsr else (None, None)
        sp = self._adc(sp_sum, nz[0])
        sn = self._adc(sn_sum, nz[1])
        return self.d + self.weights @ (sp - sn)
