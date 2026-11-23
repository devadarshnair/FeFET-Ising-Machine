"""Check one top-level RTL run against the golden model and the test's extra checks.

Usage: check_top.py <case_dir> <run_dir>
  case_dir holds test.inst, golden.trace, meta.json (from gen_tests.py); run_dir holds rtl.trace and rtl.log.
Prints one line "PASS <run>: ..." or "FAIL <run>: ..." (plus detail lines) and exits 0 or 1.

Checks:
  always            trace bit-exact; TB_TOP_END ok (cycles per step, no field overflow, no timeout);
                    TCAM counters: 2 searches per step and N*NSEG row writes in knapsack mode, none in QUBO mode;
                    no dropped writes.
  opt               best_f equals the known optimum.
  feasible_le_opt   best_x is feasible, f(best_x) = best_f, best_f <= brute-force optimum (reports if equal).
  transition        empirical transition frequencies of the RTL run match the exact DA transition matrix
                    (chi-square, p >= 1e-3), and a wrong model (lowest-index selection) is rejected (p < 1e-6).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

import tim_golden as tg  # noqa: E402
from compare_trace import first_difference, read_lines  # noqa: E402

P_PASS = 1e-3
P_WRONG = 1e-6
P_PASS_OFF = 0.01       # offset-on chain (P3.05): p must exceed 0.01


def parse_log(text: str) -> dict:
    vals = {}
    for key, val in re.findall(r"(\w+)=(-?\d+)", " ".join(ln for ln in text.splitlines() if ln.startswith("TB_TOP"))):
        vals[key] = int(val)
    vals["end_ok"] = "TB_TOP_END ok" in text
    return vals


def bits_from_hex(text: str, n: int) -> np.ndarray:
    v = int(text, 16)
    return np.array([(v >> i) & 1 for i in range(n)], dtype=np.int64)


def chi_square(counts: np.ndarray, mat: np.ndarray) -> tuple[float, int, float]:
    """Pooled chi-square of observed transition counts against matrix rows (cells with expectation < 5 merged)."""
    stat, dof = 0.0, 0
    for s in range(mat.shape[0]):
        n_s = counts[s].sum()
        if n_s == 0:
            continue
        exp = n_s * mat[s]
        obs = counts[s]
        big = exp >= 5
        e_cells = list(exp[big])
        o_cells = list(obs[big])
        small_e, small_o = exp[~big].sum(), obs[~big].sum()
        if small_e > 0 or small_o > 0:
            e_cells.append(small_e)
            o_cells.append(small_o)
        e_arr, o_arr = np.array(e_cells), np.array(o_cells)
        if len(e_arr) < 2:
            continue
        if np.any(e_arr == 0):
            if np.any(o_arr[e_arr == 0] > 0):
                return float("inf"), 1, 0.0
            keep = e_arr > 0
            e_arr, o_arr = e_arr[keep], o_arr[keep]
        stat += float(((o_arr - e_arr) ** 2 / e_arr).sum())
        dof += len(e_arr) - 1
    return stat, dof, float(stats.chi2.sf(stat, dof))


def transition_check(inst: tg.Instance, rtl_lines: list[str]) -> tuple[list[str], list[str]]:
    n = inst.n
    flips = [int(ln.split()[1]) for ln in rtl_lines if not ln.startswith("final")]
    counts = np.zeros((1 << n, 1 << n))
    s = 0
    for k in flips:
        nxt = s ^ (1 << k) if k >= 0 else s
        counts[s, nxt] += 1
        s = nxt
    errors, notes = [], []
    good = tg.transition_matrix(inst, "uniform")
    wrong = tg.transition_matrix(inst, "first")
    st_good, dof, p_good = chi_square(counts, good)
    st_wrong, dof_w, p_wrong = chi_square(counts, wrong)
    notes.append(f"chi2 vs exact DA matrix {st_good:.1f} on {dof} dof, p = {p_good:.3g}; "
                 f"vs wrong (lowest-index) selector {st_wrong:.1f} on {dof_w} dof, p = {p_wrong:.3g}; "
                 f"{int(counts.sum())} transitions, {int((counts.sum(axis=1) > 0).sum())} states visited")
    # stationary distribution of the DA chain vs Boltzmann at the same T (information only)
    w, v = np.linalg.eig(good.T)
    pi = np.real(v[:, np.argmin(np.abs(w - 1.0))])
    pi = pi / pi.sum()
    codes = np.arange(1 << n)
    X = ((codes[:, None] >> np.arange(n)[None, :]) & 1).astype(np.int64)
    f = X @ inst.d + ((X @ inst.P) * X).sum(axis=1) // 2
    boltz = np.exp((f - f.max()) / (inst.t0 / 65536.0))
    boltz /= boltz.sum()
    occ = counts.sum(axis=1) / counts.sum()
    notes.append(f"total variation: DA stationary vs Boltzmann {0.5 * np.abs(pi - boltz).sum():.3f}; "
                 f"RTL occupancy vs DA stationary {0.5 * np.abs(occ - pi).sum():.3f}")
    if p_good < P_PASS:
        errors.append(f"transition frequencies do not match the exact matrix (p = {p_good:.3g})")
    if p_wrong >= P_WRONG:
        errors.append(f"test has no power: the wrong model is not rejected (p = {p_wrong:.3g})")
    return errors, notes


def transition_off_check(inst: tg.Instance, rtl_lines: list[str]) -> tuple[list[str], list[str]]:
    """Offset ON: the chain is on (x, k), E_off = k * deoff (scripts/golden/trans_off.py)."""
    import trans_off as to
    counts = to.observed_counts(inst, rtl_lines)
    good, wrong = to.build_chain(inst, "uniform"), to.build_chain(inst, "first")
    noff = to.build_chain(inst, "uniform", ignore_off=True)
    st_g, dof_g, p_g = to.chi_square_sparse(counts, good)
    st_w, dof_w, p_w = to.chi_square_sparse(counts, wrong)
    _, _, p_n = to.chi_square_sparse(counts, noff)
    n_states = len(counts)
    notes = [f"chi2 vs exact (x, E_off) chain {st_g:.1f} on {dof_g} dof, p = {p_g:.3g}; vs wrong (lowest-index) "
             f"selector {st_w:.1f} on {dof_w} dof, p = {p_w:.3g}; vs no-offset model p = {p_n:.3g}; {sum(sum(r.values()) for r in counts.values())} "
             f"transitions from {n_states} (x, k) states; max k seen {max(k for (_, k) in counts)}"]
    errors = []
    if p_g <= P_PASS_OFF:
        errors.append(f"transition frequencies do not match the exact offset-on chain (p = {p_g:.3g})")
    if p_w >= P_WRONG:
        errors.append(f"test has no power: the wrong model is not rejected (p = {p_w:.3g})")
    if p_n >= P_WRONG:
        errors.append(f"test has no power for E_off: the no-offset model is not rejected (p = {p_n:.3g})")
    return errors, notes


def main(argv: list[str]) -> int:
    case_dir, run_dir = Path(argv[1]), Path(argv[2])
    run = run_dir.name
    meta = json.loads((case_dir / "meta.json").read_text())
    inst = tg.read_inst(case_dir / "test.inst")
    errors, notes = [], []
    rtl_path, log_path = run_dir / "rtl.trace", run_dir / "rtl.log"
    if not rtl_path.exists() or not log_path.exists():
        print(f"FAIL {run}: missing rtl.trace or rtl.log")
        return 1
    golden, rtl = read_lines(case_dir / "golden.trace"), read_lines(rtl_path)
    diff = first_difference(golden, rtl)
    if diff:
        errors.append(f"trace differs at {diff}")
    log = parse_log(log_path.read_text())
    if not log["end_ok"]:
        errors.append("testbench did not end ok (timeout, cycles per step or overflow; see rtl.log)")
    if meta.get("act"):
        ga, ra = case_dir / "golden.act", run_dir / "rtl.act"
        if not ra.exists():
            errors.append("missing rtl.act")
        else:
            gl, rl = read_lines(ga), read_lines(ra)
            d = first_difference(gl, rl)
            if d:
                errors.append(f"activity counters differ at {d}")
            notes.append(f"{len(rl)} per-step activity lines equal P2.06 counters")
    grs, rrs = case_dir / "golden.rs", run_dir / "rtl.rs"
    if grs.exists() and rrs.exists():      # restart cycles per step: the golden model's S_RST cycle count must equal the RTL's rs_cycles exactly
        gr, rr = read_lines(grs), read_lines(rrs)
        if gr != rr:
            errors.append(f"restart cycles differ: golden {gr[:3]}.. ({len(gr)} restarts), RTL {rr[:3]}.. ({len(rr)})")
        elif gr:
            notes.append(f"{len(gr)} restarts, S_RST cycles equal the golden model ({sorted({int(l.split()[1]) for l in gr})[:4]}..)")
    knap = meta["mode"] == "knap"
    want_search = 2 * meta["steps"] if knap else 0
    want_write = meta["n"] * meta["nseg"] if knap else 0
    if log.get("searches") != want_search or log.get("writes") != want_write or log.get("wdrop") != 0:
        errors.append(f"TCAM counters: searches {log.get('searches')} (want {want_search}), writes "
                      f"{log.get('writes')} (want {want_write}), dropped {log.get('wdrop')}")
    notes.append(f"{log.get('steps')} steps, {log.get('cps')} cycles/step, {log.get('run_cycles')} run cycles")
    final = rtl[-1].split() if rtl and rtl[-1].startswith("final") else None
    if final is None:
        errors.append("no final line in the RTL trace")
    else:
        best_f = int(final[1])
        best_x = bits_from_hex(final[4], inst.n)
        if "opt" in meta["checks"] and best_f != meta["opt"]:
            errors.append(f"best_f {best_f} != optimum {meta['opt']}")
        if "opt" in meta["checks"]:
            notes.append(f"best_f {best_f}, optimum {meta['opt']}")
        if "feasible_le_opt" in meta["checks"]:
            if not tg.feasible(inst, best_x) or tg.objective(inst, best_x) != best_f or best_f > meta["opt"]:
                errors.append(f"best state check failed (best_f {best_f}, opt {meta['opt']})")
            notes.append(f"best_f {best_f}, brute-force optimum {meta['opt']}, found optimum: "
                         f"{'yes' if best_f == meta['opt'] else 'no'}")
    if "transition" in meta["checks"]:
        e, n = transition_check(inst, rtl)
        errors += e
        notes += n
    if "transition_off" in meta["checks"]:
        e, n = transition_off_check(inst, rtl)
        errors += e
        notes += n
    status = "FAIL" if errors else "PASS"
    print(f"{status} {run}: " + ("; ".join(errors) if errors else "trace bit-exact; " + "; ".join(notes[:1])))
    for line in notes[1:] if not errors else notes:
        print(f"     {run}: {line}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
