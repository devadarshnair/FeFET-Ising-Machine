"""Derive the digital energy rows from the OSU gscl45nm liberty file (internal_power and pin capacitance) x synthesised NAND2-eq counts.

usage: derive_digital_energy.py <gscl45nm.lib> [--write]
e_toggle  = mean over NAND2X1 input pins of (rise_power + fall_power)/2 at the smallest load/slew entry
            + 0.5 * C_load * V^2, C_load = two NAND2X1 input pins (fanout 2), V = nom_voltage
e_gate    = ACTIVITY * e_toggle          fJ per NAND2-eq per active cycle (no wire cap, no clock tree)
e_dff_wr  = DFFPOSX1 clock + D + Q internal power (rise + fall) + 0.5 C V^2 of one fanout-2 load
Liberty energy values are read as pJ (capacitive_load_unit 1 pF, voltage 1 V; the file states no energy unit).
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

ACTIVITY = 0.1
NAND2_EQ_DFF = 4.25
GATES = {"add16": 122.5, "stall": 630.25 - 32 * NAND2_EQ_DFF, "offset": 413.5 - 24 * NAND2_EQ_DFF,
         "xoshiro": 1936.25, "ramp_comb": 1537.5, "hold_comb": 225.0}
TABLE = Path(__file__).resolve().parents[1] / "docs/hw/energy_table_v1_p309.csv"
TWEAKS = Path(__file__).resolve().parents[1] / "docs/hw/energy_table_tweaks_i11_i3_i5.csv"
SRC = "OSU gscl45nm.lib (SHA-256 69c0641d...62d6f, FreePDK45 mirror baichen318 a75cb11, same file as P3.09)"


def cell_text(lib: str, name: str) -> str:
    start = lib.index(f"cell ({name})")
    return lib[start: lib.index("\ncell (", start + 1)]


def first(block: str, kind: str) -> float:
    m = re.search(kind + r"\(\w+\)\s*\{[^}]*?values\s*\(\s*\\?\s*\"?([0-9.eE+-]+)", block)
    return float(m.group(1))


def pin_cap(cell: str, pin: str) -> float:
    return float(re.search(rf"pin\({pin}\)\s*\{{[^}}]*?\bcapacitance : ([0-9.]+)", cell).group(1))


def derive(lib: str) -> dict:
    volt = float(re.search(r"nom_voltage : ([0-9.]+)", lib).group(1))
    nand = cell_text(lib, "NAND2X1")
    internal = []
    for blk in re.findall(r"internal_power\(\)\s*\{(.*?)\n    \}", nand, re.S):
        internal.append((first(blk, "rise_power") + first(blk, "fall_power")) / 2)
    c_load = 2 * (pin_cap(nand, "A") + pin_cap(nand, "B")) / 2
    half_cv2 = 0.5 * c_load * volt ** 2
    e_toggle = sum(internal) / len(internal) * 1000 + half_cv2 * 1000
    e_gate = ACTIVITY * e_toggle
    dff = cell_text(lib, "DFFPOSX1")
    pins = {p: re.search(rf"pin\({p}\)\s*\{{(.*?)\n  \}}", dff, re.S).group(1) for p in ("CLK", "D", "Q")}
    clk = first(pins["CLK"], "rise_power") + first(pins["CLK"], "fall_power")
    din = (first(pins["D"], "rise_power") + first(pins["D"], "fall_power")) / 2
    qint = (first(pins["Q"], "rise_power") + first(pins["Q"], "fall_power")) / 2
    e_reg = (clk + din + qint) * 1000 + half_cv2 * 1000
    leak = float(re.search(r"cell_leakage_power : ([0-9.]+)", nand).group(1))
    v = {"e_toggle": e_toggle, "e_gate": e_gate, "e_reg_write": e_reg, "leak_nw_per_nand2": leak}
    v["e_add"] = GATES["add16"] * e_gate
    v["e_stall_counter"] = GATES["stall"] * e_gate + 32 * e_reg
    v["e_offset_add"] = GATES["offset"] * e_gate + 24 * e_reg
    v["e_shadow_bit"] = e_reg
    v["e_rng_draw"] = GATES["xoshiro"] * e_gate
    v["e_ramp_update"] = v["e_i3_ramp_update_rtl"] = GATES["ramp_comb"] * e_gate + 80 * e_reg
    v["e_i5_hold_ctl_rtl"] = GATES["hold_comb"] * e_gate + 16 * e_reg
    return v


NOTE = ("P5b ENERGY_RECONCILE: digital energy derived from " + SRC + ": e_gate = {eg:.4f} fJ per NAND2-eq per active cycle "
        "(NAND2X1 internal_power rise/fall mean + 0.5 C V^2 for fanout 2 = {et:.3f} fJ per toggle, x activity 0.1); "
        "e_dff = {er:.2f} fJ per flop write (DFFPOSX1 CLK+D+Q internal + load); {how}; generic synth counts (P3.09 flow), "
        "no wire cap, clock tree or glitching; liberty read as pJ (file gives no energy unit); source=derived (lib x synth); was {old}")
HOW = {
    "e_add": "122.5 comb NAND2-eq (synth 16 b adder) x e_gate (cross-check Horowitz ISSCC 2014: 16 b add about 50 fJ)",
    "e_stall_counter": "(630.25 - 32 x 4.25) comb NAND2-eq x e_gate + 32 DFF writes",
    "e_offset_add": "(413.5 - 24 x 4.25) comb NAND2-eq x e_gate + 24 DFF writes",
    "e_shadow_bit": "one DFF write (replaces KLIMA register 7.16 fJ, which is a cross-check only)",
    "e_rng_draw": "1936.25 NAND2-eq xoshiro128** x e_gate (KLIMA PRNG 365 fJ is a cross-check, different generator)",
    "e_reg_write": "one DFF write (KLIMA register 7.16 fJ is a cross-check)",
    "e_i3_ramp_update_rtl": "1537.5 comb NAND2-eq (rtl lam_ramp.v) x e_gate + 80 DFF writes",
    "e_ramp_update": "1537.5 comb NAND2-eq (rtl lam_ramp.v) x e_gate + 80 DFF writes",
    "e_i5_hold_ctl_rtl": "225.0 comb NAND2-eq (rtl hold_ctl.v) x e_gate + 16 DFF writes",
}


def update(path: Path, rows: dict) -> list:
    with open(path, newline="") as fh:
        text = fh.read()
    eol = "\r\n" if "\r\n" in text else "\n"
    rd = list(csv.reader(text.splitlines()))
    head, changed = rd[0], []
    ik, iv, isrc, ipl, ilo, ihi = (head.index(c) for c in ("key", "value", "source", "placeholder", "band_lo_x", "band_hi_x"))
    for row in rd[1:]:
        if row[ik] in rows:
            changed.append((row[ik], row[iv], rows[row[ik]][0]))
            row[iv], row[isrc], row[ipl], row[ilo], row[ihi] = (f"{rows[row[ik]][0]:.4f}", rows[row[ik]][1], "0", "0.3", "3")
    with open(path, "w", newline="") as fh:
        csv.writer(fh, lineterminator=eol).writerows(rd)
    return changed


def main() -> None:
    lib = Path(sys.argv[1]).read_text()
    v = derive(lib)
    for k, x in v.items():
        print(f"{k:22s} {x:.4f}")
    if "--write" not in sys.argv:
        return
    old = {}
    for path in (TABLE, TWEAKS):
        rel = path.relative_to(path.parents[2])
        text = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, text=True, cwd=path.parent).stdout
        old.update({r["key"]: r["value"] for r in csv.DictReader(text.splitlines())})
    fill = {k: (v[k], NOTE.format(eg=v["e_gate"], et=v["e_toggle"], er=v["e_reg_write"], how=HOW[k], old=old.get(k)))
            for k in HOW}
    for path in (TABLE, TWEAKS):
        for key, was, now in update(path, fill):
            print("changed", path.name, key, was, "->", f"{now:.4f}")


if __name__ == "__main__":
    main()
