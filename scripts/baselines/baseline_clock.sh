#!/bin/bash
# P4_v2 section 7 (A7): each baseline's own clock. Synthesises + places/routes the lane at the Fujitsu DA widths (16 b couplers,
# 26 b biases, 32 b field, 26 b offset) and, under the identical flow, our lane as the reference, using the UNCHANGED timing study v1
# flow functions of rtl/pnr/run_timing_v1.sh taken from the committed tree (git archive HEAD), so concurrent RTL work in the
# worktree cannot leak in. Output: sim/out/hw/baselines_v2/clock/<tag>/ ; rows: scripts/baselines/baseline_clock.py.
#   scripts/baselines/baseline_clock.sh
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SNAP=$(mktemp -d)
trap 'rm -rf "$SNAP"' EXIT
git -C "$ROOT" archive HEAD rtl | tar -x -C "$SNAP"
git -C "$ROOT" rev-parse HEAD > "$ROOT/sim/out/hw/baselines_v2/clock_rtl_commit.txt" 2>/dev/null || true
export TT_OUT=$ROOT/sim/out/hw/baselines_v2/clock
mkdir -p "$TT_OUT"
LAST=$(grep -n '^synth_sta lane ' "$SNAP/rtl/pnr/run_timing_v1.sh" | cut -d: -f1)
sed -n "1,$((LAST - 1))p" "$SNAP/rtl/pnr/run_timing_v1.sh" | sed "s|^ROOT=.*|ROOT=$SNAP|" > "$SNAP/flow_defs.sh"
set --
cd "$SNAP/rtl/pnr" && source "$SNAP/flow_defs.sh"
synth_sta lane_ours tt_lane_i11
synth_sta lane_b3   tt_lane_i11 JW=16 BW=26 HW=32 EW=26
pnr lane_ours tt_lane_i11
pnr lane_b3   tt_lane_i11
echo "failures: $NFAIL"
[ $NFAIL -eq 0 ]
