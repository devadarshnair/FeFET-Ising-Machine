"""Corrected-pricing switches of the H8 diagnosis (docs/hw/diagnosis/PROBLEMS_AGREED.md B-1..B-3) for re-pricing stored records.

  b1: noisy Kc2/MESA records stored before 90fa2cf carry restart_cycles = 0 although restarts > 0 (the noisy restart unit never set
      last_cycles). A real restart costs at least 3 cycles, so restart_cycles == 0 with restarts > 0 is always stale; the key is dropped
      so MeasuredCostV2.adjust_counters prices restarts x (6L + 1) (Kc2, L = desc kick_L or 10) or restarts x (4 f n + 3) (MESA).
  b2: CostModel.adc_curve (SPICE E(b) ADC energy, every machine).
  b3: CostModel.tile_bits (tiled ours priced at tile full-scale bits); desc["adc_bits_tile"] is derived from the stored instance
      when the record predates it (H7 fs mode only).
"""
from __future__ import annotations

import copy
import functools

FLAGS = ("b1", "b2", "b2s", "b3", "b3b") + ("t1", "t1f", "t2", "t3", "t4", "t5", "t6", "m3", "m4", "t6s")   # b3b: B-3 SAR savings also cut clocked idle; t*: arch_t.py


def parse(spec: str | None) -> frozenset:
    """'none' / '' -> {}, 'all' -> {b1, b2, b3}, else a comma list."""
    if not spec or spec == "none":
        return frozenset()
    if spec == "all":                    # the three corrections B-1..B-3 (the S2 primary pricing); arch tweaks are never implied
        return frozenset(("b1", "b2", "b3"))
    toks = [x.strip() for x in spec.split(",")]
    out = frozenset(t for t in toks if t != "all") | (frozenset(("b1", "b2", "b3")) if "all" in toks else frozenset())
    bad = out - set(FLAGS)
    assert not bad, f"unknown cost flags {sorted(bad)}"
    return out


def apply(cost, flags: frozenset):
    """A copy of cost with the flags set (recorded on the copy as cost.cost_flags)."""
    c = copy.copy(cost)
    c.adc_curve = "b2" in flags
    c.tile_bits = "b3" in flags
    c.b3b_idle = "b3b" in flags
    c.adc_sar_logic = "b2s" in flags
    c.arch_t = frozenset(f for f in flags if f.startswith("t") or f in ("m3", "m4"))
    c.cost_flags = frozenset(flags)
    return c


def flags_of(cost) -> frozenset:
    return getattr(cost, "cost_flags", frozenset())


def _drop_stale_restart_cycles(c: dict) -> dict:
    if c.get("restarts") and c.get("restart_cycles", None) == 0:
        c = dict(c)
        del c["restart_cycles"]
    return c


@functools.lru_cache(maxsize=None)
def tile_bits_of(family: str, instance: str, adc_delta: int, tile_rows: int) -> int:
    import numpy as np
    from scripts.problems import load as ld
    import machines as ma
    from cim_field import max_tile_column_sum
    qz = ma.quantised(family, instance, "ours")
    _, P, _ = ld._pad_pow2(-qz.d, -qz.P)
    wb = max(1, int(np.abs(P).max()).bit_length())
    return max_tile_column_sum(P, wb, tile_rows).bit_length() + adc_delta


def prepare(rec: dict, cost) -> dict:
    """The record as the flagged cost should price it (unchanged object when no flag needs a change)."""
    flags = flags_of(cost)
    if not flags or rec["desc"].get("kind") == "sw":
        return rec
    rec = dict(rec)
    if "b1" in flags:
        rec["snaps"] = [{**s, "c": _drop_stale_restart_cycles(s["c"])} for s in rec["snaps"]]
        if isinstance(rec.get("counters"), dict):
            rec["counters"] = _drop_stale_restart_cycles(rec["counters"])
    d = rec["desc"]
    if "b3" in flags and d.get("kind") == "ours" and "adc_bits_tile" not in d and rec.get("power_mode") == "fs":
        import pricing as pr
        s = rec["spec"]
        rec["desc"] = {**d, "adc_bits_tile": tile_bits_of(s["family"], s["instance"], int(s.get("adc_delta", 0)), pr.TILE_ROWS)}
    if any(f.startswith("t") for f in flags) and "deg_frac" not in rec["desc"] and "spec" in rec:
        s = rec["spec"]
        machine = {"ours": "ours", "b1": "b1", "b1bs": "b1", "b3": "b3"}.get(d.get("kind"))
        if machine:
            rec["desc"] = {**rec["desc"], **structure_of(s["family"], s["instance"], machine, int(s.get("adc_delta", 0)), rec["desc"]["n_pad"])}
    return rec


@functools.lru_cache(maxsize=None)
def structure_of(family: str, instance: str, machine: str, adc_delta: int, n_pad: int) -> dict:
    """T-2 / T-3 / T-6 structure of a stored record's instance (records written before these keys existed)."""
    import numpy as np
    from scripts.problems import load as ld
    import machines as ma
    from cim_field import max_tile_column_sum
    qz = ma.quantised(family, instance, machine)
    out = {"deg_frac": float(np.count_nonzero(np.asarray(qz.P), axis=1).mean()) / n_pad}
    if machine == "ours":
        _, P, _ = ld._pad_pow2(-qz.d, -qz.P)
        wb = max(1, int(np.abs(P).max()).bit_length())
        planes = np.arange(wb)
        ones = sum(int(((np.maximum(s * P, 0)[None] >> planes[:, None, None]) & 1).sum()) for s in (1, -1))
        out["ones_frac"] = ones / (2 * wb * P.shape[0] * P.shape[1])
        out["adc_bits_tile_rows"] = {str(r): max_tile_column_sum(P, wb, r).bit_length() + adc_delta for r in (64, 128)}
    return out
