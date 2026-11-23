#!/bin/bash
# timing study v2 C3: activity-annotated gate-level power of the representative runs (gl_cfg.py cfgs), single-cycle tree (v1 netlists, SEL_PIPE = 0)
# and pipelined tree (rule-A cut mask per N, SEL_PIPE = 1). Heavy: run under the local job queue (--rss 1.5), well under 1 h.
#   scripts/hw_timing/gl_run_all.sh <t1 dir> <sweep dir> <gl root> [<t2b dir> ["variants"]]
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
T1=$1; SW=$2; GL=$3; T2B=${4:-$ROOT/sim/out/hw/timing_v1/t2b}; VARS=${5:-"v1 pipe cg"}
PY=${TIM_PY:-$HOME/miniconda3/envs/swref/bin/python}
declare -A CUT=( [64]="0 0 selp_N64_a0_w" [256]="0 16 selp_N256_a0_w4" )
run() {   # run <rep> <N> <variant> <cim>   v1: single-cycle tree + free-running generators; pipe: pipelined tree + free-running generators;
          #                                    cg: pipelined tree + gated generators (RNG_CG = 1, gated xoshiro netlist, library clock gate)
    local rep=$1 n=$2 var=$3 cim=$4 out="$GL/${1}__${3}" params sel kind rng=$T1/rng/net.v icg=""
    if [ "$var" = v1 ]; then
        params="N=$n CIM=$cim RNG_CG=0"; sel=$T1/sel_N$n/net.v; kind=part
    elif [ "$var" = cg ]; then
        read -r ac wc tag <<< "${CUT[$n]}"
        params="N=$n CIM=$cim SEL_PIPE=1 SEL_ADD_CUT=$ac SEL_WALK_CUT=$wc RNG_CG=1"; sel=$SW/$tag/net.v; kind=pipe
        rng=$T2B/rngg/net.v; icg="--icg-net $T2B/icg/net.v"
    else
        read -r ac wc tag <<< "${CUT[$n]}"
        params="N=$n CIM=$cim SEL_PIPE=1 SEL_ADD_CUT=$ac SEL_WALK_CUT=$wc RNG_CG=0"; sel=$SW/$tag/net.v; kind=pipe
    fi
    local lanes="0,$((n/3)),$((2*n/3)),$((n-1))"
    [ -z "${GL_RESTA:-}" ] && rm -rf "$out"
    "$PY" -I "$ROOT/scripts/hw_timing/gl_power.py" --out "$out" --cfg "$GL/$rep/test.cfg" --params "$params" --lanes "$lanes" \
        --lane-net "$T1/lane/net.v" --rng-net "$rng" --sel-net "$sel" --sel-kind $kind $icg --maxcyc 400000 ${GL_RESTA:+--resta} > "$out.log" 2>&1
    echo "$rep $var rc=$?"
}
for rep in maxcut64_none maxcut64_kc2_i11 col64_kc2_i11; do
    for var in $VARS; do run $rep 64 $var 1; done
done
for var in $VARS; do run maxcut256_kc2_i11 256 $var 0; done
