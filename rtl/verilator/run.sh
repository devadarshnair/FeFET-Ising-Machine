#!/bin/bash
# P3.08: Verilator target of tim_top. Builds rtl/tb/tb_top.v (the same testbench the Icarus flow uses, so the trace
# dump is the same code) with Verilator --binary --timing and runs it on a test written by scripts/golden/gen_tests.py.
# Usage:   rtl/verilator/run.sh <run>            e.g. maxcut16_kc2 (a run name of sim/out/top/tests.txt)
#          rtl/verilator/run.sh --perf256        N = 256, 1e4 steps (qubo256 instance), must take < 10 min
# Checks:  trace equals the golden model (check_top.py) AND is byte-identical to the Icarus trace
#          sim/out/run/<run>/rtl.trace (made by scripts/run_rtl_tests.sh; produced here if missing).
# Run: rtl/verilator/run.sh <run>
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY=${TIM_PY:-$HOME/miniconda3/envs/swref/bin/python}
export PATH=$HOME/tools/verilator/bin:$PATH
export NUMBA_CACHE_DIR="$ROOT/sim/out/numba_cache"
OUT="$ROOT/sim/out/verilator"
SRC=$(ls "$ROOT"/rtl/src/*.v)
mkdir -p "$OUT"

build() {   # build <dir> <n> <ncon> <nlev> <lat> <lab> <extra -P flags...>
    local d=$1 n=$2 ncon=$3 nlev=$4 lat=$5 lab=$6; shift 6
    local g=""
    for f in "$@"; do case "$f" in -P) ;; tb_top.*) g="$g -G${f#tb_top.}" ;; esac; done
    mkdir -p "$d"
    verilator --binary --timing -Wno-lint -Wno-style -Wno-fatal --top-module tb_top -GN=$n -GNCON=$ncon -GNLEV=$nlev \
        -GSEARCH_LAT=$lat -GLAB=$lab $g -Mdir "$d/obj" "$ROOT/rtl/tb/tb_top.v" $SRC -o tbv > "$d/build.log" 2>&1
}

if [ "${1:-}" = "--perf256" ]; then
    D="$OUT/perf256"; rm -rf "$D"; mkdir -p "$D"
    CASE="$ROOT/sim/out/top/qubo256"
    STEPS=10000
    sed "s/^w 000009 .*/w 000009 $(printf '%x' $STEPS)/" "$CASE/test.cfg" > "$D/test.cfg"
    build "$D" 256 8 8 2 10 || { echo "FAIL perf256: build (see $D/build.log)"; exit 1; }
    t0=$(date +%s)
    "$D/obj/tbv" +cfg="$D/test.cfg" +trace="$D/rtl.trace" +maxcyc=$((STEPS * 4 + 5000)) > "$D/rtl.log" 2>&1
    t1=$(date +%s)
    ok=0; grep -q "TB_TOP_END ok" "$D/rtl.log" && ok=1
    "$PY" -I -B - "$ROOT" "$CASE/test.inst" "$D/rtl.trace" "$STEPS" > "$D/check.log" 2>&1 <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts/golden")
import tim_golden as tg
from compare_trace import first_difference, read_lines
inst = tg.read_inst(sys.argv[2])
inst.steps = int(sys.argv[4])
res = tg.Machine(inst).run()
d = first_difference(res.trace, read_lines(sys.argv[3]))
print("PASS golden" if d is None else "FAIL golden " + d)
sys.exit(0 if d is None else 1)
PYEOF
    rc=$?
    secs=$((t1 - t0))
    if [ $ok -eq 1 ] && [ $rc -eq 0 ] && [ $secs -lt 600 ]; then
        echo "PASS perf256: N = 256, $STEPS steps, run ${secs}s (< 600 s), trace equals golden"; exit 0
    fi
    echo "FAIL perf256: tb_ok=$ok golden_rc=$rc run=${secs}s"; cat "$D/check.log"; exit 1
fi

RUN=${1:?usage: run.sh <run> | --perf256}
row=$(awk -v r="$RUN" '$1 == r' "$ROOT/sim/out/top/tests.txt")
[ -n "$row" ] || { echo "FAIL $RUN: not in sim/out/top/tests.txt (run scripts/run_rtl_tests.sh first)"; exit 1; }
read -r run case n ncon nlev lat lab maxcyc long extra <<< "$row"
[ "$extra" = "-" ] && extra=""
D="$OUT/$RUN"; rm -rf "$D"; mkdir -p "$D"
build "$D" $n $ncon $nlev $lat $lab $extra || { echo "FAIL $RUN: build (see $D/build.log)"; exit 1; }
t0=$(date +%s)
"$D/obj/tbv" +cfg="$ROOT/sim/out/top/$case/test.cfg" +trace="$D/rtl.trace" +act="$D/rtl.act" +rs="$D/rtl.rs" +maxcyc=$maxcyc > "$D/rtl.log" 2>&1
secs=$(( $(date +%s) - t0 ))
"$PY" "$ROOT/scripts/golden/check_top.py" "$ROOT/sim/out/top/$case" "$D" > "$D/check.log" 2>&1
line=$(head -1 "$D/check.log")
ICA="$ROOT/sim/out/run/$RUN"
if [ ! -f "$ICA/rtl.trace" ]; then
    "$ROOT/scripts/run_rtl_tests.sh" --only "^$RUN\$" > "$D/icarus.log" 2>&1
fi
if [ -f "$ICA/rtl.trace" ] && cmp -s "$D/rtl.trace" "$ICA/rtl.trace" && { [ ! -f "$ICA/rtl.act" ] || cmp -s "$D/rtl.act" "$ICA/rtl.act"; }; then
    same="byte-identical to Icarus"
else
    same="DIFFERS from Icarus"
fi
case "$line" in
    PASS*) [ "$same" = "byte-identical to Icarus" ] && { echo "PASS $RUN: Verilator ${secs}s, $same, ${line#PASS $RUN: }"; exit 0; } ;;
esac
echo "FAIL $RUN: $same; $line"; exit 1
