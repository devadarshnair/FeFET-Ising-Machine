"""Stage 2 (prereg/hw/S2_confirmatory_DRAFT.md section 3) instance set and its exclusion check against every earlier stage, by
CONTENT (graph hash), not only by key / seed tag. Used by tests/hw/test_s2_disjoint.py, which is a Stage 2 go-gate test (S2_GATE_TESTS).

Stage 2: tag 11; planted p3 keys 2301.., p4 keys 2401..; 64 instances at 480 spins, 16 at 240 spins."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

S2_TAG = 11
S2_SEED0 = {3: 2301, 4: 2401}
S2_COUNTS = {480: 64, 240: 16}     # ETS power: 64 instances x 3 seeds at 480 (internal review item 11.2.1); 16 x 3 at 240 (report-only)
S2_CELLS = ("p3n480", "p4n480", "p3n240", "p4n240")
S2_GATE_TESTS = ("tests/hw/test_s2_disjoint.py",)       # the S2 go script must run these and refuse to launch on any failure
EARLIER_TAGS = (0, 6, 7, 8, 9, 10)                      # Stage 2 (old), H6, H7, VARIATION_V2, H8, Stage 0/1/1b tuning
STAGE01_KEYS = {3: [str(2101 + i) for i in range(12)], 4: [str(2201 + i) for i in range(12)]}   # gen_jobs_s1.KEYS, s1b_retune.KEYS ⊂


def s2_instances() -> dict[str, list[str]]:
    out = {}
    for cell in S2_CELLS:
        k, size = int(cell[1]), int(cell.split("n")[1])
        out[cell] = [str(S2_SEED0[k] + i) for i in range(S2_COUNTS[size])]
    return out


def content_hash(prob) -> str:
    """SHA-256 of (vertices, colours, sorted undirected edge set): equal hash = the same colouring instance."""
    E = sorted(tuple(sorted((int(a), int(b)))) for a, b in prob.edges)
    return hashlib.sha256(repr((int(prob.n), int(prob.k), E)).encode()).hexdigest()


def earlier_instances() -> dict[str, set]:
    """(family, key) of every colouring instance any earlier stage generated, grouped by generator family."""
    import h6_instances as h6i
    import h7_instances as h7i
    import h8_instances as h8i
    import plan_h6 as p6
    import plan_h7 as p7
    import plan_h8 as p8
    out: dict[str, set] = {}

    def add(fam, key):
        out.setdefault(fam, set()).add(str(key))
    for k in (3, 4):                                                     # H8 (tag 9), every size and tier
        for size in p8.INST_SEEDS:
            fam = f"p{k}n{size}"
            if fam in h8i.PLANTED:
                for key in p8.planted_instances(k, size, "full"):
                    add(("h8", fam), key)
        for size in (240, 480, 960):                                     # Stage 0 / 1 / 1b tuning (tag 10)
            for key in STAGE01_KEYS[k]:
                add(("h8", f"p{k}n{size}"), key)
    for fam, keys in p7.TEST_SET.items():                                # H7 test + pilot tune
        if fam in p7.PLANTED:
            for key in keys:
                add(("h7", fam), key)
    for fam in p7.PLANTED:
        add(("h7", fam), 851 if fam.startswith("p3") else 951)
    for d in (p6.TUNE_SET, p6.TEST_SET):                                 # H6
        for fam, keys in d.items():
            if fam in h6i.FAMILIES:
                for key in keys:
                    add(("h6", fam), key)
    return out


def _problem(gen: str, fam: str, key: str):
    import h6_instances as h6i
    import h7_instances as h7i
    import h8_instances as h8i
    return {"h8": h8i.problem, "h7": h7i.problem, "h6": h6i.problem}[gen](fam, key)


def earlier_hashes() -> set[str]:
    return {content_hash(_problem(g, f, k)) for (g, f), keys in earlier_instances().items() for k in keys}


def earlier_seeds() -> set[int]:
    return {int(k) for keys in earlier_instances().values() for k in keys if str(k).isdigit()}


def s2_hashes() -> dict[tuple[str, str], str]:
    import h8_instances as h8i
    return {(c, k): content_hash(h8i.problem(c, k)) for c, ks in s2_instances().items() for k in ks}
