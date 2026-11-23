"""CiM local-field path of the golden machine (P2.03).

h_i = d_i + sum_j P_ij x_j, computed as an analog crossbar MAC would: P = P+ - P- (differential pair), each part
stored as w_bits one-bit planes; column (lane i, plane p, polarity) sums its active rows (x_j = 1) as a current,
optional additive read noise (sigma in units of one cell current, seeded), a b-bit ADC with rounding and clipping
converts the sum, and the digital shift-add rebuilds h. d_i is added digitally, exactly.

Integer noise model (P3.03, lfsr = True; mirrored by rtl/src/cim_field_unit.v): every column c = (pol*w_bits +
plane)*n + lane owns a 32-bit xorshift32 state, initialised to seed32 ^ (c * 0x9E3779B1 mod 2^32) (0 -> 1),
seed32 = cfg.seed mod 2^32. Each conversion advances the state (x ^= x<<13; x ^= x>>17; x ^= x<<5) and takes
s = sum of its four bytes (mean 510, sd 147.8); noise (units of 1/256 cell current) = ((s - 510) * sg) >> 8
(arithmetic shift), sg a 16-bit register (sg = round(sigma * 256 * 256 / 147.8) for a given sigma). The ADC code is
(sums*256 + noise + lsb*128) >> (shift + 8), clipped to 0..2^bits-1. sg = 0 gives the noise-free integer result.

ADC: full scale = n rows (cfg.fs = 0, the v1 design used by Stage 2), or cfg.fs cell currents (I7v2, H6: fs = the largest
column sum the programmed array can produce = max over columns of its number of 1-cells; standard CiM practice of setting
the ADC range from the array content, so no conversion can clip). The ADC keeps the top b bits: LSB = 2^s with the smallest s such that the rounded full
scale (n, or fs) fits b bits; with no noise and no clipping each conversion errs by at most 1/2 LSB, so
|h_cim - h| <= 1/2 LSB * sum_p 2^p * 2 (polarities). b >= bitlen(n) gives LSB = 1 and the exact field.
The exact digital field (Machine.h) stays the B3 reference and is what the objective f is updated with.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CimCfg:
    adc_bits: int = 16
    w_bits: int = 8           # magnitude bits per polarity; |P| <= 2^w_bits - 1
    sigma: float = 0.0        # read noise per column conversion, in cell-current units (char_v1 value)
    seed: int = 0
    lfsr: bool = False        # integer xorshift32 noise model above instead of numpy normal noise
    sg: int = 0               # lfsr noise gain register (16 bit)
    fs: int = 0               # ADC full scale in cell currents; 0 = n rows (v1). I7v2: max column sum (see max_column_sum)
    round_even: bool = False  # R8 / A5 (default off): round half to even at LSB > 1 (zero-mean error) instead of half up (one-sided on single-sign columns)


class CimField:
    def __init__(self, cfg: CimCfg, P: np.ndarray, d: np.ndarray):
        self.cfg = cfg
        P = P.astype(np.int64)
        assert np.abs(P).max(initial=0) < 1 << cfg.w_bits, "weight does not fit w_bits"
        self.d = d.astype(np.int64)
        planes = np.arange(cfg.w_bits)
        self.pos = ((np.maximum(P, 0)[None] >> planes[:, None, None]) & 1).astype(np.int64)   # (w, n, n)
        self.neg = ((np.maximum(-P, 0)[None] >> planes[:, None, None]) & 1).astype(np.int64)
        self.weights = (1 << planes).astype(np.int64)
        self.n = P.shape[0]
        assert 0 <= cfg.fs < 1 << 16, "fs register is 16 bit"
        self.set_bits(cfg.adc_bits)
        self.rng = np.random.default_rng(cfg.seed)
        if cfg.lfsr:
            assert 0 <= cfg.sg < 1 << 16
            col = np.arange(2 * cfg.w_bits * self.n, dtype=np.uint64)
            st = (np.uint64(cfg.seed & 0xFFFFFFFF) ^ ((col * np.uint64(0x9E3779B1)) & np.uint64(0xFFFFFFFF)))
            st[st == 0] = 1
            self.lf = st.reshape(2, cfg.w_bits, self.n)
        self.conversions = 0

    def set_bits(self, bits: int) -> None:
        """Set the ADC resolution (I7 switches it at run time): LSB = 2^s, smallest s fitting the full scale in bits."""
        self.adc_bits = bits
        top = (1 << bits) - 1
        s = 0
        while (self.fs + ((1 << s) >> 1)) >> s > top:
            s += 1
        self.shift = s
        self.top = top

    @property
    def fs(self) -> int:
        """ADC full scale in cell currents: cfg.fs, or the row count n (read at set_bits time; B1 tiles reset n)."""
        return self.cfg.fs or self.n

    @property
    def lsb(self) -> int:
        return 1 << self.shift

    def error_bound(self) -> float:
        return 0.5 * self.lsb * 2 * float(self.weights.sum())

    def _lfsr_noise(self) -> np.ndarray:
        """Advance every column LFSR once; returns the (2, w, n) integer noise (1/256 cell units)."""
        m = np.uint64(0xFFFFFFFF)
        x = self.lf
        x ^= (x << np.uint64(13)) & m
        x ^= x >> np.uint64(17)
        x ^= (x << np.uint64(5)) & m
        s = (x & np.uint64(255)) + ((x >> np.uint64(8)) & np.uint64(255)) + ((x >> np.uint64(16)) & np.uint64(255)) \
            + (x >> np.uint64(24))
        return ((s.astype(np.int64) - 510) * self.cfg.sg) >> 8

    def _adc(self, sums: np.ndarray, noise: np.ndarray | None = None) -> np.ndarray:
        self.conversions += sums.size
        if noise is not None:
            code = (sums * 256 + noise + self.lsb * 128) >> (self.shift + 8)
        elif self.cfg.sigma > 0:
            analog = sums + self.cfg.sigma * self.rng.standard_normal(sums.shape)
            code = np.floor(analog / self.lsb + 0.5).astype(np.int64)
        elif self.cfg.round_even and self.shift > 0:
            q, r = sums >> self.shift, sums & (self.lsb - 1)
            half = self.lsb >> 1
            code = q + ((r > half) | ((r == half) & ((q & 1) == 1))).astype(np.int64)
        else:
            code = (sums + (self.lsb >> 1)) >> self.shift
        return np.clip(code, 0, self.top) << self.shift

    def field(self, x: np.ndarray) -> np.ndarray:
        x = x.astype(np.int64)
        nz = self._lfsr_noise() if self.cfg.lfsr else (None, None)
        sp = self._adc(self.pos @ x, nz[0])       # (w, n): column sums per plane
        sn = self._adc(self.neg @ x, nz[1])
        return self.d + self.weights @ (sp - sn)


def max_tile_column_sum(P: np.ndarray, w_bits: int, tile_rows: int) -> int:
    """max_column_sum of the worst row tile when each column is cut into tiles of `tile_rows` rows (cost_model.tiled_counts):
    the full scale one tile ADC must cover (B-3)."""
    P = np.asarray(P, np.int64)
    return max(max_column_sum(P[:, a:a + tile_rows], w_bits) for a in range(0, P.shape[1], tile_rows))


def max_column_sum(P: np.ndarray, w_bits: int) -> int:
    """Largest number of 1-cells in any column (lane, plane, polarity) of the differential bit-plane array of P: the largest
    column current any state x can produce, i.e. the I7v2 ADC full scale (at least 1)."""
    P = np.asarray(P, np.int64)
    best = 0
    for p in range(w_bits):
        best = max(best, int((((np.maximum(P, 0) >> p) & 1).sum(axis=1)).max(initial=0)),
                   int((((np.maximum(-P, 0) >> p) & 1).sum(axis=1)).max(initial=0)))
    return max(best, 1)
