#!/bin/bash
# Run every v0 device and TCAM test (ngspice decks and their checkers), each through the memory
# guard, print PASS/FAIL per test and a summary. Exit status 1 if any test failed or any step broke.
#
# Usage: scripts/run_spice_tests.sh [all|device|tcam]      (default: all)
# Env:   MC_DECKS (default 25) and MC_K (default 8): Monte Carlo decks x samples per deck (test 3d).
#        QUICK=1 sets MC_DECKS=3 for a fast smoke run (the char table is then not representative).
# Outputs go to sim/out/ (git-ignored); bulky raw files (retention holds) are deleted once used, and
# the Monte Carlo decks write only ngspice measure lines. Generated TCAM decks are rewritten from the latest device
# results, so run the device part before the TCAM part.
cd "$(dirname "$0")/.." || exit 2
PY=${PY:-$HOME/miniconda3/envs/swref/bin/python}
G=scripts/run_guarded.sh
PART=${1:-all}
MC_DECKS=${MC_DECKS:-25}; MC_K=${MC_K:-8}
[ "${QUICK:-0}" = 1 ] && MC_DECKS=3
LOG=sim/out/run_spice_tests.log
mkdir -p sim/out/{t1a,t1b,t1c,mos,t1d,t1f,t1e,t3a,t3b,t3c,t3d}
: > "$LOG"
BROKEN=0

spice() {   # spice <deck> [GUARD_S]: run one deck, keep its log, flag a broken run
  local deck=$1 s=${2:-600} out
  case "$deck" in sim/out/*) out=${deck%.cir}.log ;; *) out=sim/out/$(basename "$deck" .cir).log ;; esac
  GUARD_S=$s $G ngspice -b -n "$deck" > "$out" 2>&1
  local rc=$?
  if [ $rc -ne 0 ] || grep -qiE '^error|fatal|singular matrix|timestep too small' "$out"; then
    echo "BROKEN  ngspice $deck (rc=$rc, see $out)" | tee -a "$LOG"; BROKEN=$((BROKEN+1))
  fi
}
py() {      # py <script> [args]: run a Python step; checkers print RESULT lines and exit 1 on FAIL
  local tmp=sim/out/py_step.log
  GUARD_S=${GUARD_S_PY:-900} $G "$PY" "$@" > "$tmp" 2>&1
  local rc=$?
  cat "$tmp" >> "$LOG"
  grep -E '^(RESULT|INFO|make_|gen_)' "$tmp"
  if [ $rc -ne 0 ] && { grep -q Traceback "$tmp" || ! grep -q '^RESULT' "$tmp"; }; then
    echo "BROKEN  python $* (rc=$rc, see $LOG)" | tee -a "$LOG"; BROKEN=$((BROKEN+1))
  fi
}

if [ "$PART" = all ] || [ "$PART" = device ]; then
  py scripts/gen_fefet_lib.py --check
  spice models/mosfet/tb_standin45.cir
  spice device/tb/t1a_nls_setA.cir;      py device/tb/check_t1a.py
  spice device/tb/t1b_loop_setB.cir
  spice device/tb/t1b_loop_slow_setB.cir; py device/tb/check_t1b.py
  spice device/tb/t1c_pulse_setB.cir 1200; py device/tb/check_t1c.py
  spice device/tb/mos_table.cir
  for f in device/tb/t1d/t1d_w*.cir; do spice "$f" 1500; done; py device/tb/check_t1d.py
  for f in device/tb/t1f/t1f_w*.cir; do spice "$f" 1500; done; py device/tb/check_t1f.py
  py device/tb/make_t1e.py --stage 1
  for f in device/tb/t1e/t1e_hold_*.cir; do spice "$f" 1800; done
  py device/tb/make_t1e.py --stage 2;  spice device/tb/t1e/t1e_read.cir;  py device/tb/check_t1e.py
  rm -f sim/out/t1e/t1e_hold_*.csv   # bulky raw holds; the read deck already holds the saved states
fi
if [ "$PART" = all ] || [ "$PART" = tcam ]; then
  py circuit/tcam/make_tcam.py write
  spice circuit/tcam/t3a_write.cir 1200; spice circuit/tcam/t3a_disturb.cir 1200
  py circuit/tcam/make_tcam.py read;    spice circuit/tcam/t3a_read.cir;  py circuit/tcam/check_t3a.py
  py circuit/tcam/make_tcam.py search
  spice circuit/tcam/t3b_word8.cir 1500; spice circuit/tcam/t3b_word8_frozen.cir 600
  for f in circuit/tcam/t3c_word64_m*.cir; do spice "$f" 2400; done
  py circuit/tcam/check_t3b.py
  py circuit/tcam/make_tcam.py mc "$MC_DECKS" "$MC_K"
  for f in sim/out/t3d/t3d_mc*.cir; do GUARD_MB=1000 spice "$f" 1800; done
  py circuit/tcam/check_t3d.py
fi

NP=$(grep -c '^RESULT .* PASS ' "$LOG"); NF=$(grep -c '^RESULT .* FAIL ' "$LOG")
echo "================ summary ================"
grep -E '^RESULT' "$LOG" | awk '{printf "%-24s %s\n", $2, $3}'
echo "PASS $NP   FAIL $NF   broken steps $BROKEN"
[ "$NF" -eq 0 ] && [ "$BROKEN" -eq 0 ]
