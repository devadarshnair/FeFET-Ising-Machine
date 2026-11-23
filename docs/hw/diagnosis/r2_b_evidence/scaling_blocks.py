"""Per-step energy by block vs N for ours_kc2_i11 and B3_v2 (H8 ideal raw records, re-priced with measured_v2), plus clock/sel_lat to 2048."""
import json, glob, math, sys, collections
from pathlib import Path
R = Path(__file__).resolve().parents[4]
for s in ("scripts/testing", "scripts/golden", "scripts/baselines"): sys.path.insert(0, str(R / s))
import types
try:
    import numba
except ImportError:  # pricing needs no JIT; stub so fujitsu_da imports
    nb = types.ModuleType("numba"); nb.njit = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f)); nb.prange = range; sys.modules["numba"] = nb
import pricing as pr, cost_model as cm
cost = cm.MeasuredCostV2()
print("clock rule: n_pad, t_clk_ns, sel_lat")
for n in (128, 256, 512, 1024, 2048):
    print(n, round(cost.at({"kind": "ours", "restart": "kc2", "n_pad": n, "n_act": n}).v("t_clk"), 3), cost.sel_lat_at(n, "ours"))
acc = collections.defaultdict(lambda: collections.defaultdict(list))
for lab in ("ours_kc2_i11", "B3_v2"):
    for fam in ("p3n120", "p3n240", "p3n480", "p3n960", "maxcut_1000"):
        fs = glob.glob(str(R / f"sim/out/hw/h8/h8/h8_main_{lab}_{fam}_ideal_*.json"))
        for f in fs:
            for r in json.load(open(f))["records"][:6]:
                sn = r["snaps"][-1]; p = pr.price(r["desc"], sn["c"], sn["t"], sn["flips"], cost)
                for k, v in p["blocks"].items(): acc[(lab, fam)][k].append(v / sn["t"])
                acc[(lab, fam)]["TOTAL"].append(p["e_total"] / sn["t"]); acc[(lab, fam)]["ns_step"].append(p["time_ns"] / sn["t"])
                acc[(lab, fam)]["bits"].append(r["desc"].get("adc_bits_fs", 0)); acc[(lab, fam)]["tiles"].append(p["tiles"])
keys = ["TOTAL", "array", "adc", "digital", "rng", "sram", "restart", "leakage", "ns_step", "bits", "tiles"]
print("\nlabel,family," + ",".join(keys) + "  (energies fJ per step)")
for (lab, fam), d in sorted(acc.items()):
    print(lab, fam, *[f"{sum(d[k])/len(d[k]):.4g}" if d.get(k) else "-" for k in keys], sep=",")
print("\nlog-log slope per step energy, p3 120->960:")
for lab in ("ours_kc2_i11", "B3_v2"):
    for k in ("TOTAL", "array", "adc", "digital", "rng", "sram", "leakage"):
        a, b = acc[(lab, "p3n120")].get(k), acc[(lab, "p3n960")].get(k)
        if a and b and sum(a) > 0 and sum(b) > 0:
            print(lab, k, round(math.log((sum(b)/len(b)) / (sum(a)/len(a))) / math.log(8), 2))
