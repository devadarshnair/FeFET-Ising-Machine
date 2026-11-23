#!/usr/bin/env bash
# One command for the whole cloud run: bash go_h8.sh core|full   (full resumes core: same job ids, done markers skip finished jobs)
#   1. setup_h8.sh   (installs everything; no manual steps)
#   2. gate: tests/hw/test_h8.py + tests/hw/test_variation_v2.py + run_h8.py --smoke-h8 --smoke-all (every job type, real report barrier). Any failure stops
#      BEFORE the billed compute.
#   3. prereg guard: prereg/hw/H8_full.md must not be a DRAFT at the pin; the TSV must equal a fresh gen_jobs_h8.py output.
#   4. h8_sched.py with the tier's TSV (memory-aware slots, deadline and hard cap), then collect_h8.sh.
set -uo pipefail
# usage: go_h8.sh core|full|core-kc2c|full-kc2c [--profile 32|16]     (default profile 32: 32 vCPU / 128 GB, Rs 64.28/h, unchanged)
#   profile 16: 16 vCPU / 64 GB (Rs 32.14/h): 16 slots, admission budget 60 GB of declared RSS (13.8 GB jobs: at most 4 at once), core deadline 450 min,
#   hard cap 470 -> guaranteed ceiling 20 + 25 + 470 + 5 = 520 min = Rs 279. Profile 32: 275 min = Rs 295.
PROFILE=${H8_PROFILE:-32}; [ "${2:-}" = "--profile" ] && PROFILE=${3:?profile}
case "$PROFILE" in 32) SA=""; DL_CORE=205;; 16) SA="--slots 16 --mem-gb 60"; DL_CORE=450;; *) echo "unknown profile $PROFILE (32|16)"; exit 2;; esac
ARG=${1:?core|full|core-kc2c|full-kc2c}                      # *-kc2c = the fairness-arm add-on (needs the tuned ours.kc2c selection at the pin)
TIER=${ARG%-kc2c}; ADDON=""; [ "$ARG" != "$TIER" ] && ADDON=--kc2c-addon
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# billing cap: set-up and gate are wall-bounded so that set-up + gate + scheduler (deadline + hard cap) + collection stay inside Rs 300 (280 min at Rs 64.28/h)
SETUP_MIN=${H8_SETUP_MIN:-20}; GATE_TESTS_MIN=${H8_GATE_TESTS_MIN:-10}; GATE_SMOKE_MIN=${H8_GATE_SMOKE_MIN:-15}
timeout -k 30 "${SETUP_MIN}m" bash "$HERE/setup_h8.sh" || { echo "setup failed or exceeded ${SETUP_MIN} min"; exit 2; }
PAYLOAD=${H8_PAYLOAD:-$(cd "$HERE/.." && pwd)}
if [ "$(id -u)" = 0 ]; then ROOT=${MD_ROOT:-$PROJECT}; else ROOT=${MD_ROOT:-$HOME/md}; fi
RUN=$ROOT/00_admin/h8_run; source "$RUN/env_h8.sh"
log() { printf '[%s] %s\n' "$(date -u '+%F %T UTC')" "$*" | tee -a "$RUN/queue.log"; }
cd "$H8_WT"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { log "REFUSED: tracked changes in the worktree"; exit 2; }
head -5 prereg/hw/H8_full.md | grep -q "DRAFT" && [ -z "${H8_ALLOW_DRAFT:-}" ] && { log "REFUSED: prereg/hw/H8_full.md is still a DRAFT at the pin (freeze it by commit; H8_ALLOW_DRAFT=1 only for a dry run)"; exit 2; }
TSV=$HERE/jobs_h8_$ARG.tsv
"$H8_PY" -I scripts/testing/gen_jobs_h8.py --tsv "$RUN/fresh_$ARG.tsv" --tier "$TIER" $ADDON >/dev/null
[ -z "$ADDON" ] || "$H8_PY" -I -c "import sys; sys.path.insert(0,'scripts/testing'); import plan_h8 as p; sys.exit(0 if p.kc2c_ready() else 1)" || { log "REFUSED: the tuned ours.kc2c selection is not in the tree at the pin"; exit 2; }
cmp -s "$RUN/fresh_$ARG.tsv" "$TSV" || { log "REFUSED: $TSV differs from a fresh gen_jobs_h8.py output at the pin (regenerate the payload)"; exit 2; }
if [ ! -e "$RUN/GATE_OK_$(git rev-parse HEAD)" ]; then
  log "gate: tests"; timeout -k 30 "${GATE_TESTS_MIN}m" "$H8_PY" -m pytest -q -x tests/hw/test_h8.py tests/hw/test_variation_v2.py -p no:cacheprovider > "$RUN/gate_tests.log" 2>&1 || { log "GATE FAILED: tests (see gate_tests.log)"; exit 3; }
  log "gate: smoke-h8 --smoke-all"; timeout -k 30 "${GATE_SMOKE_MIN}m" "$H8_PY" -I scripts/testing/run_h8.py --smoke-h8 --smoke-all --tier "$TIER" ${ADDON:+--with-kc2c} > "$RUN/gate_smoke.log" 2>&1 || { tail -30 "$RUN/gate_smoke.log"; log "GATE FAILED: smoke (see gate_smoke.log)"; exit 3; }
  git checkout -q -- . ; date -u > "$RUN/GATE_OK_$(git rev-parse HEAD)"; log "gate ok"
fi
DL=${H8_DEADLINE_MIN:-$([ "$TIER" = core ] && echo $DL_CORE || echo 540)}; HARD=${H8_HARD_MIN:-$((DL + 20))}   # core: 20 + 10 + 15 + 215 + collection <= 280 min
log "run tier $TIER, profile $PROFILE: deadline ${DL} min, hard cap ${HARD} min"
"$H8_PY" "$HERE/h8_sched.py" --tsv "$TSV" --run "$RUN" --wt "$H8_WT" --py "$H8_PY" --plan $SA --deadline-min "$DL" | tee -a "$RUN/queue.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "REFUSED: the simulated schedule does not fit the deadline / memory budget of profile $PROFILE (core tier would not complete)"; exit 4; }
"$H8_PY" "$HERE/h8_sched.py" --tsv "$TSV" --run "$RUN" --wt "$H8_WT" --py "$H8_PY" --deadline-min "$DL" --hard-min "$HARD" $SA
rc=$?
bash "$HERE/collect_h8.sh" "$ARG"
exit $rc
