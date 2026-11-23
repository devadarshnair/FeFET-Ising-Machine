"""Stage 3.0-B screening job list (STAGE3_PLAN): trajectory-changing / variation hooks of round 2 at TUNING-ONLY instances (tag 10: p3 keys 2101-2112, Max-Cut R5001-R5005).
Same effort for every hook: two settings each (one for single-setting hooks), same instances and seeds, base arm = the S2-confirmed ours_new (c 0, K 0.25n); equal screening of the
baselines: ours_none and B3 (their Stage 1b selections) are run on the same Max-Cut / p3n960 screens. Kill rules are in STAGE3_PLAN.md section 3.
usage: s3_0_jobs.py plan OUT.tsv [group]   (groups: robust, barrier480, maxcut, barrier960)"""
import json
import sys

PY = "$PY -I scripts/testing/run_s1.py"
OUT = "sim/out/hw/s30"
BASE = {"kick_c": 0, "knob": 0.25}
MC_BASE = {"kick_c": 0.08, "knob": 0.5}          # Stage 1 gk selection (tuning-only)
B3_SEL = {"pct_hi": 90, "pct_lo": 5, "knob": 1.0, "t_hi_mult": 1.5, "t_lo_mult": 0.0625}
NONE_SEL = {"pct_hi": 90, "pct_lo": 5, "knob": 0.5, "t_hi_mult": 2.0, "t_lo_mult": 0.5}
K3 = [str(2101 + i) for i in range(12)]
RK = [f"R{5001 + i}" for i in range(5)]
HOOKS = {   # name -> cfg overrides (two settings each)
    "burstA": {"burst_K": 0.25, "burst_len": 0.05, "burst_up": 2}, "burstB": {"burst_K": 0.1, "burst_len": 0.1, "burst_up": 3},
    "ccBurst": {"cc": "burst", "burst_K": 0.25, "burst_len": 0.05, "burst_up": 2}, "ccAlways": {"cc": "always"},
    "conflictA": {"kick_conflict": True, "kick_L": 2, "knob": 0.1}, "conflictB": {"kick_conflict": True, "kick_L": 2, "knob": 0.25},
    "lahcA": {"lahc_len": 50}, "lahcB": {"lahc_len": 200},
    "boA": {"bo_K": 5, "bo_T": 50}, "boB": {"bo_K": 20, "bo_T": 200},
    "escA": {"esc_step": 1, "esc_max": 2}, "escB": {"esc_step": 1, "esc_max": 5},
    "adaptA": {"adaptive_m": 3}, "adaptB": {"adaptive_m": 6},
    "colourPar": {"colour_par": True},
}
ROBUST = {   # name -> (mit suffix, cfg)
    "scr5": ("+scr5", {}), "lcor8": ("+lcor8", {}), "scr5+lcor8": ("+scr5+lcor8", {}), "sparse": ("", {"sim_sparse": True}),   # sparse storage keeps only 1-cells: no complement partner, so MIT is wv+cal (no diff)
    "incrR50": ("", {"sim_incremental": True, "sim_refresh": 50}), "incrR50+scr5": ("+scr5", {"sim_incremental": True, "sim_refresh": 50}),
}
POINTS = ((0.0, 1), (0.03, 1), (0.25, 2))        # (C2C share, k)


def cfgs(d):
    return ",".join(f"{k}={json.dumps(v) if not isinstance(v, (str, bool)) else (str(v).lower() if isinstance(v, bool) else v)}" for k, v in d.items())


def run(jid, label, family, cell, cond, mit, share, k, keys, seeds, cfg):
    return (jid, f"{PY} run --id {jid} --stage s30 --arm {jid.split('.')[1]} --cid {jid.split('.')[2]} --label {label} --family {family} --cell {cell} --cond {cond} --mit {mit} --shares {share} "
                 f"--keys {','.join(keys)} --seeds {seeds} --k {k} --tile 0 --cfg {cfgs(cfg)} --out {OUT}/{jid}.jsonl")


def jobs(group):
    out = []
    if group in ("all", "robust", "robust2"):
        for sh, k in POINTS:
            for name, (suf, cfg) in ROBUST.items():
                if group == "robust2" and name != "sparse":
                    continue
                if group == "robust" and name == "sparse":
                    continue
                mit = "wv+cal" if name == "sparse" else "wv+diff+cal" + suf
                out.append(run(f"s30.rob_{name}.s{sh}k{k}", "ours_kc2_i11", "p3n240", "p3n240", "nominal", mit, sh, k, K3, 3, {**BASE, **cfg}))
            if group == "robust2":
                out.append(run(f"s30.rob_nodiffM0.s{sh}k{k}", "ours_kc2_i11", "p3n240", "p3n240", "nominal", "wv+cal", sh, k, K3, 3, BASE))
        for R in (0, 50, 200):      # T-1 at the working point: does the incremental field keep success at share 0.5?
            cfg = {**BASE, "sim_incremental": True, **({"sim_refresh": R} if R else {})}
            out.append(run(f"s30.incr_R{R}.s0.5k1", "ours_kc2_i11", "p3n240", "p3n240", "nominal", "wv+diff+cal", 0.5, 1, K3, 3, cfg))
        out.append(run("s30.base_M0.s0.5k1", "ours_kc2_i11", "p3n240", "p3n240", "nominal", "wv+diff+cal", 0.5, 1, K3, 3, BASE))
    if group in ("all", "barrier480"):
        out.append(run("s30.bar_base.p3n480", "ours_kc2_i11", "p3n480", "p3n480", "ideal", "none", 0, 1, K3[:8], 3, BASE))
        for name, h in HOOKS.items():
            out.append(run(f"s30.bar_{name}.p3n480", "ours_kc2_i11", "p3n480", "p3n480", "ideal", "none", 0, 1, K3[:8], 3, {**BASE, **h}))
    if group in ("all", "maxcut"):
        out.append(run("s30.mc_base.R", "ours_kc2_i11", "maxcut", "mc", "ideal", "none", 0, 1, RK, 2, MC_BASE))
        out.append(run("s30.mc_oursnone.R", "ours_none", "maxcut", "mc", "ideal", "none", 0, 1, RK, 2, NONE_SEL))
        out.append(run("s30.mc_B3.R", "B3_v2", "maxcut", "mc", "ideal", "none", 0, 1, RK, 2, B3_SEL))
        for name, h in HOOKS.items():
            out.append(run(f"s30.mc_{name}.R", "ours_kc2_i11", "maxcut", "mc", "ideal", "none", 0, 1, RK, 2, {**MC_BASE, **h}))
    if group in ("all", "barrier960"):
        out.append(run("s30.b960_base.p3n960", "ours_kc2_i11", "p3n960", "p3n960", "ideal", "none", 0, 1, K3[:6], 2, BASE))
        out.append(run("s30.b960_B3.p3n960", "B3_v2", "p3n960", "p3n960", "ideal", "none", 0, 1, K3[:6], 2, B3_SEL))
        for name in ("burstA", "burstB", "escA", "adaptA"):      # survivors of the p3n480 no-regression rule (success >= base - 0.15 = 0.68), one setting per class
            out.append(run(f"s30.b960_{name}.p3n960", "ours_kc2_i11", "p3n960", "p3n960", "ideal", "none", 0, 1, K3[:6], 2, {**BASE, **HOOKS[name]}))
    return out


if __name__ == "__main__":
    g = sys.argv[3] if len(sys.argv) > 3 else "all"
    js = jobs(g)
    open(sys.argv[2], "w").write("\n".join(f"{i}\t{c}" for i, c in js) + "\n")
    print(len(js), "jobs", g)
