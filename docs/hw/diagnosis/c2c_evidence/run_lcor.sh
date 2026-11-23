#!/bin/bash
# R3: realistic retirement: no per-cell spare redraw (scr off); per-cell correction table of k entries per column (lcorK).
cd "$(dirname "$0")/../../../.."
E=docs/hw/diagnosis/c2c_evidence; PY=$HOME/miniconda3/envs/swref/bin/python
K=$(seq -s, 2101 2112)
CFG="kick_c=0,knob=0.25,esc_step=1,esc_max=2,sim_incremental=true,sim_refresh=200"
for k in 16 64; do for m in 1 1.3333; do
  S0_L0_SIGMA_MULT=$m $PY scripts/testing/s0_sweep.py ours_kc2_i11 p3n240 nominal wv+diff+cal+lcor$k 0.02,0.1,0.3 $K 3 $E/s3lcor${k}_t$m.jsonl --cfg "$CFG"
done; done
S0_L0_SIGMA_MULT=1.3333 $PY scripts/testing/s0_sweep.py ours_kc2_i11 p3n240 nominal wv+diff+cal 0.02,0.1,0.3 $K 3 $E/s3none_t1.3333.jsonl --cfg "$CFG"
