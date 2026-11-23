#!/bin/bash
# C2C_ESTIMATE bracket runs: p3n240, keys 2101-2112 x 3 seeds, k = 1; one local job queue job per point, sequential.
cd "$(dirname "$0")/../../../.."
E=docs/hw/diagnosis/c2c_evidence
K=$(seq -s, 2101 2112)
S3CFG="kick_c=0,knob=0.25,esc_step=1,esc_max=2,sim_incremental=true,sim_refresh=200"
run() {  # name mult cond mit shares cfg
  local name=$1 mult=$2 cond=$3 mit=$4 sh=$5 cfg=$6
  local extra=(); [ -n "$cfg" ] && extra=(--cfg "$cfg")
  S0_L0_SIGMA_MULT=$mult $HOME/miniconda3/envs/swref/bin/python scripts/testing/s0_sweep.py ours_kc2_i11 p3n240 $cond $mit $sh $K 3 $E/$name.jsonl "${extra[@]}"
}
run h8_ideal 1 ideal wv+diff+cal 0.5 ""
run s3_ideal 1 ideal wv+diff+cal+scr8 0.5 "$S3CFG"
for m in 1 0.6667 1.3333; do      # level-0 sigma 0.15 (model) / 0.10 / 0.20 V
  run h8_t$m $m nominal wv+diff+cal 0.02,0.1,0.3 ""
  run s3_t$m $m nominal wv+diff+cal+scr8 0.02,0.1,0.3 "$S3CFG"
done
