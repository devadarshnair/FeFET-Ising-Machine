"""Exact transition chain of the machine with the dynamic offset ON (P3.05, FIXES R7).

With deoff > 0 the state is (x, k): the spin vector x and the number k of consecutive steps without an accepted lane,
E_off = k * deoff (it resets to 0 on a flip). At fixed T (geom = 0) one step from (x, k) is: every lane accepts with
its exact probability over the 2^lab LUT addresses (geff_i + E_off + theta >= 0), independently; if c lanes accept,
one is chosen with the count-tree probabilities (select_prob), the flip moves to (x ^ e_i, 0); if c = 0 the state
moves to (x, k + 1). The chain is finite: k stops growing when every lane accepts with probability 1 in every x.
Restricted to n <= 10, geom = 0, no knapsack. `pick = "first"` is the deliberately wrong lowest-index selector;
`ignore_off = True` is the deliberately wrong model that ignores E_off in the acceptance (a no-offset machine).
"""
from __future__ import annotations

import numpy as np
from scipy import stats

import tim_golden as tg


def k_max(inst: tg.Instance, lut: np.ndarray) -> int:
    n = inst.n
    theta = (inst.t0 * lut) >> (tg.TEMP_FRAC + tg.LUT_FRAC)
    need = 0
    for xs in range(1 << n):
        x = np.array([(xs >> i) & 1 for i in range(n)], dtype=np.int64)
        gain = np.where(x == 1, -(inst.d + inst.P @ x), inst.d + inst.P @ x)
        need = max(need, int((-(gain + theta.min())).max()))
    return max(0, -(-need // inst.deoff))


def build_chain(inst: tg.Instance, pick: str = "uniform", ignore_off: bool = False) -> dict[tuple[int, int], list[tuple[tuple[int, int], float]]]:
    n = inst.n
    assert n <= 10 and inst.geom == 0 and inst.deoff > 0 and inst.mode == "qubo" and inst.lane_en is None
    lut = np.array(tg.make_lut(inst.lab), dtype=np.int64)
    theta = (inst.t0 * lut) >> (tg.TEMP_FRAC + tg.LUT_FRAC)
    kmax = k_max(inst, lut)
    ns = 1 << n
    subsets = np.array([[(s >> i) & 1 for i in range(n)] for s in range(ns)], dtype=bool)
    members = [np.flatnonzero(subsets[s]) for s in range(ns)]
    chain = {}
    for xs in range(ns):
        x = subsets[xs].astype(np.int64)
        h = inst.d + inst.P @ x
        gain = np.where(x == 1, -h, h)
        for k in range(kmax + 1):
            e = 0 if ignore_off else k * inst.deoff
            p = (gain[:, None] + e + theta[None, :] >= 0).mean(axis=1)
            prob = np.where(subsets, p[None, :], 1.0 - p[None, :]).prod(axis=1)
            out: dict[tuple[int, int], float] = {}
            if prob[0] > 0:
                assert ignore_off or k < kmax, "chain does not close"
                out[(xs, k + 1)] = float(prob[0])
            for s in range(1, ns):
                if prob[s] == 0:
                    continue
                mem = members[s]
                for rank, lane in enumerate(mem):
                    w = tg.select_prob(len(mem), rank) if pick == "uniform" else float(rank == 0)
                    if w:
                        key = (xs ^ (1 << int(lane)), 0)
                        out[key] = out.get(key, 0.0) + float(prob[s]) * w
            chain[(xs, k)] = list(out.items())
    return chain


def chi_square_sparse(counts: dict, chain: dict) -> tuple[float, int, float]:
    """Pooled chi-square of observed transitions against the chain rows (cells with expectation < 5 merged)."""
    stat, dof = 0.0, 0
    for s, obs in counts.items():
        n_s = sum(obs.values())
        row = dict(chain[s])
        if any(t not in row for t in obs):
            return float("inf"), 1, 0.0
        e_cells, o_cells, small_e, small_o = [], [], 0.0, 0
        for t, p in row.items():
            e = n_s * p
            if e >= 5:
                e_cells.append(e)
                o_cells.append(obs.get(t, 0))
            else:
                small_e += e
                small_o += obs.get(t, 0)
        if small_e > 0:
            e_cells.append(small_e)
            o_cells.append(small_o)
        if len(e_cells) < 2:
            continue
        e_arr, o_arr = np.array(e_cells), np.array(o_cells)
        stat += float(((o_arr - e_arr) ** 2 / e_arr).sum())
        dof += len(e_arr) - 1
    return stat, dof, float(stats.chi2.sf(stat, dof)) if dof else 1.0


def observed_counts(inst: tg.Instance, trace_lines: list[str]) -> dict:
    """Transition counts over states (x, k) from a trace (flip index column 1, E_off column 6)."""
    counts: dict = {}
    xs, k = 0, 0
    for ln in trace_lines:
        if ln.startswith("final"):
            continue
        f = ln.split()
        flip, eoff = int(f[1]), int(f[6])
        nxt = (xs ^ (1 << flip), 0) if flip >= 0 else (xs, k + 1)
        assert eoff == nxt[1] * inst.deoff, "trace E_off disagrees with the (x, k) chain"
        row = counts.setdefault((xs, k), {})
        row[nxt] = row.get(nxt, 0) + 1
        xs, k = nxt
    return counts
