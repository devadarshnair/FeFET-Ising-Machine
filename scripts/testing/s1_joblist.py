"""Stage 1 job list generator (STAGE0_RESULTS.md). Emits docs/hw/diagnosis/STAGE1_JOBLIST.tsv with per-job runs, runtime
(from Stage 0 smokes) and declared RSS. Planning artefact only: nothing is run. `needs` names the implementation each job is blocked on.
usage: python s1_joblist.py > STAGE1_JOBLIST.tsv"""
import math

# measured single-core seconds per run (Stage 0 smokes; ours ideal unless noted). B3 and B1 scale from the H8 cloud wall times (ours 1.8/10.2 s, B3 1.5/6.8, B1 7.2/52 at 240/480).
S = {  # (family, cond) -> ours seconds / run
    ("p3n480", "ideal"): 12, ("p4n480", "ideal"): 14, ("p3n960", "ideal"): 86, ("p4n960", "ideal"): 95, ("gk", "ideal"): 25,
    ("p3n240", "ideal"): 2.2, ("p4n240", "ideal"): 2.5,
    ("p3n240", "nominal"): 4.6, ("p3n480", "nominal"): 17, ("p3n960", "nominal"): 130, ("gk", "nominal"): 36,
}
RSS = {("p3n240", "ideal"): .15, ("p4n240", "ideal"): .15, ("p3n480", "ideal"): .25, ("p4n480", "ideal"): .25, ("p3n960", "ideal"): .6, ("p4n960", "ideal"): .6, ("gk", "ideal"): .3,
       ("p3n240", "nominal"): .6, ("p3n480", "nominal"): 1.5, ("p3n960", "nominal"): 5.0, ("gk", "nominal"): 4.0}
ARM_X = {"ours": 1.0, "B3": 0.8, "kc2c": 1.0, "none_B1": 1.0, "B1nom": 1.8, "B1bs": 3.6}   # B1nom: native mitigated B1, measured at n240: 8.1 s/run vs ours 4.6 s/run (Stage 0.2), RSS 0.32 GB
L_RULE = {"p3n480": 480, "p4n480": 480, "p3n960": 960, "p4n960": 960, "gk": 1000}
rows = []
GATED = ("p3n960", "p4n960", "gk")   # noisy 960-class jobs: blocked until GATE 0.5.r13_960 passes (or its difference is reported)


def L(c, n):
    return max(10, math.ceil(c * n))


def add(jid, stage, arm, cfg, cell, cond, share, inst, seeds, needs, lane="local", rnd=1):
    if cell in GATED and cond == "nominal":
        lane = "cloud"
    cell_key = cell
    sec = S[(cell_key, cond)] * ARM_X[arm.split(":")[0]]
    runs = inst * seeds
    rows.append((jid, stage, arm, cfg, cell, cond, share, inst, seeds, runs, round(sec, 1), round(runs * sec / 60, 1), RSS[(cell_key, cond)], lane, needs, rnd))


GK_NOTE = "gk = G43-47 TUNING-ONLY (P4.02-used) until the rudy generator exists; no result on gk is confirmatory"
# 1a: R4 + K. Every arm gets the SAME number of configurations per round: 12 in round 1, top 4 in round 2 (960 only).
# ours label = (c, K); L = max(10, ceil(c n_act)) so one label maps to one c. Labels whose L coincides at a given n are aliases: run once, still counted as evaluated.
CS = (0, .02, .04, .08)
KS = (.5, 1, 2)
for cell, n in (("p3n480", 480), ("p4n480", 480), ("gk", 1000)):
    inst = 6 if cell == "gk" else 8
    seen = {}
    for c in CS:
        for k in KS:
            Lv = L(c, n)
            if (Lv, k) in seen:
                continue                                  # alias of an already scheduled label (same L, K): not re-run
            seen[(Lv, k)] = c
            add(f"1a.ours.{cell}.c{c}.K{k}", "1a", "ours", f"c={c} (L={Lv});K={k}n", cell, "ideal", "-", inst, 2, "R4 kick_L in desc ")
    for i in range(12):
        add(f"1a.B3.{cell}.g{i:02d}", "1a", "B3", f"grid{i}", cell, "ideal", "-", inst, 2, "B3 tuning grid file (registered with the prereg)")
        add(f"1a.kc2c.{cell}.g{i:02d}", "1a", "kc2c", f"Tfinal x K x c grid{i}", cell, "ideal", "-", inst, 2, "R4 kick_L")
        add(f"1a.none_B1.{cell}.g{i:02d}", "1a", "none_B1", f"T grid{i}", cell, "ideal", "-", inst, 2, "ours_none/B1 shared ideal tuning (A6)")
# p4n960 is NOT tuned in round 2 (cost; every arm incl. baselines was at ~0 % there in H8): its config is transferred from p4n480 / p3n960 by the same rule for every arm.
for cell in ("p3n960",):    # round 2: top 4 of every arm (same count)
    for arm in ("ours", "B3", "kc2c", "none_B1"):
        for i in range(4):
            add(f"1a.{arm}.{cell}.top{i}", "1a", arm, f"round-1 rank {i + 1}", cell, "ideal", "-", 8, 3, "round-1 selection", "cloud", 2)
# 1b: R6 tabu / R5 targeted on the selected (c, K)
for cell in ("p3n480", "p4n480"):
    for cfg in ("base", "tabu0.5", "tabu1", "tabu2", "R5", "R5+tabu1", "R5+tabu2"):
        add(f"1b.ours.{cell}.{cfg}", "1b", "ours", cfg, cell, "ideal", "-", 8, 2, "R6 (R5 only if pre-registered as a design contribution)")
for cfg in ("base", "tabu1", "R5+tabu1"):
    add(f"1b.ours.p3n960.{cfg}", "1b", "ours", cfg, "p3n960", "ideal", "-", 6, 3, "R6/R5", "cloud")
for cfg in ("base", "tabu0.5", "tabu1", "tabu2"):
    add(f"1b.ours.gk.{cfg}", "1b", "ours", cfg, "gk", "ideal", "-", 6, 2, "R6; " + GK_NOTE)
# 1c.k: k x share grid on p3n240 (where the remaining H-1 exposure is). M0 = registered ours stack; B1 wv+cal and B1 bit-sliced.
for kk in (2, 3):
    for sh in (0, 0.03, 0.1, 0.25, 0.5):
        add(f"1c.k.M0.k{kk}.s{sh}", "1c.k", "ours", f"M0 k={kk}", "p3n240", "nominal", sh, 12, 5, "s0_sweep.py --k option ")
        add(f"1c.k.B1wvcal.k{kk}.s{sh}", "1c.k", "B1nom", f"B1 wv+cal k={kk}", "p3n240", "nominal", sh, 8, 4, "--k option")
        add(f"1c.k.B1bs.k{kk}.s{sh}", "1c.k", "B1bs", f"B1 bit-sliced wv+diff+cal+bin k={kk}", "p3n240", "nominal", sh, 8, 4, "--k option; B1 bit-sliced arm (H-2)")
for sh in (0, 0.1, 0.2, 0.5):
    add(f"1c.k.B1bs.k1.s{sh}", "1c.k", "B1bs", "B1 bit-sliced k=1", "p3n240", "nominal", sh, 8, 4, "B1 bit-sliced arm (H-2)")
# 1c: robustness at the MEASURED cliff (k = 1, shares 0 / 0.01 / 0.03). M0 n240 reuses Stage 0.2 (same keys, same seeds): not re-run.
# n240 is one 256-row tile, so R13 is irrelevant there; variance-reduction tests are at n480 (2 tiles) with --ours-tile-rows 256.
for sh in (0, 0.01, 0.03):
    add(f"1c.R10_dither.p3n240.s{sh}", "1c", "ours", "R10 uniform +-LSB/2, tau=LSB/2 (falsification arm)", "p3n240", "nominal", sh, 12, 5, "R10 ")
    add(f"1c.Metropolis_ctrl.p3n240.s{sh}", "1c", "ours", "Metropolis T=LSB, exact field (matched control for R10)", "p3n240", "nominal", sh, 12, 5, "R12(b)/R10 control ")
    add(f"1c.nodiff_M0.p3n240.s{sh}", "1c", "ours", "wv+cal, NO diff (single-sign columns)", "p3n240", "nominal", sh, 12, 5, "none (mitigation label wv+cal)")
for arm, need in (("M0_onecol_legacy", "none"), ("M0_tiled256", "R13 (done)"), ("tiled256+R9_refcol", "R9 "), ("tiled256+R11_oppoint_cal", "R11 ")):
    for sh in (0, 0.01, 0.03):
        add(f"1c.{arm}.p3n480.s{sh}", "1c", "ours", arm, "p3n480", "nominal", sh, 10, 4, need)
# field-error Monte Carlo (no walks): the mean-vs-variance question. ~0.1 CPU-h each; priced at the 6 s measured for n240.
for tag, extra in (("nodiff.p3n240.s0", "s0_h4_field.py needs --mit option "), ("nodiff.p3n240.s0.5", "--mit option"), ("tiled256.p3n480.s0", "R13"), ("onecol.p3n480.s0", "none")):
    rows.append((f"1c.fmc.{tag}", "1c", "ours", "field MC 10 draws x 20 states", tag.split(".")[1], "nominal", "0" if tag.endswith("s0") else "0.5", 10, 20, 200, 0.6, 2.0, 1.0, "local", extra, 1))
# 1d: Max-Cut hybrid (tuning-only instances)
for cfg in ("ours_none_T", "hyb_f0.1", "hyb_f0.25", "hyb_f0.5", "I11_T1", "I11_T2", "I11_T3"):
    add(f"1d.maxcut.{cfg}", "1d", "ours", cfg, "gk", "ideal", "-", 12, 3, "R12 ; " + GK_NOTE)
# 1e: nominal re-check of the selected stack (n960-class: GATE 0d applies to gk, 1024 lanes)
for arm, ax in (("ours_sel", "ours"), ("B3_sel", "B3"), ("B1_sel", "B1nom")):
    add(f"1e.{arm}.p3n480", "1e", ax, arm, "p3n480", "nominal", 0.5, 8, 4, "selection from 1a-1d")
    add(f"1e.{arm}.gk", "1e", ax, arm, "gk", "nominal", 0.5, 6, 3, "selection from 1a-1d; " + GK_NOTE)
# Stage 0 item deferred from the local run (MemAvailable never reached 8 GB with another project job resident): N = 960 tiled identity and field MC
rows.append(("0.5.r13_960", "0d", "ours", "tiled256 nominal vs stored ideal, 2 records", "p3n960", "nominal", 0.5, 1, 2, 2, 300.0, 10.0, 7.0, "cloud", "s0_r13_960.py p3n960 2 out.json", 0))
for sh in (0, 0.5):
    for t in (0, 256):
        rows.append((f"0.3.h4_960.s{sh}.tile{t}", "0d", "ours", "field MC real leakage", "p3n960", "nominal", sh, 1, 2, 2, 300.0, 10.0, 7.0, "cloud", "s0_h4_field.py p3n960 2101 SHARE real 2 5 out.json [256]", 0))
# order: gate first; add depends_on
rows.sort(key=lambda r: (r[0] != "0.5.r13_960", r[1] != "0d"))
print("job_id\tstage\tarm\tcfg\tcell\tcond\tc2c_share\tinstances\tseeds\truns\ts_per_run\tjob_min\trss_gb\tlane\tneeds\tround\tdepends_on")
for r in rows:
    dep = "FIRST CLOUD JOB (hard gate)" if r[0] == "0.5.r13_960" else ("GATE:0.5.r13_960 must pass (or its difference be reported)" if (r[4] in GATED and r[5] == "nominal") else ("0.5.r13_960" if r[1] == "0d" else ""))
    print("\t".join(str(x) for x in r) + "\t" + dep)
import sys
tot = sum(r[9] * r[10] for r in rows) / 3600
by = {}
for r in rows:
    by[r[1]] = by.get(r[1], 0) + r[9] * r[10] / 3600
RATE, TAIL, SETUP_H, GATE_H = 2.01, 1.15, 0.4, 0.25     # Rs per vCPU-h, tail factor, set-up wall hours, gate-job wall hours (instance Rs 64.28/h)
cost = tot * RATE * TAIL + (SETUP_H + GATE_H) * 64.28
print(f"# total CPU-h {tot:.1f}; by stage " + ", ".join(f"{k}={v:.1f}" for k, v in sorted(by.items())) + f"; jobs {len(rows)}; longest job {max(r[11] for r in rows):.0f} min; "
      f"cost Rs {cost:.0f} incl. set-up {SETUP_H} h + gate {GATE_H} h at Rs 64.28/h (budget Rs 125)", file=sys.stderr)
