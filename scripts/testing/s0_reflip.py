"""Stage 0.4 (the experiment plan II.2): re-flip diagnostic for the Kc2 kick (ideal device, registered ours_kc2_i11 config). For each kick event i:
S_i = kicked spins, xp_i = pre-kick state. After the repair the next pre-kick state is xp_{i+1}. returned_i = fraction of S_i whose value in
xp_{i+1} equals its value in xp_i (the repair re-flipped it); drift_i = fraction of NON-kicked spins that differ between xp_i and xp_{i+1}.
usage: s0_reflip.py FAMILY KEY R OUT.json [SWEEPS]   (tuning-tag fresh planted keys; maxcut keys G<k>)"""
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
from cost_model import CostModel  # noqa: E402


def main(argv):
    fam, key, r, out = argv[:4]
    n = ma.mapped(fam, key).spins
    sweeps = float(argv[4]) if len(argv) > 4 else (150.0 if fam == "maxcut" else float(min(600, max(150, round(150 * n / 240)))))
    a = SimpleNamespace(label="ours_kc2_i11", family=fam, phase="main", cond="ideal", mit="", c2c=0.5, sweeps=sweeps, ours_tile_rows=0)
    spec = rh.make_spec(a, key, int(r))
    if fam != "maxcut":
        spec = dataclasses.replace(spec, tag=10, inst_index=1500 + int(key) % 1000)
    steps = int(round(sweeps * n))
    b = ma.build(spec, CostModel(), steps, None)
    m = b.m
    ev = []
    orig = m.restart._kick

    def kick(mm):
        xb = mm.x[:n].copy()
        orig(mm)
        ev.append((xb, np.flatnonzero(mm.x[:n] != xb)))
    m.restart._kick = kick
    best_t = 0
    last = m.best_f
    for t in range(1, steps + 1):
        m.step()
        if m.best_f != last:
            last, best_t = m.best_f, t
    ret, drift, hams, sizes = [], [], [], []
    for (xp, S), (xq, _) in zip(ev, ev[1:]):
        mask = np.ones(n, bool)
        mask[S] = False
        ret.append(float((xq[S] == xp[S]).mean()))
        drift.append(float((xq[mask] != xp[mask]).mean()))
        hams.append(int((xq != xp).sum()))
        sizes.append(len(S))
    res = {"family": fam, "key": key, "r": int(r), "n": n, "L": m.restart.L, "K": m.restart.K, "kicks": len(ev), "best_E": ma._energy(b, m),
           "last_best_frac": round(best_t / steps, 3), "mean_returned": float(np.mean(ret)) if ret else None,
           "median_returned": float(np.median(ret)) if ret else None, "mean_drift_nonkicked": float(np.mean(drift)) if drift else None,
           "frac_kicks_returned_ge_0.5": float(np.mean(np.array(ret) >= 0.5)) if ret else None, "median_hamming_successive": float(np.median(hams)) if hams else None}
    Path(out).write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main(sys.argv[1:])
