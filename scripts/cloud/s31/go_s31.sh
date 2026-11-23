#!/usr/bin/env bash
# One command for the Stage 3.1 + 3.1b tuning run on the cloud box (tuning-only; DRAFT plan, the Stage 3 plan section 4):  bash go_s31.sh [--smoke-only]
#   1. setup_s31.sh (zero manual steps, hard-timed)
#   2. gate: tests (3.1 job list + tuning/confirmatory instance disjointness, round-2 algorithm / escape hook tests, arch_t) and the smoke gate = EVERY job type once at tiny budget
#      (1 instance, 1 seed, 1 sweep) through the REAL dependency scheduler, including the SEL.31 / SEL.31b selection steps and the report. Any failure stops BEFORE the billed compute.
#   3. guards: shipped TSVs equal a fresh gen_jobs_s31.py output at the pin; the WORST-CASE COST of the configured caps must not exceed S31_CAP_RS.
#   4. s31_sched.py with jobs_s31.tsv (117 rows), then collect_s31.sh.
# Launch environment (16 vCPU, Rs 32.14/h):  S31_RATE_RS_H=32.14 S31_DEADLINE_MIN=70 S31_HARD_MIN=80 S31_CAP_RS=65 bash go_s31.sh
#   worst case = (S31_SETUP_MIN 15 + tests 6 + smoke 8 + S31_HARD_MIN 80 + collect 4) min = 113 min = Rs 60.5 (cap Rs 65). Typical: about 10 min set-up/gate + 50-60 min run = Rs 35-40.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SETUP_MIN=${S31_SETUP_MIN:-15}; GATE_TESTS_MIN=${S31_GATE_TESTS_MIN:-6}; GATE_SMOKE_MIN=${S31_GATE_SMOKE_MIN:-8}; COLLECT_MIN=${S31_COLLECT_MIN:-4}
DL=${S31_DEADLINE_MIN:-70}; HARD=${S31_HARD_MIN:-$((DL + 10))}; RATE=${S31_RATE_RS_H:-32.14}; CAP=${S31_CAP_RS:-65}
WORST=$(python3 -c "print(round(($SETUP_MIN+$GATE_TESTS_MIN+$GATE_SMOKE_MIN+$HARD+$COLLECT_MIN)/60*$RATE,1))")
python3 -c "import sys; sys.exit(0 if $WORST <= $CAP else 1)" || { echo "REFUSED: worst-case cost Rs $WORST exceeds the cap Rs $CAP (lower S31_HARD_MIN / S31_DEADLINE_MIN, or fix S31_RATE_RS_H)"; exit 2; }
echo "worst-case cost with these caps: Rs $WORST (cap Rs $CAP; rate Rs $RATE/h; hard cap $HARD min)"
timeout -k 30 "${SETUP_MIN}m" bash "$HERE/setup_s31.sh" || { echo "setup failed or exceeded ${SETUP_MIN} min"; exit 2; }
PAYLOAD=${S31_PAYLOAD:-$(cd "$HERE/.." && pwd)}
if [ "$(id -u)" = 0 ]; then ROOT=${MD_ROOT:-$PROJECT}; else ROOT=${MD_ROOT:-$HOME/md}; fi
RUN=$ROOT/00_admin/s31_run; source "$RUN/env_s31.sh"
log() { printf '[%s] %s\n' "$(date -u '+%F %T UTC')" "$*" | tee -a "$RUN/queue.log"; }
cd "$S31_WT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { log "REFUSED: tracked changes in the worktree"; exit 2; }
"$S31_PY" -I scripts/testing/gen_jobs_s31.py --tsv "$RUN/fresh_jobs_s31.tsv" --smoke-tsv "$RUN/fresh_jobs_s31_smoke.tsv" 2>/dev/null
cmp -s "$RUN/fresh_jobs_s31.tsv" "$HERE/jobs_s31.tsv" || { log "REFUSED: jobs_s31.tsv differs from a fresh gen_jobs_s31.py output at the pin (rebuild the payload)"; exit 2; }
cmp -s "$RUN/fresh_jobs_s31_smoke.tsv" "$HERE/jobs_s31_smoke.tsv" || { log "REFUSED: jobs_s31_smoke.tsv differs from a fresh output"; exit 2; }
if [ ! -e "$RUN/GATE_OK_$(git rev-parse HEAD)" ]; then
  log "gate: tests"
  timeout -k 30 "${GATE_TESTS_MIN}m" "$S31_PY" -m pytest -q -x tests/hw/test_s31_jobs.py tests/hw/test_round2_algo.py tests/hw/test_round2_escape.py tests/hw/test_arch_t.py -p no:cacheprovider > "$RUN/gate_tests.log" 2>&1 || { tail -20 "$RUN/gate_tests.log"; log "GATE FAILED: tests (refusing to launch)"; exit 3; }
  log "gate: smoke through the real scheduler (every job type, tiny budgets, selection steps, report)"; rm -rf sim/out/hw/s31_smoke sim/out/hw/s31b_smoke; mkdir -p "$RUN/smoke"
  SMOKE_MEM="--mem-frac 0.5"; [ -z "${S31_SMOKE_MEMGB:-}" ] || SMOKE_MEM="--mem-gb $S31_SMOKE_MEMGB"
  timeout -k 30 "${GATE_SMOKE_MIN}m" "$S31_PY" "$HERE/s31_sched.py" --tsv "$HERE/jobs_s31_smoke.tsv" --run "$RUN/smoke" --wt "$S31_WT" --py "$S31_PY" --slots "${S31_SMOKE_SLOTS:-16}" $SMOKE_MEM > "$RUN/gate_smoke.log" 2>&1
  [ -e "$RUN/smoke/S31_DONE" ] || { tail -30 "$RUN/gate_smoke.log"; log "GATE FAILED: smoke (see gate_smoke.log)"; exit 3; }
  grep -q "^# Stage 3.1 report" sim/out/hw/s31_smoke/s31_report.md || { log "GATE FAILED: smoke report missing"; exit 3; }
  [ -s sim/out/hw/s31_smoke/selection_31.json ] && [ -s sim/out/hw/s31b_smoke/selection_31b.json ] || { log "GATE FAILED: smoke selection files missing"; exit 3; }
  git checkout -q -- . ; date -u > "$RUN/GATE_OK_$(git rev-parse HEAD)"; log "gate ok"
fi
[ "${1:-}" = "--smoke-only" ] && { log "smoke-only: stopping before the billed run"; exit 0; }
log "run Stage 3.1 + 3.1b: deadline ${DL} min, hard cap ${HARD} min, worst case Rs $WORST"
"$S31_PY" "$HERE/s31_sched.py" --tsv "$HERE/jobs_s31.tsv" --run "$RUN" --wt "$S31_WT" --py "$S31_PY" --plan --deadline-min "$DL" | tee -a "$RUN/queue.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "REFUSED: the simulated schedule does not fit the deadline / memory budget"; exit 4; }
"$S31_PY" "$HERE/s31_sched.py" --tsv "$HERE/jobs_s31.tsv" --run "$RUN" --wt "$S31_WT" --py "$S31_PY" --deadline-min "$DL" --hard-min "$HARD"
rc=$?
timeout -k 30 "${COLLECT_MIN}m" bash "$HERE/collect_s31.sh" stage31
exit $rc
