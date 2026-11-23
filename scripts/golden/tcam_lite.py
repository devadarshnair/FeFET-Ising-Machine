"""TCAM-lite visited-state arm (P2.05, FIXES R6 subset, optional, off by default; author decision D2).

Match/miss only (no count readout). A ring of M exact-match rows stores visited states. While the stall counter
(consecutive steps without a strict improvement of the best-so-far feasible objective, as in power.py) is a
positive multiple of K_w, the current state is written into the next row (ring order). After every step that
flipped a lane the new state is searched; a hit (exact match with a stored row) locks out the lane that just
flipped (it may not be accepted) for L_lock steps. Visited-state check as a negative control (hw_prior_art 1.5).
Off: the machine is bit-exact with P2.04.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TcamLiteCfg:
    on: bool = False
    M: int = 16              # stored rows
    K_w: int = 16            # write period (steps) while stalled
    L_lock: int = 8          # lockout length in steps

    def __post_init__(self):
        assert self.M >= 1 and self.K_w >= 1 and self.L_lock >= 1


class TcamLite:
    def __init__(self, cfg: TcamLiteCfg, machine):
        self.cfg = cfg
        n = machine.inst.n
        self.rows = np.zeros((cfg.M, n), dtype=np.int64)
        self.valid = np.zeros(cfg.M, dtype=bool)
        self.ptr = 0
        self.stall = 0
        self.last_best = machine.best_f
        self.lock_until = np.zeros(n, dtype=np.int64)     # lane locked while t <= lock_until
        self.writes = 0
        self.searches = 0
        self.hits = 0
        self.lockout_blocks = 0                            # steps in which a locked lane was ready to flip

    def locked(self, t: int) -> np.ndarray:
        return self.lock_until >= t

    def search(self, x: np.ndarray) -> bool:
        self.searches += 1
        return bool((self.valid & (self.rows == x).all(axis=1)).any())

    def write(self, x: np.ndarray) -> None:
        self.rows[self.ptr] = x
        self.valid[self.ptr] = True
        self.ptr = (self.ptr + 1) % self.cfg.M
        self.writes += 1

    def after_step(self, m, k: int) -> None:
        """k = lane flipped this step (-1 if none); called after the step's update and restart."""
        improved = m.best_f > self.last_best
        self.last_best = m.best_f
        self.stall = 0 if improved else self.stall + 1
        if k >= 0 and self.search(m.x):
            self.hits += 1
            self.lock_until[k] = m.t + self.cfg.L_lock
        if self.stall > 0 and self.stall % self.cfg.K_w == 0:
            self.write(m.x)
