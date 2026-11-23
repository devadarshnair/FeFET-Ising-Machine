#!/bin/bash
# Verilator lint of tim_top, default and -Wall, at N = 8/64/256 with the optional blocks built (CIM = 1, TCL = 1), in the v0 build, the pipelined select tree (all cuts / no extra cuts), the Kc2-only restart unit and the ungated generators (RNG_CG = 0). Must print nothing
# but the OK line: every remaining style-only warning class is waived at the top of its file with a reason (lint_off comments).
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export PATH=$HOME/tools/verilator/bin:$PATH
rc=0
for n in 8 64 256; do
    for w in "" "-Wall"; do
        for v in "" "-GSEL_PIPE=1 -GSEL_ADD_CUT=-1 -GSEL_WALK_CUT=-1 -GRS_MESA=0" "-GSEL_PIPE=1 -GSEL_ADD_CUT=0 -GSEL_WALK_CUT=0" "-GRNG_CG=0"; do
            out=$(verilator --lint-only $w --top-module tim_top -GN=$n -GCIM=1 -GTCL=1 $v "$ROOT"/rtl/src/*.v 2>&1 | grep -E '^%(Warning|Error)')
            [ -z "$out" ] || { echo "LINT N=$n $w $v:"; echo "$out"; rc=1; }
        done
    done
done
[ $rc -eq 0 ] && echo "LINT OK (N = 8/64/256, default and -Wall)"
exit $rc
