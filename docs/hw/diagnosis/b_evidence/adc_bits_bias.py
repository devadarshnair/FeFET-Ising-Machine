"""B-evidence: how much does linear-per-bit ADC pricing (e_adc_conv_bit = E(8)/8) mis-charge each machine vs the SPICE E(b)
curve (circuit/adc/adc_energy.csv)? Reads stored price blocks of H8 main nominal records; no re-simulation."""
import json, glob, csv, collections, sys
from pathlib import Path
R = Path(__file__).resolve().parents[4]
E = {int(r["bits"]): float(r["e_adc_fJ"]) for r in csv.DictReader(open(R / "circuit/adc/adc_energy.csv"))}
PB = 45.5875
acc = collections.defaultdict(list)
for f in sorted(glob.glob(str(R / "sim/out/hw/h8/h8/h8_main_*_nominal_*.json"))):
    d = json.load(open(f)); lab = d["h8"]["label"]
    if lab not in ("ours_kc2_i11", "B1_best", "B3_v2"): continue
    for r in d["records"]:
        de = r["desc"]; p = r["price"]; fam = f.split("_main_")[1].split("_nominal")[0].replace(lab + "_", "")
        b = de.get("adc_bits_fs", de.get("adc_bits", 8)) if de["kind"] != "b3" else 0
        mc = r.get("mit_cost") or {}
        e = mc.get("e_run_fJ", p["e_total"])
        adc = p["blocks"].get("adc", 0.0)
        if de["kind"] == "ours" and "diff" in (r.get("mit") or ""):
            adc_tot = adc * (b + 1) / b; bb = b + 1               # diff charges +1 SAR bit
        else:
            adc_tot = adc; bb = b
        corr = adc_tot * (E[bb] / (bb * PB) if bb else 1) if bb in E or not bb else adc_tot
        acc[(fam, lab)].append((e, adc_tot / e if e else 0, (e - adc_tot + corr) / e if e else 1, bb, p["time_ns"] / (r["counters"]["cycles"] if "counters" in r else r["snaps"][-1]["c"]["cycles"])))
print("family,label,mean_bits,adc_share,energy_factor_if_E(b),ns_per_raw_cycle")
out = {}
for (fam, lab), v in sorted(acc.items()):
    n = len(v); m = [sum(x[i] for x in v) / n for i in range(5)]
    out[(fam, lab)] = m
    print(f"{fam},{lab},{m[3]:.2f},{m[1]:.3f},{m[2]:.3f},{m[4]:.3f}")
print("\nfamily, ratio-change factor ours/B3, ours/B1 (multiply reported ETS99 ratio)")
for fam in sorted({k[0] for k in out}):
    o = out.get((fam, "ours_kc2_i11"))
    if not o: continue
    s = [f"{o[2] / out[(fam, c)][2]:.3f}" if (fam, c) in out else "-" for c in ("B3_v2", "B1_best")]
    print(fam, *s)
