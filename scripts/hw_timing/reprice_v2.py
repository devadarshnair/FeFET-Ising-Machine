"""Offline re-pricing of the Stage 3 (H6, Max-Cut / colouring) and Stage 4 (H7, planted colouring + DIMACS) records under measured_v2
(timing study v2). No new runs: the frozen evaluators are re-run on the stored raw counters with the cost model swapped.

VALIDITY. The pipelined select tree stretches state SEL; the selected spin of every step is bit-identical (rtl_spotcheck, tb_select_pipe), so
trajectories, success and every counter except `cycles` are unchanged and the old-behaviour raw counters re-price exactly: cycles += steps *
(sel_lat - 1) (cost_model.MeasuredCostV2.adjust_counters). A different selection BEHAVIOUR (e.g. an overlapped / stale-state pipeline that picks
another spin) would NOT be covered by this: those records would have to be re-run. That is not what select_tree_pipe does.

Variants (increments over published measured_v1; see docs/hw/results/TIMING_PIPELINE_V2.md):
  L1_kc2only   single-cycle tree (v0 behaviour), N = 512 measured, Kc2 charged the measured Kc2-only restart unit
  L2_pipe      + pipelined tree: clock and SEL latency
  L3_sel       + area / leakage of the select tree and the controller charged to every machine
  L3_v2        + the Kc2-only restart unit path in the clock of arm-kc2 machines (PRIMARY measured_v2)
  L3_lane      L3 with the baselines on the lane-path clock and no select tree (stated H7 sensitivity)
  L3_laneclk      L3 with the rule-B tree (the clock stays at about the lane path, more SEL cycles; L3_v2 uses rule A, the shortest step)
  L4_settle<S> L3_v2 + CiM array settle of S ns per read (analog parameter; v1 / L3 charge one cycle)
  L5_ungated   L3_v2 with ungated lane generators (RNG_CG = 0)
  L5_laneratio L3_v2 with e_add / e_lut_read / e_reg_write x the measured annotated / table ratio
Usage: reprice_v2.py --stage 3|4 --raw sim/out/hw/stage3 --variant L3_v2 --out docs/hw/results/timing_v2/h6_L3_v2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for sub in ("testing", "golden", "baselines"):
    sys.path.insert(0, str(HERE.parent / sub))
import evaluate_h6 as e6  # noqa: E402
import evaluate_h7 as e7  # noqa: E402
import fujitsu_da  # noqa: E402
from cost_model import MeasuredCostV2, measured_v2_table, table_hash  # noqa: E402

VARIANTS = {
    "L1_kc2only": dict(restart_cycles=False, pipelined=False, kc2_only=True, charge_select=False, restart_in_clock=False, idle_charge=False),
    "L2_pipe": dict(restart_cycles=False, pipelined=True, kc2_only=True, charge_select=False, restart_in_clock=False, idle_charge=False),
    "L3_sel": dict(restart_cycles=False, pipelined=True, kc2_only=True, charge_select=True, restart_in_clock=False, idle_charge=False),
    "L3_clk": dict(restart_cycles=False, pipelined=True, kc2_only=True, charge_select=True, restart_in_clock=True, idle_charge=False),
    "L3_rc": dict(idle_charge=False),       # + restart cycles priced (Kc2 6L+1, MESA 4d+3 per restart)
    "L3_v2": dict(),                       # PRIMARY: + idle energy of every machine (gated generators), one rule
    "L3_lane": dict(baseline_clock="lane_path"),
    "L3_laneclk": dict(tree="lane"),       # rule B select tree (fewest SEL cycles at the lane-path clock) instead of rule A (shortest step)
    "L5_mesa0": dict(mesa_flip_frac=0.0),
    "L5_mesa1": dict(mesa_flip_frac=1.0),
    "L5_worst": dict(clock_stat="worst"),
    "L3_laneclk_worst": dict(tree="lane", clock_stat="worst"),   # rule-B tree at the worst N = 1024 clock (restart units included)
    "L5_ungated": dict(gen_gated=False),   # lane generators without clock gating (RNG_CG = 0): every lane generator pays its clock every cycle
    "L5_laneratio": dict(),                # lane-logic operation rows scaled by the measured annotated / table ratio (needs --annotated)
}


def kwargs_of(variant: str) -> dict:
    if variant.startswith("L4_settle"):
        return dict(settle_ns=float(variant[len("L4_settle"):]))
    return VARIANTS[variant]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, choices=(3, 4), required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=e6.ev.N_BOOT)
    ap.add_argument("--scale", nargs="*", default=[], help="analog sensitivity factors key=x on cost-table rows (CostModel.scale), e.g. e_adc_conv_bit=2")
    ap.add_argument("--annotated", help="annotated_rows.json (C3): variant L5_laneratio scales the lane-logic operation rows by the measured annotated / table ratio")
    ap.add_argument("--sens", action="store_true", help="Stage 4: also run the evaluator's own sensitivities (slow)")
    a = ap.parse_args()
    kw = kwargs_of(a.variant)
    if a.variant == "L5_laneratio":
        ann = json.loads(Path(a.annotated).read_text())
        a.scale += [f"{k}={ann['lane_ratio']}" for k in ("e_add", "e_lut_read", "e_reg_write")]
    scale = {k: float(x) for k, x in (kv.split("=") for kv in a.scale)}
    if scale:
        kw = {**kw, "scale": scale}
    make = lambda **extra: MeasuredCostV2(**{**kw, **extra})  # noqa: E731
    t = measured_v2_table()
    fujitsu_da.b3_table = lambda: t
    if a.stage == 3:
        e6.CostModel = lambda: make()
        rep = e6.evaluate(a.raw, a.boot)
        md = e6.markdown(rep)
    else:
        e7.MeasuredCost = lambda **k: make(**k) if "baseline_clock" in k and "baseline_clock" not in kw else make()
        rep = e7.evaluate(a.raw, a.boot, sensitivities=a.sens)
        md = e7.markdown(rep)
    h = table_hash(t)
    import hashlib
    from cost_model import TABLE_MEASURED_V2_BLOCKS
    blocks_sha = hashlib.sha256(Path(TABLE_MEASURED_V2_BLOCKS).read_bytes()).hexdigest()
    rep["blocks_sha256"] = blocks_sha          # the per-N block rows (restart units, trees, idle energies) every priced table drew its rows from
    rep["cost_table"], rep["cost_table_sha256"], rep["variant"], rep["variant_kwargs"] = "measured_v2", h, a.variant, dict(kw)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text(f"cost table: measured_v2 (sha256 {h[:16]}), variant {a.variant} {kw}\n\n" + md)
    out.write_text(json.dumps(rep, indent=1, default=float))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
