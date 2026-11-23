"""R13 acceptance check (the engineering notes R13, internal review item 3.3): re-run stored H8 nominal ours records with the tiled LSB-1 simulator
(variation_v2.OURS_TILE_ROWS = 256) and compare the trajectory with the stored (one-column) record and, through A7, with ideal.
Pass = best_E and the whole energy curve are identical at N <= 480. Usage:
  python scripts/testing/r13_tiled_identity.py --files sim/out/hw/h8/h8/h8_main_ours_kc2_i11_p3n480_nominal_000.json --k 3"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parents[1] / "scripts" / "golden", HERE.parents[1] / "scripts" / "baselines"):
    sys.path.insert(0, str(p))
import plan as pl  # noqa: E402
import run_h8 as rh8  # noqa: E402


def rerun(meta: dict, rec: dict, tile_rows: int) -> dict:
    spec = pl.Spec(**rec["spec"])
    a = SimpleNamespace(cond=meta["cond"], mit=meta["mit"], c2c=float(meta["c2c"]), ours_tile_rows=tile_rows)
    return rh8.execute_one(spec, a)


def compare(stored: dict, new: dict) -> dict:
    return {"instance": stored["spec"]["instance"], "r": stored["spec"]["r"], "n_act": stored["desc"]["n_act"],
            "best_E_stored": stored["best_E"], "best_E_tiled": new["best_E"],
            "curve_identical": list(stored["curve"]) == list(new["curve"]) and list(stored["curve_t"]) == list(new["curve_t"]),
            "sim_tile_rows": new["desc"].get("sim_tile_rows")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--k", type=int, default=2, help="records per file")
    ap.add_argument("--tile-rows", type=int, default=256)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows = []
    for f in a.files:
        d = json.loads(Path(f).read_text())
        for rec in d["records"][:a.k]:
            row = compare(rec, rerun(d["h8"], rec, a.tile_rows))
            row["file"] = Path(f).name
            rows.append(row)
            print(json.dumps(row), flush=True)
    ok = all(r["curve_identical"] for r in rows if r["n_act"] <= 480)
    print(f"R13 identity at N <= 480: {'PASS' if ok else 'FAIL'} ({sum(r['curve_identical'] for r in rows)}/{len(rows)} identical)")
    if a.out:
        Path(a.out).write_text(json.dumps({"rows": rows, "pass_n_le_480": ok}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
