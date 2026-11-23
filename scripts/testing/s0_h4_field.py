"""Stage 0.3 (the experiment plan II.2): H-4 falsifier. Field-error distribution (read field - exact field) of the nominal ours machine on a fresh
instance, over random states and programming draws, at a given C2C share, with the real level-0 leakage model or a leakage-free level 0.
usage: s0_h4_field.py FAMILY KEY SHARE LEAK(real|none) NDRAWS NSTATES OUT.json [TILE_ROWS]"""
import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import run_h8 as rh  # noqa: E402
import machines as ma  # noqa: E402
import variation_v2 as v2  # noqa: E402
from cost_model import CostModel  # noqa: E402


def main(argv):
    mit_label = "wv+diff+cal"
    if "--mit" in argv:                      # e.g. --mit wv+cal (no diff: single-sign columns, B's original H-4 case)
        i = argv.index("--mit")
        mit_label = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    fam, key, share, leak, nd, ns, out = argv[:7]
    tile = int(argv[7]) if len(argv) > 7 else 0
    share, nd, ns = float(share), int(nd), int(ns)
    if leak == "none":
        orig = v2.program_cells

        def no_leak(levels, binary, pert, mit, rng):
            res = orig(levels, binary, pert, mit, rng)
            tgt = v2.transfer().target(0, binary)
            for k in ("i_cal", "i_op"):
                res[k] = np.where(np.asarray(levels) == 0, tgt, res[k])
            return res
        v2.program_cells = no_leak
    a = SimpleNamespace(label="ours_kc2_i11", family=fam, phase="main", cond="nominal", mit=mit_label, c2c=share, sweeps=150.0, ours_tile_rows=tile)
    mit = v2.Mitigation.parse(a.mit)
    v2.OURS_TILE_ROWS = tile or None
    errs, rows = [], []
    with v2.c2c_share(share):
        for r in range(nd):
            spec = dataclasses.replace(rh.make_spec(a, key, r), tag=10, inst_index=1500 + int(key) % 1000)
            b = ma.build(spec, CostModel(), 100, mit)
            cim = b.m.cim
            n = cim.n_act
            P = np.asarray(b.m.inst.P, np.int64)[:n, :n]
            rng = np.random.default_rng(1234 + r)
            e = []
            for _ in range(ns):
                x = (rng.random(n) < 1 / 3).astype(np.int64)
                e.append(np.rint(cim.cf.field_delta(x)).astype(np.int64) - P @ x)
            e = np.concatenate(e)
            errs.append(e)
            rows.append({"draw": r, "mean": float(e.mean()), "sd": float(e.std()), "frac_nonzero": float((e != 0).mean()),
                         "frac_neg": float((e < 0).mean()), "frac_pos": float((e > 0).mean())})
            print(json.dumps(rows[-1]), flush=True)
    e = np.concatenate(errs)
    vals, cnt = np.unique(e, return_counts=True)
    res = {"family": fam, "share": share, "leak": leak, "tile_rows": tile, "n_draws": nd, "n_states": ns, "n_act": int(n),
           "mean": float(e.mean()), "sd": float(e.std()), "frac_nonzero": float((e != 0).mean()), "frac_neg": float((e < 0).mean()),
           "frac_pos": float((e > 0).mean()), "hist": {int(v): int(c) for v, c in zip(vals, cnt) if abs(v) <= 6}, "draws": rows}
    Path(out).write_text(json.dumps(res, indent=1))
    print("SUMMARY", json.dumps({k: res[k] for k in ("share", "leak", "mean", "sd", "frac_nonzero", "frac_neg", "frac_pos")}))


if __name__ == "__main__":
    main(sys.argv[1:])
