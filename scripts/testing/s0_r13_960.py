"""Stage 0.5 (the experiment plan II.2): R13 identity at N = 960. Re-run STORED IDEAL ours_kc2_i11 records of a 960-spin family as nominal
(wv+diff+cal, C2C share 0.5) with the tiled LSB-1 simulator (256 rows) and compare with the stored ideal record (A7: nominal == ideal)
and the stored one-column nominal record. usage: s0_r13_960.py FAMILY NREC OUT.json"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import plan as pl  # noqa: E402
import run_h8 as rh8  # noqa: E402

RAW = HERE.parents[1] / "sim/out/hw/h8/h8"


def main(argv):
    fam, nrec, out = argv[0], int(argv[1]), argv[2]
    ideal = sorted(RAW.glob(f"h8_main_ours_kc2_i11_{fam}_ideal_*.json"))
    nominal = sorted(RAW.glob(f"h8_main_ours_kc2_i11_{fam}_nominal_*.json"))
    recs_i = [r for f in ideal for r in json.loads(f.read_text())["records"]]
    recs_n = {(r["spec"]["instance"], r["spec"]["r"]): r for f in nominal for r in json.loads(f.read_text())["records"]}
    rows = []
    for rec in recs_i[:nrec]:
        spec = pl.Spec(**{**rec["spec"], "pert": rh8.pert_of("nominal")})
        a = SimpleNamespace(cond="nominal", mit="wv+diff+cal", c2c=0.5, ours_tile_rows=256)
        new = rh8.execute_one(spec, a)
        old_n = recs_n.get((rec["spec"]["instance"], rec["spec"]["r"]))
        row = {"instance": rec["spec"]["instance"], "r": rec["spec"]["r"], "best_E_ideal": rec["best_E"], "best_E_tiled_nominal": new["best_E"],
               "best_E_onecol_nominal": old_n["best_E"] if old_n else None,
               "curve_identical_to_ideal": list(new["curve"]) == list(rec["curve"]), "curve_identical_to_onecol_nominal": bool(old_n) and list(new["curve"]) == list(old_n["curve"]),
               "flips_ideal": rec["flips"], "flips_tiled": new["flips"], "wall_s": new.get("wall_s")}
        rows.append(row)
        print(json.dumps(row), flush=True)
    Path(out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
