"""H6 follow-up design (prereg/hw/H6_followup.md) as data: fresh instances, fresh seed stream, arms, restart-threshold sweep,
H5 re-run. One source for gen_jobs_stage3.py, run_cell.py (H6 specs) and evaluate_h6.py. Nothing here imports a machine model."""
from __future__ import annotations

from dataclasses import dataclass

import plan as pl

SEED_TAG = 6                    # Spec.tag of every H6 run: mix_seed(BASE, family, inst_index, r, 6) = a fresh seed stream
INST_BASE = 200                 # inst_index of H6 instances = 200 + position in H6 TEST/TUNE lists (+50 for tune)
SWEEPS = pl.SWEEPS
TUNED_STAGE2 = "docs/hw/results/stage2_eval/tuned.json"     # Stage 2 tuning selections (tuning data only), sha256 in the prereg

FAMILIES = ("maxcut", "col3p", "col4p")
# fresh instances: never used in Stage 2 (Max-Cut Stage 2 used G1-5, G11-15 test and G6, G7, G16, G18 tune)
TUNE_SET = {"maxcut": ["G9", "G20"], "col3p": [str(s) for s in range(601, 605)], "col4p": [str(s) for s in range(701, 705)]}
TEST_SET = {"maxcut": ["G8", "G10", "G17", "G19", "G21"], "col3p": [str(s) for s in range(501, 516)],
            "col4p": [str(s) for s in range(511, 526)]}
TEST_SEEDS = {"maxcut": 20, "col3p": 10, "col4p": 10}
TUNE_SEEDS = 8                  # amendment 1: widened from 4 (the tuning split is thin; the TEST contrast stays confirmatory)
L3_SWEEPS = (300, 600)          # L3 budget sweep for ours kc2+I11 (150 = the main arm)

# restart-threshold sweep (author request): K in {n/8 .. 4n}; Kc2 also kick size L in {10, 40}; MESA uses the epoch harness
K_MULTS = (0.125, 0.25, 0.5, 1.0, 2.0, 4.0)
KICK_L = (10, 40)
EPOCH_SWEEPS = 10               # P4.02a (B1 calibration attempt 2) epoch length
# H6 amendment 1: the stall rule fires after K steps without a new best, so K < the epoch (10 sweeps = 10 n steps) restarts the walk
# before it can cool. MESA-epoch K is therefore swept at 1x, 2x, 4x the epoch (K in sweeps = 10, 20, 40), replacing K_MULTS for MESA only.
MESA_K_MULTS = tuple(float(m * EPOCH_SWEEPS) for m in (1, 2, 4))
B1_MESA_EPOCH_KNOB = MESA_K_MULTS[0]        # B1_mesa_epoch: K = 1 epoch (was K = n, truncated)


def sweep_configs(restart: str, cfg_base: dict) -> list[dict]:
    """Restart sweep grid around the Stage 2 tuned percentile pair of the arm."""
    out = []
    if restart == "mesa":
        return [dict(cfg_base, cid=f"mesa_ep_K{k:g}", knob=k, epoch_sweeps=EPOCH_SWEEPS) for k in MESA_K_MULTS]
    for k in K_MULTS:
        if restart == "kc2":
            for L in KICK_L:
                out.append(dict(cfg_base, cid=f"kc2_K{k:g}_L{L}", knob=k, kick_L=L))
        elif restart == "da_offset":             # equivalent knob: offset rate T_lo / div, div = 1/k scaled to the Stage 2 grid {4, 2}
            out.append(dict(cfg_base, cid=f"da_div{4 * k:g}", knob=4.0 * k))
    return out


SWEEP_ARMS = ("ours.kc2.i10", "ours.mesa.i10", "ours.da_offset.i10")
SWEEP_BASE = {"ours.kc2.i10": "ours.kc2.i10", "ours.mesa.i10": "ours.mesa.i10", "ours.da_offset.i10": "ours.da_offset.i10"}

# main test arms (sim arm key, cfg source). cfg source "tuned:<key>" = Stage 2 tuned config of that arm key for the family
# (Stage 2 colouring configs stand in for col3p/col4p); "sweep:<arm>" = the H6 restart-sweep selection; "b1mesa_epoch" = B1 MESA
# with the P4.02a epoch harness, K = 1 epoch (amendment 1; was K = n), at the Stage 2 tuned b1.mesa percentile pair.
@dataclass(frozen=True)
class H6Arm:
    label: str
    arm: str
    cfg: str
    sweeps: int = SWEEPS


def test_arms(family: str) -> list[H6Arm]:
    a = [H6Arm("ours_none", "ours.none.i10", "tuned:ours.none.i10"),
         H6Arm("ours_kc2_i11", "ours.kc2.i10.i11", "tuned:ours.kc2.i10.i11"),
         H6Arm("ours_none_i7v2", "ours.none.i7v2i10", "tuned:ours.none.i10"),
         H6Arm("ours_kc2_i11_i7v2", "ours.kc2.i7v2i10.i11", "tuned:ours.kc2.i10.i11"),
         H6Arm("ours_kc2_swept", "ours.kc2.i10", "sweep:ours.kc2.i10"),
         H6Arm("ours_mesa_swept", "ours.mesa.i10", "sweep:ours.mesa.i10"),
         H6Arm("ours_da_swept", "ours.da_offset.i10", "sweep:ours.da_offset.i10"),
         H6Arm("B1_best", "b1.none", "tuned:b1.none"),
         H6Arm("B1_mesa_epoch", "b1.mesa", "b1mesa_epoch"),
         H6Arm("B3", "b3.b3", "tuned:b3.b3")]
    if family == "maxcut":
        a += [H6Arm(f"ours_kc2_i11_S{s}", "ours.kc2.i10.i11", "tuned:ours.kc2.i10.i11", s) for s in L3_SWEEPS]
    return a


# H5 re-run: Max-Cut, first 3 H6 test instances, 10 seeds, the 18 evaluable non-duplicate H5 points; B2 on QKP kept (fresh seeds)
H5_FAMILY, H5_INSTANCES, H5_SEEDS = "maxcut", 3, 10
H5_ARMS = (H6Arm("h5_ours_none", "ours.none.off", "tuned:ours.none.i10"),
           H6Arm("h5_ours_kc2_i11", "ours.kc2.off.i11", "tuned:ours.kc2.i10.i11"),
           H6Arm("h5_ours_none_i7v2", "ours.none.i7v2", "tuned:ours.none.i10"))
# amendment 1: B1 (MESA epoch harness, K = 1 epoch) on the device-sigma and read-noise axes only (6 points) so the H5-a ratio of
# 10 %-loss points vs B1 exists for those two axes; the full 18-point B1 run (about 12 CPU-h) does not fit the budget.
H5_B1 = H6Arm("h5_b1_mesa_epoch", "b1.mesa", "b1mesa_epoch")
H5_B1_POINTS = ("nominal", "dev_x0", "dev_x2", "dev_x4", "read_x2", "read_x4")
H5_B2_INSTANCES, H5_B2_SEEDS, H5_B2_R0 = 10, 10, 100        # seeds r = 100..109: not used in Stage 2 (0..4)


def h5_points() -> list:
    return [p for p in pl.H5_POINTS if p.evaluable and p.pid not in pl.H5_DUPLICATES]


def h5_arm_points(arm: H6Arm) -> list:
    """Points of one H5 arm: all 18 evaluable ones, or the 6-point subset for B1."""
    return [p for p in h5_points() if arm != H5_B1 or p.pid in H5_B1_POINTS]


def inst_index(family: str, inst: str) -> int:
    if inst in TEST_SET.get(family, []):
        return INST_BASE + TEST_SET[family].index(inst)
    return INST_BASE + 50 + TUNE_SET[family].index(inst)


# cloud seconds per run, measured in Stage 2 (queue.log job time / runs, 32 vCPU); col*: local timing x CLOUD_OVER_LOCAL
S_PER_RUN = {("ours", "maxcut"): 18.2, ("ours_i11", "maxcut"): 15.5, ("b1", "maxcut"): 78.4, ("b3", "maxcut"): 6.9,
             ("ours_pert", "maxcut"): 26.3}
