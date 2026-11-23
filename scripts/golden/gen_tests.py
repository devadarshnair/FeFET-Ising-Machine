"""Generate the TIM v0 test cases: instance files, host write scripts, golden traces and unit-test vectors.

Run: scripts/run_guarded.sh <python> scripts/golden/gen_tests.py [--out sim/out]
Writes:
  <out>/top/<name>/{test.inst, test.cfg, golden.trace, meta.json} for every top-level test
  <out>/top/tests.txt   one line per run: run_name case_dir N NCON NLEV SEARCH_LAT LAB maxcyc short|long
  <out>/unit/rng_vectors.txt  splitmix64 and xoshiro128** vectors for rtl/tb/tb_rng.v
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import instances as gi  # noqa: E402
import gen_cim_vectors  # noqa: E402
import tim_golden as tg  # noqa: E402
from cim_field import CimCfg  # noqa: E402
from counters import CycleCfg  # noqa: E402
from power import PowerCfg  # noqa: E402
from restart import RestartCfg  # noqa: E402

NCON = 8
LAB = 10
EXAMPLE = REPO / "sim/data/ring8.inst"
DEGREE_TABLE = REPO / "scripts/problems/gset_degree_table.csv"


def gset_max_degree() -> int:
    """Largest vertex degree over the G-set table (G63, 589); the n = 800 stress instance reaches it."""
    import csv
    with open(DEGREE_TABLE) as fh:
        return max(int(r["max_deg"]) for r in csv.DictReader(fh))


def gset800_like(hub_deg: int):
    """G1-like (n = 800, 19176 unit-weight edges, uniform random) plus a hub (vertex 0) lifted to degree hub_deg."""
    import numpy as np
    n, m = 800, 19176
    rng = np.random.default_rng([20261115, 800])
    edges = set()
    while len(edges) < m:
        i, j = rng.integers(0, n, size=2)
        if i != j:
            edges.add((int(min(i, j)), int(max(i, j))))
    deg0 = sum(1 for (i, j) in edges if i == 0)
    for j in rng.permutation(np.arange(1, n)):
        if deg0 >= hub_deg:
            break
        if (0, int(j)) not in edges:
            edges.add((0, int(j)))
            deg0 += 1
    return n, [(i, j, 1) for (i, j) in sorted(edges)]


def sel_lat_of(add_cut: int, walk_cut: int, n: int) -> int:
    """Cycles in state SEL of the pipelined select tree (rtl/src/select_tree_pipe.v): 2 + cuts after adder levels + cuts after walk steps."""
    lg = n.bit_length() - 1
    return 2 + bin(add_cut & ((1 << lg) - 1)).count("1") + bin(walk_cut & ((1 << (lg - 1)) - 1)).count("1")


def sel_flags(add_cut: int, walk_cut: int, extra: str = "") -> str:
    return f"-P tb_top.SEL_PIPE=1 -P tb_top.SEL_ADD_CUT={add_cut} -P tb_top.SEL_WALK_CUT={walk_cut} {extra}".strip()


# pipelined-tree test configurations: case-name suffix -> (ADD_CUT, WALK_CUT, N it applies to). The cases are the unpipelined ones
# re-run with the golden cycle model at the matching sel_lat; every trace is identical to the unpipelined one.
SEL_CASES = {"maxcut16_i7i10": (0b0101, 0b010, 16), "qubo16_i10skip": (0, 0, 16), "qubo64_cim": (0b011010, 0b10101, 64)}


def _case(name, inst, checks, extra=None):
    return dict(name=name, inst=inst, checks=checks, extra=extra or {})


def ring8_example() -> tg.Instance:
    d, P = gi.maxcut_qubo(8, gi.ring_graph(8))
    return gi.qubo_instance(d, P, seed=0x5EED0008, steps=300, t_start=2.0, t_end=0.1, deoff=1)


def build_cases() -> list[dict]:
    cases = [_case("ring8", tg.read_inst(EXAMPLE), ["opt"])]

    d, P = gi.random_qubo(64, 1, 20, 30)
    cases.append(_case("qubo64", gi.qubo_instance(d, P, seed=0x0B064, steps=1500, t_start=60.0, t_end=1.0,
                                                  deoff=4), []))

    d, P = gi.maxcut_qubo(16, gi.random_graph(16, 0.4, 2))
    cases.append(_case("maxcut16", gi.qubo_instance(d, P, seed=0x3C16, steps=3000, t_start=3.0, t_end=0.1,
                                                    deoff=1), ["opt"]))

    d, P = gi.maxcut_qubo(64, gi.torus_graph(8, 8))
    cases.append(_case("torus64", gi.qubo_instance(d, P, seed=0x70264, steps=6000, t_start=3.0, t_end=0.05,
                                                   deoff=1), ["opt"], {"opt": 128}))

    raw = gi.d5c_make_instance(16, 8, 3)
    knap = gi.d5c_to_tim(raw, rule="hw", T0=2.0, T_min=0.02, budget=4000, seed=0, lam=2.0, dE_off=0.5, Q=8)
    cases.append(_case("knap16", knap, ["feasible_le_opt"]))
    knap_q16 = gi.d5c_to_tim(raw, rule="hw", T0=2.0, T_min=0.02, budget=4000, seed=0, lam=2.0, dE_off=0.5, Q=16)
    cases.append(_case("knap16_q16", knap_q16, ["feasible_le_opt"]))

    raw = gi.d5c_make_instance(64, 8, 1)
    cases.append(_case("knap64", gi.d5c_to_tim(raw, rule="hw", T0=3.0, T_min=0.1, budget=1500, seed=1, lam=1.0,
                                               dE_off=1.0, Q=8), []))

    d, P = gi.random_qubo(8, 4, 3, 3, density=0.6)
    cases.append(_case("trans8", gi.qubo_instance(d, P, seed=0x7A8, steps=40000, t_start=2.0, t_end=None,
                                                  deoff=0), ["transition"]))

    # Offset on. Parameters fixed by the k-spread criterion (E_off = k*deoff reaches k = 2 with >= 5000 transitions at
    # each of k = 0, 1, 2) before any chi-square was computed; small weights keep the (x, k) chain at 8 spins exact.
    d, P = gi.random_qubo(8, 4, 6, 6, density=0.6)
    cases.append(_case("trans8_off", gi.qubo_instance(d, P, seed=0x7A9, steps=40000, t_start=0.5, t_end=None,
                                                      deoff=1), ["transition_off"]))

    d, P = gi.random_qubo(64, 9, 500, 2000)
    cases.append(_case("qubo64_wide", gi.qubo_instance(d, P, seed=0x0B065, steps=1000, t_start=3000.0,
                                                       t_end=100.0, deoff=200), []))

    d, P = gi.random_qubo(256, 5, 10, 10)
    cases.append(_case("qubo256", gi.qubo_instance(d, P, seed=0x0B256, steps=40, t_start=20.0, t_end=5.0,
                                                   deoff=2), []))

    d, P = gi.maxcut_qubo(16, gi.random_graph(16, 0.4, 2))
    mc = gi.qubo_instance(d, P, seed=0x3C16, steps=3000, t_start=3.0, t_end=0.1, deoff=1)
    for arm in ("kc2", "mesa", "none", "da_offset"):
        cfg = RestartCfg(arm=arm, K=32, L=10)
        cases.append(_case(f"maxcut16_{arm}", mc, ["opt"] if arm != "none" else [], {"restart": cfg}))

    d, P = gi.random_qubo(64, 1, 20, 30)
    cases.append(_case("qubo64_cim", gi.qubo_instance(d, P, seed=0x0B064, steps=1500, t_start=60.0, t_end=1.0,
                                                      deoff=4), [],
                       {"cim": CimCfg(adc_bits=5, w_bits=8, lfsr=True, sg=2000, seed=0xC1A0F00D)}))

    cases.append(_case("maxcut16_i7i10", mc, [],
                       {"restart": RestartCfg(arm="kc2", K=48, L=5),
                        "cim": CimCfg(adc_bits=8, w_bits=8, lfsr=True, sg=300, seed=0x5EED1010),
                        "power": PowerCfg(i10=True, K_g=8, i7=True, b_hi=8, b_lo=4, K_p=16)}))

    # P4.01 B1 (Yin MESA, scripts/baselines/yin_mesa.py): n = 16 fits one 32x32 tile, so the tiled B1 field equals
    # the plain CiM field; MESA Count_max = 2n (K None), 3-bit weights, 8-bit ADC, no DA offset, no I7/I10, sg = 0.
    cases.append(_case("b1_maxcut16", dataclasses.replace(mc, deoff=0), ["opt"],
                       {"restart": RestartCfg(arm="mesa", K=None),
                        "cim": CimCfg(adc_bits=8, w_bits=3, lfsr=True, sg=0, seed=0xB1)}))

    # P4.03 B3 (Fujitsu DA, scripts/baselines/fujitsu_da.py, schedule "geom"): digital field (no CiM), parallel trial,
    # uniform select, dynamic offset arm da_offset at the ablation rate 1 (rate 0, the paper's final setting, is the
    # same machine with E_off held at 0 and is covered by maxcut16_none); no restarts, no I7/I10.
    cases.append(_case("b3_maxcut16", dataclasses.replace(mc, deoff=1), ["opt"], {"restart": RestartCfg(arm="da_offset")}))

    d, P = gi.random_qubo(16, 3, 20, 30)
    cold = gi.qubo_instance(d, P, seed=0x1010, steps=3000, t_start=4.0, t_end=0.3, deoff=0)
    cases.append(_case("qubo16_i10skip", cold, [],
                       {"restart": RestartCfg(arm="kc2", K=48, L=5),
                        "cim": CimCfg(adc_bits=8, w_bits=8, lfsr=True, sg=12, seed=0x5EED1010),
                        "power": PowerCfg(i10=True, K_g=8, i7=True, b_hi=8, b_lo=5, K_p=16)}))

    d, P = gi.random_qubo(200, 6, 10, 10)
    inst200 = gi.qubo_instance(d, P, seed=0x0200256, steps=300, t_start=20.0, t_end=3.0, deoff=2)
    hub = gset_max_degree()
    n800, edges = gset800_like(hub)
    d, P = gi.maxcut_qubo(n800, edges)
    assert int(d.max()) == hub, "hub degree"
    g800 = gi.qubo_instance(d, P, seed=0x6501, steps=40, t_start=40.0, t_end=5.0, deoff=2)
    cases.append(_case("gset800", tg.pad_instance(g800, 1024), [], {"sparse": True}))

    cases.append(_case("lane200_256", tg.pad_instance(inst200, 256), []))
    # timing study v2: restart units at N >= 64 (two-stage permutation read with 32-word groups, two-stage MESA encoder with 32-spin groups)
    d, P = gi.random_qubo(64, 1, 20, 30)
    q64 = gi.qubo_instance(d, P, seed=0x0B065, steps=1500, t_start=60.0, t_end=1.0, deoff=4)
    cases.append(_case("qubo64_kc2", q64, [], {"restart": RestartCfg(arm="kc2", K=16, L=10)}))
    cases.append(_case("qubo64_mesa", q64, [], {"restart": RestartCfg(arm="mesa", K=16)}))
    d, P = gi.random_qubo(256, 5, 10, 10)
    cases.append(_case("qubo256_kc2", gi.qubo_instance(d, P, seed=0x0B256, steps=120, t_start=20.0, t_end=5.0, deoff=2),
                       [], {"restart": RestartCfg(arm="kc2", K=6, L=10)}))
    cases.append(_case("qubo256_mesa", gi.qubo_instance(d, P, seed=0x0B256, steps=120, t_start=20.0, t_end=5.0, deoff=2),
                       [], {"restart": RestartCfg(arm="mesa", K=6)}))
    # pipelined select tree: the same machines with the cycle model at sel_lat (traces equal the unpipelined cases)
    by_name = {c["name"]: c for c in cases}
    for base, (ac, wc, n) in SEL_CASES.items():
        b = by_name[base]
        cases.append(_case(f"{base}_sl", b["inst"], b["checks"], {**b["extra"], "sel_lat": sel_lat_of(ac, wc, n)}))
    return cases


# Runs: (run name, case name, SEARCH_LAT, "short" | "long"). The three knap16 runs share one golden trace.
# "long" runs only run with run_rtl_tests.sh --long (qubo256: about 70 s, mostly the N^2 = 65536 coupling writes).
RUNS = [("ring8", "ring8", 2, "short"), ("qubo64", "qubo64", 2, "short"), ("maxcut16", "maxcut16", 2, "short"),
        ("torus64", "torus64", 2, "short"), ("knap16", "knap16", 2, "short"), ("knap16_lat1", "knap16", 1, "short"),
        ("knap16_lat3", "knap16", 3, "short"), ("knap16_q16", "knap16_q16", 2, "short"),
        ("knap64", "knap64", 2, "short"), ("trans8", "trans8", 2, "short"), ("trans8_off", "trans8_off", 2, "short"), ("qubo256", "qubo256", 2, "long"),
        ("lane200_256", "lane200_256", 2, "short"),
        ("maxcut16_kc2", "maxcut16_kc2", 2, "short"), ("maxcut16_mesa", "maxcut16_mesa", 2, "short"),
        ("maxcut16_none", "maxcut16_none", 2, "short"), ("maxcut16_da", "maxcut16_da_offset", 2, "short"),
        ("qubo64_wide", "qubo64_wide", 2, "short"), ("gset800", "gset800", 2, "long"),
        ("qubo64_cim", "qubo64_cim", 2, "short", "-P tb_top.CIM=1"),
        ("maxcut16_i7i10", "maxcut16_i7i10", 2, "short", "-P tb_top.CIM=1"),
        ("qubo16_i10skip", "qubo16_i10skip", 2, "short", "-P tb_top.CIM=1"),
        ("b1_maxcut16", "b1_maxcut16", 2, "short", "-P tb_top.CIM=1 -P tb_top.CIMWB=3"),
        ("b3_maxcut16", "b3_maxcut16", 2, "short"),
        # timing study v2: pipelined select tree (SEL_PIPE=1, cuts SEL_ADD_CUT / SEL_WALK_CUT) and the Kc2-only restart unit (RS_MESA=0)
        ("maxcut16_i7i10_sl", "maxcut16_i7i10_sl", 2, "short", sel_flags(*SEL_CASES["maxcut16_i7i10"][:2], "-P tb_top.CIM=1")),
        ("qubo16_i10skip_sl", "qubo16_i10skip_sl", 2, "short", sel_flags(*SEL_CASES["qubo16_i10skip"][:2], "-P tb_top.CIM=1")),
        ("qubo64_cim_sl", "qubo64_cim_sl", 2, "short", sel_flags(*SEL_CASES["qubo64_cim"][:2], "-P tb_top.CIM=1")),
        ("maxcut16_sl2", "maxcut16", 2, "short", sel_flags(0, 0)),
        ("knap16_sl", "knap16", 2, "short", sel_flags(0b0101, 0b010)),
        ("maxcut16_kc2_nomesa", "maxcut16_kc2", 2, "short", "-P tb_top.RS_MESA=0"),
        ("maxcut16_kc2_nomesa_sl", "maxcut16_kc2", 2, "short", sel_flags(0b1111, 0b111, "-P tb_top.RS_MESA=0")),
        ("lane200_256_sl", "lane200_256", 2, "short", sel_flags(0b01010101, 0b0101010)),
        # timing study v2: generators on a free-running clock with enable (RNG_CG = 0, the v0 structure) must give the same traces as the gated default
        ("maxcut16_i7i10_nocg", "maxcut16_i7i10", 2, "short", "-P tb_top.CIM=1 -P tb_top.RNG_CG=0"),
        ("maxcut16_kc2_nocg", "maxcut16_kc2", 2, "short", "-P tb_top.RNG_CG=0"),
        ("qubo64_kc2", "qubo64_kc2", 2, "short"), ("qubo64_mesa", "qubo64_mesa", 2, "short"),
        ("qubo256_kc2", "qubo256_kc2", 2, "long"), ("qubo256_mesa", "qubo256_mesa", 2, "long")]


ACT_FIELDS = ("cycles", "field_reads", "skipped_reads", "array_cell_reads", "adc_conversions", "adc_conv_bits",
              "adc_lowbit_conv", "adc_lowbit_bits", "gated_cycles")


def write_act(steps: list[dict], path: Path) -> None:
    """Per-step activity counters (P2.06 OpCounters subset that the RTL power_ctl exports), one line per step."""
    lines = [f"{i + 1} " + " ".join(str(c[f]) for f in ACT_FIELDS) for i, c in enumerate(steps)]
    path.write_text("\n".join(lines) + "\n")


def write_case(case: dict, top: Path) -> dict:
    inst = case["inst"]
    out = top / case["name"]
    out.mkdir(parents=True, exist_ok=True)
    tg.write_inst(inst, out / "test.inst")
    rs = case["extra"].get("restart")
    cim = case["extra"].get("cim")
    pw = case["extra"].get("power")
    tg.write_cfg(inst, out / "test.cfg", NCON, rs, cim, pw, sparse=bool(case["extra"].get("sparse")))
    mach = tg.Machine(inst, restart=rs, cim=cim, power=pw, counters=CycleCfg(sel_lat=case["extra"].get("sel_lat", 1)) if pw else None)
    res = mach.run()
    if mach.counters is not None:
        write_act(mach.counters.steps, out / "golden.act")
    tg.write_trace(res.trace, out / "golden.trace")
    (out / "golden.rs").write_text("".join(f"{t} {c}\n" for t, c in zip(mach.restart.events, mach.restart.event_cycles)))
    meta = dict(name=case["name"], n=inst.n, mode=inst.mode, steps=inst.steps, q=inst.q, ncon=NCON,
                nseg=-(-(NCON * inst.q) // tg.SEGW) if inst.mode == "knap" else 1, checks=case["checks"],
                golden_best_f=res.best_f, golden_flips=res.flips,
                restarts=len(mach.restart.events), cim_bits=cim.adc_bits if cim else 0,
                act=mach.counters is not None, sel_lat=case["extra"].get("sel_lat", 1))
    if "opt" in case["checks"] or "feasible_le_opt" in case["checks"]:
        meta["opt"] = case["extra"].get("opt") or gi.brute_force_best(inst)[0]
    with open(out / "meta.json", "w") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def write_rng_vectors(path: Path) -> None:
    """splitmix64 outputs for two seeds, then 64 outputs of each of 5 generators seeded by the chain."""
    seed = 0x0123456789ABCDEF
    lines = [f"{seed:016x}"] + [f"{z:016x}" for z in tg.splitmix64_stream(seed, 10)]
    for st in tg.seed_states(seed, 5):
        g = tg.Xoshiro128ss(*st)
        lines.append(" ".join(f"{v:08x}" for v in st))
        lines += [f"{g.next():08x}" for _ in range(64)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "sim/out"))
    ap.add_argument("--write-example", action="store_true", help="(re)write sim/data/ring8.inst and stop")
    args = ap.parse_args()
    if args.write_example:
        tg.write_inst(ring8_example(), EXAMPLE)
        return 0
    out = Path(args.out)
    top = out / "top"
    metas = {c["name"]: write_case(c, top) for c in build_cases()}
    lines = []
    for run, case, lat, length, *flags in RUNS:
        meta = metas[case]
        sl = meta["sel_lat"]
        if flags and "SEL_PIPE=1" in flags[0]:
            ac, wc = (int(re.search(rf"{k}=(\d+)", flags[0]).group(1)) for k in ("SEL_ADD_CUT", "SEL_WALK_CUT"))
            sl = sel_lat_of(ac, wc, meta["n"])
        inst_cps = 6 + sl + 2 * lat if meta["mode"] == "knap" else 3 + sl
        inst_cps += meta.get("cim_bits", 0) + 1 if meta.get("cim_bits") else 0
        maxcyc = int(1.5 * (2 * (meta["n"] + 1) + 2 + meta["steps"] * inst_cps)) + 1000
        lines.append(f"{run} {case} {meta['n']} {NCON} {meta['q'] if meta['mode'] == 'knap' else 8} {lat} {LAB} "
                     f"{maxcyc} {length} {flags[0] if flags else '-'}")
    (top / "tests.txt").write_text("\n".join(lines) + "\n")
    write_rng_vectors(out / "unit/rng_vectors.txt")
    gen_cim_vectors.generate(out / "unit")
    for name, meta in metas.items():
        print(f"{name}: n={meta['n']} mode={meta['mode']} steps={meta['steps']} golden_best={meta['golden_best_f']} "
              f"flips={meta['golden_flips']} restarts={meta['restarts']} opt={meta.get('opt', '-')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
