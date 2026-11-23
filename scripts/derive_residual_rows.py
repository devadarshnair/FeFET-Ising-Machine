"""Derive the former placeholder rows (leakage, LUT read, array write, ADC bias, B2 logic gates) and rewrite them in the cost tables.

usage: derive_residual_rows.py <gscl45nm.lib> [--write]
Checks the liberty SHA-256 first. Sources: liberty cell_leakage_power (NAND2X1), circuit/char_v1.csv, circuit/adc/adc_energy.csv.
"""
import csv
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_digital_energy import GATES, NAND2_EQ_DFF, SRC, cell_text, derive  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LIB_SHA = "69c0641df1dc737e5c8dbd3950f2daf3b52c6e7767aa081e35e9b0739bf62d6f"
LAB, LUT_BITS, MUX2_EQ = 10, 12, 2.0          # accept LUT 1024 x 12 b (SPEC_v0 LAB=10, STATUS.md); MUX2X1 3.7544 / NAND2X1 1.8772 um2 = 2.0
TABLE = ROOT / "docs/hw/energy_table_v1_p309.csv"


def char_rows() -> list[dict]:
    with open(ROOT / "circuit/char_v1.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def derive_rows(libtext: str) -> dict:
    d = derive(libtext)
    eg = d["e_gate"]
    writes = [float(r["value"]) for r in char_rows() if r["block"] == "crossbar_write" and r["key"] == "e_write_fJ"]
    with open(ROOT / "circuit/adc/adc_energy.csv", newline="") as fh:
        cmp8 = next(float(r["e_cmp_fJ"]) for r in csv.DictReader(fh) if r["bits"] == "8")
    leak = float(re.search(r"cell_leakage_power : ([0-9.]+)", cell_text(libtext, "NAND2X1")).group(1))
    lib = f"{SRC}"
    return {
        "p_leak_nand2_nw": (leak, 0.5, 5, "leakage", "power", "nW static per NAND2-eq (all machines, scaled by own gate count)",
                            f"{lib}: NAND2X1 cell_leakage_power {leak} (liberty nW), typical corner; static energy = leakage x synthesised NAND2-eq x time; "
                            "DFF counted as 4.25 NAND2-eq (DFFPOSX1 leaks 54.98 nW = 16.7 NAND2-eq, so flop leakage is under-counted by about 4x; band hi covers it); "
                            "ROM/SRAM storage excluded; source=derived (lib x synth); replaces p_leak 10 uW placeholder"),
        "e_lut_read": (LAB * LUT_BITS * MUX2_EQ * eg, 0.3, 3, "digital", "energy", "fJ per LUT read",
                       f"{lib}: read path of the 1024 x 12 b accept LUT as a mux tree, LAB {LAB} levels x {LUT_BITS} b x MUX2X1 (2.0 NAND2-eq) x e_gate {eg:.4f}; "
                       "ROM bit storage not synthesised (behavioural in RTL); source=derived (lib x synth)"),
        "e_array_write": (sum(writes) / len(writes), 0.5, 2, "tcam", "energy", "fJ per cell write (TCAM-lite row = cells x this)",
                          "char_v1 (hw/p1-device 7f24c65) crossbar_write e_write_fJ, mean of levels 0-7; TCAM dropped (R5): never charged, cost_model asserts array_writes == 0"),
        "e_adc_bias_step": (cmp8, 0.2, 5, "leakage", "energy", "fJ per ungated step (ADC comparator bias, one shared ADC)",
                            f"circuit/adc/adc_energy.csv (char_v1 ADC rows) e_cmp_fJ at 8 b = {cmp8} fJ: comparator energy of one conversion held as bias for one step, gated by I10; "
                            "not scaled by column count (one shared bias per step): lower bound for column-parallel ADCs; source=derived (char_v1)"),
        "g_b2_logic": (2 * GATES["add16"] + 16 * NAND2_EQ_DFF + GATES["xoshiro"], 0.7, 1.5, "digital", "gates",
                       "NAND2-eq (B2 digital: 2 adders + 16 b register + one xoshiro128**)",
                       "P3.09 synth counts: 2 x 122.5 (16 b adder) + 16 x 4.25 (DFF) + 1936.25 (xoshiro128**); B2 area keeps digital 0, this row is for leakage only; source=derived (synth)"),
    }


def main() -> None:
    raw = Path(sys.argv[1]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == LIB_SHA, "liberty hash mismatch"
    rows = derive_rows(raw.decode())
    for k, r in rows.items():
        print(f"{k:18s} {r[0]:.6g}")
    if "--write" not in sys.argv:
        return
    with open(TABLE, newline="") as fh:
        rd = list(csv.reader(fh))
    head, keys = rd[0], {r[0]: r for r in rd[1:]}
    for k, (val, lo, hi, block, kind, unit, src) in rows.items():
        new = [k, block, kind, unit, f"{val:.6g}", str(lo), str(hi), src, "0"]
        if k in keys:
            rd[rd.index(keys[k])] = new
        else:
            rd.append(new)
    rd = [r for r in rd if r[0] not in ("p_leak", "e_tcam_row_search")]
    rd.append(["e_tcam_row_search", "tcam", "energy", "unused", "0", "1", "1",
               "unused: TCAM dropped (user ruling R5, P1.08 DROPPED); cost_model.energy asserts tcam_searches == 0, so this row is never charged; the SPICE v0 15.4 fJ is not carried", "0"])
    with open(TABLE, "w", newline="") as fh:
        csv.writer(fh, lineterminator="\r\n").writerows(rd)


if __name__ == "__main__":
    main()
