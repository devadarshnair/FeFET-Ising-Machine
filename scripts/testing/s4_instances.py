"""Stage C instance sets (prereg/hw/SC_confirmatory_DRAFT.md section 3) and their exclusion check against every earlier stage, by graph CONTENT, seed and tag.
Confirmatory tag 13: planted p3n480 keys 4301-4428 (128), p4n480 keys 4501-4692 (192), p4n120 keys 4701-4740 (40). Fresh TUNING sets (tag 10, never used before): p3n480 2501-2512, p4n480 2601-2612,
p4n120 2701-2712. The DIMACS-style generated graphs (myciel / queen / kneser) are fixed, named graphs: they are RE-USED from H8 by design (seeds only are fresh, tag 13) and are excluded from the disjointness check."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import s2_instances as s2  # noqa: E402
import s3_instances as s3  # noqa: E402

SC_TAG = 13
SC_COUNTS = {"p3n480": 128, "p4n480": 192, "p4n120": 40}
SC_GATE_TESTS = ("tests/hw/test_s4_disjoint.py",)
SC_EARLIER_TAGS = s3.S3_EARLIER_TAGS + (12,)
TUNING_KEYS_C = {"p3n480": [str(2501 + i) for i in range(12)], "p4n480": [str(2601 + i) for i in range(12)], "p4n120": [str(2701 + i) for i in range(12)]}
DIMACS_CORE = ["myciel4", "myciel5", "myciel6", "queen5_5", "queen6_6", "queen7_7", "queen8_8", "queen9_9", "kneser7_2", "kneser8_3", "kneser9_3"]


def sc_instances() -> dict[str, list[str]]:
    return {"p3n480": [str(4301 + i) for i in range(128)], "p4n480": [str(4501 + i) for i in range(192)], "p4n120": [str(4701 + i) for i in range(40)]}


def sc_hashes() -> dict[tuple[str, str], str]:
    import h8_instances as h8i
    return {(c, k): s2.content_hash(h8i.problem(c, k)) for c, ks in sc_instances().items() for k in ks}


def tuning_c_hashes() -> dict[tuple[str, str], str]:
    import h8_instances as h8i
    return {(c, k): s2.content_hash(h8i.problem(c, k)) for c, ks in TUNING_KEYS_C.items() for k in ks}


def earlier_all_hashes() -> set[str]:
    """Everything earlier: H6/H7/H8, Stage 0-3.1 tuning, Stage 2 (tag 11) and Stage 3.2 (tag 12) sets."""
    import h8_instances as h8i
    out = s2.earlier_hashes() | s3.s2_set_hashes() | s3.tuning_hashes() | set(s3.s3_planted_hashes().values())
    for c, ks in (("p4n120", [str(1201 + i) for i in range(40)]),):          # H8 p4n120 (already in earlier_hashes via H8 pools; kept explicit)
        out |= {s2.content_hash(h8i.problem(c, k)) for k in ks}
    return out
