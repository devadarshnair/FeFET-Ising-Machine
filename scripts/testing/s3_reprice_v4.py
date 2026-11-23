"""Round 4 (exploratory): Stage 3.2 records re-priced under measured_v4: OpenRAM SRAMs (32 x 64 banks; leakage by cell type, default
CACTI itrs-lstp, same for both machines) (B3 coupler memory read + leakage; ours' per-cell
correction table), synthesised T-1 lanes (m3), no T-5, per-machine gating split (t6s), realistic correction table (SRAM, k = 64 per
512-row column: R3-A7, covers the C2C high bracket of about 10 % leaky zeros) as the candidate primary.
  s3_reprice_v4.py RECORDS_DIR OUT.md [B]"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_s3 as e3  # noqa: E402

rec_dir, out = sys.argv[1], sys.argv[2]
B = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
OURS, B3 = "all,b3b,t1f,m3,m4,t6s", "all,b3b,m4,t6s"
A = {"t1_lcor_k": 64, "t1_lcor_impl": "sram", "t1_refresh": 200}
P = dict(ours=OURS, ours_attrs=A, b3=B3)
SPECS = [
    ("registered primary (estimates, T-5, k 0)", {}),
    ("measured_v3 candidate (round 3: m3, no T-5, k 0, t6)", dict(ours="all,b3b,t1f,m3,t6", b3="all,b3b,t6")),
    ("**measured_v4 candidate: m3 + OpenRAM SRAMs, no T-5, SRAM table k 64, gating split**", P),
    ("v4: table k 0 (screening ideal)", {**P, "ours_attrs": {**A, "t1_lcor_k": 0}}),
    ("v4: table k 16", {**P, "ours_attrs": {**A, "t1_lcor_k": 16}}),
    ("v4: table k 32", {**P, "ours_attrs": {**A, "t1_lcor_k": 32}}),
    ("v4: B3 SRAM leakage NOT priced (as all earlier pricing)", {**P, "b3_attrs": {"m4_b3_leak": False}}),
    ("v4: SRAM cells itrs-hp (CACTI), both machines", {**P, "ours_attrs": {**A, "m4_sram_cells": "hp"}, "b3_attrs": {"m4_sram_cells": "hp"}}),
    ("v4: SRAM cells FreePDK45 nominal (OpenRAM leakage), both machines", {**P, "ours_attrs": {**A, "m4_sram_cells": "openram"}, "b3_attrs": {"m4_sram_cells": "openram"}}),
    ("v4: SRAM read from CACTI hp per bit (512 rows), both machines", {**P, "ours_attrs": {**A, "m4_sram_read": "cacti_hp"}, "b3_attrs": {"m4_sram_read": "cacti_hp"}}),
    ("v4: B3 SRAM read x0.5", {**P, "b3_scale": {"e_sram_read_bit": 0.5}}),
    ("v4: B3 SRAM read x2", {**P, "b3_scale": {"e_sram_read_bit": 2.0}}),
    ("v4: B3 RNG x0.5", {**P, "b3_scale": {"e_rng_draw": 0.5}}),
    ("v4: B3 RNG x2", {**P, "b3_scale": {"e_rng_draw": 2.0}}),
    ("v4: B3 SRAM read and RNG x0.5, no B3 SRAM leakage (worst case for ours)", {**P, "b3_scale": {"e_sram_read_bit": 0.5, "e_rng_draw": 0.5}, "b3_attrs": {"m4_b3_leak": False}}),
    ("v4: full gating on both (t6)", {**P, "ours": "all,b3b,t1f,m3,m4,t6", "b3": "all,b3b,m4,t6"}),
    ("v4: B3 un-gated", {**P, "b3": "all,b3b,m4"}),
    ("v4: analog estimates x2", {**P, "ours_attrs": {**A, "t1_est_scale": 2.0}}),
    ("v4: refresh 50 (now active)", {**P, "ours_attrs": {**A, "t1_refresh": 50}}),
    ("v4: refresh 1000", {**P, "ours_attrs": {**A, "t1_refresh": 1000}}),
    # review item s20: the declared hybrid primary and B3's coupler read at its real row width / array-only lower bound (B3 only)
    ("v4b: DECLARED PRIMARY (OpenRAM read 49.5 fJ/bit + lstp leakage, most B3-favourable hybrid)", P),
    ("v4b: B3 read = CACTI wide word 7680 b, lstp (incl. H-tree)", {**P, "b3_attrs": {"m4_sram_read": "cacti_wide_lstp"}}),
    ("v4b: B3 read = CACTI wide word 7680 b, hp", {**P, "b3_attrs": {"m4_sram_read": "cacti_wide_hp"}}),
    ("v4b: B3 read = ARRAY-ONLY LOWER BOUND (14.6 fJ/bit)", {**P, "b3_attrs": {"m4_sram_read": "array_lb"}}),
    ("v4b: B3 array-only lower bound + B3 RNG x0.5", {**P, "b3_attrs": {"m4_sram_read": "array_lb"}, "b3_scale": {"e_rng_draw": 0.5}}),
]
if len(sys.argv) > 4:
    SPECS = [s for s in SPECS if sys.argv[4] in s[0]]
groups = e3.load(rec_dir)
L = ["# Round 4: Stage 3.2 records re-priced under measured_v4 (EXPLORATORY; frozen Stage 3.2 verdicts stand)", "",
     "ETS99 ratio ours_stack / comparator (< 1 favours ours) [95 pct CI] and verdict, registered rule (dual-B3, margin -0.10, EVAL-1), B = " + str(B) + ".", "",
     "| pricing | p3n480 vs B3_sel | p3n480 vs B3_h8 | p4n480 vs B3_sel | p4n480 vs B3_h8 | p3n960 vs B3_sel | p3n960 vs B3_h8 | maxcut vs B3_sel | maxcut vs B3_h8 | decisions |",
     "|---|---|---|---|---|---|---|---|---|---|"]
res = {}
f = lambda x: "inf" if x is None or x == float("inf") else f"{x:.2f}"  # noqa: E731
for name, d in SPECS:
    r = e3.evaluate(groups, B, {**e3.BASE, **d})
    res[name] = r
    cells = []
    for cell in e3.CELLS:
        for comp in e3.COMPS:
            v = r["primary"].get(f"{cell}|{comp}")
            cells.append("-" if not v else f"{f(v['ets_ratio'])} [{f(v['ets_ci'][0])}, {f(v['ets_ci'][1])}] {v['energy']}")
    L.append(f"| {name} | " + " | ".join(cells) + " | " + "; ".join(f"{c}: {x}" for c, x in r["decision"].items()) + " |")
    print(L[-1][:260], flush=True)
Path(out).write_text("\n".join(L) + "\n")
Path(out).with_suffix(".json").write_text(json.dumps({k: {"primary": v["primary"], "decision": v["decision"]} for k, v in res.items()}, indent=1, default=float))
