"""Stall-gated power (I10) and stall-adaptive ADC precision (I7) of the golden machine (P2.04). Defaults off.

Counter: consecutive steps without a strict improvement of the best-so-far feasible objective (the MESA counter of
restart.py, kept here so it exists for every restart arm); updated after the step, read by the next step.

I10 (event-driven read): the field read (array MAC + ADC, or the digital h when no CiM path) is skipped when no flip
was accepted in the previous step and the field cache is valid; the cached field is used instead. Any state change
(flip, restart reload/kick) or ADC precision change invalidates the cache. This is lossless for a deterministic
field (no CiM, or CiM with sigma = 0): a skipped read would return the cached value. With read noise it freezes
the last noise sample instead of drawing a new one (not lossless). During a skipped read
with counter > K_g the ADC bias is also gated (counted in bias_gated).

I7 (precision): ADC bits = b_hi while counter <= K_p, b_lo once counter > K_p, back to b_hi on the step after an
improvement (the counter resets to 0). Needs the CiM path.

Counter semantics (documented for H6, unchanged; RTL power_ctl.v matches): the counter resets ONLY on a strict improvement of
the best-so-far objective, not on an accepted flip. After the early descent, new bests are rare, so once counter > K_p
the ADC stays at b_lo for most of the run, with b_hi bursts of K_p + 1 steps after each new best. I7 is therefore in
practice "a b_lo ADC with high-precision bursts", and b_lo must be accurate enough to anneal on.
I7 v1 (Stage 2): ADC full scale = n rows, b_hi = bitlen(n), b_lo = b_hi - 4: at n = 1024 the b_lo LSB is 16 cell currents
while real column sums are <= ~26, so ~88 % of fields quantise to 0 (design flaw, docs/hw/results/STAGE2_RESULTS.md).
I7v2 (H6): ADC full scale = the largest column sum of the programmed array (CimCfg.fs = cim_field.max_column_sum), so
b_hi = bitlen(fs) is exact (LSB 1) and b_lo = b_hi - 1 gives LSB 2 (error <= 1 cell current per conversion) when the rounded half
scale fits; for fs = 2^b - 2 or 2^b - 1 it would be LSB 4, so the machine runner keeps b_lo = b_hi there (machines.i7v2_bits).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PowerCfg:
    i10: bool = False
    K_g: int = 64            # I10 ADC bias gating threshold on the counter
    i7: bool = False
    b_hi: int = 16
    b_lo: int = 8
    K_p: int = 32            # I7 switch threshold on the counter

    def __post_init__(self):
        assert self.K_g >= 0 and self.K_p >= 0 and 1 <= self.b_lo <= self.b_hi


class PowerUnit:
    def __init__(self, cfg: PowerCfg, machine):
        self.cfg = cfg
        assert not cfg.i7 or machine.cim is not None, "I7 needs the CiM field path"
        self.counter = 0
        self.last_best = machine.best_f
        self.cache = None
        self.reads = 0
        self.skipped = 0
        self.bias_gated = 0
        self.bits_trace: list[int] = []

    def invalidate(self) -> None:
        self.cache = None

    def field(self, m):
        """Field for this step, with I7 precision selection and I10 read skipping."""
        if self.cfg.i7:
            bits = self.cfg.b_lo if self.counter > self.cfg.K_p else self.cfg.b_hi
            if bits != m.cim.adc_bits:
                m.cim.set_bits(bits)
                self.cache = None
            self.bits_trace.append(bits)
        if self.cfg.i10 and self.cache is not None:
            self.skipped += 1
            if self.counter > self.cfg.K_g:
                self.bias_gated += 1
            return self.cache
        self.reads += 1
        h = m.h.copy() if m.cim is None else m.cim.field(m.x)
        self.cache = h
        return h

    def after_step(self, m) -> None:
        improved = m.best_f > self.last_best
        self.last_best = m.best_f
        self.counter = 0 if improved else self.counter + 1
