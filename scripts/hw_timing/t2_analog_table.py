"""Markdown table of the analog sensitivity corners (analog_model.sensitivity_corners) on the primary measured_v2 pricing: ETS99 ratio of
the headline contrasts and the area ratio (A) with its verdict, and whether a registered verdict (win / loss / inconclusive / tie) changes against the nominal row.
Reads docs/hw/results/timing_v2/h{6,7}_analog_<corner>.json and h{6,7}_L5_*.json."""
from __future__ import annotations

import json
from pathlib import Path

R = Path(__file__).resolve().parents[2] / "docs/hw/results/timing_v2"
KEYS = [(6, "maxcut", "ours_none_off vs B1_best"), (6, "maxcut", "ours_none_fs vs B1_best"), (6, "col3p", "ours_kc2_i11_off vs B1_best"),
        (7, "p3n240", "ours_kc2_i11 vs B1_best"), (7, "p3n480", "ours_kc2_i11 vs B1_best"), (7, "p4n480", "ours_kc2_i11 vs B1_best"),
        (7, "dimacs", "ours_kc2_i11 vs B1_best"), (7, "dimacs", "ours_none vs B1_best")]


def load(prefix: int, name: str) -> dict | None:
    p = R / f"h{prefix}_{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def main() -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import analog_model
    corners = ["nominal"] + [c for c in analog_model.sensitivity_corners() if c != "nominal"] + ["L5_ungated", "L5_laneratio", "L5_mesa0", "L5_mesa1", "L5_worst"]
    head = ["corner"] + [f"{f}: {c.split(' vs ')[0]}" for _, f, c in KEYS]
    print("| " + " | ".join(head) + " |\n|" + "---|" * len(head))
    nominal = {}
    flips = []
    for c in corners:
        cells = []
        for pre, fam, con in KEYS:
            rep = load(pre, "L3_v2" if c == "nominal" else c if c.startswith("L5_") else f"analog_{c}")
            if rep is None:
                cells.append("-")
                continue
            x = rep["families"][fam]["contrasts"][con]
            r, e, ar, av = x["ets_ratio"], x["energy"], x["area_ratio"], x["area"]
            cells.append(f"{r:.3f} {e.split(' ')[0]}; A {ar:.2f} {av.split(' ')[0]}")
            key = (pre, fam, con)
            if c == "nominal":
                nominal[key] = (e, av)
            elif key in nominal:
                for what, a, b in (("energy", nominal[key][0], e), ("area", nominal[key][1], av)):
                    if a != b:
                        flips.append(f"{c}: {fam} {con} {what}: {a} -> {b}")
        print(f"| {c} | " + " | ".join(cells) + " |")
    print("\nverdict changes against nominal: " + ("; ".join(flips) if flips else "none"))


if __name__ == "__main__":
    main()
