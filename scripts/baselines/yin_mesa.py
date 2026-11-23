"""B1 = Yin et al. 2024 (Nat. Commun. 15:2419) FeFET CiM annealer with MESA, as a configuration of OUR golden machine.

Label: "literature-parameterised" (PLAN D5(3)): Yin publish no energy/time figures (docs/hw/lit/yin2024_supp.md
row 32), so every energy/time/area number comes from the SAME shared table (docs/hw/energy_table_v1_p309.csv via
scripts/golden/cost_model.py) and the same device/field model (scripts/golden/cim_field.py) as our design. Only the
architecture (32x32 tiles, digital tile sum, no I7/I10, no DA offset) and the schedule (MESA) differ.

Parameter sheet rows used ([FT] found in text, [U] labelled default; numbers = rows of yin2024_supp.md):
  tile 32 x 32 1FeFET1R cells                     [FT] 1-3   (1 MOhm series R, +-4 V / 1 us writes, 28 nm: rows 3, 4, 6;
                                                             priced through the shared table, not separately)
  coupling bits w_bits = 3 (Max-Cut)              [U]  16
  ADC bits = 8 (w_bits <= 3 -> 8 b)               [U]  14
  restart = MESA (golden restart.py arm "mesa")   [FT] 18
  Count_max = 2n stagnant steps                   [U]  17, R1 choice 1
  stall = no strict best-so-far improvement;
  on stall reload best, T := T0                   [U]  R1 choice 2 (golden mesa arm)
  RNG = off-array digital generator               [U]  24, R1 choice 3 (golden lane xoshiro streams; no device noise
                                                             is used as the random source)
  cooling = geometric                             [U]  19 (golden geometric schedule)
  T0 by the Aramon acceptance rule                [U]  20 (set by the caller per instance; P4.02)
  perturbation "a few bit flips" = 3              [U]  21: recorded only. The shared machine proposes single flips per
                                                             step for every architecture (fairness: schedule-level
                                                             differences only); P4.02 must state this deviation.
  dynamic offset: none (Yin have no DA offset)    instance deoff := 0
  I7 / I10: off (Yin have neither)                power = None

Tiling (n > 32): the n x n coupling matrix is cut into ceil(n/32) x ceil(n/32) blocks; each block occupies 2*w_bits
physical 32x32 tiles (one per bit plane and polarity, the differential mapping of cim_field.py). Every tile converts
its 32 columns per read with its own ADC (full scale 32 rows); the partial column results of the row tiles are
summed digitally ((row_tiles - 1) adds per logical column). n is the number of enabled spins.
"""
from __future__ import annotations

import dataclasses
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
sys.path.insert(0, str(GOLDEN))

from cim_field import CimCfg, CimField  # noqa: E402
from cost_model import CostModel  # noqa: E402
from counters import CycleCfg  # noqa: E402
from restart import RestartCfg  # noqa: E402
from tim_golden import Instance, Machine, RunResult  # noqa: E402

LABEL = "literature-parameterised"
TILE = 32


@dataclass(frozen=True)
class B1Cfg:
    tile: int = TILE
    w_bits: int = 3
    adc_bits: int = 8
    count_max: int | None = None     # None = 2n (R1 choice 1)
    sigma: float = 0.0               # read noise per tile column conversion, cell-current units (shared char value)
    seed: int = 0
    perturb_bits: int = 3            # recorded [U] row 21, not used (see module docstring)
    label: str = LABEL

    def restart(self) -> RestartCfg:
        return RestartCfg(arm="mesa", K=self.count_max)

    def cim(self) -> CimCfg:
        return CimCfg(adc_bits=self.adc_bits, w_bits=self.w_bits, sigma=self.sigma, seed=self.seed)


def n_active(inst: Instance) -> int:
    return inst.n if inst.lane_en is None else int(np.asarray(inst.lane_en).sum())


def tile_counts(n: int, cfg: B1Cfg = B1Cfg()) -> dict[str, int]:
    """Exact per-read tiling counts for n spins."""
    nb = math.ceil(n / cfg.tile)
    planes = 2 * cfg.w_bits
    tiles = nb * nb * planes
    cols = planes * nb * cfg.tile              # logical columns (lane x plane x polarity), padded lanes included
    return dict(blocks=nb, tiles=tiles, conversions=tiles * cfg.tile, cell_reads=tiles * cfg.tile * cfg.tile,
                tile_sum_adds=(nb - 1) * cols, shift_adds=2 * cfg.w_bits * n)


class TiledCimField:
    """Field of the tiled B1 array: per-tile column ADC (full scale = tile rows), digital sum of row tiles."""

    def __init__(self, cfg: B1Cfg, P: np.ndarray, d: np.ndarray, lane_en: np.ndarray | None = None):
        self.b1 = cfg
        n = P.shape[0]
        idx = np.arange(n) if lane_en is None else np.flatnonzero(lane_en)
        self.idx = idx
        self.cnt = tile_counts(len(idx), cfg)
        nb, t = self.cnt["blocks"], cfg.tile
        Pa = np.zeros((nb * t, nb * t), dtype=np.int64)
        Pa[:len(idx), :len(idx)] = P[np.ix_(idx, idx)]
        self.d = d.astype(np.int64)
        self.n = n
        self.cfg = CimCfg(adc_bits=cfg.adc_bits, w_bits=cfg.w_bits, sigma=cfg.sigma, seed=cfg.seed)
        # one CimField per row tile r: lanes x tile rows slice of P; its ADC full scale is the tile height t
        self.tiles = []
        for r in range(nb):
            tf = CimField(dataclasses.replace(self.cfg, seed=cfg.seed + r), Pa[:, r * t:(r + 1) * t],
                          np.zeros(nb * t, dtype=np.int64))
            tf.n = t
            tf.set_bits(cfg.adc_bits)
            self.tiles.append(tf)
        self.adc_bits = cfg.adc_bits
        self.conversions = 0

    def set_bits(self, bits: int) -> None:
        raise AssertionError("B1 has no I7 precision control")

    def field(self, x: np.ndarray) -> np.ndarray:
        nb, t = self.cnt["blocks"], self.b1.tile
        xa = np.zeros(nb * t, dtype=np.int64)
        xa[:len(self.idx)] = x[self.idx]
        acc = np.zeros(nb * t, dtype=np.int64)
        for r, tf in enumerate(self.tiles):
            acc += tf.field(xa[r * t:(r + 1) * t])
        self.conversions += self.cnt["conversions"]
        h = self.d.copy()
        h[self.idx] += acc[:len(self.idx)]
        return h


def b1_instance(inst: Instance) -> Instance:
    """B1 has no dynamic offset."""
    return dataclasses.replace(inst, deoff=0)


def b1_machine(inst: Instance, cfg: B1Cfg = B1Cfg(), counters: bool = True) -> Machine:
    inst = b1_instance(inst)
    m = Machine(inst, restart=cfg.restart(), cim=cfg.cim(), power=None, counters=CycleCfg() if counters else None)
    m.cim = TiledCimField(cfg, inst.P, inst.d, inst.lane_en)
    return m


def run_b1(inst: Instance, cfg: B1Cfg = B1Cfg(), steps: int | None = None) -> tuple[Machine, RunResult]:
    m = b1_machine(inst, cfg)
    return m, m.run(steps, keep_trace=False)


def b1_counts(m: Machine) -> dict[str, int]:
    """Golden op counters with the CiM read terms replaced by the exact tiled counts."""
    c = dict(m.counters.total)
    cnt, reads, bits = m.cim.cnt, c["array_reads"], m.cim.adc_bits
    n = m.inst.n
    untiled_shift = 2 * m.cim.cfg.w_bits * n
    c["array_cell_reads"] = reads * cnt["cell_reads"]
    c["adc_conversions"] = reads * cnt["conversions"]
    c["adc_conv_bits"] = reads * cnt["conversions"] * bits
    c["adds"] += reads * (cnt["tile_sum_adds"] + cnt["shift_adds"] - untiled_shift)
    c["tiles"] = cnt["tiles"]
    return c


def b1_native_counts(m: Machine) -> dict[str, int]:
    """Counts for Yin's native 3-bit cells (A1): one multilevel cell per coupling and polarity (2 columns per lane, no bit
    planes, no shift-add); same 32x32 tiling. The field values are identical (exact ADC), only the cost counters change."""
    c = b1_counts(m)
    cnt, reads, bits = m.cim.cnt, c["array_reads"], m.cim.adc_bits
    nb, t = cnt["blocks"], m.cim.b1.tile
    tiles = nb * nb * 2
    c["tiles"] = tiles
    c["array_cell_reads"] = reads * tiles * t * t
    c["adc_conversions"] = reads * tiles * t
    c["adc_conv_bits"] = c["adc_conversions"] * bits
    c["adds"] += reads * ((nb - 1) * 2 * nb * t + n_active(m.inst) - cnt["tile_sum_adds"] - cnt["shift_adds"])
    return c


def b1_energy(m: Machine, cost: CostModel | None = None, c: dict | None = None) -> dict[str, float]:
    """Energy in fJ per block, same table and formulas as ours (cost_model.CostModel), MESA restart block."""
    cost = cost or CostModel()
    c = c or b1_counts(m)
    v, steps, n = cost.v, len(m.counters.steps), n_active(m.inst)
    time_ns = c["cycles"] * v("t_clk")
    return {
        "array": c["array_cell_reads"] * v("e_array_cell_read"),
        "adc": cost.adc_fj(c),
        "digital": c["adds"] * v("e_add") + c["lut_reads"] * v("e_lut_read") + c["reg_writes"] * v("e_reg_write"),
        "rng": c["rng_draws"] * v("e_rng_draw"),
        "tcam": 0.0,
        "restart": steps * v("e_stall_counter") + c["best_updates"] * n * v("e_shadow_bit"),
        "leakage": cost.leak_fj(b1_gate_eq(n, cost), time_ns) + steps * v("e_adc_bias_step"),
    }


def b1_gate_eq(n: int, cost: CostModel) -> float:
    """NAND2-eq of the B1 digital part (lane logic + RNG + MESA stall counter + shadow register): area and leakage share it."""
    v = cost.v
    return n * (v("g_digital_per_lane") + v("g_rng_per_lane") + v("g_shadow_per_bit")) + v("g_stall_counter")


def b1_area(n: int, cfg: B1Cfg = B1Cfg(), cost: CostModel | None = None) -> dict[str, float]:
    """Area in um2 per block: tiles x 32x32 cells, one ADC per tile column, shared digital/RNG/MESA gate counts."""
    cost = cost or CostModel()
    v, g, cnt = cost.v, cost.v("a_nand2"), tile_counts(n, cfg)
    return {
        "array": cnt["cell_reads"] * v("a_array_cell"),
        "adc": cnt["conversions"] * v("a_adc_col"),
        "digital": n * v("g_digital_per_lane") * g,
        "rng": n * v("g_rng_per_lane") * g,
        "tcam": 0.0,
        "restart": v("g_stall_counter") * g + n * v("g_shadow_per_bit") * g,
        "leakage": 0.0,
    }


# ------------------------------------------------------------------------------------------------ P4_v2 (BASELINES_V2)
# MESA v2 (prereg/calib/P4_v2_reproduction.md R1, R5): the reading of Yin's MESA text that P4.02 / P4.02a / H6 approached in
# three steps, now in one place and locked by tests/hw/test_baselines_v2.py:
#   * each epoch starts from the best state so far ("the previous optimum") and resets T := T0;
#   * within an epoch T falls geometrically T0 -> T_end over E sweeps and is then HELD at T_end (per-epoch cooling, P4.02a);
#   * the trap counter (no strict improvement of the EPOCH best) only runs once T has reached T_end, so an epoch can never end
#     before it has cooled (K >= epoch, the H6 amendment-1 fix, now structural rather than a K floor);
#   * at Count_max the epoch ends; the next epoch's start is the best state with m in {1, 2, 3} distinct bits flipped
#     (Yin's "random perturbations by flipping a few bits"; on the shared single-flip machine the perturbation is the epoch
#     kick, on the native kernel it is every proposal).
from restart import RestartUnit  # noqa: E402

MESA2_EPOCH_SWEEPS = 10          # P4.02a value (not tuned)
MESA2_KICK_MAX = 3               # "a few bits": m uniform in {1, 2, 3}


def mesa2_instance(inst: Instance, t_end: float, n_act: int, epoch_sweeps: int = MESA2_EPOCH_SWEEPS) -> tuple[Instance, int]:
    """Per-epoch geometric alpha: T0 -> t_end over epoch_sweeps x n_act steps (the run length stays inst.steps)."""
    from instances import alpha_reg, temp_reg  # noqa: PLC0415
    t0 = inst.t0 / float(1 << 16)
    return dataclasses.replace(inst, geom=1, alpha=alpha_reg(t0, t_end, epoch_sweeps * n_act)), temp_reg(t_end)


class MesaV2Unit(RestartUnit):
    """Golden restart unit for MESA v2 (replaces the machine's RestartUnit after construction; counters record its restarts)."""

    def __init__(self, machine, K: int, t_floor: int, epoch_steps: int, kick_max: int = MESA2_KICK_MAX):
        super().__init__(RestartCfg(arm="mesa", K=K), machine)
        assert t_floor >= 1 and kick_max >= 1 and epoch_steps >= 1
        self.t_floor = int(t_floor)
        self.epoch_steps = int(epoch_steps)
        self.e = 0
        self.kick_max = min(kick_max, max(len(self.perm) - 1, 1))
        self.cooled = machine.temp <= self.t_floor
        self.epoch_best = machine.f
        self.kicks: list[int] = []

    @property
    def offset_enabled(self) -> bool:
        return False                                 # Yin have no DA offset

    def after_step(self, m) -> bool:
        self.e += 1
        if m.temp <= self.t_floor or self.e >= self.epoch_steps:   # hold at T_end (golden geom keeps multiplying: clamp)
            m.temp = self.t_floor
            self.cooled = True
        if m.f > self.epoch_best:
            self.epoch_best = m.f
            self.stall = 0
        elif self.cooled:
            self.stall += 1
        if self.stall < self.K:
            return False
        m.load_state(m.best_x)
        mbits = 1 + ((m.sel.next() * self.kick_max) >> 32)
        x = m.x.copy()
        size = len(self.perm)
        for a in range(mbits):                       # partial Fisher-Yates on the persistent lane permutation (as Kc2)
            j = a + ((m.sel.next() * (size - a)) >> 32)
            self.perm[a], self.perm[j] = self.perm[j], self.perm[a]
            x[self.perm[a]] ^= 1
        m.load_state(x)
        if m.is_feasible() and m.f > m.best_f:
            m.best_f, m.best_x, m.best_step = m.f, m.x.copy(), m.t
        m.temp = m.inst.t0
        m.eoff = 0
        self.cooled = m.temp <= self.t_floor
        self.e = 0
        self.epoch_best = m.f
        self.stall = 0
        self.events.append(m.t)
        self.kicks.append(int(mbits))
        return True


def b1_mesa2_machine(inst: Instance, cfg: B1Cfg, t_end: float, epoch_sweeps: int = MESA2_EPOCH_SWEEPS) -> Machine:
    """B1 machine (tiled CiM field) with MESA v2. Count_max = cfg.count_max (None -> 2n)."""
    n = n_active(inst)
    inst2, t_floor = mesa2_instance(inst, t_end, n, epoch_sweeps)
    m = b1_machine(inst2, cfg)
    m.restart = MesaV2Unit(m, cfg.count_max or 2 * n, t_floor, epoch_sweeps * n)
    m.deoff = 0
    return m


# Native Yin kernel (R1): ONE proposal per iteration flipping m in {1, 2, 3} distinct bits, exact dE, Metropolis. mode 0 =
# conventional SA (geometric T0 -> T_end over the whole run), mode 1 = MESA v2 (rules above). Maximises f = d.x + x.P.x / 2.
import numba as nb  # noqa: E402


@nb.njit(cache=True)
def _yin_seed(seed):
    np.random.seed(seed)


@nb.njit(cache=True)
def _yin_run(d, P, sweeps, T0, Tend, epoch_iters, count_max, mode):
    n = d.shape[0]
    total = sweeps * n
    x = np.zeros(n, np.int64)
    h = d.copy()
    f = 0
    best_f = 0
    best_x = x.copy()
    curve = np.zeros(sweeps, np.int64)
    idx = np.empty(3, np.int64)
    ratio_run = Tend / T0
    e = 0
    trap = 0
    epoch_best = 0
    epochs = 0
    for t in range(total):
        if mode == 0:
            T = T0 * ratio_run ** (t / max(total - 1, 1))
        else:
            T = T0 * ratio_run ** (min(e, epoch_iters - 1) / max(epoch_iters - 1, 1))
        m = 1 + np.random.randint(3)
        c = 0
        while c < m:
            j = np.random.randint(n)
            dup = False
            for a in range(c):
                if idx[a] == j:
                    dup = True
            if not dup:
                idx[c] = j
                c += 1
        df = 0
        for a in range(m):
            i = idx[a]
            si = 1 if x[i] == 0 else -1
            df += si * h[i]
            for b in range(a):
                k = idx[b]
                sk = 1 if x[k] == 0 else -1
                df += si * sk * P[i, k]
        if df >= 0 or np.random.random() < np.exp(df / T):
            for a in range(m):
                i = idx[a]
                s = 1 if x[i] == 0 else -1
                x[i] ^= 1
                for q in range(n):
                    h[q] += s * P[q, i]
            f += df
            if f > best_f:
                best_f = f
                best_x[:] = x
        if mode == 1:
            e += 1
            if f > epoch_best:
                epoch_best = f
                trap = 0
            elif e >= epoch_iters:
                trap += 1
            if trap >= count_max:
                x[:] = best_x
                h[:] = d
                for i in range(n):
                    if x[i] == 1:
                        for q in range(n):
                            h[q] += P[q, i]
                f = best_f
                epoch_best = f
                e = 0
                trap = 0
                epochs += 1
        if (t + 1) % n == 0:
            curve[(t + 1) // n - 1] = best_f
    return best_f, curve, epochs, best_x


def yin_native_run(d, P, sweeps: int, t0: float, t_end: float, mode: str, seed: int, count_max: int | None = None,
                   epoch_sweeps: int = MESA2_EPOCH_SWEEPS) -> tuple[int, np.ndarray, int, np.ndarray]:
    """(best f, best-so-far f after every sweep, epochs, best x) of one native Yin run; mode 'sa' or 'mesa'."""
    n = len(d)
    _yin_seed(int(seed) & 0x7FFFFFFF)
    return _yin_run(np.asarray(d, np.int64), np.asarray(P, np.int64), int(sweeps), float(t0), float(t_end),
                    int(epoch_sweeps * n), int(count_max or 2 * n), {"sa": 0, "mesa": 1}[mode])
