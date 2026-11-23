"""RTL spot check (IMPL_PLAN P6.01 acceptance): the Verilator model of tim_top and the golden model run the SAME small
instances and their per-step state/energy traces and (with I7/I10) per-step activity counters must be bit-exact.

Cells: 3 families (maxcut, maxsat, colouring; small instances through the same problem loaders as the smoke matrix)
       x 4 restart arms (none, da_offset, mesa, kc2) x I7+I10 {off, on}  = 24 cells, STEPS steps each (all tweaks off).
I7v2 cells (H6, `run_i7v2`): ADC full scale = max column sum, I7 b_lo = b_hi - 1, with I10 and LFSR noise, kc2 / none x 3 families.
Tweak cells (H2 rungs 4c-4e, `run_tweaks`): I11 (kc2) and I5 (hold 3, group 4, da_offset) x 3 families x I7/I10 {off, on} = 12
       cells; I3 on a 16-item knapsack (hw rule, TCAM, CiM off; QUBO families have no penalty): off and ramped, 2 cells.
The RTL tree is taken from HW_RTL_ROOT (default: this repository, whose rtl/ = hw/p3-rtl plus the H6 I7v2 adc_fs register); the golden model is this repository's. Verilator is built once per padded size N.
SELECTION LATENCY (timing study v2): `--sel off|mid|max` builds the RTL with the single-cycle select tree (default, old behaviour) or the pipelined
select_tree_pipe (mid: cuts ADD 0b0101 / WALK 0b010, SEL_LAT 5; max: a cut after every adder level and walk step, SEL_LAT 2 + LOG2N + LOG2N - 1) and
runs the golden model with CycleCfg(sel_lat) so that the per-step cycle counts (activity trace) match; the state traces are identical in all settings.
Usage: python -I scripts/rtl_spotcheck.py [--steps 300] [--only <substring>] [--sel off|mid|max]      (run under the local job queue --rss 1.5)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SEED = 0       # added to every instance seed (smoke_all --seeds); 0 = the registered seeds
REPO = Path(__file__).resolve().parents[1]
for sub in ("scripts/golden", "."):
    sys.path.insert(0, str(REPO / sub))

import tim_golden as tg  # noqa: E402
from cim_field import CimCfg, max_column_sum  # noqa: E402
from compare_trace import first_difference, read_lines  # noqa: E402
from counters import CycleCfg  # noqa: E402
from gen_tests import ACT_FIELDS, LAB, NCON  # noqa: E402
from instances import d5c_make_instance, d5c_to_tim, qubo_instance  # noqa: E402
from power import PowerCfg  # noqa: E402
from restart import RestartCfg  # noqa: E402
from tweaks import TweakCfg  # noqa: E402

from scripts.problems import load as ld  # noqa: E402
from scripts.problems import maxcut as mc  # noqa: E402
from scripts.problems import spin_table as st  # noqa: E402

ARMS = ("none", "da_offset", "mesa", "kc2")
STEPS = 300
T_START, T_END = 3.0, 0.1
LAT = 2
NLEV = 8
CIMWB = 8      # tim_top CIMWB parameter (plane count of the noise-column map); golden w_bits must equal it
WORK = REPO / "sim" / "out" / "hw" / "rtl_spotcheck"
SEL_MODE = "off"                    # --sel: off | mid | max (set in main)
def _verilator_bin() -> Path:
    """VERILATOR_BIN, else the verilator on PATH (cloud: conda env eda), else ~/tools/verilator/bin (local build)."""
    if os.environ.get("VERILATOR_BIN"):
        return Path(os.environ["VERILATOR_BIN"])
    found = shutil.which("verilator")
    return Path(found).resolve().parent if found else Path.home() / "tools" / "verilator" / "bin"


VERILATOR = _verilator_bin()


def rtl_root() -> Path:
    root = Path(os.environ.get("HW_RTL_ROOT", REPO))       # this worktree carries the RTL (I7v2 adc_fs is only here, not in hw-p3)
    if not (root / "rtl" / "src" / "tim_top.v").exists():
        raise SystemExit(f"RTL root {root} has no rtl/src/tim_top.v (set HW_RTL_ROOT)")
    return root


def small_families() -> dict[str, ld.MappedQubo]:
    return {"maxcut": ld.from_problem("maxcut", mc.torus_pm1(4, 1), 16),
            "maxsat": ld.from_problem("maxsat", st.random_ksat(6, 26, 3, seed=301), 6),
            "colouring": ld.from_problem("colouring", st.random_colouring(6, 0.5, 3, seed=202), 6)}


def make_case(mq: ld.MappedQubo, arm: str, power_on: bool, steps: int, i7v2: bool = False):
    """Same construction as scripts/smoke_all.run_ours (quantise, pad to a power of two, CiM field, optional I7+I10)."""
    qz = ld.quantise(mq, ld.QUANT["ours"])
    d, P, lane = ld._pad_pow2(qz.d, qz.P)
    inst = qubo_instance(d, P, seed=11 + SEED, steps=steps, t_start=T_START, t_end=T_END, deoff=1)
    if mq.spins != len(d):
        inst = type(inst)(**{**inst.__dict__, "lane_en": lane})
    wb = CIMWB
    assert int(abs(qz.P).max()) < 1 << wb, "weight does not fit the RTL CIMWB"
    b_hi = max(4, inst.n.bit_length())
    fs = 0
    if i7v2:                     # I7v2 (H6): full scale = max column sum, b_hi = bits of fs (exact), b_lo = b_hi - 1
        fs = max_column_sum(inst.P, wb)
        b_hi = fs.bit_length()
    b_lo = max(1, b_hi - 1) if i7v2 else max(3, b_hi - 4)
    pw = PowerCfg(i7=True, i10=True, b_hi=b_hi, b_lo=b_lo, K_p=5, K_g=8) if power_on else None
    return inst, RestartCfg(arm=arm, K=32, L=10), CimCfg(adc_bits=b_hi, w_bits=wb, lfsr=True, sg=300, seed=0xC1A0F00D + SEED,
                                                         fs=fs), pw


def sel_params(n: int) -> tuple[int, int, int, int]:
    """(SEL_PIPE, ADD_CUT, WALK_CUT, SEL_LAT) for the current --sel mode at padded size n."""
    lg = n.bit_length() - 1
    if SEL_MODE == "off":
        return 0, 0, 0, 1
    ac, wc = (0b0101, 0b010) if SEL_MODE == "mid" else ((1 << lg) - 1, (1 << (lg - 1)) - 1)
    ac, wc = ac & ((1 << lg) - 1), wc & ((1 << (lg - 1)) - 1)
    return 1, ac, wc, 2 + bin(ac).count("1") + bin(wc).count("1")


def build(rtl: Path, n: int, work: Path, cim: int = 1) -> Path:
    srcs = sorted(str(p) for p in (rtl / "rtl" / "src").glob("*.v")) + [str(rtl / "rtl" / "tb" / "tb_top.v")]
    digest = hashlib.sha256(b"".join(Path(p).read_bytes() for p in srcs)).hexdigest()[:10]      # RTL edit -> fresh build
    sp, ac, wc, _ = sel_params(n)
    exe = work / f"tbv_N{n}{'' if cim else '_nocim'}{f'_sel{ac}_{wc}' if sp else ''}_{digest}" / "obj" / "tbv"
    if exe.exists():
        return exe
    env = {**os.environ, "PATH": f"{VERILATOR}:{os.environ['PATH']}"}
    srcs = srcs[:-1]
    cmd = ["verilator", "--binary", "--timing", "-Wno-lint", "-Wno-style", "-Wno-fatal", "--top-module", "tb_top", f"-GN={n}",
           f"-GNCON={NCON}", f"-GNLEV={NLEV}", f"-GSEARCH_LAT={LAT}", f"-GLAB={LAB}", f"-GCIM={cim}",
           f"-GSEL_PIPE={sp}", f"-GSEL_ADD_CUT={ac}", f"-GSEL_WALK_CUT={wc}", "-Mdir", str(exe.parent.parent / "obj"),
           str(rtl / "rtl" / "tb" / "tb_top.v"), *srcs, "-o", "tbv"]
    (exe.parent.parent).mkdir(parents=True, exist_ok=True)
    with open(exe.parent.parent / "build.log", "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    return exe


def act_lines(steps: list[dict]) -> list[str]:
    return [f"{i + 1} " + " ".join(str(c[f]) for f in ACT_FIELDS) for i, c in enumerate(steps)]


def run_cell(rtl: Path, family: str, mq: ld.MappedQubo, arm: str, power_on: bool, steps: int,
             tw: TweakCfg | None = None, tag: str = "") -> dict:
    inst, rs, cim, pw = make_case(mq, arm, power_on, steps)
    return run_instance(rtl, family, inst, rs, cim, pw, steps, tw, arm, tag)


def run_instance(rtl: Path, family: str, inst, rs: RestartCfg, cim: CimCfg | None, pw: PowerCfg | None, steps: int,
                 tw: TweakCfg | None, arm: str, tag: str = "") -> dict:
    mach = tg.Machine(inst, restart=rs, cim=cim, power=pw, counters=CycleCfg(sel_lat=sel_params(inst.n)[3]) if pw else None, tweaks=tw)
    res = mach.run()
    work = WORK / (f"sel_{SEL_MODE}" if SEL_MODE != "off" else "") / f"{family}_{arm}_{'i7i10' if pw else 'plain'}{tag}"
    work.mkdir(parents=True, exist_ok=True)
    cfg, trace, act, log, rsf = work / "test.cfg", work / "rtl.trace", work / "rtl.act", work / "rtl.log", work / "rtl.rs"
    tg.write_cfg(inst, cfg, NCON, rs, cim, pw, tweaks=tw)
    exe = build(rtl, inst.n, WORK, cim=int(cim is not None))
    sl = sel_params(inst.n)[3]
    cps = 3 + sl + (cim.adc_bits + 1 if cim else 0) if inst.mode != "knap" else 6 + sl + 2 * LAT
    maxcyc = int(1.5 * (2 * (inst.n + 1) + 2 + steps * cps)) + 1000
    with open(log, "w") as fh:
        subprocess.run([str(exe), f"+cfg={cfg}", f"+trace={trace}", f"+act={act}", f"+rs={rsf}", f"+maxcyc={maxcyc}"], stdout=fh,
                       stderr=subprocess.STDOUT, check=False)
    row = dict(family=family, arm=arm, i7_i10="on" if pw else "off", n=inst.n, steps=steps, restarts=len(mach.restart.events),
               trace_lines=0, act_lines=0, status="ok", note="", tweak=tag.lstrip("_") or "off")
    errs = []
    if "TB_TOP_END ok" not in log.read_text():
        errs.append("testbench did not end ok")
    if not trace.exists():
        errs.append("no rtl.trace")
    else:
        rtl_tr = read_lines(trace)
        row["trace_lines"] = len(rtl_tr)
        d = first_difference(res.trace, rtl_tr)
        if d:
            errs.append(f"trace differs at {d}")
    gold_rs = [f"{t} {c}" for t, c in zip(mach.restart.events, mach.restart.event_cycles)]
    if not rsf.exists() or read_lines(rsf) != gold_rs:        # restart cycles (S_RST, rs_cycles) cycle-exact against the golden model
        errs.append(f"restart cycles differ: golden {gold_rs[:3]} ({len(gold_rs)}), RTL {read_lines(rsf)[:3] if rsf.exists() else 'none'}")
    if pw is not None:
        if not act.exists():
            errs.append("no rtl.act")
        else:
            ra = read_lines(act)
            row["act_lines"] = len(ra)
            d = first_difference(act_lines(mach.counters.steps), ra)
            if d:
                errs.append(f"activity counters differ at {d}")
    if errs:
        row["status"] = "FAIL"
        row["note"] = "; ".join(errs)
    return row


def knap_case(steps: int, ramp: bool):
    """16-item, 8-constraint knapsack (hw TCAM rule, same generator as gen_tests knap16); I3 ramp over steps // 2."""
    raw = d5c_make_instance(16, 8, 3)
    inst = d5c_to_tim(raw, rule="hw", T0=2.0, T_min=0.02, budget=steps, seed=SEED, lam=2.0, dE_off=0.5, Q=NLEV)
    tw = TweakCfg(i3=True, lam_lo=inst.lam // 4, ramp_steps=steps // 2) if ramp else None
    return inst, tw


def run_all(steps: int = STEPS, only: str = "") -> list[dict]:
    rtl = rtl_root()
    rows = []
    for family, mq in small_families().items():
        for power_on in (False, True):
            for arm in ARMS:
                if only and only not in f"{family}_{arm}_{power_on}":
                    continue
                rows.append(run_cell(rtl, family, mq, arm, power_on, steps))
    return rows


def run_i7v2(steps: int = STEPS, only: str = "") -> list[dict]:
    """I7v2 cells (H6): 3 families x {kc2, none} with I7v2 + I10 on, the noisy LFSR readout, ADC full scale = max column sum."""
    rtl = rtl_root()
    rows = []
    for family, mq in small_families().items():
        for arm in ("kc2", "none"):
            if only and only not in f"{family}_{arm}":
                continue
            inst, rs, cim, pw = make_case(mq, arm, True, steps, i7v2=True)
            rows.append(run_instance(rtl, family, inst, rs, cim, pw, steps, None, arm, "_i7v2"))
    return rows


TWEAK_CELLS = (("i11", "kc2", TweakCfg(i11=True)), ("i5", "da_offset", TweakCfg(i5=True, hold=3, group=4)))


def tweak_cells(steps: int = STEPS, only: str = "") -> list:
    """Thunks, one per tweak cell: I11 / I5 on the three QUBO families (I7/I10 off and on) and I3 on a knapsack (off, ramped)."""
    rtl = rtl_root()
    cells = []
    for family, mq in small_families().items():
        for name, arm, tw in TWEAK_CELLS:
            for power_on in (False, True):
                if only and only not in f"{family}_{name}_{power_on}":
                    continue
                cells.append(lambda mq=mq, family=family, arm=arm, power_on=power_on, tw=tw, name=name:
                             run_cell(rtl, family, mq, arm, power_on, steps, tw, f"_{name}"))
    for ramp in (False, True):
        if only and only not in f"knap_i3_{ramp}":
            continue
        cells.append(lambda ramp=ramp: run_knap(rtl, steps, ramp))
    return cells


def run_knap(rtl: Path, steps: int, ramp: bool) -> dict:
    inst, tw = knap_case(steps, ramp)
    return run_instance(rtl, "knapsack", inst, RestartCfg(arm="da_offset"), None, None, steps, tw, "da_offset",
                        "_i3" if ramp else "_i3_off")


def run_tweaks(steps: int = STEPS, only: str = "") -> list[dict]:
    return [cell() for cell in tweak_cells(steps, only)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=STEPS)
    ap.add_argument("--only", default="")
    ap.add_argument("--sel", choices=("off", "mid", "max"), default="off", help="select tree: single-cycle (default) or pipelined (T2)")
    a = ap.parse_args()
    global SEL_MODE
    SEL_MODE = a.sel
    rows = run_all(a.steps, a.only) + run_tweaks(a.steps, a.only) + run_i7v2(a.steps, a.only)
    for r in rows:
        print(f"{r['status']:4s} {r['family']:9s} {r['arm']:9s} I7/I10 {r['i7_i10']:3s} tweak={r['tweak']:3s} N={r['n']:3d} steps={r['steps']} "
              f"restarts={r['restarts']} trace={r['trace_lines']} act={r['act_lines']} {r['note']}")
    nfail = sum(r["status"] != "ok" for r in rows)
    print(f"RTL SPOT CHECK (select tree {SEL_MODE}): {len(rows) - nfail}/{len(rows)} bit-exact")
    return 1 if nfail or not rows else 0


if __name__ == "__main__":
    sys.exit(main())
