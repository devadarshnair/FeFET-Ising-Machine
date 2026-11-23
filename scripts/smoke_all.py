"""P6.01 end-to-end smoke matrix. SMOKE ONLY: no contrast between machines is computed or reported.

Matrix (rows in sim/out/hw/P6.01/smoke.csv; count = 4 arms x 2 power x 3 families x VERIFY_ON + extras, see ROWS_EXPECTED):
  ours : restart arm none/da_offset/mesa/kc2 x (I7+I10 off / on) x {maxcut, maxsat>256 spins (R6 tiling), colouring}
         level-0 verify ON (R7) ; plus one as-measured row (verify OFF) on the >256 MaxSAT
  B1   : Yin MESA, native 3-bit cells with write-verify on all levels incl. level 0 (A1/A2 final), 3 families (MaxSAT >256
         spins tiled 32x32); plus the bit-sliced secondary arm (3 rows) and as-measured rows of both on the >256 MaxSAT
  B2   : HyCiM filter-SA, 3 families (n > 100 columns tiled in 100-column tiles), verify ON ; plus one as-measured row
  B3   : Fujitsu DA, 3 families (digital SRAM scales)
  extra H2 rungs (kc2, power off, verify ON): I11 greedy+kick, I5 Vth noise (hold/group 1 and 4) x 3 families; I3 fixed / ramped /
  exact filter on a 14-item knapsack (D5c generator), CiM field path. Cost rows of I3/I5 are placeholders (energy_table_tweaks_i11_i3_i5.csv).
Level-0 verify ON (A2 final) and tiling (R6/A5) follow the project rulings; as-measured rows are extra arms. Every machine is costed from the same
canonical table (cost_model.canonical_table, char_v1 rows). Checks per row: finite numbers, cost blocks sum to total,
counter consistency; across rows: restarts and I10-skipped reads and I7 low-bit conversions were exercised.
RTL spot check (IMPL_PLAN P6.01): +24 rows machine=rtl_check, +14 tweak rows (I11/I5 on 3 families x I7/I10, I3 off/ramped on a knapsack; scripts/rtl_spotcheck.py; Verilator tim_top from HW_RTL_ROOT, default
sibling worktree hw-p3, vs golden, 3 small families x 4 arms x I7/I10 off/on, 300 steps, bit-exact trace + activity counters). Seeds: one.
Run: local job queue --rss 3 -- python scripts/smoke_all.py [--steps 300]
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
for sub in ("scripts/golden", "scripts/baselines", "scripts", "."):
    sys.path.insert(0, str(REPO / sub))

import fujitsu_da as b3  # noqa: E402
import rtl_spotcheck as rsc  # noqa: E402
import hycim as hc  # noqa: E402
import hycim_b2 as b2  # noqa: E402
import yin_mesa as b1  # noqa: E402
from cim_field import CimCfg  # noqa: E402
from cost_model import Arch, CostModel, tiled_counts, total  # noqa: E402
from counters import CycleCfg  # noqa: E402
from instances import d5c_make_instance, d5c_to_tim, qubo_instance  # noqa: E402
from power import PowerCfg  # noqa: E402
from restart import RestartCfg  # noqa: E402
from tim_golden import Machine  # noqa: E402
from tweaks import TweakCfg  # noqa: E402

from scripts.problems import load as ld  # noqa: E402
from scripts.problems import spin_table as st  # noqa: E402

OUT = REPO / "sim" / "out" / "hw" / "P6.01"
OURS_TILE_ROWS = ld.OURS_MAX_SPINS     # 256: our native array; larger instances tile rows by this (R6)
B2_TILE = b2.COLS                      # 100 columns
ARMS = ("none", "da_offset", "mesa", "kc2")
T_START, T_END = 3.0, 0.1
SEED = 0               # added to every instance/run seed; main() sets it per --seeds pass (0 = registered seeds)


def families() -> dict[str, ld.MappedQubo]:
    return {"maxcut": ld.maxcut_instances()[1],                                   # torus8, 64 spins
            "maxsat": ld.from_problem("maxsat", st.random_ksat(60, round(4.26 * 60), 3, seed=300), 60),   # 316 spins
            "colouring": ld.colouring_instances()[1]}


def pad_pow2(mq, qz):
    """Golden Machine MAXIMISES f = d.x + x.P.x/2 while the mapped QUBO is a minimisation form: the machines are fed (-d, -P)
    (same convention as scripts/testing/machines.py) and best_energy = -best_f + offset (see machine_energy)."""
    d, P, lane = ld._pad_pow2(-qz.d, -qz.P)
    return d, P, lane


def machine_energy(mq, best_f) -> int:
    return -int(best_f) + mq.offset


def ours_instance(mq, steps, seed, machine):
    qz = ld.quantise(mq, ld.QUANT[machine])
    d, P, lane = pad_pow2(mq, qz)
    inst = qubo_instance(d, P, seed=seed, steps=steps, t_start=T_START, t_end=T_END, deoff=0 if machine == "b1" else 1)
    if mq.spins != len(d):
        inst = type(inst)(**{**inst.__dict__, "lane_en": lane})
    return inst, qz


def finite(d: dict) -> bool:
    return all(math.isfinite(v) for v in d.values() if isinstance(v, (int, float)))


def base_row(machine, arm, family, mq, i7_i10="", tweak=""):
    return dict(machine=machine, arm=arm, family=family, instance=mq.name, spins=mq.spins, mapped_sha256=mq.sha256()[:16],
                i7_i10=i7_i10, tweak=tweak, rng_draws=0, lut_reads=0, ramp_updates=0, vth_samples=0, verify_l0="", tiles=1, steps=0, best_energy="", restarts=0, skipped_reads=0, lowbit_conv=0,
                array_reads=0, adc_conversions=0, adc_conv_bits=0, flips=0, time_ns=0.0, e_total_fJ=0.0, e_blocks_sum_fJ=0.0,
                e_array=0.0, e_adc=0.0, e_digital=0.0, e_rng=0.0, e_sram=0.0, e_filter=0.0, e_restart=0.0, e_leak=0.0,
                a_total_um2=0.0, e_program_fJ=0.0, t_program_us=0.0, status="", note="", wall_s=0.0)


def fill_energy(row, blocks, area):
    row.update(e_total_fJ=total(blocks), e_blocks_sum_fJ=math.fsum(blocks.values()), a_total_um2=total(area),
               e_array=blocks.get("array", 0.0), e_adc=blocks.get("adc", 0.0), e_digital=blocks.get("digital", 0.0),
               e_rng=blocks.get("rng", 0.0), e_sram=blocks.get("sram", 0.0), e_filter=blocks.get("filter", 0.0),
               e_restart=blocks.get("restart", 0.0), e_leak=blocks.get("leakage", 0.0))


def run_ours(mq, family, arm, power_on, verify, steps, cost, tweak="", tw=None):
    inst, qz = ours_instance(mq, steps, 11 + SEED, "ours")
    n = inst.n
    wb = max(1, int(np.abs(qz.P).max()).bit_length())
    b_hi = max(4, n.bit_length())            # exact field at the full-n sum; tiled per-tile conversion costed in tiled_counts
    pw = PowerCfg(i7=power_on, i10=power_on, b_hi=b_hi, b_lo=max(3, b_hi - 4), K_p=5, K_g=8) if power_on else None
    m = Machine(inst, RestartCfg(arm), cim=CimCfg(adc_bits=b_hi, w_bits=wb), power=pw, counters=CycleCfg(), tweaks=tw)
    res = m.run()
    c, tiles = tiled_counts(m.counters.total, n, wb, OURS_TILE_ROWS)
    arch = Arch(n=n, w_bits=wb, arm=arm, row_tiles=tiles, i11=bool(tw and tw.i11), i5=bool(tw and tw.i5))
    blocks, area = cost.energy(c, arch, steps), cost.area(arch)
    cells = m.cim.pos.size + m.cim.neg.size
    zeros = int(cells - m.cim.pos.sum() - m.cim.neg.sum())
    prog = cost.program_cost(cells, zeros, verify, "bin")
    row = base_row("ours", arm, family, mq, i7_i10="on" if power_on else "off", tweak=tweak)
    row.update(verify_l0="on" if verify else "as_measured", tiles=tiles, steps=steps, best_energy=machine_energy(mq, res.best_f),
               restarts=c["restarts"], skipped_reads=c["skipped_reads"], lowbit_conv=c["adc_lowbit_conv"],
               array_reads=c["array_reads"], adc_conversions=c["adc_conversions"], adc_conv_bits=c["adc_conv_bits"],
               rng_draws=c["rng_draws"], lut_reads=c["lut_reads"], ramp_updates=c["ramp_updates"], vth_samples=c["vth_samples"],
               flips=res.flips, time_ns=cost.time_ns(c) + (math.ceil(math.log2(tiles)) * steps * cost.v("t_clk") if tiles > 1 else 0),
               **prog)
    fill_energy(row, blocks, area)
    row["note"] = f"N={n} w_bits={wb} adc_bits={b_hi}; tiles are row tiles of {OURS_TILE_ROWS}; extra adder-tree cycles included"
    return row


class _KnapView:
    """Minimal stand-in for a MappedQubo row label (knapsack has no QUBO mapping)."""
    def __init__(self, name, spins):
        self.name, self.spins, self.offset = name, spins, 0

    def sha256(self):
        return f"{self.name}"


def run_i3(rule, tw, steps, cost, tweak):
    """I3 rung: fixed penalty (rule penalty) / ramped penalty / HyCiM-role exact filter, on a small knapsack, CiM field path."""
    raw = d5c_make_instance(14, 2, 0)
    inst = d5c_to_tim(raw, rule=rule, T0=2.0, T_min=0.05, budget=steps, seed=SEED, lam=6.0, dE_off=0.5, Q=8)
    wb = max(1, int(np.abs(inst.P).max()).bit_length())
    m = Machine(inst, RestartCfg("da_offset"), cim=CimCfg(adc_bits=16, w_bits=wb), counters=CycleCfg(), tweaks=tw)
    res = m.run()
    c = m.counters.total
    arch = Arch(n=inst.n, w_bits=wb, arm="da_offset", tcam_rows=0 if m.rows is None else inst.n * inst.m * inst.q,
                i3=bool(tw and tw.i3))
    blocks, area = cost.energy(c, arch, steps), cost.area(arch)
    cells = m.cim.pos.size + m.cim.neg.size
    prog = cost.program_cost(cells, int(cells - m.cim.pos.sum() - m.cim.neg.sum()), True, "bin")
    row = base_row("ours", "da_offset", "knapsack", _KnapView(f"qkp14x2_{rule}", inst.n), tweak=tweak)
    row.update(verify_l0="on", tiles=1, steps=steps, best_energy=int(res.best_f), restarts=c["restarts"],
               skipped_reads=c["skipped_reads"], lowbit_conv=c["adc_lowbit_conv"], array_reads=c["array_reads"],
               adc_conversions=c["adc_conversions"], adc_conv_bits=c["adc_conv_bits"], rng_draws=c["rng_draws"],
               lut_reads=c["lut_reads"], ramp_updates=c["ramp_updates"], vth_samples=c["vth_samples"], flips=res.flips,
               time_ns=cost.time_ns(c), **prog)
    fill_energy(row, blocks, area)
    row["note"] = f"rule={rule}; QKP n=14 m=2 (D5c generator seed 0), knapsack best = feasible objective; tcam pricer rows=n*m*q if hw"
    return row


def native_levels_program(cost, inst_p, nb, tile, verify):
    """B1 native 3-bit cells (A1): write-verify on levels 1-7 (open-loop sigma/mu, +-5 % window, geometric attempts) and, with
    level-0 verify (R7/A2 final), level 0 with the 3-bit window attempts of the canonical table; as-measured = level 0 once."""
    with open(b2.CELL_CSV, newline="") as fh:
        cell = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(fh)]
    size = nb * tile
    P = np.zeros((size, size), np.int64)
    P[:inst_p.shape[0], :inst_p.shape[1]] = inst_p
    lev = np.concatenate([np.maximum(P, 0).ravel(), np.maximum(-P, 0).ravel()])
    cnt = np.bincount(lev, minlength=8)
    e = t = 0.0
    for k in range(8):
        if k == 0:
            a = cost.v("n_l0_attempts_3bit") if verify else 1.0
        else:
            a = 1.0 / math.erf(b2.WV_TOL / (cell[k]["sigma_over_mu"] * math.sqrt(2.0)))
        vr = verify or k > 0
        e += cnt[k] * a * (cell[k]["e_write_fJ"] + (cell[k]["e_read_fJ"] if vr else 0.0))
        t += cnt[k] * a * (cell[k]["t_write_us"] + (b2.T_VERIFY_US if vr else 0.0))
    return {"e_program_fJ": e, "t_program_us": t}


def run_b1(mq, family, verify, steps, cost, native=True):
    """native=True: Yin 3-bit cells with write-verify on all levels (A1 primary); False: bit-sliced secondary arm."""
    inst, qz = ours_instance(mq, steps, 11 + SEED, "b1")
    m = b1.b1_machine(inst)
    res = m.run(steps, keep_trace=False)
    c = b1.b1_native_counts(m) if native else b1.b1_counts(m)
    blocks = b1.b1_energy(m, cost, c)
    n_act = b1.n_active(inst)
    cnt = b1.tile_counts(n_act)
    area = b1.b1_area(n_act, cost=cost)
    if native:
        area["array"] = c["tiles"] * b1.TILE * b1.TILE * cost.v("a_array_cell")
        area["adc"] = c["tiles"] * b1.TILE * cost.v("a_adc_col")
        prog = native_levels_program(cost, np.asarray(qz.P), cnt["blocks"], b1.TILE, verify)
        tiles = c["tiles"]
    else:
        cells = cnt["tiles"] * b1.TILE * b1.TILE
        nonzero = int(sum(tf.pos.sum() + tf.neg.sum() for tf in m.cim.tiles))
        prog = cost.program_cost(cells, cells - nonzero, verify, "bin")
        tiles = cnt["tiles"]
    row = base_row("b1", "mesa" if native else "mesa_bitsliced", family, mq)
    row.update(verify_l0="on" if verify else "as_measured", tiles=tiles, steps=steps, best_energy=machine_energy(mq, res.best_f),
               restarts=c["restarts"], skipped_reads=c["skipped_reads"], lowbit_conv=c["adc_lowbit_conv"],
               array_reads=c["array_reads"], adc_conversions=c["adc_conversions"], adc_conv_bits=c["adc_conv_bits"],
               flips=res.flips, time_ns=cost.time_ns(c), **prog)
    fill_energy(row, blocks, area)
    row["note"] = (f"Yin native 3-bit cells (A1), 32x32 tiles, {cnt['blocks']}x{cnt['blocks']} blocks x 2 polarities" if native
                   else f"bit-sliced secondary arm: {cnt['blocks']}x{cnt['blocks']} blocks x 6 planes")
    return row


def run_b2(mq, family, verify, steps, cost):
    n = mq.spins
    tiles = math.ceil(n / B2_TILE)
    qd = np.ones(n, np.int64)
    inst = hc.Inst(mq.name, -mq.d, -np.triu(mq.P, 1), qd, int(qd.sum()))      # unit weights, capacity = n: filter never binds
    T = hc.temps("S1", max(1.0, float(np.abs(mq.d).max() + np.abs(mq.P).max())), steps)
    x0, y0 = hc.initial_state(inst, "filter", hc.seed_of(601 + SEED, 0))
    best, rej, final, mine = hc.run_one(inst, "filter", T, x0, y0, hc.seed_of(601 + SEED, 1))
    sub = [hc.Inst(f"{mq.name}_t{k}", -mq.d[k * B2_TILE:(k + 1) * B2_TILE], np.zeros((len(qd[k * B2_TILE:(k + 1) * B2_TILE]),) * 2),
                   qd[k * B2_TILE:(k + 1) * B2_TILE], len(qd[k * B2_TILE:(k + 1) * B2_TILE])) for k in range(tiles)]
    # energy: ΔE row reads + ADC use the full n (shared with the profit matrix); filter energy summed over tiles; the
    # extra tile decisions cost one 1-bit comparator conversion per step each (b2.adc_energy_fj) and the partial decisions are combined by (tiles-1) adds
    v = cost.v
    xr = np.ones(n, np.int64)
    filt = sum(b2.filter_energy_fj(s, xr[k * B2_TILE:(k + 1) * B2_TILE]) for k, s in enumerate(sub))
    blocks = {"array": steps * n * b2.PROFIT_BITS * v("e_array_cell_read"),
              "adc": b2.adc_energy_fj(steps, tiles, cost),
              "digital": steps * (2 * v("e_add") + v("e_reg_write") + (tiles - 1) * v("e_add")),
              "rng": steps * 4 * v("e_rng_draw"), "filter": steps * filt, "restart": 0.0,
              "leakage": b2.leakage_fj(steps, cost)}
    progs = [b2.program_cost(s, verify, cost) for s in sub]
    area = {"array": n * b2.PROFIT_BITS * v("a_array_cell") + tiles * b2.ROWS * b2.COLS * 2 * v("a_array_cell"),
            "adc": tiles * b2.CMP_BITS * v("a_adc_col"), "digital": 0.0, "rng": 0.0, "tcam": 0.0, "restart": 0.0, "leakage": 0.0}
    row = base_row("b2", "hycim", family, mq)
    row.update(verify_l0="on" if verify else "as_measured", tiles=tiles, steps=steps, best_energy=-float(best) + mq.offset,
               array_reads=steps, adc_conversions=steps * (b2.PROFIT_BITS + tiles - 1), adc_conv_bits=steps * (b2.PROFIT_BITS + tiles - 1),
               time_ns=steps * v("t_clk"), e_program_fJ=sum(p["e_program_fJ"] for p in progs),
               t_program_us=sum(p["t_program_us"] for p in progs))
    fill_energy(row, blocks, area)
    row["note"] = f"HyCiM filter-SA on unit-weight/capacity=n (filter never binds); {tiles} column tiles of {B2_TILE}; rej={int(rej)}"
    return row


def run_b3(mq, family, steps, cost):
    inst, _ = ours_instance(mq, steps, 11 + SEED, "b3")
    m = b3.b3_machine(inst)
    res = m.run(steps, keep_trace=False)
    c = b3.b3_counts(m)
    blocks = b3.b3_energy(m, cost)
    n_act = inst.n if inst.lane_en is None else int(inst.lane_en.sum())
    area = b3.b3_area(n_act, cost=cost)
    row = base_row("b3", "da_offset", family, mq)
    row.update(steps=steps, best_energy=machine_energy(mq, res.best_f), restarts=c["restarts"], flips=res.flips,
               time_ns=cost.time_ns(c))
    fill_energy(row, blocks, area)
    row["note"] = f"digital SRAM scales with N={n_act}; sram_bit_reads={c['sram_bit_reads']}"
    return row


def run_rtl_cell(family, mq, arm, power_on, steps, cell=None):
    """RTL spot check cell (P6.01 acceptance): Verilator tim_top vs golden, bit-exact state/energy (+ activity) traces.
    cell: thunk of a tweak cell (I11 / I5 / I3, rtl_spotcheck.tweak_cells); the default is the tweaks-off cell."""
    res = cell() if cell else rsc.run_cell(rsc.rtl_root(), family, mq, arm, power_on, steps)
    mq = mq or SimpleNamespace(name=f"rtl_{res['family']}_{res['tweak']}", spins=res["n"], sha256=lambda: "")
    row = base_row("rtl_check", res["arm"], res["family"], mq, i7_i10=res["i7_i10"], tweak="" if res["tweak"] == "off" else "rtl_" + res["tweak"])
    row.update(steps=steps, restarts=res["restarts"], spins=res["n"], note=f"trace_lines={res['trace_lines']} act_lines={res['act_lines']} "
                                                                       f"{res['note']}".strip())
    row["mismatch"] = res["status"] != "ok"
    return row


def check_row(r: dict) -> list[str]:
    if r["machine"] == "rtl_check":
        return ["RTL != golden"] if r.pop("mismatch") else []
    bad = []
    if not finite(r):
        bad.append("non-finite")
    if abs(r["e_total_fJ"] - r["e_blocks_sum_fJ"]) > 1e-9 * max(1.0, abs(r["e_total_fJ"])) or r["e_total_fJ"] <= 0:
        bad.append("cost sum")
    if r["adc_conv_bits"] < r["adc_conversions"] or r["adc_conversions"] < 0:
        bad.append("adc counters")
    if r["machine"] in ("ours", "b1") and r["array_reads"] + r["skipped_reads"] != r["steps"]:
        bad.append("reads+skipped != steps")
    if r["machine"] in ("ours", "b1") and (r["e_program_fJ"] <= 0 or r["t_program_us"] <= 0):
        bad.append("program cost")
    if r["spins"] > 256 and r["machine"] == "ours" and r["tiles"] < 2:
        bad.append("R6 tiling missing")
    if r["spins"] > 32 and r["machine"] == "b1" and r["tiles"] < 2:
        bad.append("R6 tiling missing")
    if r["spins"] > 100 and r["machine"] == "b2" and r["tiles"] < 2:
        bad.append("R6 tiling missing")
    return bad


def build_jobs(steps, cost, fam):
    jobs = []
    for f, mq in fam.items():
        for arm in ARMS:
            for pw in (False, True):
                jobs.append(("ours", lambda mq=mq, f=f, arm=arm, pw=pw: run_ours(mq, f, arm, pw, True, steps, cost)))
        jobs.append(("b1", lambda mq=mq, f=f: run_b1(mq, f, True, steps, cost)))
        jobs.append(("b1", lambda mq=mq, f=f: run_b1(mq, f, True, steps, cost, native=False)))
        jobs.append(("b2", lambda mq=mq, f=f: run_b2(mq, f, True, steps, cost)))
        jobs.append(("b3", lambda mq=mq, f=f: run_b3(mq, f, steps, cost)))
    ms = fam["maxsat"]
    jobs.append(("ours", lambda: run_ours(ms, "maxsat", "kc2", True, False, steps, cost)))
    jobs.append(("b1", lambda: run_b1(ms, "maxsat", False, steps, cost)))
    jobs.append(("b1", lambda: run_b1(ms, "maxsat", False, steps, cost, native=False)))
    jobs.append(("b2", lambda: run_b2(ms, "maxsat", False, steps, cost)))
    tweaks = {"i11": TweakCfg(i11=True), "i5_h1g1": TweakCfg(i5=True), "i5_h4g4": TweakCfg(i5=True, hold=4, group=4)}
    for f, mq in fam.items():
        for label, tw in tweaks.items():
            jobs.append(("ours", lambda mq=mq, f=f, label=label, tw=tw: run_ours(mq, f, "kc2", False, True, steps, cost, label, tw)))
    for label, rule, tw in (("i3_fixed", "penalty", None), ("i3_ramp", "penalty", TweakCfg(i3=True, ramp_steps=steps // 2)),
                            ("i3_filter", "filter", None)):
        jobs.append(("ours", lambda rule=rule, tw=tw, label=label: run_i3(rule, tw, steps, cost, label)))
    for f, mq in rsc.small_families().items():
        for pw in (False, True):
            for arm in ARMS:
                jobs.append(("rtl", lambda mq=mq, f=f, arm=arm, pw=pw: run_rtl_cell(f, mq, arm, pw, steps)))
    for cell in rsc.tweak_cells(steps):
        jobs.append(("rtl", lambda cell=cell: run_rtl_cell("tweak", None, "", False, steps, cell)))
    return jobs


def set_seed(seed):
    global SEED
    SEED = seed
    rsc.SEED = seed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--seeds", type=int, default=1, help="number of seed passes (seed offsets 0..k-1; 0 = registered seeds)")
    args = ap.parse_args()
    steps, seeds = args.steps, args.seeds
    cost = CostModel()
    fam = families()
    jobs = []
    for seed in range(seeds):
        set_seed(seed)
        jobs += [(name, seed, job) for name, job in build_jobs(steps, cost, fam)]
    rows = []
    for name, seed, job in jobs:
        t0 = time.time()
        set_seed(seed)
        r = job()
        r["seed"] = seed
        r["wall_s"] = round(time.time() - t0, 2)
        bad = check_row(r)
        r["status"] = "ok" if not bad else "FAIL:" + ",".join(bad)
        rows.append(r)
        print(f"{r['machine']:5s} {r['arm']:9s} {r['family']:9s} n={r['spins']:4d} i7i10={r['i7_i10']:3s} verify={r['verify_l0']:11s} "
              f"seed={r['seed']} tw={r['tweak']:8s} tiles={r['tiles']:3d} restarts={r['restarts']:3d} skip={r['skipped_reads']:3d} low={r['lowbit_conv']:6d} "
              f"E={r['e_total_fJ']:.4g} fJ  {r['wall_s']}s  {r['status']}", flush=True)
    agg = {"restarts exercised": any(r["restarts"] > 0 for r in rows if r["machine"] == "ours" and r["arm"] in ("mesa", "kc2")),
           "I10 skipped reads": any(r["skipped_reads"] > 0 for r in rows if r["i7_i10"] == "on"),
           "I7 low-bit conversions": any(r["lowbit_conv"] > 0 for r in rows if r["i7_i10"] == "on"),
           "B1 MESA restarts": any(r["restarts"] > 0 for r in rows if r["machine"] == "b1"),
           "I11 no lane RNG / LUT": all(r["lut_reads"] == 0 and r["rng_draws"] == r["steps"] + 10 * r["restarts"]
                                        for r in rows if r["tweak"] == "i11"),
           "I5 device samples, no LUT": all(r["vth_samples"] > 0 and r["lut_reads"] == 0 for r in rows if r["tweak"].startswith("i5")),
           "I3 ramp updated": all(r["ramp_updates"] == steps // 2 for r in rows if r["tweak"] == "i3_ramp"),
           "RTL spot check 24 cells per seed bit-exact": sum(r["machine"] == "rtl_check" and not r["tweak"] and r["status"] == "ok" for r in rows) == 24 * seeds,
           "RTL I11/I3/I5 cells bit-exact (14 per seed)": sum(r["machine"] == "rtl_check" and r["tweak"] != "" and r["status"] == "ok" for r in rows) == 14 * seeds,
           "RTL restarts exercised": any(r["restarts"] > 0 for r in rows if r["machine"] == "rtl_check"),
           ">256 MaxSAT on all four": {r["machine"] for r in rows if r["family"] == "maxsat" and r["spins"] > 256} == {"ours", "b1", "b2", "b3"}}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "smoke.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    import shutil
    shutil.copy(OUT / "smoke.csv", REPO / "docs" / "hw" / "results" / "P6.01_smoke.csv")      # tracked copy (sim/out is ignored)
    print(f"rows={len(rows)} (expected {len(jobs)})", agg)
    ok = all(r["status"] == "ok" for r in rows) and all(agg.values()) and len(rows) == len(jobs)
    print("SMOKE", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
