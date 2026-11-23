"""H8 job enumeration = the single source for jobs_h8_core.tsv / jobs_h8_full.tsv and the budget (prereg/hw/H8_full.md section 8).

Cells -> jobs. Phases: main (machines x {ideal, nominal+mitigation} x families), abl (ablation ladder with mitigations), var (stress: k axis,
C2C share axis, drift, unmitigated) and sw (software context + 20x TabuCol reference); a final barrier row `report_h8` runs only when every
earlier row has a done marker. The full tier is a SUPERSET of the core file: same job ids for the core pairs (done markers skip them),
plus new jobs for the extra (instance, seed) pairs. Every job is chunked to <= CHUNK_TARGET_S estimated seconds and carries a smoke command.

Usage: python -I scripts/testing/gen_jobs_h8.py --tsv jobs_h8_core.tsv --tier core | --summary
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import h8_instances as h8i  # noqa: E402
import plan_h8 as p8  # noqa: E402

CHUNK_TARGET_S = 1500            # estimated seconds per job (margin included); hard timeout 60 min
MAX_EST_MIN = 50                 # a single run longer than this cannot be a job (assert)
RSS_FIXED = {"ours": 1.2, "b1": 1.6, "b3": 0.9, "b1y": 1.0, "sw": 0.7}   # ideal device / digital: no per-cell programming arrays
# Mitigated analog arms hold (WV_MAX_ATTEMPTS = 32) x cells float64 arrays while programming (variation_v2.program_cells): peak RSS measured
# at 5.0 GB (ours p3n960, 3.68M cells) and 2.6 GB (B1 p3n960, 1.84M cells) at 1 sweep = about 5.6 x the (32, cells) array. cells = c x lanes^2 for ours
# (c measured from the MemoryError sizes of the first smoke: planted 3.6, generated graphs 9.0, G-set: 800-node 2.4, the fresh G51-54 measured about 3.1 by the core smoke, 3.6 declared), 2 x spins^2 for B1 (two polarities).
C_CELLS = {"planted": 3.6, "graph": 9.0, "maxcut": 3.6}
PEAK_PER_ARRAY = 5.6
SMOKE_OUT = "sim/out/hw/h8_smoke"
RS_PER_H = 64.28                 # 32 vCPU instance, Rs per hour (profile 32; the default)
VCPU = 32
# Instance profiles (go_h8.sh --profile): vcpu = slots, rs_h = Rs per hour (cloud IN1), mem_gb = admission budget of declared RSS (None = 0.85 x
# MemTotal), deadline = no new job after it (core tier), hard = running jobs killed (deadline + 20 min).
PROFILES = {32: {"vcpu": 32, "rs_h": 64.28, "mem_gb": None, "mem_label": "0.85 x 128 GB", "mem_sim_gb": 108.0, "deadline_core": 205},
            16: {"vcpu": 16, "rs_h": 32.14, "mem_gb": 60.0, "mem_label": "60 of 64 GB", "mem_sim_gb": 60.0, "deadline_core": 450}}
SETUP_H, SMOKE_GATE_H = 0.25, 0.15        # typical set-up / gate wall
SETUP_CAP_MIN, GATE_CAP_MIN, DEADLINE_CORE_MIN, HARD_EXTRA_MIN, COLLECT_MIN = 20, 25, 205, 20, 5   # hard timeouts of go_h8.sh
TAIL_FACTOR = 1.15
CAP_CORE_RS = 300
RUN = "$PY -I scripts/testing/run_h8.py"


@dataclass
class Cell:
    phase: str
    label: str                    # arm label (ARMS) or sw.<algo>
    family: str
    cond: str                     # ideal | nominal | vx<k> | drift<d> (point id)
    mit: str
    c2c: float
    pairs: list                   # [(instance, seed)]
    sweeps_by_inst: dict
    spins_by_inst: dict
    tag: str = ""                  # G-set size group (G1000 / G2000): cells of family 'maxcut' differ by it

    @property
    def key(self) -> tuple:
        return (self.phase, self.label, self.family, self.tag, self.cond, self.mit, self.c2c)

    def secs(self, inst: str, seed: int) -> float:
        if self.label.startswith("sw."):
            return 0.2
        c = "ideal" if self.cond == "ideal" else "nominal"
        return p8.s_per_run(self.label, self.family, self.spins_by_inst[inst], self.sweeps_by_inst[inst], c)


@dataclass
class Job:
    id: str
    mode: str
    phase: str
    cell: Cell | None
    pairs: list
    secs: float
    command: str
    smoke: str
    rss: float


# ---------------------------------------------------------------------------------------------------------- instance sets per tier
def _grid(insts: list[str], seeds: int) -> set:
    return {(i, s) for i in insts for s in range(seeds)}


def families(tier: str) -> list[dict]:
    """[{family, insts, seeds(core,full), spins, sweeps}] in the order of the design. 'insts' = full instance list; per-tier counts below."""
    out = []
    for k in (3, 4):
        for size in (*p8.SIZES_CORE, p8.SIZE_FULL):
            fam = p8.planted_family(k, size)
            (ic, sc), (ifl, sfl) = (p8.INST_SEEDS[size]["core"], p8.INST_SEEDS[size]["full"])
            insts = p8.planted_instances(k, size, "full")
            out.append({"family": fam, "insts": insts, "core": (ic, sc), "full": (ifl, sfl),
                        "spins": {i: h8i.spins(fam, i) for i in insts}, "sweeps": {i: p8.sweeps_of(fam, i, h8i.spins(fam, i)) for i in insts}})
    gs = list(p8.GRAPHS_CORE) + list(p8.GRAPHS_FULL)
    sp = {g: h8i.spins(h8i.GRAPH_FAMILY, g) for g in gs}
    out.append({"family": h8i.GRAPH_FAMILY, "insts": gs, "core": (len(p8.GRAPHS_CORE), p8.GRAPH_SEEDS["core"]),
                "full": (len(gs), p8.GRAPH_SEEDS["full"]), "spins": sp,
                "sweeps": {g: p8.sweeps_of(h8i.GRAPH_FAMILY, g, sp[g]) for g in gs}, "graph_core": set(p8.GRAPHS_CORE)})
    for key, v in p8.MAXCUT.items():
        n = int(key[1:])
        out.append({"family": "maxcut", "tag": key, "insts": list(v["insts"]), "core": v["core"], "full": v["full"], "spins": {i: n for i in v["insts"]}, "sweeps": {i: p8.SWEEPS for i in v["insts"]}})
    return out


def tier_pairs(f: dict, tier: str, first_inst: int | None = None, seeds_cap: int | None = None) -> set:
    n, s = f[tier]
    if f["family"] == h8i.GRAPH_FAMILY and tier == "core":
        insts = [g for g in f["insts"] if g in f["graph_core"]]
    else:
        insts = f["insts"][:n]
    if first_inst is not None:
        insts = insts[:first_inst]
    if seeds_cap is not None:
        s = min(s, seeds_cap)
    return _grid(insts, s)


def cells(tier: str) -> list[Cell]:
    """Every cell of the design for a tier (core cells are a subset of full pair sets)."""
    out: list[Cell] = []
    fams = families(tier)
    arms = p8.main_arms()
    for f in fams:
        pairs = sorted(tier_pairs(f, tier))
        if not pairs:
            continue
        for lab in arms:
            for cond in p8.conds_of(lab):
                out.append(_cell("main", lab, f, cond, pairs))
        sw = [a for a in p8.SW_ARMS if f["family"] != "maxcut" or a == "sw.sa"]
        for a in sw:
            out.append(_cell("sw", a, f, "ideal", sorted({(i, 0) for i, _ in pairs}) if a == "sw.dsatur" else pairs))
    # ablation ladder with mitigations: 6 non-duplicate rungs; p3n240 / p4n240 first ABL_INSTANCES x ABL_SEEDS, G1000 first 3 x 4 seeds nominal only
    for f in fams:
        if f["family"] in ("p3n240", "p4n240"):
            pairs = sorted(tier_pairs(f, tier, p8.ABL_INSTANCES, p8.ABL_SEEDS))
            conds = ("ideal", "nominal")
        elif f.get("tag") == "G1000":
            pairs, conds = sorted(tier_pairs(f, tier, p8.ABL_MAXCUT_INSTANCES, p8.ABL_MAXCUT_SEEDS)), ("nominal",)
        else:
            continue
        for lab in p8.LADDER_ARMS:
            if lab in ("L_none", "L_kc2_i11"):          # identical to the main arms ours_none / ours_kc2_i11: reused, not re-run
                continue
            for cond in conds:
                out.append(_cell("abl", lab, f, cond, pairs))
    # stress at the design point (p3n240, p4n240)
    for f in fams:
        if f["family"] not in p8.STRESS_FAMILIES:
            continue
        pairs = sorted(tier_pairs(f, tier, p8.STRESS_INSTANCES, p8.STRESS_SEEDS))
        for lab in p8.STRESS_ARMS:
            for pid, mit, c2c in p8.stress_cells(lab):
                out.append(_cell("var", lab, f, pid, pairs, mit, c2c))
    # B1_yin context (faithful one-proposal-per-iteration reading, ideal device only, 120 / 240 spins; it solved nothing at 150 sweeps in P4_v2 R6)
    for f in fams:
        if f["family"] in ("p3n120", "p4n120", "p3n240", "p4n240"):
            out.append(_cell("ctx", "B1_yin_sa", f, "ideal", sorted(tier_pairs(f, tier, 12, 4))))
    # 20x TabuCol reference (solvability of each instance): all colouring instances, 3 seeds
    for f in fams:
        if f["family"] == "maxcut":
            continue
        ins = sorted({i for i, _ in tier_pairs(f, tier)})
        out.append(_cell("ref", "sw.tabucol", f, "ideal", [(i, s) for i in ins for s in range(p8.TABU_REF_SEEDS)]))
    return out


def _cell(phase, label, f, cond, pairs, mit=None, c2c=p8.C2C_DEFAULT) -> Cell:
    if mit is None:
        mit = "none" if (cond == "ideal" or label.startswith("sw.")) else p8.ARMS[label].mit
    fam = f["family"]
    return Cell(phase, label, fam, cond, mit, c2c, list(pairs), f["sweeps"], f["spins"], f.get("tag", ""))


def _tag(c: Cell) -> str:
    f = c.family
    return f"{f}" if f != "maxcut" else "maxcut"


# ---------------------------------------------------------------------------------------------------------- cell -> jobs
def _tokens(pairs: list) -> str:
    """merge consecutive seeds of one instance: inst/lo-hi"""
    out, cur = [], None
    for inst, s in sorted(pairs, key=lambda p: (p[0], p[1])):
        if cur and cur[0] == inst and cur[2] + 1 == s:
            cur[2] = s
        else:
            cur = [inst, s, s]
            out.append(cur)
    return ",".join(f"{i}/{lo}-{hi}" for i, lo, hi in out)


def _job_id(c: Cell, part: int, extra: bool) -> str:
    cond = c.cond + (f"_{c.mit}" if c.phase == "var" else "") + (f"_c{c.c2c:g}" if c.phase == "var" and c.c2c != p8.C2C_DEFAULT else "")
    fam = c.family if c.family != "maxcut" else f"maxcut_{c.spins_by_inst[c.pairs[0][0]]}"
    return f"h8_{c.phase}_{c.label}_{fam}_{cond}".replace("+", "") + f"_{part:03d}" + ("x" if extra else "")


def command(c: Cell, jid: str, pairs: list, out: str, sweeps_override: int | None = None) -> str:
    inst0 = pairs[0][0]
    sw = c.sweeps_by_inst[inst0] if sweeps_override is None else sweeps_override
    cmd = (f"{RUN} --id {jid} --phase {c.phase} --label {c.label} --family {c.family} --cond {c.cond} --mit {c.mit} "
           f"--c2c {c.c2c:g} --runs {_tokens(pairs)} --sweeps {sw} --out {out}")
    return cmd


def jobs_of_cell(c: Cell, base_pairs: set | None) -> list[Job]:
    """Chunk the cell's pairs; pairs also present in base_pairs get the core job ids, the rest are 'x' (extra) jobs."""
    groups = [(False, [p for p in c.pairs if base_pairs is None or p in base_pairs]), (True, [p for p in c.pairs if base_pairs is not None and p not in base_pairs])]
    out: list[Job] = []
    for extra, pairs in groups:
        if not pairs:
            continue
        # one budget per instance when budgets differ (dimacs graphs, maxcut sizes): chunk per instance group of equal sweeps
        by_sw: dict = {}
        for p in pairs:
            by_sw.setdefault(c.sweeps_by_inst[p[0]], []).append(p)
        part = 0
        for sw, ps in sorted(by_sw.items()):
            cur, tot = [], 0.0
            for p in ps:
                t = c.secs(*p)
                if cur and tot + t > CHUNK_TARGET_S:
                    out.append(_mk(c, part, extra, cur, tot, sw))
                    part += 1
                    cur, tot = [], 0.0
                cur.append(p)
                tot += t
            if cur:
                out.append(_mk(c, part, extra, cur, tot, sw))
                part += 1
    return out


def _mk(c: Cell, part: int, extra: bool, pairs: list, secs: float, sweeps: int) -> Job:
    jid = _job_id(c, part, extra)
    first = pairs[0]
    cmd = command(c, jid, pairs, p8.OUT, sweeps)
    smoke = command(c, "smoke_" + jid, [first], SMOKE_OUT, 1) + " --smoke"
    if c.label == "sw.tabucol" and c.phase in ("main", "sw"):
        pass
    m = "sw" if c.label.startswith("sw.") else p8.ARMS[c.label].machine
    rss = rss_of(c, m, pairs)
    assert secs / 60 <= MAX_EST_MIN or len(pairs) == 1, (jid, secs)
    assert secs / 60 <= MAX_EST_MIN * 1.0, f"single run exceeds {MAX_EST_MIN} min: {jid} {secs / 60:.0f} min"
    return Job(jid, "par", c.phase, c, pairs, secs, cmd, smoke, rss)


def rss_of(c: Cell, machine: str, pairs: list) -> float:
    """Declared peak host RSS (GB) of a job: fixed base, plus the 32-attempt programming arrays for a mitigated analog run (cond != ideal)."""
    base = RSS_FIXED[machine]
    if machine not in ("ours", "b1") or c.cond == "ideal" or "wv" not in c.mit:
        return base
    spins = max(c.spins_by_inst[i] for i, _ in pairs)
    lanes = p8.lanes_of(spins)
    kind = "maxcut" if c.family == "maxcut" else "graph" if c.family == h8i.GRAPH_FAMILY else "planted"
    cells = C_CELLS[kind] * lanes * lanes if machine == "ours" else 2.0 * spins * spins
    return round(base + PEAK_PER_ARRAY * 32 * 8 * cells / 2 ** 30, 1)


def barrier(tier: str, suffix: str = "") -> Job:
    ev = "$PY -I scripts/testing/evaluate_h8.py"
    return Job(f"report_h8_{tier}{suffix}", "all", "report", None, [], 60.0,
               f"{ev} --raw {p8.OUT} --out {p8.OUT}/h8_report_{tier}{suffix}.json --tier {tier}",
               f"{ev} --raw {SMOKE_OUT} --out {SMOKE_OUT}/h8_report_smoke.json --boot 20 --smoke", 1.5)


def all_jobs(tier: str, kc2c_addon: bool = False) -> list[Job]:
    """kc2c_addon: only the fairness-arm jobs (ours_kc2c) and a report barrier with its own id, to be run AFTER the tuned ours.kc2c selection exists."""
    core_cells = {c.key: set(c.pairs) for c in cells("core")}
    jobs: list[Job] = []
    for c in cells(tier):
        key = c.key
        base = core_cells.get(key, set()) if tier == "full" else None
        jobs += jobs_of_cell(c, base)
    ids = [j.id for j in jobs]
    assert len(ids) == len(set(ids)), "duplicate job ids"
    if kc2c_addon:
        jobs = [j for j in jobs if j.cell.label == "ours_kc2c"]
    jobs.sort(key=lambda j: -j.secs)
    return jobs + [barrier(tier, "_kc2c" if kc2c_addon else "")]


def extra_only(tier_jobs: list[Job], core_jobs: list[Job]) -> list[Job]:
    have = {j.id for j in core_jobs}
    return [j for j in tier_jobs if j.id not in have and j.mode == "par"]


# ---------------------------------------------------------------------------------------------------------- budget
def cpu_hours(jobs: list[Job]) -> dict:
    by: dict = {}
    for j in jobs:
        if j.mode == "par":
            by[j.phase] = by.get(j.phase, 0.0) + j.secs / 3600
    return by


def cost(cpu_h: float, extra_only_: bool = False, profile: int = 32) -> dict:
    """Billed wall = tail-inflated jobs / vCPU (+ typical set-up and gate unless the cost is an increment on a running instance)."""
    pr = PROFILES[profile]
    wall = cpu_h * TAIL_FACTOR / pr["vcpu"] + (0.0 if extra_only_ else SETUP_H + SMOKE_GATE_H)
    return {"cpu_h": round(cpu_h, 1), "wall_h": round(wall, 2), "rs": round(wall * pr["rs_h"])}


def worst_case_rs(profile: int = 32) -> dict:
    """Guaranteed ceiling of a core run: every phase is hard-timed (set-up 20, gate 10 + 15, scheduler deadline + 20 min kill window, collection 5 min)."""
    pr = PROFILES[profile]
    mins = SETUP_CAP_MIN + GATE_CAP_MIN + pr["deadline_core"] + HARD_EXTRA_MIN + COLLECT_MIN
    return {"minutes": mins, "rs": round(mins / 60 * pr["rs_h"])}


def plan_makespan(tier: str, profile: int = 32) -> dict:
    """Simulated schedule (h8_sched.simulate: file order, first fit under slots and declared-RSS budget) from the TSV rows' estimated minutes."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("h8_sched", HERE.parents[1] / "scripts/cloud/h8/h8_sched.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    pr = PROFILES[profile]
    rows = [{"id": j.id, "mode": j.mode, "rss": j.rss, "est": float(max(1, math.ceil(j.secs / 60))), "tmo": 60.0, "cmd": ""} for j in all_jobs(tier)]
    return m.simulate(rows, pr["vcpu"], pr["mem_sim_gb"])


def budget() -> dict:
    core = all_jobs("core")
    full = all_jobs("full")
    c_h = sum(cpu_hours(core).values())
    ex = extra_only(full, core)
    e_h = sum(j.secs for j in ex) / 3600
    out = {"core": {**cost(c_h), "jobs": sum(j.mode == "par" for j in core), "by_phase": {k: round(v, 1) for k, v in cpu_hours(core).items()},
                    "max_job_min": round(max(j.secs for j in core if j.mode == "par") / 60, 1)},
           "full_extra": {**cost(e_h, True), "jobs": len(ex), "max_job_min": round(max(j.secs for j in ex) / 60, 1) if ex else 0},
           "full_total": {**cost(c_h + e_h)}, "core_worst_case": worst_case_rs(),
           "kc2c_in_lists": p8.main_arms().count("ours_kc2c") == 1}
    for prof in (32, 16):
        out[f"profile_{prof}"] = {"core": cost(c_h, False, prof), "core_worst_case": worst_case_rs(prof), "core_plan": plan_makespan("core", prof),
                                  "deadline_min": PROFILES[prof]["deadline_core"], "full_extra": cost(e_h, True, prof), "full_total": cost(c_h + e_h, False, prof)}
    return out


def write_tsv(path: Path, tier: str, kc2c_addon: bool = False) -> int:
    jobs = all_jobs(tier, kc2c_addon)
    lines = ["# id\tmode\trss_gb\test_min\ttimeout_min\tcommand ($PY expanded by run_h8.sh)\tsmoke_command (1 run, 1 sweep, sim/out/hw/h8_smoke)",
             f"# H8 full study, tier {tier}, DRAFT prereg until frozen by commit. par = one process per slot; all = barrier. LPT order."]
    for j in jobs:
        est = max(1, math.ceil(j.secs / 60))
        tmo = 60 if j.mode == "all" else min(60, max(10, math.ceil(est * 1.6) + 5))
        lines.append(f"{j.id}\t{j.mode}\t{j.rss}\t{est}\t{tmo}\t{j.command}\t{j.smoke}")
    path.write_text("\n".join(lines) + "\n")
    return len(jobs)


SMOKE_REPRESENTATIVE = ("p3n240", h8i.GRAPH_FAMILY, "maxcut1000")


def _fam_tag(c: Cell) -> str:
    return f"maxcut{c.spins_by_inst[c.pairs[0][0]]}" if c.family == "maxcut" else c.family


def smoke_types(tier: str = "full") -> list[Job]:
    """(a) coverage: one job per distinct (phase, arm label, family class, condition class, mitigation), the largest first (memory / size extremes);
    (b) rectangle: every first-chunk job of three representative families (p3n240, the generated graphs, G-set 800), so that the report barrier of
    the smoke sees complete (instance, seed) rectangles for every arm; (c) the barrier."""
    seen, out, ids = set(), [], set()
    jobs = all_jobs(tier)
    for j in jobs:
        if j.mode == "all":
            continue
        c = j.cell
        key = (c.phase, c.label, "maxcut" if c.family == "maxcut" else "g" if c.family == h8i.GRAPH_FAMILY else "pl", c.cond if c.phase == "var" else c.cond[:5], c.mit)
        if key not in seen:
            seen.add(key)
            out.append(j)
            ids.add(j.id)
    for j in sorted(jobs, key=lambda x: x.id):
        if j.mode == "par" and j.id not in ids and j.id.endswith("_000") and _fam_tag(j.cell) in SMOKE_REPRESENTATIVE:
            out.append(j)
            ids.add(j.id)
    return out + [j for j in jobs if j.mode == "all"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--tier", choices=("core", "full"), default="core")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--kc2c-addon", action="store_true", help="TSV with only the ours.kc2c jobs of the tier (implies --with-kc2c) + its own report barrier")
    ap.add_argument("--with-kc2c", action="store_true", help="emit the ours.kc2c fairness-arm jobs even if its tuned selection is not yet in the tree")
    a = ap.parse_args()
    p8.FORCE_KC2C = a.with_kc2c or a.kc2c_addon
    if a.tsv:
        print(f"wrote {write_tsv(a.tsv, a.tier, a.kc2c_addon)} rows to {a.tsv}")
    if a.summary:
        print(budget())


if __name__ == "__main__":
    main()
