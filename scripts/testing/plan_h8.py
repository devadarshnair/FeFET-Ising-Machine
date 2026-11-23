"""H8 full design (prereg/hw/H8_full.md, DRAFT until frozen by commit) as data. One source for gen_jobs_h8.py, run_h8.py and
evaluate_h8.py. Nothing here imports a machine model (the cost-per-run model is plain arithmetic on measured seconds).

Question: apples to apples, where does each machine win and how far does that scale? Machines (hardware-priced): ours (Kc2 + I11, none),
B1 (best parallel-trial arm), B3 (Fujitsu DA v2), the fairness arm ours.kc2c (pending hook). Every analog machine runs with its CHOSEN
variation mitigation (VARIATION_V2 4c) at nominal variation, and on the ideal device. Primary pricing: measured_v2 (L3_v2) + mitigation
overheads (variation_v2.mitigation_cost) charged per run.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

SEED_TAG = 9                         # Spec.tag of every H8 run: disjoint from Stage 2 (0), 3 (6), 4 (7), VARIATION_V2 (8)
INST_BASE = 500                      # inst_index = 500 + position in the instance's family list (H7 used 300+, VARIATION_V2 400+)
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TUNED_S2 = "docs/hw/results/stage2_eval/tuned.json"
TUNED_BV2 = "docs/hw/results/baselines_v2/tuned.json"
OUT = "sim/out/hw/h8"
NOMINAL_K = 1.0                      # design point: all stochastic variation terms at x1 (VARIATION_V2 nominal)
C2C_DEFAULT = 0.5

# ---------------------------------------------------------------------------------------------------------- instances (fresh)
# Planted seeds: never used before (Stage 2 TEST 301-310, TUNE 401-404, H6 501-525 / 601-604 / 701-704, Stage 4 801-910, tune 851/951, VARIATION_V2 501-503 / 801-803).
PLANTED_SEED0 = {3: 1101, 4: 1201}                                   # p3 -> 1101.., p4 -> 1201..
# G-set graphs used by ANY earlier stage: Stage 2 (G1-5 G11-15 test, G6 G7 G16 G18 tune), Stage 3 / H6 (G8 G10 G17 G19 G21 test, G9 G20 tune), the
# P4.02 B1 calibration (G1-G17, G22-G26, G43-G47, G48-G50) and P4_v2 R1x (G48-G50). All 800-node graphs and G22-26 / G43-47 are therefore NOT fresh.
# Never used anywhere: G27-G42 (2000 nodes) and G51-G54 (1000 nodes, planar unit). tests/hw/test_h8.py recomputes this against every plan module.
G_CORE_1000 = ("G51", "G52", "G53", "G54")                           # 1000 nodes (1024 lanes), unweighted planar
G_FULL_2000 = ("G27", "G28", "G29", "G30", "G31")                    # 2000 nodes (2048 lanes, extrapolated pricing), +-1 random
SIZES_CORE = (120, 240, 480, 960)
SIZE_FULL = 2040
GRAPHS_CORE = ("myciel4", "myciel5", "myciel6", "queen5_5", "queen6_6", "queen7_7", "queen8_8", "queen9_9", "kneser7_2", "kneser8_3", "kneser9_3")
GRAPHS_FULL = ("myciel7", "queen10_10", "kneser10_3", "kneser10_4")

# (instances, seeds) per size: core / extra seeds+instances added by the full tier. Chosen with power_table() and the Rs cap, see POWER.
INST_SEEDS = {   # size -> {tier: (n_instances, n_seeds)}
    120: {"core": (40, 8), "full": (48, 10)},
    240: {"core": (36, 6), "full": (44, 8)},
    480: {"core": (18, 5), "full": (24, 6)},
    960: {"core": (10, 4), "full": (14, 5)},
    2040: {"core": (0, 0), "full": (4, 2)},
}
GRAPH_SEEDS = {"core": 8, "full": 12}
MAXCUT = {"G1000": {"insts": G_CORE_1000, "core": (4, 6), "full": (4, 8)}, "G2000": {"insts": G_FULL_2000, "core": (0, 0), "full": (5, 2)}}
SWEEPS = 150


def planted_family(k: int, size: int) -> str:
    return f"p{k}n{size}"


def planted_instances(k: int, size: int, tier: str = "full") -> list[str]:
    n = INST_SEEDS[size][tier][0]
    return [str(PLANTED_SEED0[k] + i) for i in range(n)]


def sweeps_of(family: str, inst: str | None = None, spins: int | None = None) -> int:
    """Budget scales with N at the H7 per-spin rate: sweeps = max(150, 150 x spins / 240), capped at 600 (a 2040-spin run at 1275 sweeps
    would exceed the 60 min job limit for B1; the cap is applied equally to every machine and stated in the prereg)."""
    if family == "maxcut":
        return SWEEPS
    assert spins is not None
    return min(600, max(SWEEPS, round(SWEEPS * spins / 240)))


# ---------------------------------------------------------------------------------------------------------- arms
@dataclass(frozen=True)
class H8Arm:
    label: str
    arm: str                  # Spec.arm
    cfg: str                  # s2:<key> (Stage 2 tuned.json, per family kind) | bv2:<key> (baselines_v2 tuned.json) | kc2c (pending hook)
    mit: str                  # chosen mitigation at nominal ("none" = digital / nothing)
    machine: str              # ours | b1 | b3 | b1y
    role: str = "main"        # main | ladder | context


ARMS = {a.label: a for a in (
    H8Arm("ours_kc2_i11", "ours.kc2.fs.i11", "s2:ours.kc2.i10.i11", "wv+diff+cal", "ours"),
    H8Arm("ours_none", "ours.none.fs", "s2:ours.none.i10", "wv+diff+cal", "ours"),
    H8Arm("B1_best", "b1.none.fs", "s2:b1.none", "wv+cal", "b1"),
    H8Arm("B3_v2", "b3.b3v2", "bv2:b3.b3v2", "none", "b3"),
    H8Arm("ours_kc2c", "ours.kc2.fs", "kc2c", "wv+diff+cal", "ours"),        # fairness arm, hook (see KC2C_PENDING)
    H8Arm("B1_yin_sa", "b1y.sa", "bv2:b1y.sa", "none", "b1y", "context"),
    # ablation ladder (D3): restart arms and power tweaks of ours, all at the fs ADC, all with the chosen mitigation stack
    H8Arm("L_none", "ours.none.fs", "s2:ours.none.i10", "wv+diff+cal", "ours", "ladder"),
    H8Arm("L_da", "ours.da_offset.fs", "s2:ours.da_offset.i10", "wv+diff+cal", "ours", "ladder"),
    H8Arm("L_mesa", "ours.mesa.fs", "s2:ours.mesa.i10", "wv+diff+cal", "ours", "ladder"),
    H8Arm("L_kc2", "ours.kc2.fs", "s2:ours.kc2.i10", "wv+diff+cal", "ours", "ladder"),
    H8Arm("L_kc2_i11", "ours.kc2.fs.i11", "s2:ours.kc2.i10.i11", "wv+diff+cal", "ours", "ladder"),
    H8Arm("L_kc2_i7v2_i11", "ours.kc2.i7v2.i11", "s2:ours.kc2.i10.i11", "wv+diff+cal", "ours", "ladder"),
    H8Arm("L_kc2_i7v2i10_i11", "ours.kc2.i7v2i10.i11", "s2:ours.kc2.i10.i11", "wv+diff+cal", "ours", "ladder"),
    H8Arm("L_kc2_i11_i5", "ours.kc2.fs.i5_h4g4", "s2:ours.kc2.i10", "wv+diff+cal", "ours", "ladder"),
)}
MAIN_ARMS = ("ours_kc2_i11", "ours_none", "B1_best", "B3_v2", "ours_kc2c")
LADDER_ARMS = tuple(a for a, v in ARMS.items() if v.role == "ladder")
KC2C_PENDING = "docs/hw/results/baselines_v2/tuned.json -> tuned.<colouring|maxcut>['ours.kc2.i10'] with cid kc2c_* and tfinal (the retune_v2 select output)"
# B2 (HyCiM) is QKP-only (BASELINES_V2 3b): it has no colouring / Max-Cut formulation in this repository and is excluded, stated in the prereg.
I3_NOTE = "I3 (penalty ramp) is knapsack-only (tweaks.py): no colouring / Max-Cut arm exists; recorded as not applicable"


def _kc2c_selected(kind: str) -> dict | None:
    """The retune_v2 select output stores the fairness arm under its TUNE key 'ours.kc2.i10' (retune_v2.TUNE_KEY) with cid 'kc2c_*' and a tfinal knob;
    the key 'ours.kc2c' is accepted too. A plain Stage 2 Kc2 config (no tfinal) is never taken for it."""
    p = REPO / TUNED_BV2
    if not p.exists():
        return None
    t = json.loads(p.read_text())["tuned"].get(kind, {})
    for key in ("ours.kc2c", "ours.kc2.i10"):
        c = t.get(key)
        if c and str(c.get("cid", "")).startswith("kc2c_") and "tfinal" in c:
            return c
    return None


def kc2c_cfg(kind: str) -> dict | None:
    """The tuned ours.kc2c selection once the baselines run / cloud run delivered it, else None (the run refuses). H8_KC2C_SMOKE_STUB=1
    (set only by --smoke-h8) substitutes the Stage 2 Kc2 config with tfinal 0.5 so the plumbing is smoked; such records are never data."""
    c = _kc2c_selected(kind)
    if c is None and os.environ.get("H8_KC2C_SMOKE_STUB") == "1":
        base = json.loads((REPO / TUNED_S2).read_text())["tuned"][kind]["ours.kc2.i10"]
        return {**base, "tfinal": 0.5, "cid": "smoke_stub"}
    return c


def kc2c_ready() -> bool:
    return _kc2c_selected("colouring") is not None and _kc2c_selected("maxcut") is not None


FORCE_KC2C = False      # gen_jobs_h8 --with-kc2c: emit the fairness-arm jobs before the tuned selection exists (the run then needs it at run time)


def main_arms(tier_has_kc2c: bool | None = None) -> list[str]:
    ok = (kc2c_ready() or FORCE_KC2C) if tier_has_kc2c is None else tier_has_kc2c
    return [a for a in MAIN_ARMS if a != "ours_kc2c" or ok]


# device conditions of the main grid: ideal device (no variation, no mitigation) and nominal variation with the chosen mitigation
CONDS = ("ideal", "nominal")


def conds_of(label: str) -> tuple[str, ...]:
    return ("ideal",) if ARMS[label].machine in ("b3", "b1y") else CONDS     # digital: no analog variation; Yin context: ideal only


# ---------------------------------------------------------------------------------------------------------- stress (VARIATION_V2 axes)
STRESS_FAMILIES = ("p3n240", "p4n240")
STRESS_INSTANCES, STRESS_SEEDS = 10, 6
ABL_INSTANCES, ABL_SEEDS = 10, 5                  # ablation ladder: p3n240 / p4n240 first 10 instances x 5 seeds (both conditions)
ABL_MAXCUT_INSTANCES, ABL_MAXCUT_SEEDS = 3, 4     # G1000 first 3 x 4 seeds, nominal only
STRESS_ARMS = ("ours_kc2_i11", "B1_best")
K_AXIS = (0.5, 1.5, 2.0, 3.0)                    # nominal (k = 1) is the main grid
C2C_AXIS = (0.0, 0.25, 0.75)                     # 0.5 = default = main grid; share of sigma(Vth)^2 that is cycle-to-cycle (unmeasured)
C2C_AT_K = (1.0, 2.0)
DRIFT_AXIS = (0.01, 0.02, 0.05)                  # V per decade, parametric (retention k = 0 in char_v1)
STRESS_EXTRA_MIT = {"B1_best": "wv+diff+cal+bin"}   # VARIATION_V2: B1 at k = 3 needs bit-slicing


def stress_cells(label: str) -> list[tuple[str, str, float]]:
    """(point id, mitigation, c2c share) cells of one analog machine at the stress families (nominal / chosen = main grid, not repeated)."""
    a = ARMS[label]
    cells = [("vx1", "none", C2C_DEFAULT)]                                                # nominal without mitigation
    cells += [(f"vx{k:g}", a.mit, C2C_DEFAULT) for k in K_AXIS]
    cells += [(f"vx{k:g}", STRESS_EXTRA_MIT[label], C2C_DEFAULT) for k in (3.0,) if label in STRESS_EXTRA_MIT]
    cells += [(f"vx{k:g}", a.mit, c) for k in C2C_AT_K for c in C2C_AXIS]
    cells += [(f"drift{d:g}", a.mit, C2C_DEFAULT) for d in DRIFT_AXIS]
    return cells


# ---------------------------------------------------------------------------------------------------------- software context
SW_ARMS = ("sw.dsatur", "sw.tabucol", "sw.sa")           # colouring; Max-Cut: sw.sa only (sa_qubo)
TABU_REF_IPV, TABU_REF_SEEDS = 3000, 3                   # 20x TabuCol: solvability of each instance (not a contrast)
HW_CONTRASTS = (("ours_kc2_i11", "B3_v2"), ("ours_kc2_i11", "B1_best"), ("ours_none", "B3_v2"), ("ours_kc2_i11", "ours_none"),
                ("ours_kc2c", "B3_v2"), ("ours_kc2_i11", "ours_kc2c"))


# ---------------------------------------------------------------------------------------------------------- run-time model (measured)
# us per step at 256 / 512 lanes, ideal device, from the CLOUD Stage 4 records (sim/out/hw/stage4/h7: wall_s / steps of p3n240 150 sweeps and
# p3n480 300 sweeps). b3.b3v2 from baselines_v2 test records. Power law in lanes between them, extrapolated; Max-Cut (800 spins, 1024 lanes)
# from plan.LOCAL_RUNNER_US x CLOUD_OVER_LOCAL (Stage 2 cloud timing map): maxcut is hotter than colouring (more accepted flips).
US_PER_STEP_LANES = {"ours_kc2_i11": (50.0, 70.5), "ours_none": (69.4, 95.1), "B1_best": (200.0, 361.0), "B3_v2": (41.7, 45.3)}
US_MAXCUT_1024 = {"ours": 207.0, "b1": 815.0, "b3": 63.5}   # plan.us_per_step at 1024 lanes (800 spins), cloud-mapped
MIT_FACTOR = {"ours": 1.45, "b1": 1.55, "b3": 1.0, "b1y": 1.0}  # variation_v2b wall: mitigated / unmitigated at 240 spins (4.2/3.0, 10.4/6.7)
B1Y_REL = 0.1                                               # B1_yin one-read-per-iteration kernel: no wall recorded; assumed 0.1 x B1 (re-timed by the smoke)
MARGIN = 1.3                                                # on top of the means: p95 job variance on a shared 32-vCPU box
LADDER_REL = {"L_none": "ours_none", "L_da": "ours_none", "L_mesa": "ours_none", "L_kc2": "ours_kc2_i11", "L_kc2_i11": "ours_kc2_i11",
              "L_kc2_i7v2_i11": "ours_kc2_i11", "L_kc2_i7v2i10_i11": "ours_kc2_i11", "L_kc2_i11_i5": "ours_kc2_i11"}


def lanes_of(spins_: int) -> int:
    return max(4, 1 << (spins_ - 1).bit_length())


def us_step(label: str, spins_: int, family: str) -> float:
    a = ARMS[label]
    lanes = lanes_of(spins_)
    if label.startswith("L_"):
        label = LADDER_REL[label]
        a = ARMS[label]
    if a.machine == "b1y":
        return B1Y_REL * us_step("B1_best", spins_, family)
    if family == "maxcut":
        m = "ours" if a.machine == "ours" else a.machine
        return US_MAXCUT_1024[m] * (lanes / 1024.0) ** 0.5
    k = a.label if a.label in US_PER_STEP_LANES else {"ours_kc2c": "ours_kc2_i11"}[a.label]
    u256, u512 = US_PER_STEP_LANES[k]
    expo = math.log(u512 / u256) / math.log(2.0)
    return u256 * (lanes / 256.0) ** expo


def s_per_run(label: str, family: str, spins_: int, sweeps: int, cond: str) -> float:
    a = ARMS[label]
    base = us_step(label, spins_, family) * sweeps * spins_ * 1e-6
    f = MIT_FACTOR[a.machine] if (cond != "ideal" and a.mit != "none") else (1.0 if cond == "ideal" else 1.0)
    return base * f * MARGIN


# ---------------------------------------------------------------------------------------------------------- power analysis
def primary_family_size(tier: str) -> int:
    """Number of primary contrasts (2 per family cell: ours_kc2_i11 vs B3_v2 and vs B1_best, nominal condition) = the size of the global Holm family."""
    n = sum(1 for tt in INST_SEEDS.values() if tt[tier][0] > 0) * 2 + 1 + sum(1 for v in MAXCUT.values() if v[tier][0] > 0)
    return 2 * n


def power_diff(p1: float, p2: float, n_inst: int, n_seed: int, rho: float = 0.25, r_arms: float = 0.5, alpha: float = 0.05,
               m: int = 20) -> float:
    """Normal-approximation power of the paired difference of mean success between two arms on the same instances, Bonferroni-worst-case alpha
    / m (m = the global Holm family of the tier, primary_family_size). Power refers to the SUCCESS difference; the verdict test is the ETS99 bootstrap p. Per-instance success rates have intra-instance correlation rho (estimated 0.0-0.25 from Stage 4, the top is used); the instance
    effects of two arms correlate at r_arms. var(d_i) = tau^2 + w / S with tau^2 = 2 rho pbar(1-pbar)(1 - r_arms), w = sum_a p_a(1-p_a)(1-rho)."""
    from statistics import NormalDist
    nd = NormalDist()
    pb = 0.5 * (p1 + p2)
    tau2 = 2 * rho * pb * (1 - pb) * (1 - r_arms)
    w = (p1 * (1 - p1) + p2 * (1 - p2)) * (1 - rho)
    se = math.sqrt((tau2 + w / max(n_seed, 1)) / max(n_inst, 1))
    z = nd.inv_cdf(1 - alpha / (2 * m))
    return 1 - nd.cdf(z - abs(p1 - p2) / se) if se > 0 else 1.0


def mde(n_inst: int, n_seed: int, p: float = 0.5, power: float = 0.8, **kw) -> float:
    """Smallest success difference around p (p -/+ d/2) detected with the stated power."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        d = 0.5 * (lo + hi)
        ok = power_diff(max(0.0, p - d / 2), min(1.0, p + d / 2), n_inst, n_seed, **kw) >= power
        lo, hi = (lo, d) if ok else (d, hi)
    return hi


def power_table() -> list[dict]:
    return [{"size": s, "tier": t, "instances": n, "seeds": k, "m": primary_family_size(t), "mde_success_diff": round(mde(n, k, m=primary_family_size(t)), 3)}
            for s, tt in INST_SEEDS.items() for t, (n, k) in tt.items() if n]
