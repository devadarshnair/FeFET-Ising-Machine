"""Stage 2 go-gate test (internal review section 11, item 3): the tag-11 instances are disjoint from every earlier stage
(H6, H7, H8, Stage 0/1/1b tuning and calibration) by graph content, by planted seed and by seed-stream tag."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import s2_instances as s2  # noqa: E402


def test_s2_instance_counts_match_the_draft():
    ins = s2.s2_instances()
    assert {c: len(v) for c, v in ins.items()} == {"p3n480": 64, "p4n480": 64, "p3n240": 16, "p4n240": 16}
    assert ins["p3n480"][0] == "2301" and ins["p4n480"][0] == "2401"


def test_earlier_pool_is_real():
    pool = s2.earlier_instances()
    assert "1101" in pool[("h8", "p3n480")] and "2112" in pool[("h8", "p3n480")] and "2212" in pool[("h8", "p4n960")]
    assert any(g == "h7" for g, _ in pool) and any(g == "h6" for g, _ in pool)
    assert len(s2.earlier_hashes()) > 400


def test_s2_contents_are_disjoint_from_every_earlier_instance():
    old = s2.earlier_hashes()
    new = s2.s2_hashes()
    clash = [k for k, h in new.items() if h in old]
    assert not clash, clash
    assert len(set(new.values())) == len(new)                         # no duplicate inside Stage 2 either


def test_s2_seeds_and_tag_are_fresh():
    seeds = {int(k) for v in s2.s2_instances().values() for k in v}
    assert not seeds & s2.earlier_seeds()
    assert s2.S2_TAG not in s2.EARLIER_TAGS


def test_content_hash_detects_a_reused_instance():
    import h8_instances as h8i
    assert s2.content_hash(h8i.problem("p3n480", "2101")) in s2.earlier_hashes()     # a tuning instance is caught
