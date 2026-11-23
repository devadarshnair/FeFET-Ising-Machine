#!/bin/bash
# timing study v2: P&R run-to-run variance at N = 1024. One finished synthesis (block dir with net.v / constr.sdc) is placed and routed again for every
# (seed, floorplan utilisation): place_pins -random_seed <seed>, UTIL = 30 / 60 %. Outputs sim/out/hw/timing_v1/t2seed/<block>_s<seed>_u<util>/ (same files as the
# main flow: pnr_paths.txt, pnr.log, pnr_power.txt, ...), read by scripts/hw_timing/t2_report.py (variance rows: median and worst over the runs).
#   scripts/hw_timing/t2_seed_runs.sh <synth dir> <block> <top module> "<seeds>" "<utils>"
# Heavy (restart units: up to ~45 min per run): run under the local job queue, one run per job when the block is a restart unit.
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SRC=$1; BLK=$2; TOP=$3; SEEDS=${4:-"1 2 3"}; UTILS=${5:-"30 60"}
OUTD=$ROOT/sim/out/hw/timing_v1/t2seed
mkdir -p "$OUTD"
for u in $UTILS; do
    for s in $SEEDS; do
        name=${BLK}_s${s}_u${u}
        if [ ! -s "$OUTD/$name/pnr_paths.txt" ]; then
            rm -rf "$OUTD/$name"; mkdir -p "$OUTD/$name"
            cp "$SRC/$BLK"/{net.v,constr.sdc,stat.txt,sta_paths.txt,power.txt,synth.ys} "$OUTD/$name"/ 2>/dev/null
            SEED=$s UTIL=$u TT_OUT=$OUTD TT_PNR_TIMEOUT=${TT_PNR_TIMEOUT:-3300} "$ROOT/rtl/pnr/run_timing_v2.sh" --pnr-one "$name" "$TOP"
        fi
        echo "$name rc=$?"
    done
done
