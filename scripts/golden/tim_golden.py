"""Bit-exact integer golden model of the TIM v0 machine (docs/rtl/SPEC_v0.md).

Everything here is integer arithmetic and follows the spec section by section. The RTL in rtl/src must give the
same per-step trace bit for bit. Rules:
  "hw"       the machine as built: QUBO mode, or knapsack mode with the TCAM thermometer pricer (spec 5.1).
  "penalty"  exact digital hinge (control C3). Golden model only, used by the D5c ranking check.
  "filter"   exact feasibility filter (HyCiM role). Golden model only, used by the D5c ranking check.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from counters import CycleCfg, OpCounters
from cim_field import CimCfg, CimField
from power import PowerCfg, PowerUnit
from restart import ARMS, RestartCfg, RestartUnit
from tcam_lite import TcamLite, TcamLiteCfg
from tweaks import TweakCfg, TweakUnit, cfg_words

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF
GOLDEN_GAMMA = 0x9E3779B97F4A7C15
TEMP_FRAC = 16          # T is UQ16.16
LUT_FRAC = 8            # L[a] is UQ4.8 (nats)
LUT_BITS = 12
EOFF_MAX = (1 << 24) - 1
FIELD_BITS = 18
OBJ_BITS = 32
SEGW = 64
P_BITS = 10             # coupling width (P3.06; was 8)
D_BITS = 12             # bias width (P3.06; was 8)
P_MIN, P_MAX = -(1 << (P_BITS - 1)), (1 << (P_BITS - 1)) - 1
D_MIN, D_MAX = -(1 << (D_BITS - 1)), (1 << (D_BITS - 1)) - 1
CAP_UNUSED = 65535


# ------------------------------------------------------------------------------------------------ random numbers
def splitmix64_stream(seed: int, count: int) -> list[int]:
    """splitmix64 outputs z_0 .. z_{count-1} from state x = seed (spec 5.6)."""
    x = seed & MASK64
    out = []
    for _ in range(count):
        x = (x + GOLDEN_GAMMA) & MASK64
        z = x
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        out.append(z ^ (z >> 31))
    return out


def _rotl32(v: int, k: int) -> int:
    return ((v << k) | (v >> (32 - k))) & MASK32


class Xoshiro128ss:
    """Scalar xoshiro128** 1.1, written straight from the reference C code."""

    def __init__(self, s0: int, s1: int, s2: int, s3: int):
        self.s = [s0 & MASK32, s1 & MASK32, s2 & MASK32, s3 & MASK32]

    def output(self) -> int:
        return (_rotl32((self.s[1] * 5) & MASK32, 7) * 9) & MASK32

    def advance(self) -> None:
        s0, s1, s2, s3 = self.s
        t = (s1 << 9) & MASK32
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl32(s3, 11)
        self.s = [s0, s1, s2, s3]

    def next(self) -> int:
        v = self.output()
        self.advance()
        return v


def seed_states(seed: int, n_gen: int) -> list[tuple[int, int, int, int]]:
    """States of generators 0 .. n_gen-1 in the shift-chain order of spec 5.6."""
    z = splitmix64_stream(seed, 2 * n_gen)
    states = []
    for g in range(n_gen):
        a, b = z[2 * g], z[2 * g + 1]
        st = (a & MASK32, a >> 32, b & MASK32, b >> 32)
        assert any(st), "all-zero xoshiro state"
        states.append(st)
    return states


class LaneRngs:
    """N xoshiro128** generators stepped together (numpy, 32-bit words held in uint64)."""

    def __init__(self, states: list[tuple[int, int, int, int]]):
        arr = np.array(states, dtype=np.uint64)
        self.s0, self.s1, self.s2, self.s3 = (arr[:, i].copy() for i in range(4))

    @staticmethod
    def _rotl(v, k):
        return ((v << np.uint64(k)) | (v >> np.uint64(32 - k))) & np.uint64(MASK32)

    def next(self) -> np.ndarray:
        m = np.uint64(MASK32)
        out = (self._rotl((self.s1 * np.uint64(5)) & m, 7) * np.uint64(9)) & m
        t = (self.s1 << np.uint64(9)) & m
        self.s2 ^= self.s0
        self.s3 ^= self.s1
        self.s1 ^= self.s2
        self.s0 ^= self.s3
        self.s2 ^= t
        self.s3 = self._rotl(self.s3, 11)
        return out


def make_lut(lab: int) -> list[int]:
    """L[a] = min(4095, round(256 * -ln((a + 0.5) / 2^lab))) (spec 5.2)."""
    size = 1 << lab
    return [min((1 << LUT_BITS) - 1, int(round((1 << LUT_FRAC) * -math.log((a + 0.5) / size)))) for a in range(size)]


def select_prob(c: int, r: int) -> float:
    """Exact probability that the multiply-shift draw (r16 * c) >> 16 equals r (spec 5.3)."""
    lo = -(-(r << 16) // c)
    hi = -(-((r + 1) << 16) // c)
    return (hi - lo) / 65536.0


# ------------------------------------------------------------------------------------------------ instance
@dataclass
class Instance:
    n: int
    mode: str                      # "qubo" | "knap"
    geom: int
    t0: int
    alpha: int
    deoff: int
    lam: int
    gsh: int
    wmax: int
    seed: int
    steps: int
    lab: int
    d: np.ndarray                  # (n,) int64
    P: np.ndarray                  # (n, n) int64, symmetric, zero diagonal
    W: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.int64))   # (m, n)
    C: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))        # (m,)
    q: int = 1                     # thermometer levels (knap); must equal the RTL parameter NLEV
    rule: str = "hw"
    lane_en: np.ndarray | None = None  # (n,) bool; None = all lanes on. Off lanes are padding (spec G6 fix)

    @property
    def m(self) -> int:
        return int(self.W.shape[0]) if self.mode == "knap" else 0

    def check_widths(self, ncon: int | None = None) -> None:
        """Assert that every value fits the RTL widths of spec 3."""
        n = self.n
        assert n >= 4 and n & (n - 1) == 0, "n must be a power of two"
        assert self.d.shape == (n,) and self.P.shape == (n, n)
        assert np.array_equal(self.P, self.P.T) and not np.any(np.diag(self.P))
        if self.lane_en is not None:
            off = ~self.lane_en.astype(bool)
            assert self.lane_en.shape == (n,) and self.lane_en.any()
            assert not self.d[off].any() and not self.P[off].any() and not self.P[:, off].any(), "padding not zero"
            if self.mode == "knap":
                assert not self.W[:, off].any()
        assert self.d.min() >= D_MIN and self.d.max() <= D_MAX, "bias out of the 12-bit range"
        assert self.P.min() >= P_MIN and self.P.max() <= P_MAX, "coupling out of the 10-bit range"
        assert 0 <= self.t0 < 1 << 32 and 0 <= self.alpha < 1 << 32
        assert 0 <= self.deoff < 1 << 16 and 0 <= self.lam < 1 << 16 and 0 <= self.gsh <= 4
        assert 0 <= self.seed < 1 << 64 and 0 <= self.steps < 1 << 32
        if self.mode == "knap":
            assert self.q >= 2 and self.q & (self.q - 1) == 0 and (1 << self.gsh) == self.q
            assert 1 <= self.wmax <= 63 and self.W.min() >= 0 and self.W.max() <= self.wmax
            assert self.C.min() >= 0 and self.C.max() <= CAP_UNUSED
            if ncon is not None:
                assert self.m <= ncon


# ------------------------------------------------------------------------------------------------ pricer
def thermo_rows(inst: Instance) -> np.ndarray:
    """(n, m, q) bool: stored cell (j, k) of row i is 1 iff Wq_ij >= k, Wq = floor(q * w / wmax) (spec 5.1)."""
    wq = (inst.q * inst.W.T) // inst.wmax                       # (n, m)
    levels = np.arange(1, inst.q + 1)
    return wq[:, :, None] >= levels[None, None, :]


def query_masks(inst: Instance, load: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(m, q) bool ADD and REM masks from the slacks (spec 5.1 step 2)."""
    slack = inst.C - load
    kw = np.arange(1, inst.q + 1) * inst.wmax
    qs = inst.q * slack
    add = qs[:, None] < kw[None, :]
    rem = kw[None, :] <= -qs[:, None]
    return add, rem


def tcam_counts(rows: np.ndarray, mask: np.ndarray, row_en: np.ndarray) -> np.ndarray:
    """Exact TCAM count per row: popcount(stored AND mask) over all cells, 0 for disabled rows (key = 0)."""
    cnt = (rows & mask[None, :, :]).sum(axis=(1, 2))
    return np.where(row_en, cnt, 0).astype(np.int64)


# ------------------------------------------------------------------------------------------------ machine
def effective_gain(inst: Instance, rows, x: np.ndarray, h: np.ndarray, load: np.ndarray, lam: int | None = None):
    """Spec 5.1-5.2 up to geff: returns (gain, geff, eligible or None, cnt_add, cnt_rem) for every lane.
    lam overrides inst.lam (I3 ramp); None keeps the registered value."""
    n = inst.n
    lam = inst.lam if lam is None else lam
    gain = np.where(x == 1, -h, h)
    scaled = gain << inst.gsh
    zeros = np.zeros(n, dtype=np.int64)
    if inst.mode != "knap":
        return gain, scaled, None, zeros, zeros
    if inst.rule == "hw":
        add_mask, rem_mask = query_masks(inst, load)
        cnt_add = tcam_counts(rows, add_mask, x == 0)
        cnt_rem = tcam_counts(rows, rem_mask, x == 1)
        return gain, scaled - lam * cnt_add + lam * cnt_rem, None, cnt_add, cnt_rem
    sign = np.where(x == 0, 1, -1)
    new_load = load[None, :] + sign[:, None] * inst.W.T              # (n, m)
    if inst.rule == "penalty":
        base = int(np.maximum(load - inst.C, 0).sum())
        tot = np.maximum(new_load - inst.C[None, :], 0).sum(axis=1)
        return gain, scaled - lam * (tot - base), None, zeros, zeros
    if inst.rule == "filter":
        fits = (inst.W.T <= (inst.C - load)[None, :]).all(axis=1)
        return gain, scaled, (x == 1) | fits, zeros, zeros
    raise ValueError(inst.rule)


def checksum(values: np.ndarray) -> int:
    """sum_i (i+1) * v_i mod 2^32, v as two's complement (spec 9.3)."""
    idx = np.arange(1, len(values) + 1, dtype=np.int64)
    return int(np.sum(idx * values.astype(np.int64))) % (1 << 32)


@dataclass
class RunResult:
    trace: list[str]
    best_f: int
    best_step: int
    x: np.ndarray
    best_x: np.ndarray
    h: np.ndarray
    load: np.ndarray
    f: int
    flips: int


def hexbits(bits: np.ndarray) -> str:
    v = 0
    for i, b in enumerate(bits):
        if b:
            v |= 1 << i
    return format(v, f"0{len(bits) // 4}x")


class Machine:
    """The machine state of spec 5. One call of step() is one machine step."""

    def __init__(self, inst: Instance, restart: RestartCfg | None = None, cim: CimCfg | None = None,
                 power: PowerCfg | None = None, tcam: TcamLiteCfg | None = None, counters: CycleCfg | None = None,
                 tweaks: TweakCfg | None = None):
        self.inst = inst
        n = inst.n
        states = seed_states(inst.seed, n + 1)
        self.lanes = LaneRngs(states[:n])
        self.sel = Xoshiro128ss(*states[n])
        self.lut = np.array(make_lut(inst.lab), dtype=np.int64)
        self.x = np.zeros(n, dtype=np.int64)
        self.h = inst.d.astype(np.int64).copy()
        self.P = inst.P.astype(np.int64)
        self.knap = inst.mode == "knap"
        self.load = np.zeros(inst.m, dtype=np.int64)
        self.rows = thermo_rows(inst) if self.knap and inst.rule == "hw" else None
        self.f = 0
        self.best_f = 0
        self.best_step = 0
        self.best_x = self.x.copy()
        self.eoff = 0
        self.temp = inst.t0
        self.t = 0
        self.flips = 0
        self.cnt_add = np.zeros(n, dtype=np.int64)
        self.cnt_rem = np.zeros(n, dtype=np.int64)
        self.lane_en = None if inst.lane_en is None else inst.lane_en.astype(bool).copy()
        self.restart = RestartUnit(restart or RestartCfg(), self)
        self.tw = None if tweaks is None else TweakUnit(tweaks, self)
        self.deoff = inst.deoff if self.restart.offset_enabled and not (self.tw is not None and self.tw.cfg.i11) else 0
        if self.tw is not None and self.tw.cfg.i11 and self.tw.cfg.esc_step:   # RNG-free escalating offset on the exact greedy
            self.deoff = self.tw.cfg.esc_step
        self.cim = None if cim is None else CimField(cim, inst.P, inst.d)
        self.power = None if power is None else PowerUnit(power, self)
        self.counters = None if counters is None else OpCounters(counters)
        self.tcam = TcamLite(tcam, self) if tcam is not None and tcam.on else None

    @property
    def greedy(self) -> bool:
        return self.tw is not None and self.tw.greedy

    def step(self) -> str:
        inst = self.inst
        self.t += 1
        if self.power is not None:
            reads_before = self.power.reads
            h_used = self.power.field(self)
            performed = self.power.reads > reads_before
        else:
            performed = True
            h_used = self.h if self.cim is None else self.cim.field(self.x)
        bits = None if self.cim is None else self.cim.adc_bits
        best_before = self.best_f
        _, geff, elig, self.cnt_add, self.cnt_rem = effective_gain(
            inst, self.rows, self.x, h_used, self.load, None if self.tw is None else self.tw.lam_at(self.t, inst.lam))
        gain = np.where(self.x == 1, -self.h, self.h)        # exact gain: f stays the true objective
        if self.greedy and self.tw.cfg.i11_temp > 0:          # R10 control / R12(b): greedy rule plus Metropolis noise at fixed T
            u = self.lanes.next()
            addr = (u >> np.uint64(32 - inst.lab)).astype(np.int64)
            t_reg = int(round(self.tw.cfg.i11_temp * (1 << TEMP_FRAC)))
            theta = (t_reg * self.lut[addr]) >> (TEMP_FRAC + LUT_FRAC)
            acc = geff + self.tw.cfg.i11_tol + theta >= 0
        elif self.greedy:
            thr = self.tw.lahc_threshold(self.t, self.f) if self.tw.hist is not None else 0
            bo = self.tw.bias(self)
            if bo is not None:
                geff = geff + bo
            tol = getattr(self.restart, "tolerance", lambda: 0)()
            acc = geff + self.eoff + self.tw.cfg.i11_tol + tol >= thr
            ccm = self.tw.cc_mask(tol > 0)
            if ccm is not None:
                acc = acc & (ccm | (geff > 0))
        else:
            u = self.lanes.next() if self.tw is None else self.tw.draw(self.lanes)
            addr = (u >> np.uint64(32 - inst.lab)).astype(np.int64)
            theta = (self.temp * self.lut[addr]) >> (TEMP_FRAC + LUT_FRAC)
            acc = geff + self.eoff + theta >= 0
        if elig is not None:
            acc = acc & elig
        if self.lane_en is not None:
            acc = acc & self.lane_en
        free = self.restart.tabu_mask(self.t)
        if free is not None:                                 # R6: kicked spins stay put unless the flip strictly improves
            acc = acc & (free | (geff > 0))
        if self.tcam is not None:
            locked = self.tcam.locked(self.t)
            self.tcam.lockout_blocks += int((acc & locked).any())
            acc = acc & ~locked
        r16 = self.sel.next() >> 16
        c = int(acc.sum())
        k = -1
        flipped: list[int] = []
        par = None
        if self.greedy and self.tw.classes is not None:     # colour-parallel: all strictly improving spins of one class (exact: non-adjacent)
            cls = self.tw.classes[(self.t - 1) % len(self.tw.classes)]
            par = np.flatnonzero(acc & cls & (gain > 0))
        if par is not None and par.size > 1:
            for kk in par:
                self._apply_flip(int(kk), int(gain[kk]))
            flipped = [int(v) for v in par]
            k = flipped[0]
            self.tw.par_commits += 1
        elif c > 0:
            r = (r16 * c) >> 16
            k = int(np.flatnonzero(acc)[r])
            self._apply_flip(k, int(gain[k]))
            flipped = [k]
        else:
            self.eoff = min(self.eoff + self.deoff, EOFF_MAX)
            if self.tw is not None and self.tw.cfg.esc_max:
                self.eoff = min(self.eoff, self.tw.cfg.esc_max)
        if self.tw is not None and (self.tw.cc_ok is not None or self.tw.bo is not None):
            self.tw.after_step(self, flipped)
        if self.restart.burst_left if hasattr(self.restart, "burst_left") else False:
            self.restart.burst_step(int(gain[k]) if k >= 0 else None)
        if self.tw is not None and self.tw.hist is not None and self.greedy:
            self.tw.lahc_record(self.t, self.f)
        if inst.geom and not self.greedy:                    # I11 writes no T register (spec RTL_TODO_I11_I3_I5)
            self.temp = (self.temp * inst.alpha) >> 32
        restarted = self.restart.after_step(self)
        if restarted and self.power is not None:
            self.power.invalidate()
        if self.power is not None:
            self.power.after_step(self)
        if self.tcam is not None:
            self.tcam.after_step(self, k)
        if self.counters is not None:
            self.counters.record(self, k=k, performed=performed, bits=bits, restarted=restarted,
                                 improved=self.best_f > best_before)
        assert np.abs(self.h).max() < 1 << (FIELD_BITS - 1), "field overflow"
        assert abs(self.f) < 1 << (OBJ_BITS - 1), "objective overflow"
        ccs = checksum(self.cnt_add + 256 * self.cnt_rem)
        lcs = checksum(self.load) if self.knap else 0
        return (f"{self.t} {k} {c} {checksum(acc.astype(np.int64))} {self.f} {checksum(self.h)} {self.eoff} "
                f"{self.temp} {lcs} {ccs}")

    def _apply_flip(self, k: int, gain_k: int) -> None:
        inst = self.inst
        delta = 1 if self.x[k] == 0 else -1
        self.f += gain_k
        self.x[k] ^= 1
        self.h += delta * self.P[:, k]
        if self.knap:
            self.load += delta * inst.W[:, k]
        self.eoff = 0
        self.flips += 1
        if self.power is not None:
            self.power.invalidate()
        feasible = (not self.knap) or bool((self.load <= inst.C).all())
        if feasible and self.f > self.best_f:
            self.best_f = self.f
            self.best_x = self.x.copy()
            self.best_step = self.t

    def is_feasible(self) -> bool:
        return (not self.knap) or bool((self.load <= self.inst.C).all())

    def load_state(self, x: np.ndarray) -> None:
        """Reload spin state x (MESA restart): x, h, load and f are recomputed exactly."""
        inst = self.inst
        self.x = x.astype(np.int64).copy()
        self.h = inst.d.astype(np.int64) + self.P @ self.x
        if self.knap:
            self.load = inst.W @ self.x
        self.f = objective(inst, self.x)

    def run(self, steps: int | None = None, keep_trace: bool = True) -> RunResult:
        steps = self.inst.steps if steps is None else steps
        trace = []
        for _ in range(steps):
            line = self.step()
            if keep_trace:
                trace.append(line)
        if keep_trace:
            trace.append(f"final {self.best_f} {self.best_step} {hexbits(self.x)} {hexbits(self.best_x)}")
        return RunResult(trace, self.best_f, self.best_step, self.x.copy(), self.best_x.copy(), self.h.copy(),
                         self.load.copy(), self.f, self.flips)


def pad_instance(inst: Instance, n_total: int) -> Instance:
    """Copy of inst with its n_act spins in lanes 0..n_act-1 of an n_total-lane machine; lanes n_act.. are off.

    inst.n may be any size here (e.g. 200); the padded copy has n = n_total (a power of two) and lane_en set."""
    n_act = inst.n
    assert n_total >= n_act
    d = np.zeros(n_total, dtype=np.int64)
    d[:n_act] = inst.d
    P = np.zeros((n_total, n_total), dtype=np.int64)
    P[:n_act, :n_act] = inst.P
    en = np.zeros(n_total, dtype=bool)
    en[:n_act] = True
    W = inst.W
    if inst.mode == "knap":
        W = np.zeros((inst.m, n_total), dtype=np.int64)
        W[:, :n_act] = inst.W
    return Instance(n=n_total, mode=inst.mode, geom=inst.geom, t0=inst.t0, alpha=inst.alpha, deoff=inst.deoff,
                    lam=inst.lam, gsh=inst.gsh, wmax=inst.wmax, seed=inst.seed, steps=inst.steps, lab=inst.lab,
                    d=d, P=P, W=W, C=inst.C.copy(), q=inst.q, rule=inst.rule, lane_en=en)


def objective(inst: Instance, x: np.ndarray) -> int:
    x = x.astype(np.int64)
    return int(inst.d @ x + (x @ inst.P @ x) // 2)


def feasible(inst: Instance, x: np.ndarray) -> bool:
    return inst.mode != "knap" or bool((inst.W @ x.astype(np.int64) <= inst.C).all())


# ------------------------------------------------------------------------------------------------ exact transition matrix
def lane_accept_prob(inst: Instance, x: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """P(acc_i = 1) for every lane at state x, E_off = 0, fixed T (exact over the 2^lab LUT addresses)."""
    x = x.astype(np.int64)
    knap = inst.mode == "knap"
    load = inst.W @ x if knap else np.zeros(0, dtype=np.int64)
    rows = thermo_rows(inst) if knap else None
    _, geff, elig, _, _ = effective_gain(inst, rows, x, inst.d + inst.P @ x, load)
    assert elig is None
    theta = (inst.t0 * lut) >> (TEMP_FRAC + LUT_FRAC)            # (2^lab,)
    return (geff[:, None] + theta[None, :] >= 0).mean(axis=1)


def transition_matrix(inst: Instance, pick: str = "uniform") -> np.ndarray:
    """Exact one-step matrix over the 2^n states at fixed T with dE = 0 (x alone is then Markov).

    pick = "uniform" is the machine's count-tree draw (spec 5.3). pick = "first" (lowest accepted lane, a
    priority encoder) is a deliberately wrong model, used to show that the statistical test has power."""
    n = inst.n
    assert n <= 10 and inst.geom == 0 and inst.deoff == 0
    lut = np.array(make_lut(inst.lab), dtype=np.int64)
    ns = 1 << n
    subsets = np.array([[(s >> i) & 1 for i in range(n)] for s in range(ns)], dtype=bool)
    members = [np.flatnonzero(subsets[s]) for s in range(ns)]
    mat = np.zeros((ns, ns))
    for xs in range(ns):
        x = subsets[xs].astype(np.int64)
        p = lane_accept_prob(inst, x, lut)
        prob = np.where(subsets, p[None, :], 1.0 - p[None, :]).prod(axis=1)
        mat[xs, xs] += prob[0]
        for s in range(1, ns):
            mem = members[s]
            c = len(mem)
            for rank, k in enumerate(mem):
                w = select_prob(c, rank) if pick == "uniform" else float(rank == 0)
                mat[xs, xs ^ (1 << int(k))] += prob[s] * w
    return mat


# ------------------------------------------------------------------------------------------------ file formats
def write_inst(inst: Instance, path) -> None:
    """Instance text format of spec 9.1."""
    lines = ["tim_inst v0", f"n {inst.n}", f"mode {inst.mode}", f"geom {inst.geom}", f"t0 {inst.t0}",
             f"alpha {inst.alpha}", f"deoff {inst.deoff}", f"lambda {inst.lam}", f"gsh {inst.gsh}",
             f"wmax {inst.wmax}", f"seed 0x{inst.seed:016x}", f"steps {inst.steps}", f"lut {inst.lab} {LUT_FRAC}",
             "bias " + " ".join(str(int(v)) for v in inst.d), "p"]
    lines += [" ".join(str(int(v)) for v in row) for row in inst.P]
    if inst.mode == "knap":
        lines += [f"m {inst.m}", f"q {inst.q}", "w"]
        lines += [" ".join(str(int(v)) for v in row) for row in inst.W]
        lines.append("c " + " ".join(str(int(v)) for v in inst.C))
    lines.append("end")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def read_inst(path) -> Instance:
    toks = []
    with open(path) as fh:
        for line in fh:
            toks += line.split("#", 1)[0].split()
    it = iter(toks)

    def expect(key):
        got = next(it)
        assert got == key, f"expected {key!r}, got {got!r}"

    def ints(count):
        return np.array([int(next(it), 0) for _ in range(count)], dtype=np.int64)

    expect("tim_inst")
    expect("v0")
    vals = {}
    for key in ("n", "mode", "geom", "t0", "alpha", "deoff", "lambda", "gsh", "wmax", "seed", "steps"):
        expect(key)
        vals[key] = next(it)
    expect("lut")
    lab, frac = int(next(it)), int(next(it))
    assert frac == LUT_FRAC
    n = int(vals["n"])
    expect("bias")
    d = ints(n)
    expect("p")
    P = ints(n * n).reshape(n, n)
    inst = Instance(n=n, mode=vals["mode"], geom=int(vals["geom"]), t0=int(vals["t0"]), alpha=int(vals["alpha"]),
                    deoff=int(vals["deoff"]), lam=int(vals["lambda"]), gsh=int(vals["gsh"]), wmax=int(vals["wmax"]),
                    seed=int(vals["seed"], 0), steps=int(vals["steps"]), lab=lab, d=d, P=P)
    if inst.mode == "knap":
        expect("m")
        m = int(next(it))
        expect("q")
        inst.q = int(next(it))
        expect("w")
        inst.W = ints(m * n).reshape(m, n)
        expect("c")
        inst.C = ints(m)
    expect("end")
    return inst


def cfg_lines(inst: Instance, ncon: int, rs: RestartCfg | None = None, cim: CimCfg | None = None,
              power: PowerCfg | None = None, sparse: bool = False, tweaks: TweakCfg | None = None) -> list[str]:
    """Host write script of spec 9.2 for an RTL built with N = inst.n, NCON = ncon, NLEV = inst.q."""
    n = inst.n
    inst.check_widths(ncon)
    out = []

    def w(region, offset, data):
        out.append(f"w {(region << 20) | offset:06x} {data & MASK32:x}")

    w(0, 0, (1 if inst.mode == "knap" else 0) | (inst.geom << 1))
    w(0, 1, inst.t0)
    w(0, 2, inst.alpha)
    w(0, 3, inst.deoff)
    w(0, 4, inst.lam)
    w(0, 5, inst.gsh)
    w(0, 6, inst.wmax)
    w(0, 7, inst.seed & MASK32)
    w(0, 8, inst.seed >> 32)
    w(0, 9, inst.steps)
    if rs is not None:
        n_act = n if inst.lane_en is None else int(np.asarray(inst.lane_en).sum())
        w(0, 10, 2 * n_act if rs.K is None else rs.K)
        w(0, 11, ARMS.index(rs.arm))
        w(0, 12, rs.L)
        w(0, 13, int(rs.kc2_reset_sched))
    if cim is not None:
        w(0, 14, cim.adc_bits)
        w(0, 15, cim.sg)
        w(0, 16, cim.seed & MASK32)
        if cim.fs:
            w(0, 32, cim.fs)            # I7v2 ADC full scale (RTL r_adcfs); omitted = 0 = N rows (v1)
    if power is not None:
        w(0, 17, int(power.i10) | (int(power.i7) << 1))
        w(0, 18, power.K_g)
        w(0, 19, power.K_p)
        w(0, 20, power.b_hi)
        w(0, 21, power.b_lo)
    if tweaks is not None:
        for off, data in cfg_words(tweaks, inst):
            w(0, off, data)
    for j in range(n):
        for k in range(n):
            if not sparse or inst.P[j, k]:
                w(1, j * n + k, int(inst.P[j, k]) & ((1 << P_BITS) - 1))
    for j in range(n):
        w(2, j, int(inst.d[j]) & ((1 << D_BITS) - 1))
    for a, v in enumerate(make_lut(inst.lab)):
        w(3, a, v)
    if inst.lane_en is not None:
        for j in range(n):
            w(6, j, int(bool(inst.lane_en[j])))
    if inst.mode == "knap":
        for j in range(ncon):
            for k in range(n):
                w(4, j * n + k, int(inst.W[j, k]) if j < inst.m else 0)
            w(5, j, int(inst.C[j]) if j < inst.m else CAP_UNUSED)
        out += tcam_row_lines(inst, ncon)
    return out


def tcam_row_lines(inst: Instance, ncon: int) -> list[str]:
    rows = thermo_rows(inst).reshape(inst.n, -1)                   # column c = j * q + (k - 1)
    ncols = ncon * inst.q
    nseg = -(-ncols // SEGW)
    full = np.zeros((inst.n, nseg * SEGW), dtype=bool)
    full[:, :rows.shape[1]] = rows
    care = (1 << SEGW) - 1
    out = []
    for i in range(inst.n):
        for s in range(nseg):
            bits = 0
            for c in range(SEGW):
                if full[i, s * SEGW + c]:
                    bits |= 1 << c
            out.append(f"t {i} {s} {bits:016x} {care:016x}")
    return out


def write_cfg(inst: Instance, path, ncon: int, rs: RestartCfg | None = None, cim: CimCfg | None = None,
              power: PowerCfg | None = None, sparse: bool = False, tweaks: TweakCfg | None = None) -> None:
    with open(path, "w") as fh:
        fh.write("\n".join(cfg_lines(inst, ncon, rs, cim, power, sparse, tweaks)) + "\n")


def write_trace(lines: list[str], path) -> None:
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
