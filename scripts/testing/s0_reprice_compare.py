"""Stage 0.1: compare primary H8-A verdicts (nominal, global Holm) of the frozen report with re-priced reports.
usage: s0_reprice_compare.py FROZEN.json NAME=REPRICED.json [NAME=...] > table.md"""
import json
import sys

PAIRS = ("ours_kc2_i11 vs B3_v2", "ours_kc2_i11 vs B1_best")


def row(rep, cell, pair):
    c = rep["cells"][cell]["nominal"]["contrasts"].get(pair)
    if not c:
        return None
    return c


def fmt(c):
    if c is None:
        return "-"
    r = c["ets_ratio"]
    rs = "inf" if r is None or r == float("inf") else f"{r:.3g}"
    return f"{rs} / {c['energy']} / p={c['holm_p_global']:.3g}"


def main(argv):
    frozen = json.load(open(argv[0]))
    others = [(a.split("=")[0], json.load(open(a.split("=", 1)[1]))) for a in argv[1:]]
    print("| cell | contrast | frozen: ratio / verdict / p_glob | " + " | ".join(n for n, _ in others) + " |")
    print("|---|---|---|" + "---|" * len(others))
    flips = 0
    for cell in frozen["cells"]:
        for pair in PAIRS:
            f = row(frozen, cell, pair)
            if f is None:
                continue
            outs = []
            for n, rep in others:
                c = row(rep, cell, pair)
                tag = ""
                if c is not None and c["energy"] != f["energy"]:
                    tag = " **FLIP**"
                    flips += 1
                outs.append(fmt(c) + tag)
            print(f"| {cell} | {pair.split(' vs ')[1]} | {fmt(f)} | " + " | ".join(outs) + " |")
    print(f"\nverdict-class flips (primary, nominal): {flips}")


if __name__ == "__main__":
    main(sys.argv[1:])
