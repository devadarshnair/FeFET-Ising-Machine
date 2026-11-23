"""Stage 0 helper (the experiment plan II.2): fresh-instance runs of one H8 arm with an overridden C2C share / mitigation / tile rows.
Not an H8 job; tuning-tag instances only. usage: s0_sweep.py LABEL FAMILY COND MIT SHARES(csv) KEYS(csv) NSEEDS OUT.jsonl [TILE_ROWS] [--k K] [--cfg key=val,...]
--k K: variation multiplier k of the H8 stress grid (cond nominal becomes vx<K>; k = 1 is nominal).
--cfg: overrides merged into the arm cfg (kick_L, kick_c, knob, tabu, kick_target, i11_temp, i11_tol, hyb_f)."""
import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import os
import numpy as np
import run_h8 as rh  # noqa: E402
import variation_v2 as v2  # noqa: E402

TUNE_TAG = 10


def _leak_free():
    """H-4 falsifier: level-0 cells carry their nominal current (no MC leakage tail). Enabled by env S0_LEAK=none."""
    orig = v2.program_cells

    def no_leak(levels, binary, pert, mit, rng):
        res = orig(levels, binary, pert, mit, rng)
        tgt = v2.transfer().target(0, binary)
        for k in ("i_cal", "i_op"):
            res[k] = np.where(np.asarray(levels) == 0, tgt, res[k])
        return res
    v2.program_cells = no_leak


def _l0_sigma(mult: float):
    """C2C_ESTIMATE tail bracket: scale only the level-0 (erased) sigma(Vth) by `mult` (env S0_L0_SIGMA_MULT)."""
    orig = v2.sigma_vth
    v2.sigma_vth = lambda k: orig(k) * (mult if k == 0 else 1.0)


def parse_opts(argv):
    """Split the --k / --cfg options from the positional arguments."""
    argv, k, cfg = list(argv), 1.0, {}
    if "--k" in argv:
        i = argv.index("--k")
        k = float(argv[i + 1])
        del argv[i:i + 2]
    if "--cfg" in argv:
        i = argv.index("--cfg")
        for kv in argv[i + 1].split(","):
            key, _, val = kv.partition("=")
            if val in ("true", "false"):
                cfg[key] = val == "true"
            else:
                try:
                    cfg[key] = json.loads(val)
                except json.JSONDecodeError:          # bare strings, e.g. cc=burst
                    cfg[key] = val
        del argv[i:i + 2]
    return argv, k, cfg


def cond_at_k(cond: str, k: float) -> str:
    if k == 1.0:
        return cond
    assert cond == "nominal", "--k scales the nominal point only"
    return f"vx{k:g}"


def main(argv):
    argv, k, cfg_over = parse_opts(argv)
    label, family, cond, mit, shares, keys, nseeds, out = argv[:8]
    cond = cond_at_k(cond, k)
    tile = int(argv[8]) if len(argv) > 8 else 0
    if os.environ.get("S0_LEAK") == "none":
        _leak_free()
    if os.environ.get("S0_L0_SIGMA_MULT"):
        _l0_sigma(float(os.environ["S0_L0_SIGMA_MULT"]))
    if family == "maxcut" or family.endswith("n240"):    # Max-Cut (gk, 1d): the H8 Max-Cut budget of 150 sweeps
        sweeps = 150.0
    else:
        sweeps = float(min(600, max(150, round(150 * int(family[3:]) / 240))))
    if os.environ.get("S0_SWEEPS"):                       # smoke override only
        sweeps = float(os.environ["S0_SWEEPS"])
    done = set()
    if Path(out).exists():
        done = {(r["share"], r["inst"], r["r"]) for r in map(json.loads, Path(out).read_text().splitlines())
                if r.get("k", 1.0) == k and r.get("cfg_over", {}) == cfg_over}      # resume only rows of the same --k / --cfg
    with open(out, "a") as fh:
        for s in (float(x) for x in shares.split(",")):
            for key in keys.split(","):
                for r in range(int(nseeds)):
                    if (s, key, r) in done:
                        continue
                    a = SimpleNamespace(label=label, family=family, phase="main", cond=cond, mit=mit, c2c=s, sweeps=sweeps, ours_tile_rows=tile)
                    spec = rh.make_spec(a, key, r)
                    spec = dataclasses.replace(spec, tag=TUNE_TAG, inst_index=1500 + (int(key) if key.isdigit() else int(key.lstrip("GR"))) % 1000, cfg={**spec.cfg, **cfg_over})
                    rec = rh.execute_one(spec, a)
                    fh.write(json.dumps({"label": label, "family": family, "cond": cond, "share": s, "inst": key, "r": r, "best_E": rec["best_E"],
                                         "flips": rec["flips"], "restarts": rec.get("restarts"),
                                         "k": k, "cfg_over": cfg_over}) + "\n")
                    fh.flush()


if __name__ == "__main__":
    main(sys.argv[1:])
