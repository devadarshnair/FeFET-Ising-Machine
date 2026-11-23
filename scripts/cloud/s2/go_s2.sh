#!/usr/bin/env bash
# One command for the Stage 2 cloud run (DRAFT prereg; not frozen):  bash go_s2.sh [--smoke-only]
#   1. setup_s2.sh (zero manual steps, hard-timed)
#   2. gate: tests (S2 go-gate tests = s2_instances.S2_GATE_TESTS [tag-11 disjointness by content hash], test_s2_jobs, stage-1 hooks, cost bugs) + the smoke gate (every job type
#      once at 1 sweep through the REAL scheduler: dependency gate, tiled nominal, report with the dual-B3 decision). Any failure stops BEFORE the billed compute.
#   3. guards: shipped TSVs equal a fresh gen_jobs_s2.py output at the pin; the WORST-CASE COST of the configured caps must not exceed S2_CAP_RS.
#   4. s2_sched.py with jobs_s2.tsv (0.5.r13_480 is row 1 and a hard gate of every tiled nominal job), then collect_s2.sh.
# Launch environment (16 vCPU / Rs 32.14 per h, the recommended profile):  S2_RATE_RS_H=32.14 S2_DEADLINE_MIN=190 S2_HARD_MIN=205 bash go_s2.sh
#   worst case = (S2_SETUP_MIN 20 + tests 8 + smoke 10 + S2_HARD_MIN 205 + collect 5) min = 248 min = about Rs 133 (cap Rs 150).
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SETUP_MIN=${S2_SETUP_MIN:-20}; GATE_TESTS_MIN=${S2_GATE_TESTS_MIN:-8}; GATE_SMOKE_MIN=${S2_GATE_SMOKE_MIN:-10}; COLLECT_MIN=${S2_COLLECT_MIN:-5}
DL=${S2_DEADLINE_MIN:-190}; HARD=${S2_HARD_MIN:-$((DL + 15))}; RATE=${S2_RATE_RS_H:-32.14}; CAP=${S2_CAP_RS:-150}
WORST=$(python3 -c "print(round(($SETUP_MIN+$GATE_TESTS_MIN+$GATE_SMOKE_MIN+$HARD+$COLLECT_MIN)/60*$RATE))")
python3 -c "import sys; sys.exit(0 if $WORST <= $CAP else 1)" || { echo "REFUSED: worst-case cost Rs $WORST exceeds the cap Rs $CAP (lower S2_HARD_MIN / S2_DEADLINE_MIN, or fix S2_RATE_RS_H)"; exit 2; }
echo "worst-case cost with these caps: Rs $WORST (cap Rs $CAP; rate Rs $RATE/h; hard cap $HARD min)"
timeout -k 30 "${SETUP_MIN}m" bash "$HERE/setup_s2.sh" || { echo "setup failed or exceeded ${SETUP_MIN} min"; exit 2; }
PAYLOAD=${S2_PAYLOAD:-$(cd "$HERE/.." && pwd)}
if [ "$(id -u)" = 0 ]; then ROOT=${MD_ROOT:-$PROJECT}; else ROOT=${MD_ROOT:-$HOME/md}; fi
RUN=$ROOT/00_admin/s2_run; source "$RUN/env_s2.sh"
log() { printf '[%s] %s\n' "$(date -u '+%F %T UTC')" "$*" | tee -a "$RUN/queue.log"; }
cd "$S2_WT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { log "REFUSED: tracked changes in the worktree"; exit 2; }
"$S2_PY" -I scripts/testing/gen_jobs_s2.py --tsv "$RUN/fresh_jobs_s2.tsv" --smoke-tsv "$RUN/fresh_jobs_s2_smoke.tsv" 2>/dev/null
cmp -s "$RUN/fresh_jobs_s2.tsv" "$HERE/jobs_s2.tsv" || { log "REFUSED: jobs_s2.tsv differs from a fresh gen_jobs_s2.py output at the pin (rebuild the payload)"; exit 2; }
cmp -s "$RUN/fresh_jobs_s2_smoke.tsv" "$HERE/jobs_s2_smoke.tsv" || { log "REFUSED: jobs_s2_smoke.tsv differs from a fresh output"; exit 2; }
if [ ! -e "$RUN/GATE_OK_$(git rev-parse HEAD)" ]; then
  S2TESTS=$("$S2_PY" -I -c "import sys; sys.path.insert(0,'scripts/testing'); import s2_instances as s; print(' '.join(s.S2_GATE_TESTS))") || { log "GATE FAILED: cannot read S2_GATE_TESTS"; exit 3; }
  log "gate: tests ($S2TESTS tests/hw/test_s2_jobs.py ...)"
  timeout -k 30 "${GATE_TESTS_MIN}m" "$S2_PY" -m pytest -q -x $S2TESTS tests/hw/test_s2_jobs.py tests/hw/test_stage1_hooks.py tests/hw/test_cost_bugs_b123.py -p no:cacheprovider > "$RUN/gate_tests.log" 2>&1 || { tail -20 "$RUN/gate_tests.log"; log "GATE FAILED: tests (the S2 disjointness test must pass; refusing to launch)"; exit 3; }
  log "gate: smoke through the real scheduler (every job type, 1 sweep)"; rm -rf sim/out/hw/s2_smoke; mkdir -p "$RUN/smoke"
  SMOKE_MEM="--mem-frac 0.5"; [ -z "${S2_SMOKE_MEMGB:-}" ] || SMOKE_MEM="--mem-gb $S2_SMOKE_MEMGB"
  timeout -k 30 "${GATE_SMOKE_MIN}m" "$S2_PY" "$HERE/s2_sched.py" --tsv "$HERE/jobs_s2_smoke.tsv" --run "$RUN/smoke" --wt "$S2_WT" --py "$S2_PY" --slots "${S2_SMOKE_SLOTS:-8}" $SMOKE_MEM > "$RUN/gate_smoke.log" 2>&1
  [ -e "$RUN/smoke/S2_DONE" ] || { tail -30 "$RUN/gate_smoke.log"; log "GATE FAILED: smoke (see gate_smoke.log)"; exit 3; }
  grep -q "^# Stage 2 report" sim/out/hw/s2_smoke/s2_report.md || { log "GATE FAILED: smoke report missing"; exit 3; }
  git checkout -q -- . ; date -u > "$RUN/GATE_OK_$(git rev-parse HEAD)"; log "gate ok"
fi
[ "${1:-}" = "--smoke-only" ] && { log "smoke-only: stopping before the billed run"; exit 0; }
log "run Stage 2: deadline ${DL} min, hard cap ${HARD} min, worst case Rs $WORST; gate row 0.5.r13_480 first"
"$S2_PY" "$HERE/s2_sched.py" --tsv "$HERE/jobs_s2.tsv" --run "$RUN" --wt "$S2_WT" --py "$S2_PY" --plan --deadline-min "$DL" | tee -a "$RUN/queue.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "REFUSED: the simulated schedule does not fit the deadline / memory budget"; exit 4; }
"$S2_PY" "$HERE/s2_sched.py" --tsv "$HERE/jobs_s2.tsv" --run "$RUN" --wt "$S2_WT" --py "$S2_PY" --deadline-min "$DL" --hard-min "$HARD"
rc=$?
timeout -k 30 "${COLLECT_MIN}m" bash "$HERE/collect_s2.sh" stage2
exit $rc
