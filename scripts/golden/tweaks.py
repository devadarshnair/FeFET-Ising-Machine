"""Counter-free tweaks I11, I3 and I5 of the golden machine (H2 rungs 4c, 4d, 4e). All default off; off = bit-exact.

I11 greedy + Kc2 kick: acceptance is geff + E_off >= 0 with no LUT read and no lane RNG draw (theta = 0); the DA offset
    is not used (deoff forced 0) and the temperature/E_off registers are not written. Escape is the Kc2 stall kick only
    (restart arm must be "kc2"); the kick and the count-tree selection still draw from the shared selection stream.
I3  ramped penalty gain (knapsack, rules "hw" and "penalty"): the penalty weight lam is a register updated each step,
    lam_t = lam_lo + (lam - lam_lo) * min(t, ramp_steps) // ramp_steps (soft to hard; integer). Fixed penalty = off,
    HyCiM filter = rule "filter" (existing). One ramp update per step while t <= ramp_steps.
I5  Vth-spread acceptance noise: the per-lane noise sample comes from a physical source (FeFET Vth spread) instead of a
    digital RNG + LUT. The golden model keeps the LUT's distribution (simulation entropy still comes from the lane
    streams) and models only the two correlation knobs the kill criterion names: `hold` (a sample is held for `hold`
    steps: autocorrelation) and `group` (lanes in a group share one sample: lane correlation). hold = group = 1 gives
    the same trace as I5 off; only the accounting changes (no digital RNG draws, no LUT reads, one device noise sample
    per lane group per refresh). The device noise statistics are NOT characterised (cost rows are placeholders).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TweakCfg:
    i11: bool = False
    i3: bool = False
    lam_lo: int = 0
    ramp_steps: int | None = None   # None = the instance's step budget
    i5: bool = False
    hold: int = 1
    group: int = 1
    i11_temp: float = 0.0           # R10 control / R12(b) (default off): I11 accepts with Metropolis noise at fixed T (field units); lane RNG + LUT active
    i11_tol: int = 0                # R10 (default off): I11 accepts gain >= -i11_tol (zero-gain tolerance, field units)
    hyb_f: float = 0.0              # R12(a) (default off): anneal (lane RNG, T schedule) for the first hyb_f of the budget, then I11
    lahc_len: int = 0               # barrier (default off): late-acceptance greedy, accept gain >= min(0, f(t - lahc_len) - f); no temperature
    cc: str = ""                    # configuration checking (default off): "burst" = only while a stall burst runs, "always"; a flipped spin may
                                    # not flip back until one of its neighbours (nonzero P) flips, unless the flip strictly improves
    bo_K: int = 0                   # breakout weights (default off): every bo_K stall steps, +1 to a 4-bit bias of every conflicted spin
    bo_T: int = 0                   # ... and every bo_T steps all biases decay by 1 (periodic smoothing); bias added to the gain of flipping OUT
    esc_step: int = 0               # RNG-free escalating offset (default off): +esc_step per no-move step, reset on a move, capped at esc_max
    esc_max: int = 0
    colour_par: bool = False        # colour-parallel exact greedy commits (default off; separate, later-tested hook)

    def __post_init__(self):
        assert not (self.i11 and self.i5), "I11 removes the noise path that I5 replaces"
        assert self.hold >= 1 and self.group >= 1 and self.lam_lo >= 0


class TweakUnit:
    def __init__(self, cfg: TweakCfg, machine):
        self.cfg = cfg
        inst = machine.inst
        if cfg.i11:
            assert machine.restart.cfg.arm == "kc2", "I11 needs the Kc2 kick as its only escape"
        if cfg.i3:
            assert inst.mode == "knap" and inst.rule in ("hw", "penalty"), "I3 needs a penalised knapsack rule"
            assert cfg.lam_lo <= inst.lam
        self.ramp = inst.steps if cfg.ramp_steps is None else cfg.ramp_steps
        assert self.ramp >= 1
        self.ramp_updates = 0
        self.samples = 0
        self.m = machine
        self.switch = int(cfg.hyb_f * inst.steps)
        self.hist = None if cfg.lahc_len <= 0 else [machine.f] * cfg.lahc_len
        n = inst.n
        self.nbr = None
        if cfg.cc or cfg.bo_K or cfg.colour_par:
            P = np.asarray(inst.P)
            self.nbr = [np.flatnonzero(P[:, j]) for j in range(n)]
        self.cc_ok = np.ones(n, bool) if cfg.cc else None
        self.bo = np.zeros(n, np.int64) if cfg.bo_K else None
        self.bo_updates = 0
        self.classes = None
        if cfg.colour_par:                                  # host-side greedy colouring of the interaction graph (non-adjacent classes)
            col = -np.ones(n, np.int64)
            for i in np.argsort([-len(v) for v in self.nbr], kind="stable"):
                used = set(col[self.nbr[i]].tolist())
                c = 0
                while c in used:
                    c += 1
                col[i] = c
            self.classes = [col == c for c in range(int(col.max()) + 1)]
        self.par_commits = 0
        self._u = None
        self._age = 0
        self._n = inst.n

    # ---- escape layer (digital, after the field, before the select tree; no RNG, no temperature)
    def cc_mask(self, burst_active: bool):
        if self.cc_ok is None or (self.cfg.cc == "burst" and not burst_active):
            return None
        return self.cc_ok

    def conflicted(self, m) -> np.ndarray:
        """Set spins in a violated pairwise term (x_i = x_j = 1, P_ij < 0): instance-blind, colouring and Max-Cut alike."""
        x = m.x.astype(np.int64)
        P = np.asarray(m.P)
        return (x == 1) & (((P < 0) * x[None, :]).sum(1) > 0)

    def bias(self, m) -> np.ndarray | None:
        """Breakout bias on the gain of flipping a conflicted spin OUT (0 elsewhere)."""
        if self.bo is None:
            return None
        return np.where(m.x == 1, self.bo, 0)

    def after_step(self, m, flipped: list[int]) -> None:
        if self.cc_ok is not None:
            for k in flipped:
                self.cc_ok[self.nbr[k]] = True
                self.cc_ok[k] = False
        if self.bo is not None:
            st = getattr(m.restart, "stall", 0)
            if st and st % self.cfg.bo_K == 0:
                self.bo = np.minimum(self.bo + self.conflicted(m), 15)
                self.bo_updates += 1
            if self.cfg.bo_T and m.t % self.cfg.bo_T == 0:
                self.bo = np.maximum(self.bo - 1, 0)

    def lahc_threshold(self, t: int, f: int) -> int:
        """Late acceptance: the move is accepted if it ends at or above the objective of lahc_len steps ago (or does not worsen)."""
        return min(0, self.hist[t % len(self.hist)] - f)

    def lahc_record(self, t: int, f: int) -> None:
        self.hist[t % len(self.hist)] = f

    @property
    def greedy(self) -> bool:
        return self.cfg.i11 and self.m.t > self.switch

    @property
    def lane_noise(self) -> bool:
        """Lane RNG + LUT draws this step (False only for plain I11 and for I5)."""
        if self.cfg.i5:
            return False
        return not self.greedy or self.cfg.i11_temp > 0

    def lam_at(self, t: int, lam: int) -> int | None:
        """Penalty weight of step t (None when I3 is off, so the caller keeps inst.lam)."""
        if not self.cfg.i3:
            return None
        if t <= self.ramp:
            self.ramp_updates += 1
        lo = self.cfg.lam_lo
        return lo + ((lam - lo) * min(t, self.ramp)) // self.ramp

    def draw(self, lanes) -> np.ndarray:
        """Per-lane noise words for this step. I5 off: one fresh draw per lane (the plain machine)."""
        c = self.cfg
        if not c.i5:
            return lanes.next()
        if self._u is None or self._age >= c.hold:
            u = lanes.next()
            if c.group > 1:
                u = u[(np.arange(self._n) // c.group) * c.group]
            self._u, self._age = u, 0
            self.samples += -(-self._n // c.group)
        self._age += 1
        return self._u


def cfg_words(cfg: TweakCfg, inst) -> list[tuple[int, int]]:
    """Region-0 host writes (offset, data) of the RTL tweak registers 25-31 (docs/rtl/SPEC_v0.md 6.1).

    The I3 ramp is division-free in hardware: the host writes ramp_steps, dq = (lam - lam_lo) // ramp and
    dr = (lam - lam_lo) % ramp. The RTL group size is a power of two (2^glog)."""
    ramp = inst.steps if cfg.ramp_steps is None else cfg.ramp_steps
    dq, dr = divmod(inst.lam - cfg.lam_lo, ramp) if cfg.i3 else (0, 0)
    glog = cfg.group.bit_length() - 1
    assert cfg.group == 1 << glog, "RTL I5 group size must be a power of two"
    assert dq < 1 << 16 and cfg.hold < 1 << 16
    return [(25, int(cfg.i11) | int(cfg.i3) << 1 | int(cfg.i5) << 2), (26, cfg.lam_lo), (27, ramp), (28, dq), (29, dr),
            (30, cfg.hold), (31, glog)]
