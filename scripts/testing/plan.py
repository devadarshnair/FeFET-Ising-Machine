"""Registered design of the testing phase (prereg/hw/H2, H3, H5 drafts) as data: instances, seeds, tuning grid, arms,
H3 grid, H5 perturbation points. One source for the runner, the job generator, the budget and the evaluators.

Every constant tagged [DRAFT] is a draft default the author may still change before tagging (A8); nothing here has been
run on scored data. Nothing in this module imports a machine model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

BASE_SEED = 20261116                    # [DRAFT] fixed at tagging; run r of instance i uses mix_seed(BASE_SEED, family, i, r)
SWEEPS = 150                            # steps = SWEEPS x spins (H2 section 3)
REF_SWEEP_MULT, REF_SEEDS = 10, 20      # reference set R (MaxSAT target): 20 seeds x 10x budget
N_CHECKPOINTS = 40                      # cumulative-counter snapshots per run (ETS / fixed-budget interpolation grid)
QKP_LENGTHS = (10_000, 100_000)         # B2 proposals
QKP_TARGET_FRAC = 0.99                  # [DRAFT] B2 success = best profit >= frac x exact optimum (H2 states no QKP target)
MAXCUT_TARGET_FRAC = 0.99               # H2 section 5: G-set best-known x 0.99
TILE_ROWS = 256                         # R6, ours monolithic array
FAMILIES = ("maxcut", "maxsat", "colouring")
FAMILY_ID = {"maxcut": 1, "maxsat": 2, "colouring": 3, "qkp": 4, "col3p": 5, "col4p": 6,     # col3p/col4p: H6 planted colouring
             "p3n240": 7, "p3n480": 8, "p3n960": 9, "p4n240": 10, "p4n480": 11, "p4n960": 12, "dimacs": 13}   # H7
FAMILY_ID.update({"p3n120": 16, "p4n120": 17, "p3n2040": 18, "p4n2040": 19, "dimacs8": 20})   # H8 (h8_instances); p3n240.. reuse the H7 ids
FAMILY_ID.update({"vmc120": 14, "vmc240": 15})       # VARIATION_V2 smoke: small G(n, 4n) Max-Cut (variation_v2.vmc_mapped)

_QKP_ALL = [f"jeu_100_{d}_{i}.txt" for d in (25, 50, 75, 100) for i in range(1, 11)]
TUNE_SET = {
    "maxcut": ["G6", "G7", "G16", "G18"],
    "maxsat": [str(s) for s in range(2001, 2005)],
    "colouring": [str(s) for s in range(401, 405)],
    "qkp": [f"jeu_100_{d}_{i}.txt" for d, i in ((25, 9), (25, 10), (50, 9), (50, 10), (75, 8), (75, 9), (75, 10),
                                                 (100, 8), (100, 9), (100, 10))],      # [DRAFT] 10 disjoint
}
TEST_SET = {
    "maxcut": [f"G{i}" for i in (1, 2, 3, 4, 5, 11, 12, 13, 14, 15)],
    "maxsat": [str(s) for s in range(1001, 1011)],
    "colouring": [str(s) for s in range(301, 311)],
    "qkp": [n for n in _QKP_ALL if n not in TUNE_SET["qkp"]],                          # the other 30 of the 40
}
TEST_SEEDS = {"maxcut": 10, "maxsat": 10, "colouring": 10, "qkp": 20}
TUNE_SEEDS = 2
H3_INSTANCES, H3_SEEDS = 5, 5            # first 5 of each H2 test set, 5 seeds, same seeds as H2
H5_INSTANCES = {"maxcut": 3, "maxsat": 5}
H5_SEEDS = 5

# ---------------------------------------------------------------------------------------------------------- tuning grid
PCT_PAIRS = ((85, 5), (90, 5), (85, 10), (75, 5))       # [DRAFT] (T_start, T_end) percentiles of |dE| (P4.02 rule): 4 rule pairs
STALL_K_MULT = (1, 2)                                   # K in {n, 2n} for the stall arms
DA_RATE_DIV = (4, 2)                                    # DA offset rate in {Tl/4, Tl/2}
SCHED_FRAC = (1.0, 0.5)                                 # "none": a second schedule length (fraction of the budget used to cool)
B3_OFFSET = ("off", "on")                               # Fujitsu DA offset knob; on = Tl/4
B2_SCHEDULES = ("S1", "S2", "S3", "S4")                 # B2 grid = schedule x pswap {0, PSWAP_V3}; 8 configs as everywhere else
DEFAULT_PCT = (85, 5)


@dataclass(frozen=True)
class Config:
    """One of the 8 grid points of an arm (4 percentile pairs x 2 knob values)."""
    cid: str
    pct_hi: int = 85
    pct_lo: int = 5
    knob: float = 2.0       # K multiple (mesa/kc2) | rate divisor (da_offset) | schedule fraction (none) | 0/1 offset (b3)
    sched: str = ""         # B2 schedule name
    pswap: int = 0          # B2: 1 = PSWAP_V3

    def as_dict(self):
        return asdict(self)


def knob_values(restart: str) -> tuple:
    return {"mesa": STALL_K_MULT, "kc2": STALL_K_MULT, "da_offset": DA_RATE_DIV, "none": SCHED_FRAC,
            "b3": (0.0, 1.0), "b3v2": (1.0, 0.5), "mesa2": STALL_K_MULT}[restart]     # b3v2 / mesa2: BASELINES_V2 (P4_v2 s.5)


def grid(restart: str) -> list[Config]:
    """8 configs for a restart arm of ours/B1 ('none','da_offset','mesa','kc2') or 'b3' or 'b2'."""
    if restart == "b2":
        return [Config(f"b2s{s}p{p}", sched=s, pswap=p) for s in B2_SCHEDULES for p in (0, 1)]
    out = []
    for hi, lo in PCT_PAIRS:
        for kv in knob_values(restart):
            out.append(Config(f"{restart}_p{hi}_{lo}_k{kv:g}", hi, lo, float(kv)))
    return out


def default_config(restart: str) -> Config:
    """Untuned default (rung 1, B1 as published): MESA, K = 2n, percentile rule (85, 5)."""
    return Config("default", DEFAULT_PCT[0], DEFAULT_PCT[1], 2.0)


# ------------------------------------------------------------------------------------------------------------ arms
RESTARTS = ("none", "da_offset", "mesa", "kc2")
SIM_POWERS = ("i10", "i7i10")           # H2 simulates these; "off" and "i7" are priced from the same trajectories (lossless I10)
PRICING_VARIANTS = {"off": ("i10", False), "i10": ("i10", True), "i7": ("i7i10", False), "i7i10": ("i7i10", True)}
K_P, K_G = 5, 8                         # I7 / I10 thresholds, the values of the P6.01 smoke
IDENTITY_DEOFF = False                  # [DRAFT] ablation arms are pure: DA offset only in the da_offset arm (smoke kept deoff=1 for all)


POWER_MODES = ("off", "i10", "i7", "i7i10", "i7v2", "i7v2i10", "fs")   # fs (H7): lossless ADC full scale, no I7/I10


@dataclass(frozen=True)
class Arm:
    machine: str            # ours | b1 | b1bs | b3 | b2
    restart: str            # none | da_offset | mesa | kc2 | b3 | b2
    power: str = ""         # ours: simulated power mode i10 | i7i10 (H2), off | i10 | i7 | i7i10 (H3/H5 frozen config); H6 adds
                            # i7v2 | i7v2i10 (I7 with the ADC full scale = max column sum, b_lo = b_hi - 1)
    tweak: str = ""         # "" | i11 | i5_h1g1 | i5_h4g4

    @property
    def key(self) -> str:
        return ".".join(p for p in (self.machine, self.restart, self.power, self.tweak) if p)

    @staticmethod
    def parse(key: str) -> "Arm":
        p = key.split(".")
        machine, restart = p[0], p[1]
        power = p[2] if len(p) > 2 and p[2] in POWER_MODES else ""
        tweak = p[-1] if len(p) > 2 and p[-1] not in POWER_MODES else ""
        return Arm(machine, restart, power, tweak)


def h2_arms(family: str) -> list[Arm]:
    arms = [Arm("ours", r, p) for r in RESTARTS for p in SIM_POWERS]
    arms += [Arm("ours", "kc2", p, "i11") for p in SIM_POWERS]
    arms += [Arm("b1", r) for r in RESTARTS] + [Arm("b1bs", "mesa"), Arm("b3", "b3")]
    return arms


UNTUNED = (Arm("b1", "mesa", "", "published"),)          # rung 1: B1 as published, test only


def h2_tuned_arm_keys(family: str) -> list[str]:
    return [a.key for a in h2_arms(family)]


# ------------------------------------------------------------------------------------------------------------ H3 grid
H3_READ_E = (0.2, 0.5, 1.0, 2.0, 5.0)
H3_ARRAY_ADC = (0.5, 1.0, 2.0, 3.0)
H3_ADC_DELTA = (-2, -1, 0, 1, 2)
H3_SIGMA = (0.5, 1.0, 2.0, 5.0)
H3_RNG = (0.3, 1.0, 3.0)
H3_CLOCK = (0.5, 1.0, 2.0)
H3_CELLS = len(H3_READ_E) * len(H3_ARRAY_ADC) * len(H3_ADC_DELTA) * len(H3_SIGMA) * len(H3_RNG) * len(H3_CLOCK)   # 3600
H3_TRAJ = [(dl, sg) for dl in H3_ADC_DELTA for sg in H3_SIGMA]                                                   # 20
# cost-only scale hooks (cost_model.CostModel.scale keys), H3 section 2
SCALE_KEYS = {"read": ("e_array_cell_read",), "arrayrc_adc": ("e_array_cell_read", "e_adc_conv_bit", "e_adc_bias_step"),
              "rng": ("e_rng_draw",), "clock": ("t_clk",)}

# ------------------------------------------------------------------------------------------------------- noise nominal
LEVEL7_REL_SIGMA = 0.15 / 99.15          # P4_level0_variation: level 7 sigma 0.15 nA of 99.15 nA
LEVEL0_SIGMA_UNVERIFIED = 4.86 / 99.15   # as-measured level 0 (A2 variation arm), in unit-current
LEVEL0_SIGMA_VERIFIED = 2.9 / 99.15      # level-0 verify ON (binary window), P4_level0_variation.md
WRITE_BAND = 0.05                        # write-verify residual, uniform +-5 % band
MW_V = 1.035                             # memory window used for the drift mapping (P1.06 MW(2 s) set A)
DRIFT_DECADES = 6                        # [DRAFT] log-time span of the retention sweep (1 s .. ~12 days)
TEMPCO_GAIN = -0.0015                    # [DRAFT] parametric read-gain shift per C (no tempco in the model; labelled)
MISMATCH_OFFSET_LSB = 0.25               # [DRAFT] column ADC offset std in LSB at mismatch x1 (7.4 mV, P1.11; parametric)


def sigma_nominal(rows: int) -> float:
    """[DRAFT] nominal read-noise sigma per column conversion in cell-current units: level-7 relative sigma over the ~rows/2
    active cells (the H3 sigma axis multiplies this; H2 runs ideal readout, sigma = 0, so I10 is lossless)."""
    return LEVEL7_REL_SIGMA * math.sqrt(max(rows, 1) / 2.0)


@dataclass(frozen=True)
class Perturb:
    """One H5 point. Multipliers are x1 = nominal; drift/temperature/supply physical values; corner None = TT."""
    pid: str
    dev: float = 1.0         # 1  Vth/conductance D2D sigma multiple (0 = ideal: ALL stochastic terms 0)
    l0_measured: bool = False   # 2  level 0 unverified
    write: float = 1.0       # 3  cycle-to-cycle write noise multiple
    read: float = 1.0        # 4  read noise multiple
    drift_v_dec: float = 0.0  # 5  MW loss, V per decade
    temp_c: float = 25.0     # 7
    supply: float = 1.0      # 8
    mismatch: float = 1.0    # 9
    corner: str = ""         # 10 SS | FF | "" (not evaluable: no card with corners)
    ideal: bool = False

    def as_dict(self):
        return asdict(self)

    @property
    def evaluable(self) -> bool:
        return not self.corner


def h5_points() -> list[Perturb]:
    p = [Perturb("nominal")]
    p += [Perturb("dev_x0", dev=0.0, write=0.0, read=0.0, mismatch=0.0, ideal=True),
          Perturb("dev_x2", dev=2.0), Perturb("dev_x4", dev=4.0), Perturb("l0_measured", l0_measured=True)]
    p += [Perturb(f"write_x{m}", write=float(m)) for m in (1, 2, 4)]
    p += [Perturb(f"read_x{m}", read=float(m)) for m in (1, 2, 4)]
    p += [Perturb(f"drift_{v}", drift_v_dec=v) for v in (0.0, 0.02, 0.05)]
    p += [Perturb(f"temp_{t}", temp_c=float(t)) for t in (0, 45, 85)]
    p += [Perturb(f"supply_{s}", supply=s) for s in (0.9, 1.1)]
    p += [Perturb(f"mismatch_x{m}", mismatch=float(m)) for m in (1, 2)]
    p += [Perturb("corner_SS", corner="SS"), Perturb("corner_FF", corner="FF")]
    p += [Perturb("combined", dev=4.0, l0_measured=True, write=4.0, read=4.0, drift_v_dec=0.05, temp_c=85.0, supply=0.9,
                  mismatch=2.0)]
    return p


H5_POINTS = h5_points()                  # 24 points (22 evaluable without the two corner points; temperature is parametric)
H5_ARMS = (Arm("ours", "kc2", "i7"), Arm("ours", "mesa", "i7"), Arm("ours", "none", "i7"), Arm("b1", "mesa"),
           Arm("ours", "kc2", "i7i10"))       # last: I10 freezing noise (P2.04), reported as a separate arm


# T7 extra arm: sign-magnitude weight coding (each entry stored once in the array of its own sign, the other polarity has no cell),
# reported separately, never in the 24-point decision. Same frozen Kc2 config and I7 as the main arm.
H5_EXTRA_ARMS = (Arm("ours", "kc2", "i7", "sm"),)
# B2 (HyCiM, QKP): only the points the filter's analogue path has (device sigma, read noise). Supply, temperature, drift and mismatch scale
# the weight array and the replica together, so the accept-iff-less decision is ratiometric and they are not applied (recorded, not run).
H5_B2_POINTS = ("nominal", "dev_x0", "dev_x2", "dev_x4", "read_x2", "read_x4")
H5_B2_INSTANCES = 3
H5_B2_PROPOSALS = 100_000
B2_PERT_US_PER_PROPOSAL = 60.0                          # PLACEHOLDER (smoke estimate, rounded up); Stage 0 measures the wrapped kernel ("h5_nominal"); timeouts now 2.5x est so a 2x error is survivable
CORNER_REASON = "no process-corner card in the repo (models/mosfet: TT only; docs/device/STATUS.md: no corners)"


def _same_as_nominal(p: Perturb) -> bool:
    d, n = p.as_dict(), H5_POINTS[0].as_dict()
    return p.pid != "nominal" and {k: v for k, v in d.items() if k != "pid"} == {k: v for k, v in n.items() if k != "pid"}


H5_DUPLICATES = tuple(p.pid for p in H5_POINTS if _same_as_nominal(p))   # x1 / 0-drift / x1 mismatch rows: the nominal run is reused

# ---------------------------------------------------------------------------------------------------------- timing
# Stage 1 cloud timing chunks (32 vCPU IN1, 16 Nov 2026 IST, scripts/testing/time_chunk.py, 20000 steps, 800-spin Max-Cut G1, one process
# each): us/step ours 184, B1 2115, B2 41, B3 47. They were taken at the smoke temperatures (T 3.0 -> 0.1 in energy LSB), i.e. cold: ours
# skips most field reads there (I10), so 184 us/step is NOT the cost of the registered percentile-rule schedules, where a flip is accepted
# almost every step. The runner therefore carries its own timing, measured locally under the registered schedule (scripts/testing/
# run_cell.py records, slope of two sweep counts, loaded 16-core WSL host, 17 Nov 2026 IST), and maps it to the cloud with the local
# time_chunk / cloud time_chunk ratio of the same three machines: ours 184.24/287.5, B1 2115.44/3132, B3 47.45/58.5 (local numbers from the
# earlier P6.02 table, same code, same chunks); mean 0.709. Ours is padded to 1024/512/64 lanes (R6), B1 uses 32x32 tiles, B3 per spin.
CLOUD_TIME_CHUNK_US = {"ours": 184.24, "b1": 2115.44, "b2": 40.99, "b3": 47.45}            # cold-schedule chunks, for the record
LOCAL_TIME_CHUNK_US = {"ours": 287.5, "b1": 3132.0, "b3": 58.5}
CLOUD_OVER_LOCAL = sum(CLOUD_TIME_CHUNK_US[m] / LOCAL_TIME_CHUNK_US[m] for m in LOCAL_TIME_CHUNK_US) / len(LOCAL_TIME_CHUNK_US)
# local runner us/step under the registered schedule (percentile rule), per machine and family; ours = max over {power off, I7+I10}
LOCAL_RUNNER_US = {
    "ours": {"maxcut": 291.7, "maxsat": 186.7, "colouring": 100.9},
    "b1": {"maxcut": 1150.0, "maxsat": 401.9, "colouring": 131.5},
    "b3": {"maxcut": 89.6, "maxsat": 80.2, "colouring": 60.2},
}
LOCAL_RUNNER_PERT_US = {          # with the H5 field wrapper and the noisy restart unit
    "ours": {"maxcut": 397.9, "maxsat": 259.5, "colouring": 463.0},
    "b1": {"maxcut": 2631.2, "maxsat": 811.2, "colouring": 207.4},
}
B2_US_PER_PROPOSAL = 5.0                                # PLACEHOLDER (<= 4.6 us in the chunk, rounded up); Stage 0 s0_time_b2 measures it, re-budget from sim/out/hw/time_chunk/b2_proposal.json
B1BS_OVER_B1 = 0.77 / 0.73                              # bit-sliced / native, smoke rows (not timed at 800 spins)
FAMILY_SPINS = {"maxcut": (800, 1024), "maxsat": (316, 512), "colouring": (36, 64),
                "col3p": (120, 128), "col4p": (120, 128)}                              # spins, padded lanes (col*: H6)


def us_per_step(machine: str, family: str, perturbed: bool = False) -> float:
    m = "b1" if machine == "b1bs" else machine
    table = LOCAL_RUNNER_PERT_US if perturbed and m in LOCAL_RUNNER_PERT_US else LOCAL_RUNNER_US
    return table[m][family] * CLOUD_OVER_LOCAL * (B1BS_OVER_B1 if machine == "b1bs" else 1.0)


def seconds_per_run(machine: str, family: str, sweeps: float = SWEEPS, perturbed: bool = False) -> float:
    if machine == "b2":                                  # sweeps = proposals here
        return 0.3 + sweeps * (B2_PERT_US_PER_PROPOSAL if perturbed else B2_US_PER_PROPOSAL) * 1e-6
    return sweeps * FAMILY_SPINS[family][0] * us_per_step(machine, family, perturbed) * 1e-6


@dataclass
class Spec:
    """Everything one simulated run needs. Serialised into the record (the record is self-describing)."""
    study: str                   # h2 | h3 | h5 | ref
    phase: str                   # tune | test | ref | h3 | h5
    family: str
    instance: str
    r: int                       # seed index
    arm: str                     # Arm.key
    cfg: dict = field(default_factory=dict)   # Config.as_dict()
    sweeps: float = SWEEPS
    verify_l0: bool = True
    sigma_mult: float = 0.0
    adc_delta: int = 0
    pert: dict | None = None     # Perturb.as_dict()
    proposals: int = 0           # B2 only
    inst_index: int = 0
    tag: int = 0                 # seed stream tag (ref set uses its own stream)
