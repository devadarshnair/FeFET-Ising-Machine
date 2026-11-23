"""Price logged counters with the one canonical cost table, for every machine, at run time and (re-scaled) in the evaluators.

Counters in, energy/time/area out. The functions are the baselines' own (cost_model, yin_mesa, fujitsu_da, hycim_b2); they
are called through small shims so a snapshot of cumulative counters can be priced without the machine object. The cost rules
are those of scripts/smoke_all.py (P6.01), with two additions the ladder needs: B1 restart arms other than MESA are priced by
the cost_model restart rules, and the I10 'no skip' counters (what the same trajectory would cost without I10, exact when the
readout is noise-free) are reconstructed per skipped step.
"""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _sub in ("scripts/golden", "scripts/baselines", "scripts", "."):
    if str(REPO / _sub) not in sys.path:
        sys.path.insert(0, str(REPO / _sub))

import fujitsu_da as b3  # noqa: E402
import yin_mesa as b1  # noqa: E402
from cost_model import Arch, CostModel, tiled_counts, total  # noqa: E402
import arch_t as at  # noqa: E402

TILE_ROWS = 256
FIELDS_KEEP = ("field_reads", "skipped_reads", "array_reads", "array_cell_reads", "adc_conversions", "adc_conv_bits",
               "adc_lowbit_conv", "adc_lowbit_bits", "adds", "rng_draws", "lut_reads", "reg_writes", "array_writes",
               "tcam_searches", "restarts", "gated_cycles", "best_updates", "ramp_updates", "vth_samples", "cycles")


def lane_mask(n_pad: int, n_act: int):
    return None if n_pad == n_act else np.arange(n_pad) < n_act


def unskip_delta(step_rec: dict, bits: int, n: int, w_bits: int, nominal_bits: int, array_lat: int = 1) -> dict:
    """Counters of one I10-skipped step as a performed read at `bits` would have recorded them (counters.OpCounters.record)."""
    cols = 2 * w_bits * n
    d = {"field_reads": 1, "skipped_reads": -1, "array_reads": 1, "array_cell_reads": n * cols, "adc_conversions": cols,
         "adc_conv_bits": cols * bits, "adds": 2 * w_bits * n, "cycles": array_lat + bits,
         "gated_cycles": -step_rec["gated_cycles"]}
    if bits < nominal_bits:
        d["adc_lowbit_conv"] = cols
        d["adc_lowbit_bits"] = cols * bits
    return d


def _b1_shim(desc: dict, c: dict, steps: int):
    n_pad, n_act = desc["n_pad"], desc["n_act"]
    cfg = b1.B1Cfg(adc_bits=desc.get("adc_bits", 8))
    return SimpleNamespace(
        counters=SimpleNamespace(total=c, steps=range(steps)),
        inst=SimpleNamespace(n=n_pad, lane_en=lane_mask(n_pad, n_act)),
        cim=SimpleNamespace(cnt=b1.tile_counts(n_act, cfg), adc_bits=cfg.adc_bits, cfg=SimpleNamespace(w_bits=cfg.w_bits), b1=cfg))


def _b3_shim(desc: dict, c: dict, steps: int, flips: int):
    n_pad, n_act = desc["n_pad"], desc["n_act"]
    return SimpleNamespace(
        counters=SimpleNamespace(total=c, steps=range(steps)), flips=flips,
        inst=SimpleNamespace(n=n_pad, lane_en=lane_mask(n_pad, n_act)), lane_en=lane_mask(n_pad, n_act),
        b3=b3.B3Cfg(offset_rate=int(desc.get("offset_rate", 0))))


def b1_restart_adjust(blocks: dict, area: dict, desc: dict, steps: int, c: dict, cost: CostModel) -> None:
    """B1 priced by b1_energy carries the MESA stall counter + shadow register. For another restart arm use the cost_model
    restart rules (none: no logic; da_offset: offset adder; kc2: stall counter, no shadow register)."""
    arm, n, v = desc["restart"], desc["n_act"], cost.v
    if arm == "mesa":
        return
    time_ns = c["cycles"] * v("t_clk")
    gates = b1.b1_gate_eq(n, cost) - n * v("g_shadow_per_bit") - v("g_stall_counter")
    restart = 0.0
    if arm == "kc2":
        gates += v("g_stall_counter")
        restart = steps * v("e_stall_counter")
    elif arm == "da_offset":
        gates += v("g_offset_adder")
        restart = steps * v("e_offset_add")
    blocks["restart"] = restart
    blocks["leakage"] = cost.leak_fj(gates, time_ns) + steps * v("e_adc_bias_step")
    area["restart"] = (gates - n * (v("g_digital_per_lane") + v("g_rng_per_lane"))) * v("a_nand2")


def tile_rebits(c: dict, desc: dict, cost: CostModel) -> dict:  # noqa: C901
    """B-3 fix (cost.tile_bits): when ours is cut into row tiles, each tile ADC needs only the tile full-scale bits
    (desc["adc_bits_tile"], LSB 1). The full-width conversions are re-priced from desc["adc_bits"] to that width; SAR cycles per
    read shrink by the same amount. Exact for a noise-free LSB-1 readout (sum of exact tile reads = exact column read); a noisy
    run was simulated as one column and is only approximately re-priced (see the engineering notes R3)."""
    rows = at.tile_rows(desc, cost, TILE_ROWS)
    on = getattr(cost, "tile_bits", False) or rows != TILE_ROWS
    tb = desc.get("adc_bits_tile") if rows == TILE_ROWS else desc.get("adc_bits_tile_rows", {}).get(str(rows))
    if not on or math.ceil(desc["n_pad"] / rows) <= 1 or tb is None or {"t1", "t1f"} & at.flags_of(cost):
        return c
    delta = int(desc["adc_bits"]) - int(tb)
    if delta <= 0:
        return c
    c = dict(c)
    full = c["adc_conversions"] - c.get("adc_lowbit_conv", 0)
    c["adc_conv_bits"] -= full * delta
    if c["adc_conversions"]:              # only the full-width reads lose SAR cycles; I7 low-bit reads keep theirs
        c["cycles"] -= round(c.get("array_reads", 0) * full / c["adc_conversions"]) * delta
    return c


def price(desc: dict, c: dict, steps: int, flips: int, cost: CostModel) -> dict:
    """Energy blocks (fJ), time (ns), area blocks (um2), tiles from cumulative counters c after `steps` machine steps."""
    kind = desc["kind"]
    cost = cost.at(desc)
    early = bool(at.flags_of(cost)) or getattr(cost, "b3b_idle", False)
    if early:                                  # B-3b: SAR savings before adjust_counters, so the clocked idle energy sees them too
        cost = copy.copy(cost)                 # per-record attributes (_t6_act) never leak into the shared model
        c = at.transform(desc, c, steps, flips, cost)
        if kind == "ours":
            c = tile_rebits(c, desc, cost)
        if {"t6", "t6s"} & at.flags_of(cost):
            cost._t6_act = at.lane_active_frac(desc, steps, flips, c.get("restarts", 0))
            cost._t6_split = "t6s" in at.flags_of(cost)
    c = cost.adjust_counters(desc, c, steps)
    v = cost.v
    if kind == "ours":
        if not early:
            c = tile_rebits(c, desc, cost)
        t1on = bool({"t1", "t1f"} & at.flags_of(cost))
        rows = desc["n_pad"] if t1on else at.tile_rows(desc, cost, TILE_ROWS)
        cc, tiles = tiled_counts(c, desc["n_pad"], desc["w_bits"], rows)
        arch = Arch(n=desc["n_pad"], w_bits=desc["w_bits"], arm=desc["restart"], row_tiles=tiles,
                    i11=desc.get("tweak") == "i11", i5=desc.get("tweak", "").startswith("i5"),
                    lane_rng=bool(desc.get("i11_temp") or desc.get("hyb_f")), tabu=bool(desc.get("tabu")),
                    kick_target=bool(desc.get("kick_target") or desc.get("kick_conflict")), burst=bool(desc.get("burst_K")),
                    lahc_len=int(desc.get("lahc_len", 0)), cc=bool(desc.get("cc")), breakout=bool(desc.get("bo_K")),
                    esc=bool(desc.get("esc_step")), colour_par=bool(desc.get("colour_par")),
                    field_regs=int(desc["n_pad"] * at.FIELD_BITS * at.t1f(cost, "t1_est_scale")) if ("t1f" in at.flags_of(cost) and "m3" not in at.flags_of(cost)) else 0)
        blocks, area = cost.energy(cc, arch, steps), cost.area(arch)
        at.area_extra(desc, cost, area)
        at.t1f_blocks(desc, cc, cost, area, blocks)
        extra = math.ceil(math.log2(tiles)) * steps * v("t_clk") if tiles > 1 else 0.0
        time_ns = cost.time_ns(cc) + extra
    elif kind in ("b1", "b1bs"):
        if desc.get("adc_fs"):                 # H7 one cost rule: ADC bits = bitlen(max column sum), exact (same trajectory)
            c, desc = b1_rebits(c, {k: v for k, v in desc.items() if k != "adc_fs"}, desc["adc_bits_fs"] - desc.get("adc_bits", 8))
        sh = _b1_shim(desc, c, steps)
        native = kind == "b1"
        cc = b1.b1_native_counts(sh) if native else b1.b1_counts(sh)
        blocks = b1.b1_energy(sh, cost, cc)
        n_act = desc["n_act"]
        area = b1.b1_area(n_act, cost=cost)
        if native:
            area["array"] = cc["tiles"] * b1.TILE * b1.TILE * v("a_array_cell")
            area["adc"] = cc["tiles"] * b1.TILE * v("a_adc_col")
        b1_restart_adjust(blocks, area, desc, steps, cc, cost)
        tiles, time_ns = cc["tiles"], cost.time_ns(cc)
    elif kind == "b3":
        sh = _b3_shim(desc, c, steps, flips)
        blocks = b3.b3_energy(sh, cost)
        area = b3.b3_area(desc["n_act"], cost=cost)
        tiles, time_ns = 1, cost.time_ns(c)
        at.b3_m4(desc, {**c, "sram_bit_reads": b3.b3_counts(sh)["sram_bit_reads"]}, cost, blocks, area, time_ns)
    else:
        raise ValueError(kind)
    cost.charge_restart_unit(desc, blocks, area, time_ns)
    return {"blocks": blocks, "e_total": total(blocks), "time_ns": time_ns, "area": area, "a_total": total(area), "tiles": tiles}


def interp_counters(snaps: list[dict], t: float, key: str = "c") -> tuple[dict, float]:
    """Cumulative counters (and flips) at step t, linear between the snapshots (0 before the first)."""
    ts = [0] + [s["t"] for s in snaps]
    zero = {k: 0 for k in snaps[0][key]}
    cs = [zero] + [s[key] for s in snaps]
    fl = [0] + [s["flips"] for s in snaps]
    t = min(max(t, 0), ts[-1])
    j = max(1, int(np.searchsorted(ts, t, side="left")))
    j = min(j, len(ts) - 1)
    w = 0.0 if ts[j] == ts[j - 1] else (t - ts[j - 1]) / (ts[j] - ts[j - 1])
    return {k: cs[j - 1][k] + w * (cs[j][k] - cs[j - 1][k]) for k in cs[j]}, fl[j - 1] + w * (fl[j] - fl[j - 1])


def b1_rebits(c: dict, desc: dict, delta: int) -> tuple[dict, dict]:
    """B1 ADC bits +delta without a new run: with a 32-row tile the ADC is exact for every width >= 6 bits, so the trajectory is
    unchanged; only the conversion bits (priced from desc["adc_bits"] by yin_mesa.b1_counts) and the SAR cycles of each read move
    (counters.py: cycles = array_lat + bits per read). Returns (counters, desc)."""
    c = dict(c)
    c["cycles"] += delta * c["array_reads"]
    return c, dict(desc, adc_bits=desc.get("adc_bits", 8) + delta)


def b1_native_fs_bits(P: np.ndarray, tile: int) -> int:
    """H7 full-scale rule for B1's native multilevel cells: one cell per coupling and polarity, a tile column sums the levels of
    `tile` rows, so the largest column current is max over tiles, lanes, polarities of sum(level). ADC bits = its bit length
    (exact). Same rule as ours (cim_field.max_column_sum on the bit-plane columns)."""
    P = np.asarray(P, np.int64)
    n = P.shape[0]
    best = 1
    for r in range(0, n, tile):
        blk = P[:, r:r + tile]
        best = max(best, int(np.maximum(blk, 0).sum(axis=1).max(initial=0)), int(np.maximum(-blk, 0).sum(axis=1).max(initial=0)))
    return best.bit_length()


def price_b2(instance: str, proposals: int, x_typ: list, verify: bool, cost: CostModel) -> dict:
    """B2 HyCiM on a QKP instance: energy of `proposals` filter-SA steps (hycim_b2.run_energy, same table), the one-time
    programming (write-verify of the weight and replica arrays), area as smoke_all.run_b2 (profit rows + 16 x 100 filter array)."""
    import hycim as hc
    import hycim_b2 as hb2
    inst = hc.load(instance)
    v = cost.v
    blocks = hb2.run_energy(inst, proposals, np.asarray(x_typ, np.int64), cost)
    tiles = math.ceil(inst.n / hb2.COLS)
    area = {"array": inst.n * hb2.PROFIT_BITS * v("a_array_cell") + tiles * hb2.ROWS * hb2.COLS * 2 * v("a_array_cell"),
            "adc": tiles * hb2.CMP_BITS * v("a_adc_col"), "digital": 0.0, "rng": 0.0, "tcam": 0.0, "restart": 0.0, "leakage": 0.0}
    return {"blocks": blocks, "e_total": total(blocks), "time_ns": proposals * v("t_clk"), "area": area,
            "a_total": total(area), "tiles": tiles, "prog": hb2.program_cost(inst, verify, cost)}


def ours_fs_rebits(c: dict, desc: dict) -> tuple[dict, dict]:
    """H6 'fs' pricing variant: the same noise-free trajectory with the ADC full scale set from the max column sum (I7v2 range, no
    stall switching). The ADC is exact at bitlen(fs) bits (LSB 1) exactly as at bitlen(n), so the trajectory is identical; only the
    conversion bits and the SAR cycles of each performed read change. Valid only for records simulated with I7 off and sigma 0."""
    new = desc["adc_bits_fs"]
    delta = new - desc["adc_bits"]
    c = dict(c)
    c["adc_conv_bits"] = c["adc_conversions"] * new
    c["cycles"] += delta * c["array_reads"]
    return c, dict(desc, adc_bits=new)
