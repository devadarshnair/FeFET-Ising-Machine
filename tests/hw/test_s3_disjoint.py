"""Stage 3.2 go-gate test: the tag-12 instances are disjoint from every earlier stage (H6, H7, H8, Stage 0/1/1b/3.0/3.1 tuning, Stage 2 tag 11) by graph content,
by planted seed and by seed-stream tag; the Max-Cut graphs are disjoint from the tuning graphs and from each other, and have a built reference."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import s2_instances as s2  # noqa: E402
import s3_instances as s3  # noqa: E402


def test_counts_and_keys():
    ins = s3.s3_instances()
    assert {c: len(v) for c, v in ins.items()} == s3.S3_COUNTS
    assert ins["p3n480"][0] == "3301" and ins["p4n480"][0] == "3401" and ins["maxcut"][0] == "R6001"


def test_planted_contents_disjoint_from_every_earlier_set():
    old = s2.earlier_hashes() | s3.s2_set_hashes() | s3.tuning_hashes()
    new = s3.s3_planted_hashes()
    clash = [k for k, h in new.items() if h in old]
    assert not clash, clash
    assert len(set(new.values())) == len(new)


def test_seeds_and_tag_are_fresh():
    seeds = {int(k) for c, v in s3.s3_instances().items() if c != "maxcut" for k in v}
    used = s2.earlier_seeds() | {int(k) for k in s2.s2_instances()["p3n480"]} | {int(k) for k in s2.s2_instances()["p4n480"]} | {int(k) for v in s3.TUNING_KEYS.values() for k in v}
    assert not seeds & used
    assert s3.S3_TAG not in s3.S3_EARLIER_TAGS


def test_maxcut_graphs_fresh_distinct_and_referenced():
    import mc_fresh
    new = {k: s3.mc_hash(k) for k in s3.s3_instances()["maxcut"]}
    tune = {s3.mc_hash(k) for k in s3.TUNING_MC}
    assert not set(new.values()) & tune
    assert len(set(new.values())) == len(new)
    assert all(mc_fresh.reference(k) for k in new)
