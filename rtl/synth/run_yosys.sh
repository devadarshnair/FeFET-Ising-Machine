#!/bin/bash
# P3.09: generic Yosys synthesis (synth -flatten, flops legalised to plain DFF + gates) of every block at N = 64
# and N = 256 (N-independent blocks once). Writes sim/out/hw/p3/yosys/<block>_N<n>.{ys,log,json}, then
# scripts/synth_report.py builds docs/hw/results/P3.09.md and docs/hw/results/p309_gate_counts.csv.
# Run: rtl/synth/run_yosys.sh
# rc 0 only if every block synthesised.
# Env: ONLY="block:tag ..." synthesises just those (retry); TMO=<seconds> per-block wall limit (default 1800).
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export PATH=$HOME/tools/yosys/bin:$PATH
OUT="$ROOT/sim/out/hw/p3/yosys"
PY=${TIM_PY:-$HOME/miniconda3/envs/swref/bin/python}
mkdir -p "$OUT"
SRC="$(ls "$ROOT"/rtl/src/*.v | grep -v cim_field_unit.v) $ROOT/rtl/synth/synth_wrappers.v"   # cim_field_unit.v: behavioural, while loop, not synthesisable (reported as n/a)
NFAIL=0

# synth <block> <top module> <tag> [param=value ...]
synth() {
    local block=$1 top=$2 tag=$3; shift 3
    if [ -n "${ONLY:-}" ] && ! echo " $ONLY " | grep -q " $block:$tag "; then return; fi
    local ys="$OUT/${block}_$tag.ys"
    {
        for f in $SRC; do echo "read_verilog -sv $f"; done
        for kv in "$@"; do echo "chparam -set ${kv%%=*} ${kv#*=} $top"; done
        echo "hierarchy -check -top $top"
        echo "synth -flatten ${NOABC:+-noabc} -top $top"
        echo "dfflegalize -cell \$_DFF_P_ 01"
        echo "opt_clean"
        echo "tee -o $OUT/${block}_$tag.stat.json stat -json"
        echo "stat"
    } > "$ys"
    if timeout "${TMO:-1800}" yosys -q -l "$OUT/${block}_$tag.log" "$ys" > "$OUT/${block}_$tag.out" 2>&1; then
        printf 'OK   %-14s %s\n' "$block" "$tag"
    else
        printf 'FAIL %-14s %s (see %s)\n' "$block" "$tag" "$OUT/${block}_$tag.log"; NFAIL=$((NFAIL + 1))
    fi
}

for n in 64 256; do
    synth select_tree   select_tree        N$n N=$n
    synth select_lvl    syn_select_tree_lvl N$n N=$n   # P3.11: level-indexed equivalent (tb_select_eq.v); ABC also > 1800 s at N = 256
    NOABC=1 synth selnoabc syn_select_tree_lvl N$n N=$n   # P3.11: same, no ABC (exact generic netlist, unoptimised)
    synth spin_reg      spin_reg           N$n N=$n
    synth restart_unit  restart_unit       N$n N=$n
    synth power_ctl     power_ctl          N$n N=$n
    synth constraint    constraint_unit    N$n N=$n
    synth tim_ctrl      tim_ctrl           N$n N=$n
    synth tcam_lite     tcam_lite          N$n N=$n M=16
    synth shadow_reg    syn_shadow_reg     N$n N=$n
    synth coupling_mem  coupling_mem       N$n N=$n JW=10 BW=12
    synth tcam_stub     tcam_stub          N$n NROW=$n
done
# P3.12: partitioned select_tree N = 256 = 4 x selpcnt(64) + selpglue + selpwalk(64); each ABC-synthesised alone, summed in synth_report.py
synth selpcnt  syn_sel_cnt  N64 N=64
synth selpwalk syn_sel_walk N64 N=64
synth selpglue syn_sel_glue N256 PN=64
for n in 32 128; do synth select_tree select_tree N$n N=$n; done   # P3.11: scaling cross-check for N = 256
synth xoshiro128ss  xoshiro128ss     ind
synth splitmix64    splitmix64       ind
synth lane_logic    syn_lane_logic   ind
synth field_unit    field_unit       ind JW=10 BW=12
synth accept_unit   accept_unit      ind
synth accept_lut    accept_lut       ind
synth offset_unit   offset_unit      ind
synth temp_sched    temp_sched       ind
synth query_enc     query_enc        ind
synth stall_counter syn_stall_counter ind

"$PY" -I -B "$ROOT/scripts/synth_report.py" "$OUT" "$ROOT" || NFAIL=$((NFAIL + 1))
[ $NFAIL -eq 0 ]
