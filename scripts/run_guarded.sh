#!/bin/bash
# Run one simulator job (iverilog, vvp, ngspice, python) under a memory and time cap.
# Usage: scripts/run_guarded.sh <command> [args...]
# Env: GUARD_MB (default 800, max 1500), GUARD_S (default 600, max 3600).
# Waits until at least 2000 MB is free; at most two guarded jobs run at once on the machine.
LIM=${GUARD_MB:-800}; [ "$LIM" -gt 1500 ] && LIM=1500
TMO=${GUARD_S:-600}; [ "$TMO" -gt 3600 ] && TMO=3600
got=""
while [ -z "$got" ]; do
  for slot in 1 2; do
    exec 9>"/tmp/hw_guard.slot$slot"
    if flock -n 9; then got=$slot; break; fi
    exec 9>&-
  done
  [ -z "$got" ] && sleep 3
done
while [ "$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)" -lt 2000 ]; do sleep 10; done
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p "$(dirname "$0")/../.tmp"; export TMPDIR="$(cd "$(dirname "$0")/.." && pwd)/.tmp"
timeout "$TMO" "$@" &
pid=$!
while kill -0 $pid 2>/dev/null; do
  rss=$(ps -o rss= --ppid $pid 2>/dev/null | awk '{s+=$1} END {print s+0}')
  own=$(awk '/VmRSS/{print $2}' /proc/$pid/status 2>/dev/null); rss=$((rss + ${own:-0}))
  if [ "$rss" -gt $((LIM*1024)) ]; then
    pkill -9 -P $pid; kill -9 $pid; echo "run_guarded: KILLED, RSS $((rss/1024)) MB > ${LIM} MB" >&2
  fi
  sleep 1
done
wait $pid; rc=$?
[ $rc -eq 124 ] && echo "run_guarded: KILLED after ${TMO} s" >&2
exit $rc
