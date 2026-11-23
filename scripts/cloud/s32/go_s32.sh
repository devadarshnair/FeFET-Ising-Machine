#!/usr/bin/env bash
# One command for the Stage 3.2 cloud run (DRAFT prereg; not frozen):  bash go_s32.sh [--smoke-only]
#   1. setup_s32.sh (zero manual steps, hard-timed)
#   2. gate: tests (S3 go-gate tests = s3_instances.S3_GATE_TESTS [tag-12 disjointness by content hash vs every earlier set incl. tuning and tag 11], test_s32_jobs, round-2 hook tests, arch_t, cost bugs) + the smoke gate (every job type
#      once at 1 sweep through the REAL scheduler: dependency gate, tiled nominal, report with the dual-B3 decision). Any failure stops BEFORE the billed compute.
#   3. guards: shipped TSVs equal a fresh gen_jobs_s32.py output at the pin; the WORST-CASE COST of the configured caps must not exceed S32_CAP_RS.
#   4. s32_sched.py with jobs_s32.tsv (0.5.r13_960 is row 1 and a hard gate of every tiled nominal job), then collect_s32.sh.
# Launch environment (16 vCPU / Rs 32.14 per h, the recommended profile):  S32_RATE_RS_H=32.14 S32_DEADLINE_MIN=200 S32_HARD_MIN=215 bash go_s32.sh
#   worst case = (S32_SETUP_MIN 20 + tests 8 + smoke 12 + S32_HARD_MIN 215 + collect 6) min = 261 min = about Rs 140 (cap Rs 150).
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SETUP_MIN=${S32_SETUP_MIN:-20}; GATE_TESTS_MIN=${S32_GATE_TESTS_MIN:-8}; GATE_SMOKE_MIN=${S32_GATE_SMOKE_MIN:-12}; COLLECT_MIN=${S32_COLLECT_MIN:-6}
DL=${S32_DEADLINE_MIN:-200}; HARD=${S32_HARD_MIN:-$((DL + 15))}; RATE=${S32_RATE_RS_H:-32.14}; CAP=${S32_CAP_RS:-150}
WORST=$(python3 -c "print(round(($SETUP_MIN+$GATE_TESTS_MIN+$GATE_SMOKE_MIN+$HARD+$COLLECT_MIN)/60*$RATE))")
python3 -c "import sys; sys.exit(0 if $WORST <= $CAP else 1)" || { echo "REFUSED: worst-case cost Rs $WORST exceeds the cap Rs $CAP (lower S32_HARD_MIN / S32_DEADLINE_MIN, or fix S32_RATE_RS_H)"; exit 2; }
echo "worst-case cost with these caps: Rs $WORST (cap Rs $CAP; rate Rs $RATE/h; hard cap $HARD min)"
timeout -k 30 "${SETUP_MIN}m" bash "$HERE/setup_s32.sh" || { echo "setup failed or exceeded ${SETUP_MIN} min"; exit 2; }
PAYLOAD=${S32_PAYLOAD:-$(cd "$HERE/.." && pwd)}
if [ "$(id -u)" = 0 ]; then ROOT=${MD_ROOT:-$PROJECT}; else ROOT=${MD_ROOT:-$HOME/md}; fi
RUN=$ROOT/00_admin/s32_run; source "$RUN/env_s32.sh"
log() { printf '[%s] %s\n' "$(date -u '+%F %T UTC')" "$*" | tee -a "$RUN/queue.log"; }
cd "$S32_WT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { log "REFUSED: tracked changes in the worktree"; exit 2; }
"$S32_PY" -I scripts/testing/gen_jobs_s32.py --tsv "$RUN/fresh_jobs_s32.tsv" --smoke-tsv "$RUN/fresh_jobs_s32_smoke.tsv" 2>/dev/null
cmp -s "$RUN/fresh_jobs_s32.tsv" "$HERE/jobs_s32.tsv" || { log "REFUSED: jobs_s32.tsv differs from a fresh gen_jobs_s32.py output at the pin (rebuild the payload)"; exit 2; }
cmp -s "$RUN/fresh_jobs_s32_smoke.tsv" "$HERE/jobs_s32_smoke.tsv" || { log "REFUSED: jobs_s32_smoke.tsv differs from a fresh output"; exit 2; }
if [ ! -e "$RUN/GATE_OK_$(git rev-parse HEAD)" ]; then
  S2TESTS=$("$S32_PY" -I -c "import sys; sys.path.insert(0,'scripts/testing'); import s3_instances as s; print(' '.join(s.S3_GATE_TESTS))") || { log "GATE FAILED: cannot read S32_GATE_TESTS"; exit 3; }
  log "gate: tests ($S2TESTS tests/hw/test_s32_jobs.py ...)"
  timeout -k 30 "${GATE_TESTS_MIN}m" "$S32_PY" -m pytest -q -x $S2TESTS tests/hw/test_s32_jobs.py tests/hw/test_round2_algo.py tests/hw/test_round2_escape.py tests/hw/test_arch_t.py tests/hw/test_cost_bugs_b123.py -p no:cacheprovider > "$RUN/gate_tests.log" 2>&1 || { tail -20 "$RUN/gate_tests.log"; log "GATE FAILED: tests (the S3 disjointness test must pass; refusing to launch)"; exit 3; }
  log "gate: smoke through the real scheduler (every job type, 1 sweep)"; rm -rf sim/out/hw/s32_smoke; mkdir -p "$RUN/smoke"
  SMOKE_MEM="--mem-frac 0.5"; [ -z "${S32_SMOKE_MEMGB:-}" ] || SMOKE_MEM="--mem-gb $S32_SMOKE_MEMGB"
  timeout -k 30 "${GATE_SMOKE_MIN}m" "$S32_PY" "$HERE/s32_sched.py" --tsv "$HERE/jobs_s32_smoke.tsv" --run "$RUN/smoke" --wt "$S32_WT" --py "$S32_PY" --slots "${S32_SMOKE_SLOTS:-8}" $SMOKE_MEM > "$RUN/gate_smoke.log" 2>&1
  [ -e "$RUN/smoke/S32_DONE" ] || { tail -30 "$RUN/gate_smoke.log"; log "GATE FAILED: smoke (see gate_smoke.log)"; exit 3; }
  grep -q "^# Stage 3.2 report" sim/out/hw/s32_smoke/s32_report.md || { log "GATE FAILED: smoke report missing"; exit 3; }
  git checkout -q -- . ; date -u > "$RUN/GATE_OK_$(git rev-parse HEAD)"; log "gate ok"
fi
[ "${1:-}" = "--smoke-only" ] && { log "smoke-only: stopping before the billed run"; exit 0; }
log "run Stage 3.2: deadline ${DL} min, hard cap ${HARD} min, worst case Rs $WORST; gate row 0.5.r13_960 first"
"$S32_PY" "$HERE/s32_sched.py" --tsv "$HERE/jobs_s32.tsv" --run "$RUN" --wt "$S32_WT" --py "$S32_PY" --plan --deadline-min "$DL" | tee -a "$RUN/queue.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "REFUSED: the simulated schedule does not fit the deadline / memory budget"; exit 4; }
"$S32_PY" "$HERE/s32_sched.py" --tsv "$HERE/jobs_s32.tsv" --run "$RUN" --wt "$S32_WT" --py "$S32_PY" --deadline-min "$DL" --hard-min "$HARD"
rc=$?
timeout -k 30 "${COLLECT_MIN}m" bash "$HERE/collect_s32.sh" stage2
exit $rc
