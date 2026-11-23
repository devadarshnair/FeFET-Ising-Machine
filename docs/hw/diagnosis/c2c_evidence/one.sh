#!/bin/bash
# one.sh MIT SIGMA_MULT SHARE OUTNAME : one bracket point (36 runs) of the Stage 3 stack, foreground via local job queue
cd "$(dirname "$0")/../../../.."
E=docs/hw/diagnosis/c2c_evidence; PY=$HOME/miniconda3/envs/swref/bin/python
CFG="kick_c=0,knob=0.25,esc_step=1,esc_max=2,sim_incremental=true,sim_refresh=200"
S0_L0_SIGMA_MULT=$2 $PY scripts/testing/s0_sweep.py ours_kc2_i11 p3n240 nominal $1 $3 $(seq -s, 2101 2112) 3 $E/$4.jsonl --cfg "$CFG" >> $E/run_lcor.log 2>&1
echo "$4 share $3 rc $?"
