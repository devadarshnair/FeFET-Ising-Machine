#!/bin/bash
# Round 3 synthesis of the T-1 / T-6 / screening digital blocks (rtl/r3/r3_blocks.v) with the timing study v1 flow (Yosys + ABC on Nangate45 typical,
# OpenSTA). Power is reported at three input activities so idle (0), event (1.0) and nominal (0.1) energies can be separated.
#   rtl/r3/run_round3.sh      -> sim/out/hw/r3/<tag>/{stat.txt,power_a*.txt,sta_paths.txt}
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PDK=${TT_PDK:-$HOME/tools/pdk/nangate45}
LIB=$PDK/NangateOpenCellLibrary_typical.lib
YOSYS=${TT_YOSYS:-$HOME/tools/yosys/bin/yosys}
STA=${TT_STA:-$HOME/tools/sta/bin/sta}
PERIOD_NS=${TT_PERIOD_NS:-2.0}
OUT=${R3_OUT:-$ROOT/sim/out/hw/r3}
mkdir -p "$OUT"
SRC="$ROOT/rtl/src/field_unit.v $ROOT/rtl/src/clk_gate.v $ROOT/rtl/r3/r3_blocks.v"
{ "$YOSYS" -V; "$STA" -version; } > "$OUT/tools.txt" 2>&1
NFAIL=0
run() {   # run <tag> <top> [param=value ...]
    local tag=$1 top=$2; shift 2
    local d="$OUT/$tag"; mkdir -p "$d"
    {
        for f in $SRC; do echo "read_verilog -sv $f"; done
        for kv in "$@"; do echo "chparam -set ${kv%%=*} ${kv#*=} $top"; done
        echo "hierarchy -check -top $top"
        echo "synth -flatten -top $top"
        echo "dfflibmap -liberty $LIB"
        echo "abc -liberty $LIB -D $(awk "BEGIN{print $PERIOD_NS*1000}")"
        echo "hilomap -singleton -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z"
        echo "setundef -zero"
        echo "write_verilog -noattr -noexpr $d/net_vec.v"
        echo "splitnets -ports"
        echo "opt_clean -purge"
        echo "tee -o $d/stat.txt stat -liberty $LIB"
        echo "write_verilog -noattr -noexpr $d/net.v"
    } > "$d/synth.ys"
    if ! timeout 1800 "$YOSYS" -q -l "$d/yosys.log" "$d/synth.ys" > /dev/null 2>&1; then echo "FAIL synth $tag"; NFAIL=$((NFAIL+1)); return; fi
    cat > "$d/sta.tcl" <<TCL
read_liberty $LIB
read_verilog $d/net.v
link_design $top
create_clock -name clk -period $PERIOD_NS [get_ports clk]
set_input_delay 0.10 -clock clk [delete_from_list [all_inputs] [get_ports clk]]
set_output_delay 0.05 -clock clk [all_outputs]
set_load 0.004 [all_outputs]
report_checks -path_delay max -digits 4 > $d/sta_paths.txt
foreach a {0.0 0.1 1.0} {
  set_power_activity -input -activity \$a
  report_power -digits 6 > $d/power_a\$a.txt
}
exit
TCL
    if timeout 900 "$STA" -no_splash -exit "$d/sta.tcl" > "$d/sta.log" 2>&1; then echo "OK   $tag"; else echo "FAIL sta $tag"; NFAIL=$((NFAIL+1)); fi
}
run lane_t1 r3_lane_t1 HW=16
run lane_t1_ungated r3_lane_t1_ungated HW=16
for n in 512 1024; do
    run remap_N$n r3_remap N=$n S=$((n / 32))          # spares = 1/32 of the rows (about 3 %)
    run screen_N$n r3_screen_ctl N=$n
    run lcor4_N$n r3_lcor_col N=$n K=4
    run lcor16_N$n r3_lcor_col N=$n K=16
done
echo "failures: $NFAIL"
[ $NFAIL -eq 0 ]
