#!/bin/bash
# timing study v2 (pipelined select tree, Kc2-only restart unit, N = 512): same Yosys + OpenSTA + OpenROAD flow and SDC as run_timing_v1.sh
# (this file differs only in the block list at the end; run_timing_v1.sh is kept unchanged so measured_v1 reproduces).
#   rtl/pnr/run_timing_v2.sh [--pnr] [--n "64 256 512 1024"] [--only <regex of block tag>]
# Pipeline cuts per N and tag are read from rtl/pnr/t2_cuts.txt (lines "N tag ADD_CUT WALK_CUT"); output sim/out/hw/timing_v1/t2/.
# Heavy run:  rtl/pnr/run_timing_v2.sh --pnr
# (Original header of run_timing_v1.sh follows.)
# timing study v1: technology-mapped synthesis (Yosys + ABC on Nangate45 / FreePDK45 typical), static timing and power (OpenSTA),
# and optional placement + CTS + global route (OpenROAD) of the digital blocks of the confirmed datapath.
#   rtl/pnr/run_timing_v1.sh [--smoke] [--pnr] [--n "64 256 1024"]
# Synthesis-only STA has ideal wires and no buffering (one high-fanout enable can dominate); the P&R numbers
# (repair_design buffering, CTS, repair_timing, global-route parasitics) are the ones reported.
# --smoke: N = 16 only, lane + rng + select, no P&R (CI-fast, ~1 min). Output: sim/out/hw/timing_v1/<tag>/ (gitignored).
# Heavy runs go through the gate, e.g.
#   rtl/pnr/run_timing_v1.sh --pnr
# Report: scripts/hw_timing/timing_v1_report.py <out dir> writes the measured_v1 rows.
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PDK=${TT_PDK:-$HOME/tools/pdk/nangate45}
LIB=$PDK/NangateOpenCellLibrary_typical.lib
YOSYS=${TT_YOSYS:-$HOME/tools/yosys/bin/yosys}
STA=${TT_STA:-$HOME/tools/sta/bin/sta}
OPENROAD=${TT_OPENROAD:-$HOME/miniconda3/envs/openroad/bin/openroad}
PERIOD_NS=${TT_PERIOD_NS:-2.0}     # synthesis target only; f_max comes from the measured critical path
ACT=${TT_ACT:-0.1}                 # documented switching activity for report_power (no VCD annotation)
SMOKE=0; PNR=0; NS="64 128 256 512 1024"; ONLY="."
while [ $# -gt 0 ]; do
    case $1 in --smoke) SMOKE=1; NS=16 ;; --pnr) PNR=1 ;; --n) NS=$2; shift ;; --only) ONLY=$2; shift ;; --pnr-one) ONE_NAME=$2; ONE_TOP=$3; shift 2 ;; *) echo "bad arg $1"; exit 2 ;; esac; shift
done
TAG=${TT_TAG:-t2}
OUT=${TT_OUT:-$ROOT/sim/out/hw/timing_v1/$TAG}
mkdir -p "$OUT"
for f in "$LIB" "$YOSYS" "$STA"; do [ -e "$f" ] || { echo "missing $f"; exit 3; }; done
( cd "$PDK" && sha256sum NangateOpenCellLibrary_typical.lib ) > "$OUT/lib.sha256"
{ "$YOSYS" -V; "$STA" -version; [ -x "$OPENROAD" ] && "$OPENROAD" -version 2>/dev/null; } > "$OUT/tools.txt" 2>&1
SRC="$(ls "$ROOT"/rtl/src/*.v | grep -v cim_field_unit.v) $ROOT/rtl/synth/synth_wrappers.v $ROOT/rtl/pnr/tt_wrappers.v"
NFAIL=0

synth_sta() {   # synth_sta <tag> <top> [param=value ...]; FLAT=0 keeps the hierarchy during ABC (select trees), flattened after
    local tag=$1 top=$2; shift 2
    local d="$OUT/$tag"; mkdir -p "$d"
    echo "$tag" | grep -Eq "$ONLY" || return
    if [ -s "$d/sta_paths.txt" ] && [ "${TT_RESUME:-1}" = 1 ]; then echo "SKIP $tag (done)"; return; fi
    local flat="-flatten"; [ "${FLAT:-1}" = 0 ] && flat=""
    {
        [ "${LIBCELLS:-0}" = 1 ] && echo "read_liberty -lib $LIB"
        for f in $SRC; do echo "read_verilog -sv $f"; done
        for kv in "$@"; do echo "chparam -set ${kv%%=*} ${kv#*=} $top"; done
        echo "hierarchy -check -top $top"
        echo "synth $flat -top $top"
        echo "dfflibmap -liberty $LIB"
        echo "abc -liberty $LIB -D $(awk "BEGIN{print $PERIOD_NS*1000}")"
        echo "hilomap -singleton -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z"
        echo "setundef -zero"
        echo "splitnets -ports"
        echo "opt_clean -purge"
        echo "flatten"
        echo "opt_clean -purge"
        echo "tee -o $d/stat.txt stat -liberty $LIB"
        echo "write_verilog -noattr -noexpr $d/net.v"
    } > "$d/synth.ys"
    if ! timeout 2400 "$YOSYS" -q -l "$d/yosys.log" "$d/synth.ys" > /dev/null 2>&1; then
        echo "FAIL synth $tag"; NFAIL=$((NFAIL + 1)); return
    fi
    local hasclk; hasclk=$(grep -c "input clk;" "$d/net.v")
    local ins="[all_inputs]" clk="create_clock -name clk -period $PERIOD_NS"
    if [ "$hasclk" -gt 0 ]; then ins="[delete_from_list [all_inputs] [get_ports clk]]"; clk="$clk [get_ports clk]"; fi
    cat > "$d/constr.sdc" <<SDC
$clk
set_input_delay 0.10 -clock clk $ins
set_output_delay 0.05 -clock clk [all_outputs]
set_load 0.004 [all_outputs]
# input delay 0.10 ns ~ DFF_X1 clk-to-Q, output delay 0.05 ns ~ DFF_X1 setup (Nangate45 typical): ports stand for flops
set_driving_cell -lib_cell DFF_X1 -pin Q $ins
SDC
    cat > "$d/sta.tcl" <<TCL
read_liberty $LIB
read_verilog $d/net.v
link_design $top
read_sdc $d/constr.sdc
report_checks -path_delay max -digits 4 -fields {fanout cap slew} > $d/sta_paths.txt
report_wns -digits 4 > $d/sta_wns.txt
report_tns -digits 4 >> $d/sta_wns.txt
set_power_activity -input -activity $ACT
report_power -digits 6 > $d/power.txt
exit
TCL
    if timeout 900 "$STA" -no_splash -exit "$d/sta.tcl" > "$d/sta.log" 2>&1; then
        echo "OK   $tag"
    else
        echo "FAIL sta $tag"; NFAIL=$((NFAIL + 1))
    fi
}

pnr() {   # pnr <tag> <top>: floorplan (60 % utilisation), global + detailed placement, CTS, global route, parasitic STA
    local tag=$1 top=$2 d="$OUT/$1"
    [ -s "$d/net.v" ] || return
    echo "$1" | grep -Eq "$ONLY" || return
    if [ -s "$d/pnr_paths.txt" ] && [ "${TT_RESUME:-1}" = 1 ]; then echo "SKIP pnr $tag (done)"; return; fi
    cat > "$d/pnr.tcl" <<TCL
read_lef $PDK/NangateOpenCellLibrary.tech.lef
read_lef $PDK/NangateOpenCellLibrary.macro.mod.lef
read_liberty $LIB
read_verilog $d/net.v
link_design $top
read_sdc $d/constr.sdc
initialize_floorplan -utilization ${UTIL:-60} -aspect_ratio 1 -core_space 2 -site FreePDK45_38x28_10R_NP_162NW_34O
make_tracks
place_pins -hor_layers metal3 -ver_layers metal2 -random${SEED:+ -random_seed $SEED}
global_placement -density 0.7
source $PDK/setRC.tcl
set_wire_rc -signal -layer metal3
set_wire_rc -clock -layer metal5
estimate_parasitics -placement
report_checks -path_delay max -digits 4 > $d/pnr_place_paths_prerepair.txt
repair_design
detailed_placement
estimate_parasitics -placement
if {[llength [all_registers]] > 0} {
  clock_tree_synthesis -buf_list {BUF_X4 BUF_X8} -root_buf BUF_X8 -sink_clustering_enable
  set_propagated_clock [all_clocks]
}
estimate_parasitics -placement
repair_timing -setup
detailed_placement
report_worst_slack -max -digits 4 > $d/pnr_place_wns.txt
set_routing_layers -signal metal2-metal8 -clock metal3-metal8
global_route -allow_congestion
estimate_parasitics -global_routing
report_checks -path_delay max -digits 4 > $d/pnr_paths.txt
report_worst_slack -max -digits 4 > $d/pnr_wns.txt
report_design_area
set_power_activity -input -activity $ACT
report_power -digits 6 > $d/pnr_power.txt
set die [ord::get_die_area]
puts "DIE_AREA_UM [expr {([lindex \$die 2]-[lindex \$die 0])*([lindex \$die 3]-[lindex \$die 1])}]"
exit
TCL
    if timeout ${TT_PNR_TIMEOUT:-2400} "$OPENROAD" -no_splash -exit "$d/pnr.tcl" > "$d/pnr.log" 2>&1; then
        echo "OK   pnr $tag (utilisation ${UTIL:-60} %)"
    elif [ -z "${UTIL:-}" ] && grep -q "PPL-0024" "$d/pnr.log"; then
        UTIL=25 pnr "$tag" "$top"      # pin-limited block (N-wide ports): retry once on a larger die
    else
        echo "FAIL pnr $tag (see $d/pnr.log)"; NFAIL=$((NFAIL + 1))
    fi
}

if [ -n "${ONE_NAME:-}" ]; then PNR=1; pnr "$ONE_NAME" "$ONE_TOP"; exit $NFAIL; fi   # one P&R run of an existing synthesised block (seed / utilisation study: SEED, UTIL)
CUTS=${T2_CUTS:-$ROOT/rtl/pnr/t2_cuts.txt}
# measured_v1 blocks at N = 128 and 512 (padded sizes used by Stage 3/4; v1 interpolated them): single-cycle tree, control, MESA restart unit
for n in $NS; do
    [ "$n" = 512 ] || [ "$n" = 128 ] || continue
    FLAT=0 synth_sta sel_N$n syn_select_tree_part N=$n
    synth_sta ctrl_N$n    tim_ctrl CIM=1 N=$n
    synth_sta restart_N$n restart_unit N=$n
done
# timing study v2 blocks: pipelined select tree and its controller (SEL_LAT cycles in SEL), Kc2-only restart unit (RS_MESA = 0)
while read -r n tag ac wc; do
    case "$n" in ""|\#*) continue ;; esac
    echo " $NS " | grep -q " $n " || continue
    lat=$(python3 -c "n=$n;L=n.bit_length()-1;print(2+bin($ac&((1<<L)-1)).count('1')+bin($wc&((1<<(L-1))-1)).count('1'))")
    if [ "${T2_SKIP_SELP:-0}" != 1 ]; then
        synth_sta selp_N${n}_$tag select_tree_pipe N=$n ADD_CUT=$ac WALK_CUT=$wc
        [ $PNR -eq 1 ] && pnr selp_N${n}_$tag select_tree_pipe
    fi
    cs=${T2_CTRL_STEM:-ctrlp}
    [ "${T2_CTRL:-1}" = 1 ] && synth_sta ${cs}_N${n}_$tag tim_ctrl CIM=1 N=$n SEL_LAT=$lat
    [ $PNR -eq 1 ] && [ "${T2_CTRL:-1}" = 1 ] && pnr ${cs}_N${n}_$tag tim_ctrl
done < "$CUTS"
for n in $NS; do
    synth_sta restartk_N$n restart_unit MESA=0 N=$n
    [ $PNR -eq 1 ] && pnr restartk_N$n restart_unit
done
if [ $PNR -eq 1 ]; then
    for n in $NS; do [ "$n" = 512 ] || [ "$n" = 128 ] || continue; pnr sel_N$n syn_select_tree_part; pnr ctrl_N$n tim_ctrl; pnr restart_N$n restart_unit; done
fi
# timing study v2 generator clock gating: gated xoshiro128** (no enable multiplexer, clock supplied gated) and the library clock gate
if [ "${T2_GEN:-0}" = 1 ]; then
    synth_sta rngg xoshiro128ss GATED=1
    LIBCELLS=1 synth_sta icg tt_icg
    [ $PNR -eq 1 ] && pnr rngg xoshiro128ss
fi
# full restart unit (MESA encoder + Kc2 kick) at every N, pipelined RTL (T2_RESTART_FULL = 1)
if [ "${T2_RESTART_FULL:-0}" = 1 ]; then
    for n in $NS; do
        synth_sta restart_N$n restart_unit N=$n
        [ $PNR -eq 1 ] && pnr restart_N$n restart_unit
    done
fi
echo "failures: $NFAIL"
[ $NFAIL -eq 0 ]
