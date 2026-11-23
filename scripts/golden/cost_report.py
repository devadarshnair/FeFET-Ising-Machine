"""Per-block cost report (P2.07). --smoke: small CiM Max-Cut, each restart arm, I7+I10 on."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cim_field import CimCfg  # noqa: E402
from cost_model import Arch, CostModel, placeholders, total
from counters import CycleCfg
from instances import maxcut_qubo, qubo_instance, random_graph
from power import PowerCfg
from restart import RestartCfg
from tim_golden import Machine


def report(arm: str, n: int = 16, steps: int = 300) -> None:
    d, P = maxcut_qubo(n, random_graph(n, 0.3, 0))
    inst = qubo_instance(d, P, seed=11, steps=steps, t_start=0.5, t_end=0.01, deoff=1)
    cim = CimCfg(adc_bits=8, w_bits=4)
    m = Machine(inst, RestartCfg(arm), cim=cim, power=PowerCfg(i7=True, i10=True, b_hi=8, b_lo=4, K_p=5, K_g=8),
                counters=CycleCfg())
    m.run()
    c, arch, cm = m.counters.total, Arch(n=n, w_bits=4, arm=arm), CostModel()
    e = cm.energy(c, arch, steps)
    tot = total(e)
    assert abs(math.fsum(e.values()) - tot) <= 1e-12 * max(1.0, abs(tot))
    print(f"arm={arm} steps={steps} skipped_reads={c['skipped_reads']} lowbit_conv={c['adc_lowbit_conv']} "
          f"time_ns={cm.time_ns(c):.1f}")
    for b, x in e.items():
        print(f"  E {b:8s} {x:14.3f} fJ")
    print(f"  E total    {tot:14.3f} fJ  (sum check |diff| <= 1e-12)")
    a = cm.area(arch)
    print(f"  A total    {total(a):14.3f} um2  " + " ".join(f"{k}={v:.1f}" for k, v in a.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.parse_args()
    for arm in ("none", "da_offset", "mesa", "kc2"):
        report(arm)
    print("placeholder rows:", ",".join(placeholders()))


if __name__ == "__main__":
    main()
