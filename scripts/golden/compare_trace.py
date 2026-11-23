"""Compare two TIM traces (SPEC 9.3) line by line. Usage: compare_trace.py <golden.trace> <rtl.trace>

Exit 0 and print "PASS ..." if the files are equal (ignoring blank lines and '#' comments), else print the first
differing line with field names and exit 1.
"""
from __future__ import annotations

import sys

FIELDS = ("t", "k", "nacc", "acs", "f", "hcs", "eoff", "T", "lcs", "ccs")
FINAL_FIELDS = ("final", "best_f", "best_step", "x", "best_x")


def read_lines(path) -> list[str]:
    with open(path) as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def first_difference(golden: list[str], rtl: list[str]) -> str | None:
    """None if equal, else a one-line description of the first difference."""
    for i, (a, b) in enumerate(zip(golden, rtl)):
        if a != b:
            names = FINAL_FIELDS if a.startswith("final") else FIELDS
            fa, fb = a.split(), b.split()
            diffs = [f"{n}: golden {x} rtl {y}" for n, x, y in zip(names, fa, fb) if x != y]
            return f"line {i + 1}: " + "; ".join(diffs or [f"golden '{a}' rtl '{b}'"])
    if len(golden) != len(rtl):
        return f"length: golden {len(golden)} lines, rtl {len(rtl)} lines"
    return None


def main(argv: list[str]) -> int:
    golden, rtl = read_lines(argv[1]), read_lines(argv[2])
    diff = first_difference(golden, rtl)
    if diff is None:
        print(f"PASS trace equal ({len(golden)} lines)")
        return 0
    print(f"FAIL trace differs at {diff}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
