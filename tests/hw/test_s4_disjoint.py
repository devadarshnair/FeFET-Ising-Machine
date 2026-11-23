"""Stage C go-gate test: tag-13 planted instances and the fresh tuning sets are disjoint from every earlier set (H6/H7/H8, Stage 0-3.1 tuning, Stage 2 tag 11, Stage 3.2 tag 12)
by graph content, seed and tag, and from each other; DIMACS-style graphs are declared re-used (named graphs), seeds only fresh."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in ("scripts/testing", "scripts/golden", "scripts/baselines"):
    sys.path.insert(0, str(REPO / p))
sys.path.insert(0, str(REPO))

import s2_instances as s2  # noqa: E402
import s3_instances as s3  # noqa: E402
import s4_instances as s4  # noqa: E402


def test_counts_and_keys():
    ins = s4.sc_instances()
    assert {c: len(v) for c, v in ins.items()} == s4.SC_COUNTS
    assert ins["p3n480"][0] == "4301" and ins["p4n480"][0] == "4501" and ins["p4n120"][0] == "4701"


def test_confirmatory_and_tuning_contents_fresh_and_distinct():
    old = s4.earlier_all_hashes()
    new, tune = s4.sc_hashes(), s4.tuning_c_hashes()
    assert not [k for k, h in new.items() if h in old], "confirmatory clash"
    assert not [k for k, h in tune.items() if h in old], "tuning clash"
    assert not set(new.values()) & set(tune.values())
    assert len(set(new.values())) == len(new) and len(set(tune.values())) == len(tune)


def test_seeds_and_tag_fresh():
    seeds = {int(k) for v in s4.sc_instances().values() for k in v} | {int(k) for v in s4.TUNING_KEYS_C.values() for k in v}
    used = s2.earlier_seeds() | {int(k) for v in s3.s3_instances().values() for k in v if str(k).isdigit()} | {int(k) for v in s3.TUNING_KEYS.values() for k in v}
    used |= {int(k) for c in ("p3n480", "p4n480") for k in s2.s2_instances()[c]}
    assert not seeds & used
    assert s4.SC_TAG not in s4.SC_EARLIER_TAGS


def test_dimacs_core_names_exist():
    import h8_instances as h8i
    assert all(g in h8i.GRAPHS for g in s4.DIMACS_CORE)
