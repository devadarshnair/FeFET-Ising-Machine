#!/usr/bin/env bash
# LOCAL: build the Stage 1 payload (bundle + data + manifest + executable / smoke / planning job files + this directory).
# Usage: bash build_payload_s1.sh DEST   (ship DEST to the instance; run  bash DEST/s1/go_s1.sh).  Refuses a dirty worktree. Never launches anything.
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WT=$(git -C "$HERE" rev-parse --show-toplevel)
DEST=${1:?destination dir}
ROOT=${MD_ROOT:-$PROJECT}
PY=${PY:-$HOME/miniconda3/envs/swref/bin/python}
[ -z "$(git -C "$WT" status --porcelain)" ] || { echo "worktree dirty" >&2; exit 1; }
[ "$(git -C "$WT" branch --show-current)" = hw/p4-baselines ] || { echo "not on hw/p4-baselines" >&2; exit 1; }
rm -rf "$DEST"; mkdir -p "$DEST/bundle" "$DEST/data" "$DEST/manifest" "$DEST/s1"
git -C "$WT" bundle create "$DEST/bundle/hw.bundle" --branches='hw/*' >/dev/null
git -C "$WT" rev-parse HEAD > "$DEST/manifest/PIN_HEAD"
tar --zstd -cf "$DEST/data/gset.tar.zst" -C "$ROOT" 05_external_tools/open_source_implementations/benchmarks_and_eval_tools/gset
tar --zstd -cf "$DEST/data/qkp.tar.zst" -C "$ROOT" 09_next_phase/benchmarks/qkp_billionnet_soutif 09_next_phase/items_work/09/optima.json
tar --zstd -cf "$DEST/data/qubo_bridge.tar.zst" -C "$ROOT/sw_ref_wt" --exclude=.git --exclude=__pycache__ qubo
git -C "$ROOT/sw_ref" archive --format=tar HEAD experiments/d5c_qhinge | zstd -q -o "$DEST/data/d5c_qhinge.tar.zst"
"$PY" -I "$WT/scripts/testing/gen_jobs_s1.py" --tsv "$DEST/s1/jobs_s1.tsv" --smoke-tsv "$DEST/s1/jobs_s1_smoke.tsv" --plan "$DEST/s1/STAGE1_JOBLIST.tsv" 2> "$DEST/s1/cost_estimate.txt"
cp "$HERE"/*.sh "$HERE"/*.py "$DEST/s1/"
(cd "$DEST" && find bundle data manifest s1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > manifest/SHA256SUMS)
echo "payload built at $DEST; pin $(cat "$DEST/manifest/PIN_HEAD"); rows $(grep -vc '^#' "$DEST/s1/jobs_s1.tsv"); $(cat "$DEST/s1/cost_estimate.txt")"
