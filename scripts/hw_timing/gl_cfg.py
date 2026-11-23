"""Host cfg of the representative runs for the activity-annotated power (C3): the Stage 3 / 4 machines on a 64-lane padded instance.
  gl_cfg.py <out dir>   writes <out>/{maxcut64_none,maxcut64_kc2_i11,col64_kc2_i11,maxcut256_kc2_i11}/test.cfg and params.json (steps, N)
maxcut64_none: ours arm none (L2 machine, I11 off); maxcut64_kc2_i11: Kc2 + I11 (L1 machine); col64_kc2_i11: planted colouring, Kc2 + I11.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import rtl_spotcheck as rs  # noqa: E402
import tim_golden as tg  # noqa: E402
from counters import CycleCfg  # noqa: E402
from tweaks import TweakCfg  # noqa: E402
from scripts.problems import load as ld  # noqa: E402
from scripts.problems import maxcut as mc  # noqa: E402
from scripts.problems import spin_table as st  # noqa: E402

STEPS = 400
STEPS_BY_RUN = {"maxcut256_kc2_i11": 150}


def runs() -> dict:
    return {"maxcut64_none": (ld.from_problem("maxcut", mc.torus_pm1(8, 1), 64), "none", None),
            "maxcut64_kc2_i11": (ld.from_problem("maxcut", mc.torus_pm1(8, 1), 64), "kc2", TweakCfg(i11=True)),
            "maxcut256_kc2_i11": (ld.from_problem("maxcut", mc.torus_pm1(16, 1), 256), "kc2", TweakCfg(i11=True)),
            "col64_kc2_i11": (ld.from_problem("colouring", st.random_colouring(21, 0.25, 3, seed=202), 63), "kc2", TweakCfg(i11=True))}


def main() -> int:
    out = Path(sys.argv[1])
    for name, (mq, arm, tw) in runs().items():
        steps = STEPS_BY_RUN.get(name, STEPS)
        inst, rcfg, cim, pw = rs.make_case(mq, arm, True, steps)
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        tg.write_cfg(inst, d / "test.cfg", rs.NCON, rcfg, cim, pw, tweaks=tw)
        mach = tg.Machine(inst, restart=rcfg, cim=cim, power=pw, counters=CycleCfg(), tweaks=tw)
        res = mach.run()
        (d / "params.json").write_text(json.dumps({"n": inst.n, "steps": steps, "arm": arm, "i11": tw is not None, "restarts": len(mach.restart.events),
                                                    "flips": res.flips}))
        print(name, "n", inst.n, "flips", res.flips, "restarts", len(mach.restart.events))
    return 0


if __name__ == "__main__":
    sys.exit(main())
