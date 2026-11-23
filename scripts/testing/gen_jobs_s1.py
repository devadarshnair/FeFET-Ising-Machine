"""Stage 1 job enumeration = the single source of jobs_s1.tsv (executable), jobs_s1_smoke.tsv (smoke gate) and STAGE1_JOBLIST.tsv (planning table).
docs/hw/diagnosis/the experiment plan II.3, STAGE0_RESULTS.md section 8, prereg/hw/S1_tuning_grids.json (DRAFT, tuning-only).

Dependencies (column 8 of the executable TSV; a row starts only when every listed id or id-prefix `prefix*` has a done marker):
  0.5.r13_960 (the R13 identity gate)  <- every noisy 960-class job (p3n960 / p4n960 / gk nominal)
  SEL.1a (selection of round 1)        <- 1a round 2, 1b
  SEL.2  (final stack + Stage 2 gate)  <- 1e
  report_s1                            <- everything
Usage: python -I scripts/testing/gen_jobs_s1.py --tsv jobs_s1.tsv [--smoke-tsv jobs_s1_smoke.tsv] [--plan STAGE1_JOBLIST.tsv] [--summary]
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field

PY = "$PY -I scripts/testing/run_s1.py"
OUT = "sim/out/hw/s1"
SMOKE_OUT = "sim/out/hw/s1_smoke"
CHUNK_S = 600                       # target seconds per job (estimate incl. margin x1.3); hard timeout 60 min
MARGIN = 1.3
GATE_ID = "0.5.r13_960"
GATED = ("p3n960", "p4n960", "gk")  # noisy jobs of these cells wait for the gate
KEYS = {"p3": [str(2101 + i) for i in range(12)], "p4": [str(2201 + i) for i in range(12)], "gk": ["G43", "G44", "G45", "G46", "G47"]}
PCT_PAIRS = [(85, 5), (90, 5), (85, 10), (75, 5), (90, 10), (75, 10)]
# measured single-core seconds per run (Stage 0 smokes). ESTIMATES (flagged in the planning table): n480 / gk nominal tiled, p4n960, n960 nominal.
S_IDEAL = {"p3n240": 2.2, "p4n240": 2.5, "p3n480": 12, "p4n480": 14, "p3n960": 86, "p4n960": 95, "gk": 25}
S_NOM = {"p3n240": 4.6, "p3n480": 17, "p3n480t": 60, "p3n960": 130, "gk": 150}
RSS_IDEAL = {"p3n240": .5, "p4n240": .5, "p3n480": .6, "p4n480": .6, "p3n960": 1.0, "p4n960": 1.0, "gk": .8}
RSS_NOM = {"p3n240": 1.0, "p3n480": 3.0, "p3n480t": 3.0, "p3n960": 6.5, "gk": 6.5}
ARM_X = {"ours": 1.0, "B3": 0.8, "kc2c": 1.0, "none_B1": 1.0, "B1nom": 1.8, "B1bs": 3.6}
GK_NOTE = "gk = G43-47 TUNING-ONLY (P4.02-used) until the rudy generator exists; no result on gk is confirmatory"


@dataclass
class Row:
    id: str
    stage: str
    arm: str                  # class for runtime scaling
    cfg: str                  # human label
    cell: str
    cond: str                 # ideal | nominal
    share: object
    keys: list
    seeds: int
    label: str = "ours_kc2_i11"
    mit: str = "none"
    cfg_over: dict = field(default_factory=dict)
    tile: int = 0
    k: float = 1.0
    sel: str = ""
    cid: str = ""
    needs: str = ""
    rnd: int = 1
    kind: str = "run"         # run | fmc | gate | sel | report
    deps: str = ""
    est_s: float = 0.0        # total estimated seconds incl. margin
    rss: float = 1.0
    lane: str = "local"
    cmd_extra: str = ""
    family: str = ""


def L(c: float, n: int) -> int:
    return max(10, math.ceil(c * n))


def fam_of(cell: str) -> str:
    return "maxcut" if cell == "gk" else cell


def kind_of(cell: str) -> str:
    return "gk" if cell == "gk" else cell[:2]


def secs(r: Row) -> float:
    if r.cond == "ideal":
        s = S_IDEAL[r.cell]
    else:
        key = r.cell + ("t" if r.tile and r.cell == "p3n480" else "")
        s = S_NOM[key]
    return s * ARM_X[r.arm]


def rss_of(r: Row) -> float:
    if r.cond == "ideal":
        return RSS_IDEAL[r.cell]
    key = r.cell + ("t" if r.tile and r.cell == "p3n480" else "")
    return RSS_NOM[key] if r.arm not in ("B1nom", "B1bs") else max(1.0, RSS_NOM[key] / 3)


def add(rows: list, r: Row) -> None:
    """Chunk a run row over its instance keys so that every job is <= CHUNK_S estimated seconds; ids get .pNN when split."""
    r.family = fam_of(r.cell)
    per = secs(r) * r.seeds * MARGIN
    n_keys_per_job = max(1, int(CHUNK_S // per)) if per > 0 else len(r.keys)
    chunks = [r.keys[i:i + n_keys_per_job] for i in range(0, len(r.keys), n_keys_per_job)]
    gated = r.cell in GATED and r.cond == "nominal"
    for i, ks in enumerate(chunks):
        c = Row(**{**r.__dict__})
        c.keys = ks
        if len(chunks) > 1:
            c.id = f"{r.id}.p{i:02d}"
        c.est_s = secs(r) * len(ks) * r.seeds * MARGIN
        c.rss = rss_of(r)
        c.deps = (r.deps + "," if r.deps else "") + (GATE_ID if gated else "")
        c.deps = c.deps.strip(",")
        c.lane = "cloud"
        rows.append(c)


def build() -> list[Row]:
    rows: list[Row] = []
    ks = lambda cell, n: KEYS[kind_of(cell)][:n]       # noqa: E731
    colour = (("p3n480", 480), ("gk", 1000))   # p4n480 is NOT tuned in Stage 1 (cost): p4 uses the config transferred from p3n480 by the same rule for every arm
    ninst = {"p3n480": 8, "p4n480": 8, "gk": 5}
    nseed = {"p3n480": 2, "p4n480": 2, "gk": 3}
    mit_ours = "wv+diff+cal"
    # ---- gate first (own row; runs alone? no: dependants wait by deps). Two records, ideal + tiled nominal fresh runs (stored H8 records are not shipped).
    g = Row(GATE_ID, "0d", "ours", "R13 identity: tiled-256 nominal vs ideal, 2 records (fresh runs, same spec)", "p3n960", "nominal", 0.5, ["2101"], 2, kind="gate",
            needs="s0_r13_960 logic (fresh ideal + tiled nominal)", lane="cloud")
    g.est_s = 2 * (S_IDEAL["p3n960"] + S_NOM["p3n960"] * 1.5) * MARGIN
    g.rss = 7.0
    g.family = "p3n960"
    rows.append(g)
    # ---- 1a round 1
    for cell, n in colour:
        seen = set()
        for c in (0, .02, .04, .08):
            for k in (.5, 1, 2):
                Lv = L(c, n)
                if (Lv, k) in seen:
                    continue
                seen.add((Lv, k))
                add(rows, Row(f"1a.ours.{cell}.c{c}.K{k}", "1a", "ours", f"c={c} (L={Lv});K={k}n", cell, "ideal", "-", ks(cell, ninst[cell]), nseed[cell],
                              label="ours_kc2_i11", cfg_over={"kick_c": c, "knob": k}, cid=f"c{c}_K{k}", needs="R4 hook (done)"))
        for i, ((hi, lo), kv) in enumerate((p, v) for p in PCT_PAIRS for v in (1.0, 0.5)):
            add(rows, Row(f"1a.B3.{cell}.g{i:02d}", "1a", "B3", f"B3 p{hi}_{lo} k{kv}", cell, "ideal", "-", ks(cell, ninst[cell]), nseed[cell], label="B3_v2",
                          cfg_over={"pct_hi": hi, "pct_lo": lo, "knob": kv}, cid=f"b3_p{hi}_{lo}_k{kv}", needs="prereg/hw/S1_tuning_grids.json"))
            add(rows, Row(f"1a.none_B1.{cell}.g{i:02d}", "1a", "none_B1", f"ours_none/B1 p{hi}_{lo} sched{kv}", cell, "ideal", "-", ks(cell, ninst[cell]), nseed[cell],
                          label="ours_none", cfg_over={"pct_hi": hi, "pct_lo": lo, "knob": kv}, cid=f"none_p{hi}_{lo}_k{kv}", needs="shared ideal tuning (A6)"))
        for i, (tf, k, c) in enumerate((tf, k, c) for tf in (1.0, 0.5) for k in (.5, 1, 2) for c in (0, 0.04)):
            add(rows, Row(f"1a.kc2c.{cell}.g{i:02d}", "1a", "kc2c", f"kc2c tfinal={tf} K={k}n c={c}", cell, "ideal", "-", ks(cell, ninst[cell]), nseed[cell],
                          label="ours_kc2c", cfg_over={"pct_hi": 90, "pct_lo": 5, "tfinal": tf, "knob": k, "kick_c": c}, cid=f"kc2c_t{tf}_K{k}_c{c}", needs="R4 hook (done)"))
    # ---- SEL.1a
    s1 = Row("SEL.1a", "1a", "ours", "select round-1 top configs per arm (registered rule)", "-", "-", "-", [], 0, kind="sel", deps="", est_s=60, rss=1.0, lane="cloud", needs="evaluate_s1")
    rows.append(s1)
    # ---- 1a round 2: p3n960, top 4 of each arm (+ ours registered reference)
    add(rows, Row("1a.ours.p3n960.ref", "1a", "ours", "registered reference c=0 K=2n", "p3n960", "ideal", "-", ks("p3n960", 6), 3, label="ours_kc2_i11",
                  cfg_over={"kick_c": 0, "knob": 2}, cid="ref", rnd=2, deps="SEL.1a", needs="-"))
    for arm, label in (("ours", "ours_kc2_i11"), ("B3", "B3_v2"), ("kc2c", "ours_kc2c"), ("none_B1", "ours_none")):
        for i in range(4):
            add(rows, Row(f"1a.{arm}.p3n960.top{i}", "1a", arm, f"round-1 rank {i + 1}", "p3n960", "ideal", "-", ks("p3n960", 6), 3, label=label,
                          sel=f"1a:{arm}:col:{i}", cid=f"top{i}", rnd=2, deps="SEL.1a", needs="SEL.1a"))
    # ---- 1b: R6 tabu / R5 on the selected (c, K) of ours (rank 1)
    for cell in ("p3n480",):
        for cfgname, over in (("base", {}), ("tabu0.5", {"tabu": .5}), ("tabu1", {"tabu": 1}), ("tabu2", {"tabu": 2}), ("R5", {"kick_target": True}),
                              ("R5+tabu1", {"kick_target": True, "tabu": 1}), ("R5+tabu2", {"kick_target": True, "tabu": 2})):
            add(rows, Row(f"1b.ours.{cell}.{cfgname}", "1b", "ours", cfgname, cell, "ideal", "-", ks(cell, 8), 2, label="ours_kc2_i11", cfg_over=over, sel="1a:ours:col:0",
                          cid=cfgname, deps="SEL.1a", needs="R6 / R5 hooks (done); R5 only if pre-registered as a design contribution"))
    for cfgname, over in (("base", {}), ("tabu0.5", {"tabu": .5}), ("tabu1", {"tabu": 1}), ("tabu2", {"tabu": 2})):
        add(rows, Row(f"1b.ours.gk.{cfgname}", "1b", "ours", cfgname, "gk", "ideal", "-", KEYS["gk"], 3, label="ours_kc2_i11", cfg_over=over, sel="1a:ours:gk:0", cid=cfgname,
                      deps="SEL.1a", needs="R6 hook; " + GK_NOTE))
    for cfgname, over in (("base", {}), ("tabu1", {"tabu": 1}), ("R5+tabu1", {"kick_target": True, "tabu": 1})):
        add(rows, Row(f"1b.ours.p3n960.{cfgname}", "1b", "ours", cfgname, "p3n960", "ideal", "-", ks("p3n960", 6), 3, label="ours_kc2_i11", cfg_over=over, sel="1a:ours:col:0",
                      cid=cfgname, deps="SEL.1a", needs="R6/R5 hooks"))
    # ---- 1c.k: k x share on p3n240
    for kk in (2, 3):
        for sh in (0, 0.03, 0.1, 0.25, 0.5):
            add(rows, Row(f"1c.k.M0.k{kk}.s{sh}", "1c.k", "ours", f"M0 k={kk}", "p3n240", "nominal", sh, KEYS["p3"][:10], 5, label="ours_kc2_i11", mit=mit_ours, k=kk, cid="M0", needs="--k (done)"))
            add(rows, Row(f"1c.k.B1wvcal.k{kk}.s{sh}", "1c.k", "B1nom", f"B1 wv+cal k={kk}", "p3n240", "nominal", sh, KEYS["p3"][:6], 4, label="B1_best", mit="wv+cal", k=kk, cid="B1wvcal"))
            add(rows, Row(f"1c.k.B1bs.k{kk}.s{sh}", "1c.k", "B1bs", f"B1 bit-sliced wv+diff+cal+bin k={kk}", "p3n240", "nominal", sh, KEYS["p3"][:6], 4, label="B1_best",
                          mit="wv+diff+cal+bin", k=kk, cid="B1bs", needs="B1 bit-sliced arm (H-2)"))
    for sh in (0, 0.1, 0.2, 0.5):
        add(rows, Row(f"1c.k.B1bs.k1.s{sh}", "1c.k", "B1bs", "B1 bit-sliced k=1", "p3n240", "nominal", sh, KEYS["p3"][:8], 4, label="B1_best", mit="wv+diff+cal+bin", cid="B1bs"))
    # ---- 1c: robustness at the measured cliff (k = 1). M0 n240 k=1 reuses Stage 0.2.
    for sh in (0, 0.01, 0.03):
        add(rows, Row(f"1c.R10_dither.p3n240.s{sh}", "1c", "ours", "R10 dither +-LSB/2, tolerance 1 (falsification arm)", "p3n240", "nominal", sh, KEYS["p3"], 5, label="ours_kc2_i11",
                      mit="wv+diff+cal+dith", cfg_over={"i11_tol": 1}, cid="R10", needs="R10 hook (done)"))
        add(rows, Row(f"1c.nodiff_M0.p3n240.s{sh}", "1c", "ours", "wv+cal, NO diff (single-sign columns)", "p3n240", "nominal", sh, KEYS["p3"], 5, label="ours_kc2_i11", mit="wv+cal", cid="nodiff"))
    add(rows, Row("1c.Metropolis_ctrl.p3n240", "1c", "ours", "Metropolis T=1 (LSB), exact field: matched control for R10 (ideal device, share-independent)", "p3n240", "ideal", "-",
                  KEYS["p3"], 5, label="ours_kc2_i11", cfg_over={"i11_temp": 1}, cid="metropolis_ctrl", needs="i11_temp hook (done)"))
    # n480 variance tests (two 256-row tiles): 6 instances x 3 seeds, shares {0, 0.03} (tiled nominal is ~60 s/run: estimate)
    for arm, mit, tile in (("M0_onecol_legacy", "wv+diff+cal", 0), ("M0_tiled256", "wv+diff+cal", 256), ("tiled256+R9_refcol", "wv+diff+cal+ref", 256),
                           ("tiled256+R11_oppoint_cal", "wv+diff+cal+cal2x8", 256)):
        for sh in (0, 0.03):
            add(rows, Row(f"1c.{arm}.p3n480.s{sh}", "1c", "ours", arm, "p3n480", "nominal", sh, KEYS["p3"][:6], 3, label="ours_kc2_i11", mit=mit, tile=tile, cid=arm,
                          needs="R13 / R9 / R11 hooks (done)"))
    # field-error Monte Carlo (no walks)
    for tag, cell, key, sh, extra, mitl, tile in (("nodiff.p3n240.s0", "p3n240", "2101", 0, "", "wv+cal", 0), ("nodiff.p3n240.s0.5", "p3n240", "2101", 0.5, "", "wv+cal", 0),
                                                  ("tiled256.p3n480.s0", "p3n480", "2101", 0, "", "wv+diff+cal", 256), ("onecol.p3n480.s0", "p3n480", "2101", 0, "", "wv+diff+cal", 0)):
        f = Row(f"1c.fmc.{tag}", "1c", "ours", f"field-error MC 10 draws x 20 states, mit {mitl}, tile {tile}", cell, "nominal", sh, [key], 1, kind="fmc", mit=mitl, tile=tile, cid="fmc",
                lane="cloud", needs="s0_h4_field --mit (done)")
        f.est_s = 60 * MARGIN
        f.rss = 2.0
        f.family = cell
        rows.append(f)
    # ---- 1d: Max-Cut hybrid (tuning-only instances)
    for cfgname, label, over in (("ours_none_T", "ours_none", {}), ("hyb_f0.1", "ours_kc2_i11", {"hyb_f": .1}), ("hyb_f0.25", "ours_kc2_i11", {"hyb_f": .25}),
                                 ("hyb_f0.5", "ours_kc2_i11", {"hyb_f": .5}), ("I11_T1", "ours_kc2_i11", {"i11_temp": 1}), ("I11_T2", "ours_kc2_i11", {"i11_temp": 2}),
                                 ("I11_T3", "ours_kc2_i11", {"i11_temp": 3})):
        add(rows, Row(f"1d.maxcut.{cfgname}", "1d", "ours", cfgname, "gk", "ideal", "-", KEYS["gk"], 5, label=label, cfg_over=over, cid=cfgname, needs="R12 hook (done); " + GK_NOTE))
    # ---- SEL.2
    rows.append(Row("SEL.2", "1e", "ours", "final stack + Stage 2 gate (registered rule)", "-", "-", "-", [], 0, kind="sel", deps="", est_s=60, rss=1.0, lane="cloud", needs="evaluate_s1"))
    # ---- 1e: nominal re-check of the selected stack (skipped when stage2_go is false)
    for arm, ax, label, sel, mit, tile in (("ours_sel", "ours", "ours_kc2_i11", "2:ours:{final}", mit_ours, 256), ("B3_sel", "B3", "B3_v2", "1a:B3:{kind}:0", "none", 0),
                                           ("B1_sel", "B1nom", "B1_best", "1a:none_B1:{kind}:0", "wv+cal", 0)):
        for cell in ("p3n480", "gk"):
            s = sel.replace("{kind}", "col" if cell != "gk" else "gk").replace("{final}", "final" if cell != "gk" else "final_gk")
            add(rows, Row(f"1e.{arm}.{cell}", "1e", ax, arm, cell, "nominal", 0.5, ks(cell, 6 if cell != "gk" else 5), 3, label=label, mit=mit, sel=s, tile=tile,
                          cid=arm, deps="SEL.2", needs="selection; skipped if stage2_go is false" + ("; " + GK_NOTE if cell == "gk" else "")))
    for r in rows:   # explicit dependency lists (prefix wildcards would make SEL.1a wait for its own dependants)
        if r.id == "SEL.1a":
            r.deps = ",".join(x.id for x in rows if x.stage == "1a" and x.rnd == 1 and x.kind == "run")
        if r.id == "SEL.2":
            r.deps = ",".join(x.id for x in rows if x.kind == "run" and ((x.stage == "1a" and x.rnd == 2) or x.stage in ("1b", "1d")))
    rep = Row("report_s1", "rep", "ours", "evaluate_s1 report", "-", "-", "-", [], 0, kind="report", deps="*", est_s=120, rss=2.0, lane="cloud")
    rows.append(rep)
    return rows


def run_cmd(r: Row, out: str, smoke: bool) -> str:
    sw = " --sweeps 1" if smoke else ""
    if r.kind == "gate":
        return f"{PY} gate --id {r.id} --out {out}/{r.id}.json" + (" --smoke" if smoke else "")
    if r.kind == "sel":
        return f"{PY} select --stage {r.id.split('.', 1)[1]} --dir {out} --out {out}/selection_{r.id.split('.', 1)[1]}.json"
    if r.kind == "report":
        return f"{PY} report --dir {out} --out {out}/s1_report.md"
    if r.kind == "fmc":
        t = f" {r.tile}" if r.tile else ""
        sweep_smoke = " 1 1" if smoke else " 10 20"
        return (f"$PY -I scripts/testing/s0_h4_field.py {r.family} {r.keys[0]} {r.share} real{sweep_smoke} {out}/{r.id}.json{t} --mit {r.mit}")
    import json
    parts = [f"{PY} run --id {r.id} --stage {r.stage} --arm {r.arm} --cid {r.cid or 'x'} --label {r.label} --family {r.family} --cell {r.cell} --cond {r.cond}",
             f"--mit {r.mit} --shares {r.share if r.share != '-' else 0} --keys {','.join(r.keys[:1] if smoke else r.keys)} --seeds {1 if smoke else r.seeds} --k {r.k:g}",
             f"--tile {r.tile}"]
    if r.cfg_over:
        parts.append("--cfg " + ",".join(f"{a}={json.dumps(b) if not isinstance(b, bool) else str(b).lower()}" for a, b in r.cfg_over.items()))
    if r.sel:
        parts.append(f"--sel {r.sel}")
    parts.append(f"--out {out}/{r.id}.jsonl" + sw)
    return " ".join(parts)


def tsv_rows(rows: list[Row], smoke: bool) -> list[str]:
    out = []
    for r in rows:
        est_min = max(0.2, r.est_s / 60)
        tmo = min(60.0, max(10.0, est_min * 2.5 + 5))
        if smoke:
            est_min, tmo = 0.5, 10.0
        cmd = run_cmd(r, SMOKE_OUT if smoke else OUT, smoke)
        rss = r.rss if not smoke else (3.5 if r.kind == "gate" else (min(r.rss, 5.7) if r.rss >= 3 else 1.5))
        out.append("\t".join([r.id, "par", f"{rss:.1f}", f"{est_min:.1f}", f"{tmo:.0f}", cmd, r.deps]))
    return out


def smoke_rows(rows: list[Row]) -> list[Row]:
    """One row per distinct job type, plus the complete round 1 of the colouring-480 cells (so that the selection step reads real files), the SEL / gate / report rows."""
    seen, out = set(), []
    for r in rows:
        if r.kind in ("gate", "sel", "report"):
            out.append(r)
            continue
        sig = (r.kind, r.stage if r.stage in ("1a",) and r.rnd == 1 and r.cell in ("p3n480", "p4n480") else "", r.arm, r.label, r.mit, r.cond, r.cell, r.tile, r.k, tuple(sorted(r.cfg_over)), bool(r.sel))
        if r.stage == "1a" and r.rnd == 1 and r.cell in ("p3n480", "gk"):
            out.append(r)                      # full round-1 families for p3n480 and gk (selection input)
            continue
        if sig in seen:
            continue
        seen.add(sig)
        out.append(r)
    return out


def plan_rows(rows: list[Row]) -> list[str]:
    hdr = "job_id\tstage\tarm\tcfg\tcell\tcond\tc2c_share\tk\tinstances\tseeds\truns\test_job_min\trss_gb\tlane\tneeds\tround\tdepends_on"
    out = [hdr]
    for r in rows:
        runs = len(r.keys) * r.seeds if r.kind == "run" else (1 if r.kind in ("gate", "fmc") else 0)
        out.append("\t".join(str(x) for x in (r.id, r.stage, r.arm, r.cfg, r.cell, r.cond, r.share, f"{r.k:g}", len(r.keys), r.seeds, runs, f"{r.est_s / 60:.1f}", r.rss, r.lane, r.needs, r.rnd, r.deps)))
    return out


def sim_makespan(rows: list[Row], slots: int = 32, mem_gb: float = 108.0) -> dict:
    """Event simulation with dependencies (same first-fit policy as s1_sched.py); estimated minutes per row."""
    import heapq
    done_t: dict = {}
    pend = list(rows)
    running: list = []
    t = 0.0
    ids = [r.id for r in rows]

    def ready(r):
        for d in filter(None, r.deps.split(",")):
            if d == "*":
                if any(x not in done_t for x in ids if x != r.id):
                    return False
            elif d.endswith("*"):
                if any(x not in done_t for x in ids if x.startswith(d[:-1])):
                    return False
            elif d not in done_t:
                return False
        return True
    used = lambda: sum(g for _, _, g, _ in running)       # noqa: E731
    while pend or running:
        for r in list(pend):
            if len(running) < slots and used() + r.rss <= mem_gb and ready(r):
                heapq.heappush(running, (t + max(0.2, r.est_s / 60), r.id, r.rss, r))
                pend.remove(r)
        if not running:
            break
        t, rid, _, _ = heapq.heappop(running)
        done_t[rid] = t
    return {"makespan_min": round(t, 1), "jobs": len(rows)}


def cost(rows: list[Row]) -> dict:
    cpu_h = sum(r.est_s for r in rows) / 3600
    ms = sim_makespan(rows)["makespan_min"]
    setup_h, smoke_h, collect_h = 0.3, 0.15, 0.1
    rs = (setup_h + smoke_h + ms / 60 + collect_h) * 64.28
    return {"cpu_h": round(cpu_h, 1), "makespan_min": ms, "rs": round(rs), "per_stage_cpu_h": {s: round(sum(r.est_s for r in rows if r.stage == s) / 3600, 1) for s in sorted({r.stage for r in rows})}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--smoke-tsv")
    ap.add_argument("--plan")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    rows = build()
    hdr = "# id\tmode\trss_gb\test_min\ttimeout_min\tcommand\tdeps (comma list of ids / prefix* / *)\n# Stage 1 (DRAFT, tuning-only). Dependencies replace the H8 barrier mode; see gen_jobs_s1.py.\n"
    if a.tsv:
        open(a.tsv, "w").write(hdr + "\n".join(tsv_rows(rows, False)) + "\n")
    if a.smoke_tsv:
        sm = smoke_rows(rows)
        # smoke deps: keep the same ids and dependency structure restricted to the smoke ids (barrier semantics preserved)
        ids = {r.id for r in sm}
        for r in sm:
            r.deps = ",".join(d for d in r.deps.split(",") if d and (d in ids or d.endswith("*") or d == "*"))
        open(a.smoke_tsv, "w").write(hdr + "\n".join(tsv_rows(sm, True)) + "\n")
    if a.plan:
        open(a.plan, "w").write("\n".join(plan_rows(rows)) + "\n")
    c = cost(rows)
    print(f"# jobs {len(rows)}; est CPU-h {c['cpu_h']} {c['per_stage_cpu_h']}; simulated makespan {c['makespan_min']} min on 32 slots; cost Rs {c['rs']} "
          f"(set-up 0.3 h + smoke gate 0.15 h + makespan + collect 0.1 h at Rs 64.28/h); longest job {max(r.est_s for r in rows) / 60:.0f} min", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
