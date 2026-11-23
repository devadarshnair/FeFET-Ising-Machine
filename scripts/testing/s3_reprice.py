"""Stage 3.0-A (STAGE3_PLAN): energy re-pricing of the STORED Stage 2 records under the round-2 architecture flags (arch_t.py: t1..t6, b3b).
The tweaks T-1..T-6 keep the trajectory (exact field, ideal-device counters), so the re-pricing of the logged counters is the screening result for energy; nominal-variation
exactness of T-1 is a separate simulation question (3.0-B). Exploratory screening on CONFIRMATORY records: it is NOT a Stage 2 re-analysis and is never presented as confirmatory.
usage: s3_reprice.py RECORDS_DIR OUT.md [B]"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import numpy as np  # noqa: E402
import cost_flags as cf  # noqa: E402
import evalcommon as ev  # noqa: E402
import evaluate_h8 as e8  # noqa: E402
import evaluate_s2 as s2  # noqa: E402
from cost_model import MeasuredCostV2  # noqa: E402

rec_dir, out = sys.argv[1], sys.argv[2]
B = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
CELLS = ("p3n480", "p4n480")
NEED = (("ours_new", "nominal"), ("B3_sel", "ideal"), ("B3_h8", "ideal"), ("B1_sel", "nominal"))
CONFIGS = [   # (name, flags for ours / B1, flags for B3)
    ("base (corrected pricing, as Stage 2)", "all", "all"),
    ("t1 incremental field", "all,t1", "all,t1"),
    ("t2 sparse storage (ours only; B3 not offered)", "all,t2", "all,t2"),
    ("t3 64-row tiles", "all,t3", "all,t3"),
    ("t4 skip read after reject", "all,t4", "all,t4"),
    ("t5 overlap read with select", "all,t5", "all,t5"),
    ("t6 lane clock gating, every machine", "all,t6", "all,t6"),
    ("b3b idle sees SAR savings", "all,b3b", "all,b3b"),
    ("t1+t5", "all,t1,t5", "all,t1,t5"),
    ("t1+t5+t6 (B3 also gated)", "all,t1,t5,t6", "all,t1,t5,t6"),
    ("t1+t5+t6, B3 NOT gated (fairness bound)", "all,t1,t5,t6", "all,t1,t5"),
    ("t1+t5+t6+b3b", "all,t1,t5,t6,b3b", "all,t1,t5,t6,b3b"),
    ("t1+t2+t5+t6 (t2 ours only)", "all,t1,t2,t5,t6", "all,t1,t5,t6"),
    # t1f = FULL T-1 stack (internal review s15.3.1): refresh R, screening once (amortised), spares, lcor table + checks, field-register leakage
    ("t1f full (R 100, spare 2 %, screen 1 %, k 4, est x1)", "all,t1f", "all,t1"),
    ("t1f+t5", "all,t1f,t5", "all,t1,t5"),
    ("t1f+t5+t6 (B3 also gated) PRIMARY STACK", "all,t1f,t5,t6", "all,t1,t5,t6"),
    ("t1f+t5+t6, B3 NOT gated", "all,t1f,t5,t6", "all,t1,t5"),
]
SENS = [   # sensitivities of the primary stack (ours cost attributes only; B3 as in the primary row)
    ("  sens R = 25", {"t1_refresh": 25}), ("  sens R = 50", {"t1_refresh": 50}), ("  sens R = 200", {"t1_refresh": 200}),
    ("  sens R = 1000", {"t1_refresh": 1000}), ("  sens no refresh (R = 0, upper bound)", {"t1_refresh": 0}),
    ("  sens spare 0 %", {"t1_spare_frac": 0.0}), ("  sens spare 5 %", {"t1_spare_frac": 0.05}),
    ("  sens screen 3 % retired", {"t1_screen_frac": 0.03}), ("  sens lcor k = 16", {"t1_lcor_k": 16}),
    ("  sens T-1 estimates x2", {"t1_est_scale": 2.0}), ("  sens T-1 estimates x0.5", {"t1_est_scale": 0.5}),
    ("  sens screening amortised over 10 runs", {"t1_runs_per_program": 10}),
]
CONFIGS += [(n, "all,t1f,t5,t6", "all,t1,t5,t6", a) for n, a in SENS]
SCR0 = {"t1_lcor_k": 0}       # screening-only T-1 stack (no correction table; Stage 3.0: scr alone 0.92 at all three cliff points)
CONFIGS += [("t1f screening-only (k 0)", "all,t1f", "all,t1", SCR0),
            ("t1f screening-only (k 0)+t5+t6 (B3 also gated) CANDIDATE PRIMARY", "all,t1f,t5,t6", "all,t1,t5,t6", SCR0),
            ("t1f screening-only (k 0)+t5+t6, B3 NOT gated", "all,t1f,t5,t6", "all,t1,t5", SCR0),
            ("  scr-only sens R = 25", "all,t1f,t5,t6", "all,t1,t5,t6", {**SCR0, "t1_refresh": 25}),
            ("  scr-only sens screen 3 % retired", "all,t1f,t5,t6", "all,t1,t5,t6", {**SCR0, "t1_screen_frac": 0.03}),
            ("  scr-only sens T-1 estimates x2", "all,t1f,t5,t6", "all,t1,t5,t6", {**SCR0, "t1_est_scale": 2.0}),
            ("  scr-only sens T-1 estimates x0.5", "all,t1f,t5,t6", "all,t1,t5,t6", {**SCR0, "t1_est_scale": 0.5})]
import os  # noqa: E402
if os.environ.get("S3_ONLY"):                 # run a subset (substring of the configuration name)
    CONFIGS = [c for c in CONFIGS if os.environ["S3_ONLY"] in c[0]]
groups = s2.load(rec_dir)
L = ["# Stage 3.0-A: energy re-pricing screen on the stored Stage 2 records (exploratory; NOT a Stage 2 re-analysis)", "",
     "t1f rows: FULL T-1 stack priced (refresh reads, screening verify/re-erase once per run, spare rows, remap + lcor tables with leakage, lcor checks per update, field registers with leakage); B3 rows use bare t1 flags, which do not touch B3 (CiM-only). Estimates flagged in arch_t.py; x2 / x0.5 rows bound them.", "",
     f"ETS99 ratio ours_new / comparator, nominal, p3n480 and p4n480, 64 instances x 3 seeds, H8 bootstrap B = {B}; verdict by the H8 evaluator rule WITHOUT Holm (screening). Energy per run = mean e_final.", "",
     "| configuration | cell | vs B3_sel | vs B3_h8 | vs B1_sel | ours e/run (fJ) | B3_sel e/run |", "|---|---|---|---|---|---|---|"]
res = []
for cfg_row in CONFIGS:
    name, fo, fb = cfg_row[:3]
    attrs = cfg_row[3] if len(cfg_row) > 3 else {}
    costs = {"ours": cf.apply(MeasuredCostV2(), cf.parse(fo)), "b3": cf.apply(MeasuredCostV2(), cf.parse(fb))}
    for k_, v_ in attrs.items():
        setattr(costs["ours"], k_, v_)
    for cell in CELLS:
        arms, erun = {}, {}
        runs = {}
        for arm, cond in NEED:
            cost = costs["b3"] if arm.startswith("B3") else costs["ours"]
            runs[arm] = s2.price_group(groups[(arm, cell, cond)], cost)
        sets = [{(r.inst, r.seed) for r in g} for g in runs.values()]
        pairs = set.intersection(*sets)
        insts = sorted({i for i, _ in pairs}, key=lambda s: (len(s), s))
        seeds = sorted({s for _, s in pairs})
        for arm, g in runs.items():
            arms[arm] = e8.arm_of(arm, g, insts, seeds, False)
            erun[arm] = float(np.mean([r.ra.e_total for r in g]))
        bs = ev.boot_stats(arms, B=B)
        row = []
        for comp in ("B3_sel", "B3_h8", "B1_sel"):
            c = ev.contrast(bs, "ours_new", comp)
            v = ev.energy_verdict(c, c["p_ets_lt1"])
            row.append(f"{c['ets_ratio']:.2f} [{c['ets_ci'][0]:.2f}, {c['ets_ci'][1]:.2f}] {v}")
            res.append({"config": name, "cell": cell, "comp": comp, "ratio": c["ets_ratio"], "ci": c["ets_ci"], "verdict": v})
        L.append(f"| {name} | {cell} | " + " | ".join(row) + f" | {erun['ours_new']:.3g} | {erun['B3_sel']:.3g} |")
        print(L[-1], flush=True)
Path(out).write_text("\n".join(L) + "\n")
Path(out).with_suffix(".json").write_text(json.dumps(res, indent=1, default=float))
