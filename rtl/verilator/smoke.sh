#!/bin/bash
# P3.10 (+ timing study v2 pipelined-tree and Kc2-only-unit runs): Verilator smoke on every arm: each run is built and checked by rtl/verilator/run.sh (golden bit-exact and
# byte-identical to the Icarus trace of scripts/run_rtl_tests.sh), plus the N = 256, 1e4-step timing run.
# Needs sim/out/run/<run>/rtl.trace from an earlier run_rtl_tests.sh (run.sh makes a missing one itself).
# Run: rtl/verilator/smoke.sh
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
RUNS="ring8 maxcut16 knap16 knap16_tcamlite maxcut16_kc2 maxcut16_mesa maxcut16_none maxcut16_da maxcut16_i7i10 \
qubo16_i10skip qubo64_cim trans8_off lane200_256 maxcut16_i11 maxcut16_i5 maxcut16_i11_i7i10 knap16_i3 \
maxcut16_i7i10_sl qubo16_i10skip_sl qubo64_cim_sl maxcut16_sl2 knap16_sl maxcut16_kc2_nomesa maxcut16_kc2_nomesa_sl lane200_256_sl b1_maxcut16 maxcut16_i7i10_nocg maxcut16_kc2_nocg"
nfail=0; nskip=0
for r in $RUNS; do
    # a run that scripts/golden/gen_tests.py of this tree does not generate (e.g. the H2 tweak runs live in the hw/p3-rtl generator) is skipped, not failed
    if ! awk -v r="$r" '$1 == r {f = 1} END {exit !f}' "$ROOT/sim/out/top/tests.txt" 2>/dev/null; then
        echo "SKIP $r: not in sim/out/top/tests.txt of this tree"; nskip=$((nskip + 1)); continue
    fi
    "$ROOT/rtl/verilator/run.sh" "$r" || nfail=$((nfail + 1))
done
"$ROOT/rtl/verilator/run.sh" --perf256 || nfail=$((nfail + 1))
echo "VSMOKE: $nfail failed, $nskip skipped"
[ $nfail -eq 0 ]
