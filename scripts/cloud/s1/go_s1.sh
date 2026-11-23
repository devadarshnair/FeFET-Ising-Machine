#!/usr/bin/env bash
# One command for the whole Stage 1 cloud run:  bash go_s1.sh [--smoke-only]
#   1. setup_s1.sh (zero manual steps, hard-timed)
#   2. gate: tests (stage-1 hooks, cost bugs, variation_v2) + the smoke gate = every job type once at 1 sweep through the REAL scheduler (dependencies, selection steps, R13 gate) + report.
#      Any failure stops BEFORE the billed compute.
#   3. guard: the shipped jobs_s1.tsv must equal a fresh gen_jobs_s1.py output at the pin.
#   4. s1_sched.py with jobs_s1.tsv: 0.5.r13_960 is the FIRST row and a hard gate (dependency of every noisy 960-class job: if it fails those jobs never start), then collect_s1.sh.
# Nothing here is launched by the builder; the author starts it on the instance.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SETUP_MIN=${S1_SETUP_MIN:-20}; GATE_TESTS_MIN=${S1_GATE_TESTS_MIN:-8}; GATE_SMOKE_MIN=${S1_GATE_SMOKE_MIN:-10}
DL=${S1_DEADLINE_MIN:-150}; HARD=${S1_HARD_MIN:-$((DL + 15))}     # ceiling: 20 + 18 + 165 + 5 = 208 min = Rs 223 (expected makespan about 80 min)
timeout -k 30 "${SETUP_MIN}m" bash "$HERE/setup_s1.sh" || { echo "setup failed or exceeded ${SETUP_MIN} min"; exit 2; }
PAYLOAD=${S1_PAYLOAD:-$(cd "$HERE/.." && pwd)}
if [ "$(id -u)" = 0 ]; then ROOT=${MD_ROOT:-$PROJECT}; else ROOT=${MD_ROOT:-$HOME/md}; fi
RUN=$ROOT/00_admin/s1_run; source "$RUN/env_s1.sh"
log() { printf '[%s] %s\n' "$(date -u '+%F %T UTC')" "$*" | tee -a "$RUN/queue.log"; }
cd "$S1_WT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { log "REFUSED: tracked changes in the worktree"; exit 2; }
"$S1_PY" -I scripts/testing/gen_jobs_s1.py --tsv "$RUN/fresh_jobs_s1.tsv" --smoke-tsv "$RUN/fresh_jobs_s1_smoke.tsv" 2>/dev/null
cmp -s "$RUN/fresh_jobs_s1.tsv" "$HERE/jobs_s1.tsv" || { log "REFUSED: jobs_s1.tsv differs from a fresh gen_jobs_s1.py output at the pin (rebuild the payload)"; exit 2; }
cmp -s "$RUN/fresh_jobs_s1_smoke.tsv" "$HERE/jobs_s1_smoke.tsv" || { log "REFUSED: jobs_s1_smoke.tsv differs from a fresh output"; exit 2; }
if [ ! -e "$RUN/GATE_OK_$(git rev-parse HEAD)" ]; then
  log "gate: tests"; timeout -k 30 "${GATE_TESTS_MIN}m" "$S1_PY" -m pytest -q -x tests/hw/test_stage1_hooks.py tests/hw/test_cost_bugs_b123.py tests/hw/test_variation_v2.py -p no:cacheprovider > "$RUN/gate_tests.log" 2>&1 || { tail -20 "$RUN/gate_tests.log"; log "GATE FAILED: tests"; exit 3; }
  SMOKE_MEM="--mem-frac 0.5"; [ -z "${S1_SMOKE_MEMGB:-}" ] || SMOKE_MEM="--mem-gb $S1_SMOKE_MEMGB"
  log "gate: smoke through the real scheduler (every job type, 1 sweep)"; rm -rf sim/out/hw/s1_smoke; mkdir -p "$RUN/smoke"
  timeout -k 30 "${GATE_SMOKE_MIN}m" "$S1_PY" "$HERE/s1_sched.py" --tsv "$HERE/jobs_s1_smoke.tsv" --run "$RUN/smoke" --wt "$S1_WT" --py "$S1_PY" --slots "${S1_SMOKE_SLOTS:-8}" $SMOKE_MEM > "$RUN/gate_smoke.log" 2>&1
  [ -e "$RUN/smoke/S1_DONE" ] || { tail -30 "$RUN/gate_smoke.log"; log "GATE FAILED: smoke (see gate_smoke.log)"; exit 3; }
  grep -q "^# Stage 1 report" sim/out/hw/s1_smoke/s1_report.md || { log "GATE FAILED: smoke report missing"; exit 3; }
  git checkout -q -- . ; date -u > "$RUN/GATE_OK_$(git rev-parse HEAD)"; log "gate ok"
fi
[ "${1:-}" = "--smoke-only" ] && { log "smoke-only: stopping before the billed run"; exit 0; }
log "run Stage 1: deadline ${DL} min, hard cap ${HARD} min; gate row 0.5.r13_960 first"
"$S1_PY" "$HERE/s1_sched.py" --tsv "$HERE/jobs_s1.tsv" --run "$RUN" --wt "$S1_WT" --py "$S1_PY" --plan --deadline-min "$DL" | tee -a "$RUN/queue.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "REFUSED: the simulated schedule does not fit the deadline / memory budget"; exit 4; }
"$S1_PY" "$HERE/s1_sched.py" --tsv "$HERE/jobs_s1.tsv" --run "$RUN" --wt "$S1_WT" --py "$S1_PY" --deadline-min "$DL" --hard-min "$HARD"
rc=$?
bash "$HERE/collect_s1.sh" stage1
exit $rc
