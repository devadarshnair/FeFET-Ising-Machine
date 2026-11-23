"""Restart arms of the golden machine (P2.02), selected by RestartCfg.arm.

  none       no escape mechanism: the dynamic offset is held at 0 and the machine never restarts.
  da_offset  Aramon et al. 2019 Alg. 2 (docs/hw/lit/aramon2019_da.md): E_off += deoff on every step with no
             accepted flip, E_off := 0 on accept. This is the v0 machine as it was; no restarts.
  mesa       Yin et al. 2024 MESA (docs/hw/lit/yin2024_supp.md rows 17-18 and choices 1-2): a stall counter of
             consecutive steps without a strict improvement of the best-so-far feasible objective; at Count_max
             (default 2n) the machine reloads the best state, T := T0, E_off := 0, counter := 0.
  kc2        the reference software study Kc2 (ruling R1; sw_ref/histmem/ptemp/cpu.py:285-297 stall rule, :324 trigger, :344-346
             restart_from current + kick_lane, :110-125 kick, :394-401 epoch-best reset): stall counter of
             consecutive steps without improving the EPOCH best; at K the machine kicks L distinct spins of its
             CURRENT state (partial Fisher-Yates on a persistent permutation, draws from the engine's selection
             stream), the epoch best becomes the kicked state's value (best-so-far updated if better), counter
             := 0. T and E_off are NOT reset (the reference software study PT has no schedule reset) unless kc2_reset_sched=True.
             Default L = 10 = the reference software study PTEMP_DEFAULTS (sw_ref/histmem/ptemp/engine.py:26), capped at n_act - 1
             as the reference software study caps at n - 1. Deviation: the reference software study excludes spin 0 (Ising gauge); the QUBO golden has no
             gauge, so all enabled lanes are kick candidates.
n is the number of enabled lanes. The counter is updated after the step's flip and temperature update; a restart
acts on the state the next step sees. Arms other than none keep the instance's deoff.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ARMS = ("none", "da_offset", "mesa", "kc2")


@dataclass
class RestartCfg:
    arm: str = "da_offset"
    K: int | None = None          # stall window (Count_max for mesa); None = 2 * enabled lanes
    L: int = 10                   # kc2 kick size, the reference software study ptemp/engine.py:26
    kc2_reset_sched: bool = False # kc2 only: also reset T := T0, E_off := 0 on restart (non-reference variant)
    tabu: float = 0.0             # R6 (default off): kicked spins may not flip back for round(tabu * n_act) steps unless strictly improving
    target: bool = False          # R5 (default off): L // 2 of the kick spins are the lanes of smallest |gain| (zero-gain first)
    adaptive_m: int = 0           # R7 (default off): L = L0 * 2^(j mod m), j = consecutive kicks after which the epoch best did not improve
    conflict: bool = False        # barrier (default off): ALL kick spins are set lanes (x = 1) of smallest |gain| (1-2-spin conflict kicks)
    burst_K: int = 0              # barrier (default off): after burst_K stall steps, a bounded burst of burst_len steps accepts gain >= -1 ...
    burst_len: int = 0
    burst_up: int = 0             # ... at most burst_up uphill (-1) moves per burst; the stall counter keeps running (the kick still fires at K)

    def __post_init__(self):
        assert self.arm in ARMS, self.arm


class RestartUnit:
    def __init__(self, cfg: RestartCfg, machine):
        self.cfg = cfg
        n_act = machine.inst.n if machine.lane_en is None else int(machine.lane_en.sum())
        self.K = 2 * n_act if cfg.K is None else cfg.K
        assert self.K >= 1
        self.stall = 0
        self.epoch_best = machine.f      # start state x = 0 is feasible, f = 0
        self.last_best = machine.best_f
        self.events: list[int] = []
        self.event_cycles: list[int] = []     # cycles the RTL spends in S_RST for each event (restart_cycles())
        self.last_cycles = 0
        lanes = np.arange(machine.inst.n) if machine.lane_en is None else np.flatnonzero(machine.lane_en)
        self.perm = lanes.astype(np.int64)
        self.L = min(cfg.L, max(len(lanes) - 1, 0))
        self.tabu_steps = int(round(cfg.tabu * len(lanes)))
        self.tabu_until = np.zeros(machine.inst.n, np.int64) if self.tabu_steps > 0 else None
        self.lanes_act = lanes.astype(np.int64)
        self.L0 = self.L
        self.j_fail = 0
        self.prev_epoch_best = None
        self.burst_left = self.burst_up_left = 0
        self.bursts = 0

    def _kick(self, m) -> None:
        """the reference software study kick_lane: flip L distinct lanes chosen by partial Fisher-Yates on the persistent perm."""
        x = m.x.copy()
        size = len(self.perm)
        if self.cfg.adaptive_m:              # R7: escalate the kick while kicks keep failing to improve the epoch best
            eb = self.epoch_best
            self.j_fail = self.j_fail + 1 if (self.prev_epoch_best is not None and eb <= self.prev_epoch_best) else 0
            self.prev_epoch_best = eb if self.prev_epoch_best is None else max(self.prev_epoch_best, eb)
            self.L = min(self.L0 << (self.j_fail % self.cfg.adaptive_m), max(len(self.lanes_act) - 1, 0))
            self.last_cycles = self.restart_cycles(m)
        if self.cfg.conflict:                # barrier: smallest-|gain| SET lanes (their removal is the cheapest uphill move)
            ones = self.perm[x[self.perm] == 1]
            pick = ones[np.argsort(np.abs(m.h[ones]), kind="stable")[:self.L]] if ones.size else self.perm[:0]
            x[pick] ^= 1
            if self.tabu_until is not None:
                self.tabu_until[pick] = m.t + self.tabu_steps
            m.load_state(x)
            if m.is_feasible() and m.f > m.best_f:
                m.best_f, m.best_x, m.best_step = m.f, m.x.copy(), m.t
            return
        n_rand = self.L - (self.L // 2 if self.cfg.target else 0)
        for a in range(n_rand):
            j = a + ((m.sel.next() * (size - a)) >> 32)
            self.perm[a], self.perm[j] = self.perm[j], self.perm[a]
            x[self.perm[a]] ^= 1
        kicked = list(self.perm[:n_rand])
        if self.cfg.target:              # R5: instance-blind target = smallest |gain| lanes (exact field), ties in perm order
            rest = self.perm[n_rand:]
            order = np.argsort(np.abs(m.h[rest]), kind="stable")
            tgt = rest[order[:self.L - n_rand]]
            x[tgt] ^= 1
            kicked += list(tgt)
        if self.tabu_until is not None:
            self.tabu_until[np.asarray(kicked, np.int64)] = m.t + self.tabu_steps
        m.load_state(x)
        if m.is_feasible() and m.f > m.best_f:
            m.best_f, m.best_x, m.best_step = m.f, m.x.copy(), m.t

    @property
    def offset_enabled(self) -> bool:
        return self.cfg.arm != "none"

    def after_step(self, m) -> bool:
        arm = self.cfg.arm
        if arm in ("none", "da_offset"):
            return False
        if arm == "mesa":
            improved = m.best_f > self.last_best
            self.last_best = m.best_f
        else:
            improved = m.is_feasible() and m.f > self.epoch_best
            if improved:
                self.epoch_best = m.f
        self.stall = 0 if improved else self.stall + 1
        self._maybe_burst()
        if self.stall < self.K:
            return False
        self.last_cycles = self.restart_cycles(m)
        if arm == "mesa":
            m.load_state(m.best_x)
        else:
            self._kick(m)
            self.epoch_best = m.f if m.is_feasible() else np.iinfo(np.int64).min
        if arm == "mesa" or self.cfg.kc2_reset_sched:
            m.temp = m.inst.t0
            m.eoff = 0
        self.stall = 0
        self.events.append(m.t)
        self.event_cycles.append(self.last_cycles)
        return True

    def _maybe_burst(self) -> None:
        if self.cfg.burst_K and self.stall == self.cfg.burst_K:
            self.burst_left, self.burst_up_left = self.cfg.burst_len, self.cfg.burst_up
            self.bursts += 1

    def tolerance(self) -> int:
        """Barrier burst: 1 while a burst has uphill budget left, else 0 (plain I11)."""
        return 1 if self.burst_left > 0 and self.burst_up_left > 0 else 0

    def burst_step(self, gain_taken: int | None) -> None:
        if self.burst_left > 0:
            self.burst_left -= 1
            if gain_taken is not None and gain_taken < 0:
                self.burst_up_left -= 1

    def tabu_mask(self, t: int):
        """Lanes free to flip at step t (None = tabu off)."""
        return None if self.tabu_until is None else self.tabu_until < t

    def restart_cycles(self, m) -> int:
        """Cycles the pipelined RTL restart unit spends in S_RST for the restart that starts now (rtl/src/restart_unit.v, exported as rs_cycles):
        kc2: 6 per kick (R_DRAW R_ADD R_SWP1 R_SWAP R_RD R_FL) + R_FIN; mesa: 4 per differing spin (R_ENC R_CHK R_RD R_FL) + R_ENC R_CHK R_FIN."""
        if self.cfg.arm == "mesa":
            return 4 * int((m.x != m.best_x).sum()) + 3
        sel = 2 * self.L if self.cfg.conflict else (2 * (self.L // 2) if self.cfg.target else 0)
        return 6 * self.L + 1 + sel   # R5: one min-|gain| select pass (2 cycles) per targeted spin
