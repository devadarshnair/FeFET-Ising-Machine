"""Stage 3.2 instance set (prereg/hw/S3_confirmatory_DRAFT.md section 3) and its exclusion check against every earlier stage, by graph CONTENT, seed and tag.
Tag 12; planted p3 keys 3301.. (480 and 960 spins), p4 keys 3401.. (480 spins), Max-Cut fresh random graphs R6001-R6020. Used by tests/hw/test_s3_disjoint.py (a Stage 3.2 go-gate test, S3_GATE_TESTS)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import s2_instances as s2  # noqa: E402

S3_TAG = 12
S3_COUNTS = {"p3n480": 64, "p4n480": 64, "p3n960": 64, "maxcut": 20}
S3_GATE_TESTS = ("tests/hw/test_s3_disjoint.py",)
S3_EARLIER_TAGS = s2.EARLIER_TAGS + (11,)
TUNING_KEYS = {3: [str(2101 + i) for i in range(12)], 4: [str(2201 + i) for i in range(12)]}
TUNING_MC = [f"R{5001 + i}" for i in range(5)]


def s3_instances() -> dict[str, list[str]]:
    out = {"p3n480": [str(3301 + i) for i in range(64)], "p4n480": [str(3401 + i) for i in range(64)], "p3n960": [str(3301 + i) for i in range(64)],
           "maxcut": [f"R{6001 + i}" for i in range(20)]}
    return out


def s3_planted_hashes() -> dict[tuple[str, str], str]:
    import h8_instances as h8i
    return {(c, k): s2.content_hash(h8i.problem(c, k)) for c, ks in s3_instances().items() if c != "maxcut" for k in ks}


def s2_set_hashes() -> set[str]:
    return set(s2.s2_hashes().values())


def tuning_hashes() -> set[str]:
    import h8_instances as h8i
    out = set()
    for k in (3, 4):
        for size in ((480, 960) if k == 3 else (240, 480, 960)):
            for key in TUNING_KEYS[k]:
                out.add(s2.content_hash(h8i.problem(f"p{k}n{size}", key)))
    return out


def mc_hash(key: str) -> str:
    import hashlib
    import mc_fresh
    g = mc_fresh.graph(key)
    E = sorted(tuple(sorted((int(a), int(b)))) for a, b in g.edges)
    return hashlib.sha256(repr((int(g.n), E)).encode()).hexdigest()
