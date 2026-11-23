"""Stage 1b local re-tune (internal review item 9.3.2): every arm gets 12 DISTINCT configurations from s1_retune_grids.GRIDS (continuous temperature
multipliers; edges widened for all arms including ours), the same tag-10 instances (p3n480 keys 2101-2108) and seeds 0-2, ideal device, full records saved for ETS.
Plans one job per configuration; the runner is jobs run sequentially through local job queue (one heavy job at a time, <1 h each).
usage: s1b_retune.py [--cell p4n480] plan JOBS.tsv | check | select DIR OUT.json
P4-1: --cell p4n480 tunes p4 on its own tag-10 tuning keys 2201-2208 (same grids, seeds, rule); default p3n480 (the Stage 1b run)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import s1_retune_grids as g  # noqa: E402

LABEL = {"ours_kc2_i11": ("ours", "ours_kc2_i11"), "B3_v2": ("B3", "B3_v2"), "ours_none": ("none_B1", "ours_none"), "ours_kc2c": ("kc2c", "ours_kc2c")}
CELL = "p3n480"
KEYS_BY_CELL = {"p3n480": [str(2101 + i) for i in range(8)], "p4n480": [str(2201 + i) for i in range(8)]}
KEYS = KEYS_BY_CELL[CELL]
SEEDS = 3
PROBE_ON = False
OUT = "sim/out/hw/s1b"
EXTRA = {   # reference rows (not selectable): registered / H8 configurations for the energy comparison
    "ours_ref_H8": ("ours", "ours_kc2_i11", {"kick_c": 0, "knob": 2}),
    "B3_ref_H8": ("B3", "B3_v2", {"pct_hi": 90, "pct_lo": 5, "knob": 0.5}),
}


# Edge probe (same rule for every arm whose winner sat on a grid edge): 4 extra configurations beyond the edge, same instances / seeds.
PROBE = {
    "ours_kc2_i11": [{"kick_c": c, "knob": k} for c in (0, 0.04) for k in (0.125, 0.0625)],
    "B3_v2": [{**g.BASE, "knob": 1.0, "t_hi_mult": h, "t_lo_mult": l} for h in (1.5, 2.0) for l in (0.03125, 0.015625)],
    "ours_none": [{**g.BASE, "knob": 0.5, "t_hi_mult": h, "t_lo_mult": l} for h in (3.0, 4.0) for l in (0.5, 1.0)],
    "ours_kc2c": [{**g.BASE, "tfinal": 1.0, "t_lo_mult": 0.25, "knob": k, "kick_c": c} for c in (0.12, 0.16) for k in (1, 0.5)],
}


def cid_of(cfg: dict) -> str:
    skip = {"pct_hi", "pct_lo"}
    return "_".join(f"{k}{v:g}" if isinstance(v, (int, float)) else f"{k}{v}" for k, v in cfg.items() if k not in skip or (k == "pct_hi" and cfg.get("pct_hi") != 90))


def rows():
    out = []
    for label, cfgs in g.GRIDS.items():
        arm, lab = LABEL[label]
        for i, c in enumerate(cfgs):
            out.append((f"s1b.{arm}.g{i:02d}", arm, lab, cid_of(c), c, False))
    if PROBE_ON:
        out = []
        for label, cfgs in PROBE.items():
            arm, lab = LABEL[label]
            for i, c in enumerate(cfgs):
                out.append((f"s1b.probe.{arm}.p{i:02d}", arm, lab, cid_of(c), c, False))
        return out
    for name, (arm, lab, c) in EXTRA.items():
        out.append((f"s1b.{arm}.{name}", arm, lab, name, c, True))
    return out


def jid_of(r) -> str:
    return r[0] if CELL == "p3n480" else f"{r[0]}.{CELL}"


def cmd(r) -> str:
    jid, arm, lab, cid, cfg, ref = r
    cf = ",".join(f"{k}={json.dumps(v)}" for k, v in cfg.items())
    jid = jid_of(r)
    return (f"$PY -I scripts/testing/run_s1.py run --id {jid} --stage 1a --arm {arm} --cid {cid} --label {lab} --family {CELL} --cell {CELL} --cond ideal --mit none "
            f"--shares 0 --keys {','.join(KEYS)} --seeds {SEEDS} --k 1 --tile 0 --cfg {cf} --out {OUT}/{jid}.jsonl --records {OUT}/records")


def set_cell(cell: str) -> None:
    global CELL, KEYS
    assert cell in KEYS_BY_CELL, cell
    CELL, KEYS = cell, KEYS_BY_CELL[cell]


def main(argv):
    global PROBE_ON
    if argv and argv[0] == "--cell":
        set_cell(argv[1])
        argv = argv[2:]
    if argv[0] == "plan-probe":
        PROBE_ON = True
        Path(argv[1]).write_text("\n".join(f"{jid_of(r)}\t{cmd(r)}" for r in rows()) + "\n")
        print(len(rows()), "probe jobs")
        return 0
    if argv[0] == "plan":
        Path(argv[1]).write_text("\n".join(f"{jid_of(r)}\t{cmd(r)}" for r in rows()) + "\n")
        print(len(rows()), "jobs")
    elif argv[0] == "check":
        import dataclasses
        import machines as ma
        import plan as pl
        import run_h8 as rh
        from types import SimpleNamespace
        bad = 0
        for label, cfgs in g.GRIDS.items():
            seen = {}
            for c in cfgs:
                ns = SimpleNamespace(label=label, family=CELL, phase="main", cond="ideal", mit="none", c2c=0.5, sweeps=300.0, ours_tile_rows=0)
                spec = dataclasses.replace(rh.make_spec(ns, KEYS[0], 0), tag=10, cfg={**rh.make_spec(ns, KEYS[0], 0).cfg, **c})
                key = json.dumps(ma.effective_params(spec), sort_keys=True)
                seen.setdefault(key, []).append(c)
            print(label, len(cfgs), "configs ->", len(seen), "distinct effective parameter sets")
            bad += len(cfgs) != len(seen)
        return bad
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
