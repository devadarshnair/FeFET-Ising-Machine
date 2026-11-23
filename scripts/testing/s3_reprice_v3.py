"""Round 3 (exploratory): re-price the Stage 3.2 records under measured_v3 (synthesised T-1 digital blocks, flag m3), without the T-5 credit
(the read of the flipped row depends on the selection of the same step: the round-3 design notes 2.2), with symmetric x0.5 / x2 sensitivities on B3's
SRAM read and RNG and on ours' analog estimates. Uses the registered evaluate_s3.evaluate (dual-B3 rule, margin -0.10, Holm over the cells).
  s3_reprice_v3.py RECORDS_DIR OUT.md [B]"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_s3 as e3  # noqa: E402

rec_dir, out = sys.argv[1], sys.argv[2]
B = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
A0 = {"t1_lcor_k": 0, "t1_refresh": 200}
NEW = "all,b3b,t1f,m3,t6"                       # measured_v3, no T-5
SPECS = [
    ("registered primary (estimates, with T-5)", {}),
    ("estimates, T-5 dropped", dict(ours="all,b3b,t1f,t6")),
    ("**measured_v3, T-5 dropped (new primary candidate)**", dict(ours=NEW)),
    ("measured_v3 with T-5 (for comparison only; T-5 not causally valid)", dict(ours="all,b3b,t1f,m3,t5,t6")),
    ("m3: analog estimates x2", dict(ours=NEW, ours_attrs={**A0, "t1_est_scale": 2.0})),
    ("m3: analog estimates x0.5", dict(ours=NEW, ours_attrs={**A0, "t1_est_scale": 0.5})),
    ("m3: B3 SRAM read x0.5", dict(ours=NEW, b3_scale={"e_sram_read_bit": 0.5})),
    ("m3: B3 SRAM read x2", dict(ours=NEW, b3_scale={"e_sram_read_bit": 2.0})),
    ("m3: B3 RNG x0.5", dict(ours=NEW, b3_scale={"e_rng_draw": 0.5})),
    ("m3: B3 RNG x2", dict(ours=NEW, b3_scale={"e_rng_draw": 2.0})),
    ("m3: B3 SRAM x0.5 and RNG x0.5 (worst case for ours)", dict(ours=NEW, b3_scale={"e_sram_read_bit": 0.5, "e_rng_draw": 0.5})),
    ("m3: B3 un-gated", dict(ours=NEW, b3="all,b3b")),
    ("m3: ours un-gated too (no T-6 anywhere)", dict(ours="all,b3b,t1f,m3", b3="all,b3b")),
    ("m3: correction table 16 as SRAM", dict(ours=NEW, ours_attrs={**A0, "t1_lcor_k": 16, "t1_lcor_impl": "sram"})),
    ("m3: correction table 16 as flops", dict(ours=NEW, ours_attrs={**A0, "t1_lcor_k": 16, "t1_lcor_impl": "flop"})),
    ("m3: refresh 50", dict(ours=NEW, ours_attrs={**A0, "t1_refresh": 50})),
]
groups = e3.load(rec_dir)
L = ["# Round 3: Stage 3.2 records re-priced under measured_v3 (EXPLORATORY; the frozen Stage 3.2 verdicts stand)", "",
     "ETS99 ratio ours_stack / comparator (< 1 favours ours) [95 pct CI] and verdict per cell, registered rule (dual-B3, margin -0.10, EVAL-1), B = " + str(B) + ".", "",
     "| pricing | p3n480 vs B3_sel | p3n480 vs B3_h8 | p4n480 vs B3_sel | p4n480 vs B3_h8 | p3n960 vs B3_sel | p3n960 vs B3_h8 | maxcut vs B3_sel | maxcut vs B3_h8 | decisions |",
     "|---|---|---|---|---|---|---|---|---|---|"]
res = {}
f = lambda x: "inf" if x is None or x == float("inf") else f"{x:.2f}"  # noqa: E731
for name, d in SPECS:
    spec = {**e3.BASE, **d}
    r = e3.evaluate(groups, B, spec)
    res[name] = r
    cells = []
    for cell in e3.CELLS:
        for comp in e3.COMPS:
            v = r["primary"].get(f"{cell}|{comp}")
            cells.append("-" if not v else f"{f(v['ets_ratio'])} [{f(v['ets_ci'][0])}, {f(v['ets_ci'][1])}] {v['energy']}")
    L.append(f"| {name} | " + " | ".join(cells) + " | " + "; ".join(f"{c}: {x}" for c, x in r["decision"].items()) + " |")
    print(L[-1], flush=True)
Path(out).write_text("\n".join(L) + "\n")
Path(out).with_suffix(".json").write_text(json.dumps({k: {"primary": v["primary"], "decision": v["decision"]} for k, v in res.items()}, indent=1, default=float))
