"""P2.08 (FIXES G1/P4): diagnose the integer-vs-float shift of the HQ8/HQ16 arms one factor at a time.

The integer golden model differs from the reference software study's float model (qkp_nb.py) in four places (hw_prior_art 1.4):
  lut   acceptance via the 2^LAB-entry LUT (LAB = 10, 12-bit cap, so -ln u <= ~7.6) instead of u < exp(z)
  lam   Lambda register rounded to an integer
  temp  T register UQ16.16 with a truncating multiply (T floor) instead of exact geometric T
  eoff  E_off step rounded and saturated at 2^24 - 1
DiagMachine replaces each selected factor by its float form and keeps everything else integer; with no factor
selected it is bit-exact to tim_golden.Machine (tests/hw/test_int_float_diag.py). For every arm and factor set
the effect is the mean paired difference in gap points (variant - integer baseline) on the stored D5c runs
(instances 5000-5004 x seeds 100-101, the d5c_rank_check units), with a 95 % t interval. Diagnosis only (info):
it does not evaluate or change the G1 gate rule (the TOST rule is a DRAFT, prereg/drafts/G1_tost.md, author-only).

Run: OPENBLAS_NUM_THREADS=1 NUMBA_CACHE_DIR=sim/out/numba_cache python -I scripts/golden/int_float_diag.py
     [--smoke]  (smoke: 1 instance, 1 seed, 3000 steps, arms HQ8/HX, factor sets base/lut/all)
Chunked (cloud CPU, < 1 h jobs): --chunk INST:SEED:ARM per unit (40 units), then --merge for the table.
Writes sim/out/int_float_diag/result.json and docs/hw/results/P2.08.md (full run only).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import d5c_rank_check as rc  # noqa: E402  (configs, the reference software study float model, instance ports)
import tim_golden as tg  # noqa: E402

FACTORS = ("lut", "lam", "temp", "eoff")
FACTOR_SETS = ((), ("lut",), ("lam",), ("temp",), ("eoff",), FACTORS)
TWO32 = float(1 << 32)


class DiagMachine(tg.Machine):
    """tim_golden.Machine with selected integer factors replaced by their float forms (default restart arm only)."""

    def __init__(self, inst: tg.Instance, floats: tuple[str, ...], lam_f: float, deoff_f: float, alpha_f: float):
        super().__init__(inst)
        assert set(floats) <= set(FACTORS), floats
        self.floats = frozenset(floats)
        self.lam_f, self.deoff_f, self.alpha_f = lam_f, deoff_f, alpha_f
        self.temp_f = float(inst.t0)              # UQ16.16 units, exact geometric
        self.eoff_f = 0.0

    def _penalty_units(self, x, load, cnt_add, cnt_rem):
        inst = self.inst
        if inst.rule == "hw":
            return cnt_add - cnt_rem
        if inst.rule == "penalty":
            sign = np.where(x == 0, 1, -1)
            new_load = load[None, :] + sign[:, None] * inst.W.T
            base = int(np.maximum(load - inst.C, 0).sum())
            return np.maximum(new_load - inst.C[None, :], 0).sum(axis=1) - base
        return np.zeros(inst.n, dtype=np.int64)

    def step(self) -> str:
        inst, fl = self.inst, self.floats
        self.t += 1
        _, geff, elig, self.cnt_add, self.cnt_rem = tg.effective_gain(inst, self.rows, self.x, self.h, self.load)
        gain = np.where(self.x == 1, -self.h, self.h)
        if "lam" in fl:
            units = self._penalty_units(self.x, self.load, self.cnt_add, self.cnt_rem)
            geff = geff + inst.lam * units - self.lam_f * units
        eoff = self.eoff_f if "eoff" in fl else self.eoff
        temp = self.temp_f if "temp" in fl else self.temp
        u = self.lanes.next()
        if "lut" in fl:
            theta = temp * -np.log((u.astype(np.float64) + 0.5) / TWO32) / (1 << tg.TEMP_FRAC)
        elif "temp" in fl:
            addr = (u >> np.uint64(32 - inst.lab)).astype(np.int64)
            theta = temp * self.lut[addr] / float(1 << (tg.TEMP_FRAC + tg.LUT_FRAC))
        else:
            addr = (u >> np.uint64(32 - inst.lab)).astype(np.int64)
            theta = (temp * self.lut[addr]) >> (tg.TEMP_FRAC + tg.LUT_FRAC)
        acc = geff + eoff + theta >= 0
        if elig is not None:
            acc = acc & elig
        r16 = self.sel.next() >> 16
        c = int(acc.sum())
        k = -1
        if c > 0:
            k = int(np.flatnonzero(acc)[(r16 * c) >> 16])
            self._apply_flip(k, int(gain[k]))
            self.eoff_f = 0.0
        else:
            self.eoff = min(self.eoff + self.deoff, tg.EOFF_MAX)
            self.eoff_f += self.deoff_f if self.restart.offset_enabled else 0.0
        if inst.geom:
            self.temp = (self.temp * inst.alpha) >> 32
            self.temp_f *= self.alpha_f
        self.restart.after_step(self)
        ccs = tg.checksum(self.cnt_add + 256 * self.cnt_rem)
        lcs = tg.checksum(self.load) if self.knap else 0
        return (f"{self.t} {k} {c} {tg.checksum(acc.astype(np.int64))} {self.f} {tg.checksum(self.h)} {self.eoff} "
                f"{self.temp} {lcs} {ccs}")


def float_registers(raw: dict, p: dict, kind: str, q: int, gsh: int) -> tuple[float, float]:
    """Unrounded Lambda, E_off step and alpha matching instances.d5c_to_tim (same scaling)."""
    unit = float(np.abs(raw["d"]).mean())
    scale = float(1 << gsh)
    lam = p.get("lam", 0.0)
    lam_f = {"hw": lam * unit * 50 / q * scale, "penalty": lam * unit * scale}.get(kind, 0.0)
    return lam_f, p["dE_off"] * unit * scale


def run_variant(raw_int: dict, params: dict, seed: int, floats: tuple[str, ...], budget: int) -> float:
    p = dict(params)
    rule = p.pop("rule")
    q = int(p.get("Q", 8))
    kind = {"penalty": "penalty", "qhinge": "hw", "filter": "filter"}[rule]
    gsh = int(round(math.log2(q))) if kind == "hw" else 3
    inst = rc.gi.d5c_to_tim(raw_int, rule=kind, T0=p["T0"], T_min=p["T_min"], budget=budget, seed=seed,
                            lam=p.get("lam", 0.0), dE_off=p["dE_off"], Q=q, gsh=gsh)
    lam_f, deoff_f = float_registers(raw_int, p, kind, q, gsh)
    alpha_f = (p["T_min"] / p["T0"]) ** (1.0 / max(budget - 1, 1))
    m = DiagMachine(inst, floats, lam_f, deoff_f, alpha_f)
    m.temp_f = p["T0"] * float(np.abs(raw_int["d"]).mean()) * (1 << gsh) * (1 << tg.TEMP_FRAC)
    return float(m.run(keep_trace=False).best_f)


def t_ci(v: list[float]) -> tuple[float, float]:
    from scipy import stats
    a = np.asarray(v, dtype=float)
    if len(a) < 2:
        return float(a.mean()), float("nan")
    return float(a.mean()), float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / math.sqrt(len(a)))


def run_unit(inst: int, seed: int, arm: str, params: dict, sets: tuple, names: list[str], budget: int) -> dict[str, float]:
    """Best objective of one (instance, seed, arm): the float model and every factor set."""
    raw_f = rc.qk.make_instance(rc.N_ITEMS, rc.M_CONS, inst)
    raw_i = rc.gi.d5c_make_instance(rc.N_ITEMS, rc.M_CONS, inst)
    pf = dict(params[arm])
    rule = pf.pop("rule")
    out = {"float": rc.qk.run(raw_f, rule, budget=budget, seed=seed, **pf)["best_f"]}
    for s, nm in zip(sets, names):
        out[nm] = run_variant(raw_i, params[arm], seed, s, budget)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--chunk", metavar="INST:SEED:ARM", help="run one unit (all factor sets) and write its JSON; no table")
    ap.add_argument("--merge", action="store_true", help="build the table from all chunk JSONs (every unit must exist)")
    args = ap.parse_args()
    insts, seeds, arms, sets = rc.INSTS, rc.SEEDS, rc.ARMS, FACTOR_SETS
    budget = rc.H.budget(rc.N_ITEMS)
    if args.smoke:
        insts, seeds, arms, sets, budget = insts[:1], seeds[:1], ("HQ8", "HX"), ((), ("lut",), FACTORS), 3000
    params = {a: rc.H.engine_params(c, rc.N_ITEMS) for a, c in rc.selected_configs().items() if a in arms}
    names = ["+".join(s) or "int" for s in sets]
    out = HERE.parent.parent / "sim/out/int_float_diag"
    chunk_dir = out / ("chunks_smoke" if args.smoke else "chunks")
    best, t0 = {}, time.time()
    if args.chunk:
        inst, seed, arm = args.chunk.split(":")
        inst, seed = int(inst), int(seed)
        assert inst in insts and seed in seeds and arm in arms, args.chunk
        res = run_unit(inst, seed, arm, params, sets, names, budget)
        chunk_dir.mkdir(parents=True, exist_ok=True)
        tmp = chunk_dir / f".{inst}_{seed}_{arm}.tmp"
        tmp.write_text(json.dumps(dict(inst=inst, seed=seed, arm=arm, budget=budget, best=res)))
        tmp.rename(chunk_dir / f"{inst}_{seed}_{arm}.json")
        print(f"chunk {args.chunk} done ({time.time() - t0:.0f} s)", flush=True)
        return 0
    if args.merge:
        for inst in insts:
            for seed in seeds:
                for arm in arms:
                    c = json.loads((chunk_dir / f"{inst}_{seed}_{arm}.json").read_text())
                    assert c["budget"] == budget, "chunk budget differs"
                    for nm, v in c["best"].items():
                        best[(inst, seed, arm, nm)] = v
    else:
        for inst in insts:
            for seed in seeds:
                for arm in arms:
                    for nm, v in run_unit(inst, seed, arm, params, sets, names, budget).items():
                        best[(inst, seed, arm, nm)] = v
                print(f"inst {inst} seed {seed} done ({time.time() - t0:.0f} s)", flush=True)
    bk = {i: max(v for k, v in best.items() if k[0] == i) for i in insts}

    def gap(i, s, a, nm):
        return 100.0 * (bk[i] - best[(i, s, a, nm)]) / bk[i]

    rows = []
    for a in arms:
        for nm in names[1:] + ["float"]:
            d = [gap(i, s, a, nm) - gap(i, s, a, "int") for i in insts for s in seeds]
            mean, hw = t_ci(d)
            rows.append(dict(arm=a, variant=nm, effect=mean, ci95=hw, n=len(d)))
    mean_gap = {a: {nm: float(np.mean([gap(i, s, a, nm) for i in insts for s in seeds])) for nm in names + ["float"]}
                for a in arms}
    vals = all(np.isfinite(r["effect"]) for r in rows)
    result = dict(smoke=args.smoke, budget=budget, insts=insts, seeds=seeds, mean_gap=mean_gap, effects=rows,
                  finite=vals, seconds=round(time.time() - t0))
    out.mkdir(parents=True, exist_ok=True)
    (out / ("smoke.json" if args.smoke else "result.json")).write_text(json.dumps(result, indent=1, default=str))
    lines = [f"Effect of switching each integer factor to float, gap points (variant - integer), mean ± 95 % t "
             f"half-width over {len(insts) * len(seeds)} paired runs, budget {budget}. Negative = float form better.",
             "", "| arm | " + " | ".join(names[1:] + ["float model"]) + " |", "|---|" + "---|" * len(names)]
    for a in arms:
        cells = [f"{r['effect']:+.3f} ± {r['ci95']:.3f}" for r in rows if r["arm"] == a]
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    lines += ["", "| arm | " + " | ".join(names + ["float"]) + " |", "|---|" + "---|" * (len(names) + 1)]
    for a in arms:
        lines.append(f"| {a} | " + " | ".join(f"{mean_gap[a][nm]:.3f}" for nm in names + ["float"]) + " |")
    table = "\n".join(lines)
    print(table, f"\nfinite: {vals} ({result['seconds']} s)", sep="\n")
    if not args.smoke:
        rep = HERE.parent.parent / "docs/hw/results/P2.08.md"
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text("# P2.08 integer vs float diagnosis (info, not a gate result)\n\n" + table + "\n")
    return 0 if vals else 1


if __name__ == "__main__":
    sys.exit(main())
