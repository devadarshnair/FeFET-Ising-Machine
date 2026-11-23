"""H7 scale-up design (prereg/hw/H7_scaleup.md, DRAFT) as data: colouring families at 240/480/960 spins + DIMACS-construction
graphs, fresh seed stream, hardware arms with the full-scale ADC as the default for every machine, published software references,
variation at the confirmed design point. One source for gen_jobs_stage4.py, run_cell.py (--h7-cfg) and evaluate_h7.py.
Nothing here imports a machine model."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import plan as pl

SEED_TAG = 7                     # Spec.tag of every H7 run: a seed stream disjoint from Stage 2 (0) and Stage 3 (6)
INST_BASE = 300                  # inst_index = 300 + position in the TEST list
SWEEPS = pl.SWEEPS               # 150, as Stages 2-3 (the scale question is asked at a fixed per-spin budget)
TUNED_STAGE2 = "docs/hw/results/stage2_eval/tuned.json"   # Stage 2 colouring selections; no re-tuning in H7
EPOCH_SWEEPS, B1_MESA_EPOCH_KNOB = 10, 10.0                 # B1_mesa_epoch exactly as Stage 3 (H6 amendment 1: K = 1 epoch)

AMENDMENT1 = Path(__file__).resolve().parents[2] / "prereg" / "hw" / "H7_amendment1.md"


def stage4_sizes() -> tuple[int, ...]:
    """Sizes run in Stage 4: the STAGE4_SIZES line of prereg/hw/H7_amendment1.md (960 dropped for budget), else all three."""
    m = re.search(r"^STAGE4_SIZES:\s*([\d,\s]+)$", AMENDMENT1.read_text(), re.M) if AMENDMENT1.exists() else None
    return tuple(int(x) for x in m.group(1).split(",")) if m else (240, 480, 960)


SIZES = stage4_sizes()
PLANTED = {                                   # family -> (n vertices, k colours, expected degree); H6 degrees, larger n
    "p3n240": (80, 3, 4.5), "p3n480": (160, 3, 4.5), "p3n960": (320, 3, 4.5),
    "p4n240": (60, 4, 8.0), "p4n480": (120, 4, 8.0), "p4n960": (240, 4, 8.0),
}
# DIMACS name -> (vertices, unique edges, chromatic number). DIMACS .col headers list queen edges twice (queen5_5 "p edge 25 320").
DIMACS = {"myciel4": (23, 71, 5), "myciel5": (47, 236, 6), "myciel6": (95, 755, 7),
          "queen5_5": (25, 160, 5), "queen6_6": (36, 290, 7), "queen7_7": (49, 476, 7), "queen8_8": (64, 728, 9)}
FAMILIES = tuple(f for f in PLANTED if int(f.split("n")[1]) in SIZES) + ("dimacs",)
# Budget scales with N (pilot 16 Nov IST on TUNE-only instances p3 851 / p4 951, never in TEST: at 480 spins and 150 sweeps neither
# ours Kc2+I11 nor B1 reached a proper 3-colouring; see prereg section 3). Sweeps per spin = 150 x N / 240; seeds and instances are
# trimmed with N to stay inside the Rs 150 cap (power stated in the prereg, section 6).
SWEEPS_BY_SIZE = {240: 150, 480: 300, 960: 600}
SEEDS_BY_SIZE = {240: 10, 480: 8, 960: 6}
INSTANCES_BY_SIZE = {240: 10, 480: 10, 960: 5}
TEST_SET = {f: [str(s) for s in range(801 if f.startswith("p3") else 901,
                                      (801 if f.startswith("p3") else 901) + INSTANCES_BY_SIZE[int(f.split("n")[1])])]
            for f in PLANTED}


def spins(family: str, inst: str) -> int:
    n, k = (PLANTED[family][:2]) if family in PLANTED else (DIMACS[inst][0], DIMACS[inst][2])
    return n * k
TEST_SET["dimacs"] = ["myciel4", "myciel5", "myciel6", "queen5_5", "queen6_6", "queen7_7", "queen8_8"]
TEST_SEEDS = 10                  # 240-spin planted families and dimacs


def size_of(family: str) -> int:
    return int(family.split("n")[1]) if family in PLANTED else 240


def sweeps_of(family: str, inst: str | None = None) -> int:
    """Sweeps per run. Planted: by size. DIMACS: scaled per graph, sweeps = max(150, round(150 x spins / 240)) (same per-spin budget
    rule as the planted families, floor at the Stage 2-3 budget)."""
    if family == "dimacs":
        assert inst is not None, "dimacs budgets are per graph"
        return max(SWEEPS, round(SWEEPS * spins(family, inst) / 240))
    return SWEEPS_BY_SIZE[size_of(family)]


def test_seeds(family: str) -> int:
    return SEEDS_BY_SIZE[size_of(family)]


@dataclass(frozen=True)
class H7Arm:
    label: str
    arm: str
    cfg: str                      # tuned:<Stage 2 colouring key> | b1mesa_epoch | sw:<json-free tag>
    kind: str = "hw"              # hw (priced) | sw (quality only)


HW_ARMS = (H7Arm("ours_kc2_i11", "ours.kc2.fs.i11", "tuned:ours.kc2.i10.i11"),
           H7Arm("ours_none", "ours.none.fs", "tuned:ours.none.i10"),
           H7Arm("B1_best", "b1.none.fs", "tuned:b1.none"),
           H7Arm("B1_mesa_epoch", "b1.mesa.fs", "b1mesa_epoch"),
           H7Arm("B3", "b3.b3", "tuned:b3.b3"))
TABU_IPV = 150                   # TabuCol iterations per vertex = the machines' sweeps (one recolouring move per vertex per sweep)
TABU_REF_IPV = 3000              # reference TabuCol (20x): solvability of each instance, not a contrast
TABU_REF_SEEDS = 3
SW_ARMS = (H7Arm("SW_dsatur", "sw.dsatur", "sw:dsatur", "sw"),
           H7Arm("SW_tabucol", "sw.tabucol", f"sw:tabucol:{TABU_IPV}", "sw"),
           H7Arm("SW_sa", "sw.sa", "sw:sa", "sw"))
SW_REF = H7Arm("SW_tabucol_ref", "sw.tabucol", f"sw:tabucol:{TABU_REF_IPV}", "sw")


def test_arms(family: str, inst: str | None = None) -> list[H7Arm]:
    """B1_mesa_epoch (0 % success on both Stage 3 colouring families) is dropped at 960 spins for cost; the comparator there is
    B1_best. Software budgets follow the family's sweeps (SA sweeps; TabuCol iterations per vertex)."""
    S = sweeps_of(family, inst) if family != "dimacs" or inst else SWEEPS     # dimacs without inst: labels only, cfg budget is a placeholder
    hw = [a for a in HW_ARMS if not (a.label == "B1_mesa_epoch" and size_of(family) == 960)]
    sw = [H7Arm(a.label, a.arm, f"sw:tabucol:{S}" if a.arm == "sw.tabucol" else a.cfg, "sw") for a in SW_ARMS]
    return hw + sw


# H7-V: variation at the confirmed design point (report-only, H5 rules): the two 240-spin planted families, first 3 instances x 10
# seeds, ours Kc2+I11 (fs, simulated so ADC clipping under noise is real) and B1_best (fs priced).
V_FAMILIES = ("p3n240", "p4n240")
V_INSTANCES, V_SEEDS = 3, 10
V_POINTS = ("nominal", "dev_x0", "dev_x2", "dev_x4", "read_x2", "write_x2", "mismatch_x2", "drift_0.02", "temp_85", "combined")
V_ARMS = (HW_ARMS[0], HW_ARMS[2])


def v_points() -> list:
    return [p for p in pl.H5_POINTS if p.pid in V_POINTS]


def inst_index(family: str, inst: str) -> int:
    return INST_BASE + TEST_SET[family].index(inst)


def sw_cfg(src: str) -> dict:
    parts = src.split(":")
    return {"cid": "_".join(parts[1:]), "algo": parts[1], **({"iters_per_vertex": int(parts[2])} if len(parts) > 2 else {})}
