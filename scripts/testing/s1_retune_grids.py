"""Proposal for the Stage 1 re-tune (internal review item 9.3.2). The job list and the registered grid file
(prereg/hw/S1_tuning_grids.json); this module only fixes what each arm can be given so that every label is a distinct,
behaviour-changing configuration, and checks it.

Why the old grids were short: on colouring |dE| is integer-valued, so pct_lo 5 / 10 (and pct_hi 85 / 90) give the same temperatures.
The temperature knobs are now continuous multipliers of the (90, 5) percentile temperatures (machines.scaled_temps), the same rule
for every annealing arm. Grids are widened past each Stage 1 winner that sat on an edge (STAGE1_RESULTS section 1):
- ours_kc2_i11: K = 0.5n won on both cells (edge) -> K in {0.25, 0.5, 1}; c = 0.08 won on gk (edge) -> c up to 0.16.
- B3_v2: p90 (top) and knob 0.5 (coldest end, about 0.17 T_end on p3) won -> T_start x {1, 1.5, 2.5}, T_final x {1/16 .. 1/2}.
- ours_none / B1: p90 and schedule fraction 0.5 (edge) won -> T_start x {1, 2}, T_end x {0.25, 0.5, 1}, fraction {0.25, 0.5}.
- ours_kc2c: tfinal 0.5 (coldest, about 0.17 T_end on p3) and c = 0.04 (top) won -> T_end x {0.1, 0.25}, K {0.5, 1, 2}, c {0.04, 0.08}.
"""
from __future__ import annotations

import itertools

BASE = {"pct_hi": 90, "pct_lo": 5}


def _grid(**axes) -> list[dict]:
    keys = list(axes)
    return [{**BASE, **dict(zip(keys, v))} for v in itertools.product(*axes.values())]


GRIDS = {
    "ours_kc2_i11": [{"kick_c": c, "knob": k} for c in (0, 0.04, 0.08, 0.16) for k in (0.25, 0.5, 1)],
    "B3_v2": _grid(knob=[1.0], t_hi_mult=[1.0, 1.5, 2.5], t_lo_mult=[0.0625, 0.125, 0.25, 0.5]),
    "ours_none": _grid(knob=[0.25, 0.5], t_hi_mult=[1.0, 2.0], t_lo_mult=[0.25, 0.5, 1.0]),
    "ours_kc2c": _grid(tfinal=[1.0], t_lo_mult=[0.1, 0.25], knob=[0.5, 1, 2], kick_c=[0.04, 0.08]),
}
