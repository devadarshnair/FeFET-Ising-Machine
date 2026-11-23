#!/bin/bash
# Compile and run every TIM v0 test through the memory guard (scripts/run_guarded.sh), one job at a time.
# Prints PASS/FAIL per test and a summary table; exits non-zero if any test fails.
#
# Usage: scripts/run_rtl_tests.sh [--long] [--only <regex>]
#   default  golden self-test, test generation, unit testbenches, elaboration at N = 16/64/256, short top-level runs
#   --long   also the long top-level runs (marked "long" in sim/out/top/tests.txt)
#   --only   run only tests whose name matches the regex (test generation always runs)
# Env: TIM_PY (Python interpreter; default the swref env). Outputs go to sim/out/ (git-ignored).
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY=${TIM_PY:-$HOME/miniconda3/envs/swref/bin/python}
G="$ROOT/scripts/run_guarded.sh"
OUT="$ROOT/sim/out"
SRC=$(ls "$ROOT"/rtl/src/*.v)
export NUMBA_CACHE_DIR="$OUT/numba_cache"

LONG=0
ONLY="."
while [ $# -gt 0 ]; do
    case "$1" in
        --long) LONG=1 ;;
        --only) ONLY="$2"; shift ;;
        *) echo "unknown option $1"; exit 2 ;;
    esac
    shift
done

mkdir -p "$OUT/unit" "$OUT/run" "$OUT/elab" "$NUMBA_CACHE_DIR"
NAMES=()
STATUS=()
SECS=()
NFAIL=0

record() {   # name status seconds detail
    NAMES+=("$1"); STATUS+=("$2"); SECS+=("$3")
    [ "$2" = "PASS" ] || NFAIL=$((NFAIL + 1))
    printf '%-4s %-16s %4ss  %s\n' "$2" "$1" "$3" "$4"
}

want() { echo "$1" | grep -Eq "$ONLY"; }

# ---------------------------------------------------------------- golden model
if want golden_selftest; then
    t0=$(date +%s)
    log="$OUT/unit/golden_selftest.log"
    "$G" "$PY" -I -B "$ROOT/scripts/golden/selftest_golden.py" > "$log" 2>&1
    rc=$?
    t1=$(date +%s)
    line=$(tail -1 "$log")
    if [ $rc -eq 0 ]; then record golden_selftest PASS $((t1 - t0)) "$line"
    else record golden_selftest FAIL $((t1 - t0)) "$line (see $log)"; grep '^FAIL' "$log"; fi
fi

t0=$(date +%s)
if ! "$G" "$PY" "$ROOT/scripts/golden/gen_tests.py" --out "$OUT" > "$OUT/gen_tests.log" 2>&1; then
    record gen_tests FAIL $(( $(date +%s) - t0 )) "test generation failed (see $OUT/gen_tests.log)"
    echo "SUMMARY: test generation failed"; exit 1
fi

# ---------------------------------------------------------------- unit testbenches
UNIT_TBS="tb_rng tb_select tb_select_pipe tb_accept tb_field tb_coupling tb_offset_temp tb_tcam tb_pricer tb_constraint tb_restart tb_cim_field"
for tb in $UNIT_TBS; do
    want "$tb" || continue
    t0=$(date +%s)
    vvpf="$OUT/unit/$tb.vvp"
    log="$OUT/unit/$tb.log"
    if ! "$G" iverilog -g2012 -Wall -s "$tb" -o "$vvpf" "$ROOT/rtl/tb/$tb.v" $SRC > "$OUT/unit/$tb.compile.log" 2>&1; then
        record "$tb" FAIL $(( $(date +%s) - t0 )) "compile error (see $OUT/unit/$tb.compile.log)"
        continue
    fi
    "$G" vvp -n "$vvpf" +vec="$OUT/unit/rng_vectors.txt" +vec0="$OUT/unit/cim_vec0.txt" +vec1="$OUT/unit/cim_vec1.txt" > "$log" 2>&1
    line=$(grep -E '^(PASS|FAIL)' "$log" | tail -1)
    t1=$(date +%s)
    case "$line" in
        PASS*) record "$tb" PASS $((t1 - t0)) "${line#PASS $tb }" ;;
        *)     record "$tb" FAIL $((t1 - t0)) "${line:-no PASS line} (see $log)" ;;
    esac
done

# ---------------------------------------------------------------- elaboration of the top level
for n in 16 64 256; do
    name="elab_n$n"
    want "$name" || continue
    t0=$(date +%s)
    log="$OUT/elab/tim_top_n$n.log"
    if "$G" iverilog -g2012 -Wall -s tim_top -P tim_top.N=$n -o "$OUT/elab/tim_top_n$n.vvp" $SRC > "$log" 2>&1; then
        nw=$(grep -c -i warning "$log")
        record "$name" PASS $(( $(date +%s) - t0 )) "tim_top elaborates at N = $n ($nw warnings)"
    else
        record "$name" FAIL $(( $(date +%s) - t0 )) "elaboration failed (see $log)"
    fi
done

# ---------------------------------------------------------------- top-level runs, bit-exact against golden
while read -r run case n ncon nlev lat lab maxcyc long extra <&3; do   # fd 3: vvp/python must not eat the list
    [ "$extra" = "-" ] && extra=""
    want "$run" || continue
    if [ "$long" = "long" ] && [ $LONG -eq 0 ]; then
        continue
    fi
    t0=$(date +%s)
    R="$OUT/run/$run"
    rm -rf "$R"; mkdir -p "$R"
    if ! "$G" iverilog -g2012 -Wall -s tb_top -P tb_top.N=$n -P tb_top.NCON=$ncon -P tb_top.NLEV=$nlev \
            -P tb_top.SEARCH_LAT=$lat -P tb_top.LAB=$lab $extra -o "$R/tb.vvp" "$ROOT/rtl/tb/tb_top.v" $SRC \
            > "$R/compile.log" 2>&1; then
        record "$run" FAIL $(( $(date +%s) - t0 )) "compile error (see $R/compile.log)"
        continue
    fi
    "$G" vvp -n "$R/tb.vvp" +cfg="$OUT/top/$case/test.cfg" +trace="$R/rtl.trace" +act="$R/rtl.act" +rs="$R/rtl.rs" +maxcyc=$maxcyc \
        > "$R/rtl.log" 2>&1
    "$G" "$PY" "$ROOT/scripts/golden/check_top.py" "$OUT/top/$case" "$R" > "$R/check.log" 2>&1
    t1=$(date +%s)
    line=$(head -1 "$R/check.log")
    case "$line" in
        PASS*) record "$run" PASS $((t1 - t0)) "${line#PASS $run: }" ;;
        *)     record "$run" FAIL $((t1 - t0)) "${line#FAIL $run: }" ;;
    esac
    tail -n +2 "$R/check.log" | sed 's/^/     /'
done 3< "$OUT/top/tests.txt"

# ---------------------------------------------------------------- summary
echo
echo "SUMMARY"
printf '  %-16s %-4s %6s\n' test result secs
for k in "${!NAMES[@]}"; do
    printf '  %-16s %-4s %6s\n' "${NAMES[$k]}" "${STATUS[$k]}" "${SECS[$k]}"
done
echo "  ${#NAMES[@]} tests, $(( ${#NAMES[@]} - NFAIL )) passed, $NFAIL failed$([ $LONG -eq 0 ] && echo ' (long runs skipped; use --long)')"
[ $NFAIL -eq 0 ]
