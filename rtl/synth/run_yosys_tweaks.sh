#!/bin/bash
# I11 / I3 / I5: generic Yosys synthesis (same flow as P3.09: synth -flatten, dfflegalize to $_DFF_P_) of the logic the three
# tweaks add: lam_ramp (I3), hold_ctl and lane_rnd_mux N = 64/256 (I5), accept_unit with the I11 greedy pin free vs tied low.
# Then scripts/synth_report_tweaks.py writes docs/hw/results/I11_I3_I5_synth.md + the gate-count csv and appends rows to
# docs/hw/energy_table_v1_p309.csv. Run under the gate:
#   rtl/synth/run_yosys_tweaks.sh
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export PATH=$HOME/tools/yosys/bin:$PATH
OUT="$ROOT/sim/out/hw/p3/yosys_tweaks"
PY=${TIM_PY:-$HOME/miniconda3/envs/swref/bin/python}
mkdir -p "$OUT"
SRC="$(ls "$ROOT"/rtl/src/*.v | grep -v cim_field_unit.v) $ROOT/rtl/synth/synth_wrappers_tweaks.v"
NFAIL=0
synth() {   # synth <block> <top> <tag> [param=value ...]
    local block=$1 top=$2 tag=$3; shift 3
    local ys="$OUT/${block}_$tag.ys"
    {
        for f in $SRC; do echo "read_verilog -sv $f"; done
        for kv in "$@"; do echo "chparam -set ${kv%%=*} ${kv#*=} $top"; done
        echo "hierarchy -check -top $top"
        echo "synth -flatten -top $top"
        echo "dfflegalize -cell \$_DFF_P_ 01"
        echo "opt_clean"
        echo "tee -o $OUT/${block}_$tag.stat.json stat -json"
        echo "stat"
    } > "$ys"
    if timeout 900 yosys -q -l "$OUT/${block}_$tag.log" "$ys" > "$OUT/${block}_$tag.out" 2>&1; then
        printf 'OK   %-12s %s\n' "$block" "$tag"
    else
        printf 'FAIL %-12s %s (see %s)\n' "$block" "$tag" "$OUT/${block}_$tag.log"; NFAIL=$((NFAIL + 1))
    fi
}
synth lamramp   lam_ramp       ind
synth holdctl   hold_ctl       ind
synth rndmux    lane_rnd_mux   N64  LOG2N=6
synth rndmux    lane_rnd_mux   N256 LOG2N=8
synth acceptg   accept_unit    ind
synth acceptg0  syn_accept_g0  ind
synth add16     syn_add16      ind
"$PY" -I -B "$ROOT/scripts/synth_report_tweaks.py" "$OUT" "$ROOT" || NFAIL=$((NFAIL + 1))
[ $NFAIL -eq 0 ]
