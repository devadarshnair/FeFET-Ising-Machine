#!/bin/bash
# timing study v2: every offline re-pricing run of the report (no new simulations): increment ladder and analog sensitivity corners, Stage 3 and Stage 4.
#   scripts/hw_timing/reprice_all.sh <stage 3|4> <group: ladder|analog|annot> [raw dir]
# Heavy-ish (evaluator bootstrap): run under the local job queue (--rss 2); chunked by group so each job stays well under 1 h.
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY=${TIM_PY:-$HOME/miniconda3/envs/swref/bin/python}
ST=$1; GROUP=$2
RAW=${3:-$ROOT/sim/out/hw/stage$ST}
OUT=$ROOT/docs/hw/results/timing_v2
P="$PY -I $ROOT/scripts/hw_timing/reprice_v2.py --stage $ST --raw $RAW"
PFX=$([ "$ST" = 3 ] && echo h6 || echo h7)
export NUMBA_CACHE_DIR=$ROOT/sim/out/numba_cache
case $GROUP in
ladder)
    for v in L1_kc2only L2_pipe L3_sel L3_clk L3_rc L3_v2 L3_lane L3_laneclk L3_laneclk_worst L4_settle20; do
        $P --variant $v --out $OUT/${PFX}_$v.json > $OUT/${PFX}_$v.log 2>&1; echo "$v rc=$?"
    done ;;
analog)
    # one-at-a-time analog corners on the primary pricing (L3_v2), and all-low / all-high
    for c in $("$PY" -I -c "import sys; sys.path.insert(0, '$ROOT/scripts/hw_timing'); import analog_model as a; print(' '.join(a.sensitivity_corners()))"); do
        args=$("$PY" -I -c "import sys; sys.path.insert(0, '$ROOT/scripts/hw_timing'); import analog_model as a; k = a.sensitivity_corners()['$c']; print(' '.join(f'{r}={x}' for r, x in k['scale'].items()), '|', k['settle_ns'] or '')")
        sc=${args%%|*}; st=${args##*|}
        v=L3_v2; [ -n "${st// /}" ] && v=L4_settle${st// /}
        $P --variant $v ${sc:+--scale $sc} --out $OUT/${PFX}_analog_$c.json > $OUT/${PFX}_analog_$c.log 2>&1; echo "$c rc=$?"
    done ;;
recheck3)
    # restart-unit seed rows changed the N = 1024 restart medians / worst: re-price the variants they can touch
    for v in L3_v2 L3_laneclk L3_laneclk_worst L5_worst L3_lane L5_ungated; do
        $P --variant $v --out $OUT/${PFX}_$v.json > $OUT/${PFX}_$v.log 2>&1; echo "$v rc=$?"
    done ;;
annot)
    $P --variant L5_ungated --out $OUT/${PFX}_L5_ungated.json > $OUT/${PFX}_L5_ungated.log 2>&1; echo "L5_ungated rc=$?"
    for v in L5_mesa0 L5_mesa1 L5_worst; do $P --variant $v --out $OUT/${PFX}_$v.json > $OUT/${PFX}_$v.log 2>&1; echo "$v rc=$?"; done
    $P --variant L5_laneratio --annotated $OUT/annotated_rows.json --out $OUT/${PFX}_L5_laneratio.json > $OUT/${PFX}_L5_laneratio.log 2>&1; echo "L5_laneratio rc=$?" ;;
esac
