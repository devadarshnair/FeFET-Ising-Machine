"""B3 = Fujitsu Digital Annealer (Aramon et al. 2019, arXiv 1806.08815v3) as a configuration of OUR golden machine.

Sheet: docs/hw/lit/aramon2019_da.md ([FT] found in text, [U] labelled default).
  parallel trial over all n lanes, one accepted flip chosen uniformly   [FT] Alg. 2  (golden lanes + select tree)
  dynamic offset: E_off += rate per step with no accept, := 0 on accept  [FT] Alg. 2  (golden restart arm da_offset)
  offset rate: NOT published; paper's final runs had the offset OFF     [FT] App. A  -> default rate 0 [U];
                                                                        a positive rate is an ablation arm
  schedule: linear in 1/T, T updated every iteration, Th/Tl from the
  5-10th / 80-85th percentile rule on |dE| of proposed moves             [FT] App. A  (golden-only override, see below)
  start state: all zeros for every run                                  [FT] App. A  (golden x0 = 0)
  couplers 16 b, biases 26 b, stored in SRAM; digital field update       [FT] Sec. I  (COSTED at 16 / 26 b; the shared
                                                                        machine computes with its 10 / 12 b datapath)
  no ADC, no CiM array                                                  [FT]
  RNG: TGFSR in the paper; here the golden xoshiro lane streams          [U]  (fairness: same RNG for every arch)

Schedule: the RTL temp_sched is geometric only. B3 runs with `schedule="geom"` are RTL-equivalent (b3_maxcut16
bit-exact); `schedule="lin_beta"` (Aramon) overrides T in the golden model after every step and is used for the P4.04
calibration only. This is a schedule-level difference recorded as such, not a machine change.

Cost mapping (digital, not FeFET CiM): per step every lane does its Metropolis trial (RNG draw, LUT read, compare:
golden op counters x the shared table); per accepted flip the 16 b coupler row j (n x 16 b) is read from SRAM and n
field adders update h. Energy = golden counters priced with the P3.11-corrected table (Yosys gate counts) plus SRAM
read energy per bit from literature (docs/hw/energy_table_b3_extra.csv, labelled literature, not characterised).
Area = n^2 x 16 b + n x 26 b SRAM bit cells + n x (lane logic + RNG) + select tree + offset adder + stall-free
(no restart counter). Width caveat: the Yosys lane counts are at the shared 10 / 12 b widths, so for the DA's 16 / 26 b
they are a lower bound on the field part (field_unit is 369 of 6579 NAND2-eq per lane; accept_unit dominates).
"""
from __future__ import annotations

import csv
import dataclasses
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
sys.path.insert(0, str(GOLDEN))

from cost_model import CostModel, canonical_table  # noqa: E402
from counters import CycleCfg  # noqa: E402
from instances import temp_reg  # noqa: E402
from restart import RestartCfg  # noqa: E402
from tim_golden import Instance, Machine  # noqa: E402

LABEL = "literature-parameterised"
DOCS = Path(__file__).resolve().parents[2] / "docs" / "hw"


@dataclass(frozen=True)
class B3Cfg:
    offset_rate: int = 0             # E_off increment per no-accept step, energy LSB; 0 = paper's final setting
    coupler_bits: int = 16
    bias_bits: int = 26
    schedule: str = "geom"           # "geom" (RTL-equivalent) or "lin_beta" (Aramon App. A, golden only)
    t_high: float | None = None      # lin_beta only: Th, Tl in energy LSB
    t_low: float | None = None
    label: str = LABEL

    def __post_init__(self):
        assert self.schedule in ("geom", "lin_beta") and self.offset_rate >= 0
        if self.schedule == "lin_beta":
            assert self.t_high and self.t_low and self.t_high >= self.t_low > 0

    def restart(self) -> RestartCfg:
        return RestartCfg(arm="da_offset")


def b3_table() -> dict:
    return canonical_table()        # P4.08: same table as ours/B1/B2 (cost_model.canonical_table)


def b3_cost(**kw) -> CostModel:
    return CostModel(table=b3_table(), **kw)


def b3_instance(inst: Instance, cfg: B3Cfg = B3Cfg()) -> Instance:
    return dataclasses.replace(inst, deoff=cfg.offset_rate)


def lin_beta_temps(cfg: B3Cfg, steps: int) -> list[int]:
    """T register per step for beta linear from 1/Th to 1/Tl over `steps` iterations (T used by step t+1)."""
    b0, b1 = 1.0 / cfg.t_high, 1.0 / cfg.t_low
    return [temp_reg(1.0 / (b0 + (b1 - b0) * t / max(steps - 1, 1))) for t in range(steps)]


class B3Machine(Machine):
    """Golden machine with the DA configuration; lin_beta sets T before each step."""

    def __init__(self, inst: Instance, cfg: B3Cfg = B3Cfg(), counters: bool = True):
        inst = b3_instance(inst, cfg)
        if cfg.schedule == "lin_beta":
            inst = dataclasses.replace(inst, geom=0, alpha=0, t0=temp_reg(cfg.t_high))
        super().__init__(inst, restart=cfg.restart(), cim=None, power=None, counters=CycleCfg() if counters else None)
        self.b3 = cfg
        self._temps = lin_beta_temps(cfg, inst.steps) if cfg.schedule == "lin_beta" else None
        self.accepts = 0          # sum over steps of the number of accepting lanes c
        self.any_accept = 0       # steps with c > 0
        self.window = None        # (start step, accepts, any_accept) for a low-T window, set by the caller

    def step(self) -> str:
        if self._temps is not None:
            self.temp = self._temps[min(self.t, len(self._temps) - 1)]
        line = super().step()
        c = int(line.split()[2])
        self.accepts += c
        self.any_accept += c > 0
        if self.window is not None and self.t > self.window[0]:
            s, a, p = self.window
            self.window = (s, a + c, p + (c > 0))
        return line


def b3_machine(inst: Instance, cfg: B3Cfg = B3Cfg(), counters: bool = True) -> B3Machine:
    return B3Machine(inst, cfg, counters)


def b3_counts(m: B3Machine) -> dict[str, int]:
    """Golden op counters plus the SRAM bit reads of the DA datapath (one coupler row per accepted flip)."""
    c = dict(m.counters.total)
    n = m.inst.n if m.lane_en is None else int(m.lane_en.sum())
    c["sram_bit_reads"] = m.flips * n * m.b3.coupler_bits
    c["array_cell_reads"] = c["adc_conversions"] = c["adc_conv_bits"] = 0
    return c


def b3_energy(m: B3Machine, cost: CostModel | None = None) -> dict[str, float]:
    """Energy in fJ per block: digital trial + field update (shared table), SRAM reads (literature), DA offset adder."""
    cost = cost or b3_cost()
    v, c, steps = cost.v, b3_counts(m), len(m.counters.steps)
    time_ns = c["cycles"] * v("t_clk")
    return {
        "array": 0.0,
        "adc": 0.0,
        "sram": c["sram_bit_reads"] * v("e_sram_read_bit"),
        "digital": c["adds"] * v("e_add") + c["lut_reads"] * v("e_lut_read") + c["reg_writes"] * v("e_reg_write"),
        "rng": c["rng_draws"] * v("e_rng_draw"),
        "tcam": 0.0,
        "restart": steps * v("e_offset_add") if m.b3.offset_rate > 0 else 0.0,
        "leakage": cost.leak_fj(b3_gate_eq(m.inst.n if m.lane_en is None else int(m.lane_en.sum()), cost), time_ns),   # no ADC bias term
    }


def select_tree_eq(n: int, gate_csv: Path | None = None) -> float:
    """NAND2-eq of the select tree at n (power of two): p309_gate_counts rows; between rows, linear in n."""
    rows = {}
    path = gate_csv or DOCS / "results" / "p309_gate_counts.csv"
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["block"] in ("select_tree", "select_tree_est") and r["N"] != "-":
                rows.setdefault(int(r["N"]), float(r["nand2_eq"]))
    if n in rows:
        return rows[n]
    ks = sorted(rows)
    lo = max([k for k in ks if k <= n], default=ks[0])
    hi = min([k for k in ks if k >= n], default=ks[-1])
    if lo == hi:
        return rows[lo] * n / lo
    return rows[lo] + (rows[hi] - rows[lo]) * (n - lo) / (hi - lo)


def b3_gate_eq(n: int, cost: CostModel) -> float:
    """NAND2-eq of the B3 digital part (lane logic + RNG + select tree + offset adder): area and leakage share it."""
    v = cost.v
    return n * (v("g_digital_per_lane") + v("g_rng_per_lane")) + select_tree_eq(n) + v("g_offset_adder")


def b3_area(n: int, cfg: B3Cfg = B3Cfg(), cost: CostModel | None = None) -> dict[str, float]:
    """Area in um2 per block (cell area only; SRAM bit cell from literature)."""
    cost = cost or b3_cost()
    v, g = cost.v, cost.v("a_nand2")
    sram_bits = n * n * cfg.coupler_bits + n * cfg.bias_bits
    return {
        "array": 0.0,
        "adc": 0.0,
        "sram": sram_bits * v("a_sram_bit"),
        "digital": (n * v("g_digital_per_lane") + select_tree_eq(n)) * g,
        "rng": n * v("g_rng_per_lane") * g,
        "tcam": 0.0,
        "restart": v("g_offset_adder") * g,
        "leakage": 0.0,
    }


def acceptance_boost(m: B3Machine) -> float:
    """Measured parallel-trial boost in the window: P_parallel / P_single = n * P(c > 0) / E[c] (Aramon Eq. 2)."""
    assert m.window is not None
    _, a, p = m.window
    n = m.inst.n if m.lane_en is None else int(m.lane_en.sum())
    return float("nan") if a == 0 else n * p / a


def sk_qubo(n: int, seed: int, kind: str, sigma: int = 10):
    """SK spin glass (fully connected) as integer QUBO: maximise sum_{i<j} J_ij s_i s_j, s = 2x - 1.
    kind "bimodal": J = +-1; "gaussian": J = round(sigma * N(0, 1)) (integer-scaled, as Aramon scale by 1e5).
    QUBO: P_ij = 4 J_ij, d_i = -2 sum_j J_ij; objective(x) = Ising value - sum_{i<j} J_ij."""
    rng = np.random.default_rng([20261116, n, seed, 0 if kind == "bimodal" else 1])
    if kind == "bimodal":
        J = rng.choice(np.array([-1, 1]), size=(n, n))
    else:
        J = np.rint(sigma * rng.standard_normal((n, n))).astype(np.int64)
    J = np.triu(J, 1)
    J = (J + J.T).astype(np.int64)
    return (-2 * J.sum(axis=1)).astype(np.int64), (4 * J).astype(np.int64)


def dE_percentiles(d: np.ndarray, P: np.ndarray, seed: int, samples: int = 200) -> tuple[float, float]:
    """Aramon App. A rule inputs: |dE| of single-flip proposals from uniformly random states; returns (p7.5, p82.5)."""
    rng = np.random.default_rng([seed, 99])
    vals = []
    for _ in range(samples):
        x = rng.integers(0, 2, len(d))
        h = d + P @ x
        vals.append(np.abs(np.where(x == 1, -h, h)))
    a = np.concatenate(vals)
    a = a[a > 0]
    return float(np.percentile(a, 7.5)), float(np.percentile(a, 82.5))


def tts99(p: float, iters: int) -> float:
    """Aramon Sec. IV: R99 = ln(0.01) / ln(1 - p); TTS = R99 x iterations per run (inf if p = 0, iters if p = 1)."""
    if p <= 0:
        return math.inf
    if p >= 1:
        return float(iters)
    return math.log(0.01) / math.log(1 - p) * iters


# ------------------------------------------------------------------------------------------------ P4_v2 (BASELINES_V2)
# Fast kernels of the SAME DA algorithm as B3Machine (parallel trial over all variables, one accepted flip chosen uniformly,
# offset off = Aramon App. A final setting, start x = 0), in float Metropolis instead of the golden LUT, for the paper-scale
# reproductions R2 / R3 of prereg/calib/P4_v2_reproduction.md. Golden convention: maximise f = d.x + x.P.x / 2 (P zero diag);
# gain_i = (1 - 2 x_i) h_i, h = d + P x, accept iff gain >= 0 or u < exp(beta gain). Equivalence to B3Machine: tests/hw/
# test_baselines_v2.py (same best-energy distribution on small SK; same deterministic greedy limit).
import numba as nb  # noqa: E402


@nb.njit(cache=True)
def _da_seed(seed):
    np.random.seed(seed)


@nb.njit(cache=True)
def _da_anneal_runs(d, P, betas, runs):
    """`runs` independent DA anneals; returns (best_f, best_step) per run (step 1-based; 0 = start state)."""
    n, L = d.shape[0], betas.shape[0]
    best = np.zeros(runs, np.int64)
    when = np.zeros(runs, np.int64)
    acc = np.empty(n, np.int64)
    for r in range(runs):
        x = np.zeros(n, np.int64)
        h = d.copy()
        f = 0
        bf, bt = 0, 0
        for t in range(L):
            b = betas[t]
            c = 0
            for i in range(n):
                g = h[i] if x[i] == 0 else -h[i]
                if g >= 0 or np.random.random() < np.exp(b * g):
                    acc[c] = i
                    c += 1
            if c > 0:
                k = acc[np.random.randint(c)]
                s = 1 if x[k] == 0 else -1
                f += h[k] if x[k] == 0 else -h[k]
                x[k] ^= 1
                for j in range(n):
                    h[j] += s * P[j, k]
                if f > bf:
                    bf, bt = f, t + 1
        best[r], when[r] = bf, bt
    return best, when


def lin_betas(t_high: float, t_low: float, steps: int) -> np.ndarray:
    """Aramon App. A: beta linear from 1/Th to 1/Tl, updated every iteration."""
    return np.linspace(1.0 / t_high, 1.0 / t_low, steps)


def da_anneal(d, P, t_high: float, t_low: float, steps: int, runs: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    _da_seed(int(seed) & 0x7FFFFFFF)
    return _da_anneal_runs(np.asarray(d, np.int64), np.asarray(P, np.int64), lin_betas(t_high, t_low, steps), int(runs))


@nb.njit(cache=True)
def _da_const_t(d, P, T, therm, meas):
    """Constant-T DA dynamics; after `therm` iterations, mean of Pp and Ps (Aramon Eqs. 1-2) over `meas` iterations."""
    n = d.shape[0]
    x = np.zeros(n, np.int64)
    h = d.copy()
    acc = np.empty(n, np.int64)
    A = np.empty(n)
    sp, ss = 0.0, 0.0
    for t in range(therm + meas):
        c = 0
        for i in range(n):
            g = h[i] if x[i] == 0 else -h[i]
            A[i] = 1.0 if g >= 0 else np.exp(g / T)
            if g >= 0 or np.random.random() < A[i]:
                acc[c] = i
                c += 1
        if t >= therm:
            ss += A.mean()
            lq = 0.0
            one = False
            for i in range(n):
                if A[i] >= 1.0:
                    one = True
                    break
                lq += np.log1p(-A[i])
            sp += 1.0 if one else -np.expm1(lq)
        if c > 0:
            k = acc[np.random.randint(c)]
            s = 1 if x[k] == 0 else -1
            x[k] ^= 1
            for j in range(n):
                h[j] += s * P[j, k]
    return sp / meas, ss / meas


def da_const_t(d, P, T: float, therm: int, meas: int, seed: int) -> tuple[float, float]:
    """(mean Pp, mean Ps) of Aramon Fig. 1-2 at constant temperature T (iterations, not sweeps)."""
    _da_seed(int(seed) & 0x7FFFFFFF)
    return _da_const_t(np.asarray(d, np.int64), np.asarray(P, np.int64), float(T), int(therm), int(meas))


def b3v2_t_final(t_high: float, t_low: float, knob: float) -> float:
    """P4_v2 section 5: B3 v2 secondary knob = final temperature of the lin-beta schedule. knob 1.0 -> T_low; knob 0.5 ->
    T_low^2 / T_high, the final temperature ours' 'none' arm reaches at schedule fraction 0.5 (geometric schedule continued
    for the second half), so ours and B3 v2 search the same (T_start, T_final) set."""
    assert knob in (1.0, 0.5), knob
    return t_low if knob == 1.0 else t_low * t_low / t_high


def b3v2_cfg(t_high: float, t_low: float, knob: float) -> B3Cfg:
    """B3 v2 = Aramon's final configuration: offset OFF, linear-in-beta from Th to T_final, start x = 0."""
    return B3Cfg(offset_rate=0, schedule="lin_beta", t_high=t_high, t_low=b3v2_t_final(t_high, t_low, knob))


def aramon_table1(kind: str, sigma: int = 10) -> tuple[float, float]:
    """(Th, Tl) of Aramon Table I (DA row) in our units: bimodal unchanged; Gaussian J ~ N(0,1) x 1e5 -> x sigma."""
    return (40.0, 4.0) if kind == "bimodal" else (2e5 * sigma / 1e5, 1e4 * sigma / 1e5)


def jeffreys_tts(successes: int, runs: int, steps: int) -> float:
    """Aramon Sec. IV: TTS = L R99 with theta = Jeffreys Beta(0.5, 0.5) posterior mean (y + 0.5) / (r + 1)."""
    theta = (successes + 0.5) / (runs + 1.0)
    return steps * max(1.0, math.log(0.01) / math.log(1 - theta))
