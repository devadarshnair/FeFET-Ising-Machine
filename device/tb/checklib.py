"""Small helpers shared by the test checkers (device/tb/check_*.py, circuit/tcam/check_*.py).

Every checker prints one line per sub-test in the form
    RESULT <test id> PASS|FAIL  <what was achieved>  | target: <what was wanted>
and exits with status 1 if any sub-test failed. scripts/run_spice_tests.sh collects these lines.
"""
import csv
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "sim" / "out"
sys.path.insert(0, str(REPO / "device" / "py"))


def read_wrdata(path):
    """Read an ngspice 'wrdata' file written with wr_singlescale and wr_vecnames."""
    with open(path) as f:
        names = f.readline().split()
    data = np.loadtxt(path, skiprows=1, ndmin=2)
    return {n: data[:, k] for k, n in enumerate(names)}


def write_csv(path, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([f"{v:.6g}" if isinstance(v, (float, np.floating)) else v for v in r])


class Report:
    """Collect PASS/FAIL lines; call finish() at the end."""

    def __init__(self):
        self.failed = 0

    def check(self, test_id, passed, achieved, target):
        word = "PASS" if passed else "FAIL"
        if not passed:
            self.failed += 1
        print(f"RESULT {test_id} {word}  {achieved}  | target: {target}", flush=True)

    def info(self, text):
        print(f"INFO {text}", flush=True)

    def finish(self):
        sys.exit(1 if self.failed else 0)


def at_times(t, y, t_query):
    """Linear interpolation of y(t) at t_query (t must be increasing)."""
    return np.interp(t_query, t, y)
