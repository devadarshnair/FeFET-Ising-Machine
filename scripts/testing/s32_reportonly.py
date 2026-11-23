"""Stage 3.2 supplementary report-only contrasts (NOT produced by the registered evaluator_s3 output; added afterwards, exploratory): ours_stack vs ours_new (bridge) and vs B1_sel at p3n480,
and Max-Cut success under the 0.99 / 0.995 / raised-reference rules per arm. Same pricing as the primary (evaluate_s3.BASE). usage: s32_reportonly.py RECORDS OUT.md [B]"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_s3 as e3  # noqa: E402
import evalcommon as ev  # noqa: E402
import evaluate_h8 as e8  # noqa: E402
import plan as pl  # noqa: E402

rec, out = sys.argv[1], sys.argv[2]
B = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
g = e3.load(rec)
spec = e3.BASE
ev.EQ_SUCC = 0.10
ev.ZERO_COMPARATOR_NOT_EVALUABLE = True
costs = {"ours_stack": e3.cost_for(spec["ours"], spec["ours_attrs"]), "ours_new": e3.cost_for(spec["bridge"], {}), "B1_sel": e3.cost_for(spec["bridge"], {}),
         "B3_sel": e3.cost_for(spec["b3"], {}), "B3_h8": e3.cost_for(spec["b3"], {})}
runs = {k: e3.price(v, costs[k[0]], k[0] == "ours_stack") for k, v in g.items() if k[0] in costs}
L = ["# Stage 3.2 supplementary report-only contrasts (exploratory; added after the registered evaluator run)", "",
     f"B = {B}; margin -0.10 verdict class shown for orientation only (these contrasts are outside the Holm family).", "",
     "| contrast (p3n480, nominal) | instances x seeds | ETS ratio ours_stack / comparator [95 % CI] | d success [95 % CI] | verdict class |", "|---|---|---|---|---|"]
for comp in ("ours_new", "B1_sel"):
    need = [("ours_stack", "p3n480"), (comp, "p3n480")]
    pairs = set.intersection(*[{(r.inst, r.seed) for r in runs[k]} for k in need])
    insts = sorted({i for i, _ in pairs}, key=lambda s: (len(s), s))
    seeds = sorted({s for _, s in pairs})
    arms = {k[0]: e8.arm_of(k[0], [r for r in runs[k] if r.inst in insts and r.seed in seeds], insts, seeds, False) for k in need}
    bs = ev.boot_stats(arms, B=B)
    c = ev.contrast(bs, "ours_stack", comp)
    f = lambda x: f"{x:.3g}"  # noqa: E731
    L.append(f"| ours_stack vs {comp} | {len(insts)} x {len(seeds)} | {f(c['ets_ratio'])} [{f(c['ets_ci'][0])}, {f(c['ets_ci'][1])}] | {c['d_success']:+.2f} [{c['d_success_ci'][0]:+.2f}, {c['d_success_ci'][1]:+.2f}] | {ev.energy_verdict(c, c['p_ets_lt1'])} |")
L += ["", "## Success per arm (192 / 128 / 100 runs)", "", "| cell | arm | success | mean best_E |", "|---|---|---|---|"]
for (arm, cell), rs in sorted(runs.items(), key=lambda kv: (kv[0][1], kv[0][0])):
    L.append(f"| {cell} | {arm} | {sum(r.best_E <= 0 for r in rs) / len(rs):.2f} (colouring) | {sum(r.best_E for r in rs) / len(rs):.2f} |" if cell != "maxcut" else f"| {cell} | {arm} | see Max-Cut table | {sum(r.best_E for r in rs) / len(rs):.1f} |")
import mc_fresh  # noqa: E402
import json  # noqa: E402
L += ["", "## Max-Cut success under the three rules (cut >= frac x reference; raised = reference replaced by the best cut found by any arm)", "", "| arm | 0.99 x ref | 0.995 x ref | 0.99 x raised | mean cut / ref | runs |", "|---|---|---|---|---|---|"]
best = {}
mc = {}
for (arm, cell), fs in g.items():
    if cell == "maxcut":
        for d in fs:
            for rec_ in d["records"]:
                k = rec_["spec"]["instance"]
                mc.setdefault(arm, []).append((k, -rec_["best_E"]))
                best[k] = max(best.get(k, 0), -rec_["best_E"])
for arm, xs in sorted(mc.items()):
    n = len(xs)
    r99 = sum(c >= 0.99 * mc_fresh.reference(k) for k, c in xs) / n
    r995 = sum(c >= 0.995 * mc_fresh.reference(k) for k, c in xs) / n
    rraised = sum(c >= 0.99 * max(mc_fresh.reference(k), best[k]) for k, c in xs) / n
    L.append(f"| {arm} | {r99:.2f} | {r995:.2f} | {rraised:.2f} | {sum(c / mc_fresh.reference(k) for k, c in xs) / n:.4f} | {n} |")
Path(out).write_text("\n".join(L) + "\n")
print("\n".join(L))
