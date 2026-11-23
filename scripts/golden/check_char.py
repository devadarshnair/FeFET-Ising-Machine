"""Schema check for characterisation tables (char_v1): python -I scripts/golden/check_char.py circuit/char_v1.csv
PASS iff header matches, every row has source in {SPICE, lit, DERIVED}, a band with lo <= 1 <= hi, a finite numeric value and
(for rows with a sigma) a finite non-negative sigma."""
import csv
import math
import sys

COLS = ["block", "key", "param", "unit", "value", "sigma", "band_lo_x", "band_hi_x", "source", "note"]
REQUIRED_BLOCKS = {"crossbar_read", "crossbar_write", "adc", "level0_verify"}


def check(path: str) -> list[str]:
    errs = []
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        if rd.fieldnames != COLS:
            return [f"header {rd.fieldnames} != {COLS}"]
        rows = list(rd)
    seen, ids = set(), set()
    for i, r in enumerate(rows, 2):
        seen.add(r["block"])
        rid = (r["block"], r["key"], r["param"])
        if rid in ids:
            errs.append(f"line {i}: duplicate {rid}")
        ids.add(rid)
        if r["source"] not in ("SPICE", "lit", "DERIVED"):
            errs.append(f"line {i}: source {r['source']!r}")
        try:
            lo, hi, v = float(r["band_lo_x"]), float(r["band_hi_x"]), float(r["value"])
            if not (lo <= 1.0 <= hi) or not math.isfinite(v):
                errs.append(f"line {i}: bad band/value {lo} {hi} {v}")
            if r["sigma"] != "" and not (math.isfinite(float(r["sigma"])) and float(r["sigma"]) >= 0):
                errs.append(f"line {i}: bad sigma")
        except ValueError:
            errs.append(f"line {i}: non-numeric field")
        if not r["note"].strip() or not r["unit"].strip():
            errs.append(f"line {i}: empty unit/note")
    if REQUIRED_BLOCKS - seen:
        errs.append(f"missing blocks {sorted(REQUIRED_BLOCKS - seen)}")
    return errs


if __name__ == "__main__":
    e = check(sys.argv[1])
    print("schema PASS" if not e else "schema FAIL\n" + "\n".join(e))
    sys.exit(1 if e else 0)
