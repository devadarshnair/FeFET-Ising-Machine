#!/usr/bin/env bash
# LOCAL: build the payload (bundle + data + manifest + both job TSVs + this directory) for the H8 cloud run. Refuses a dirty worktree.
# Usage: bash build_payload_h8.sh DEST   (DEST/ is created; ship DEST to the instance and run  bash DEST/h8/go_h8.sh core)
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WT=$(git -C "$HERE" rev-parse --show-toplevel)
DEST=${1:?destination dir}
ROOT=${MD_ROOT:-$PROJECT}; REPO=$ROOT/hw
PY=${PY:-$HOME/miniconda3/envs/swref/bin/python}
[ -z "$(git -C "$WT" status --porcelain)" ] || { echo "worktree dirty" >&2; exit 1; }
[ "$(git -C "$WT" branch --show-current)" = hw/p4-baselines ] || { echo "not on hw/p4-baselines" >&2; exit 1; }
rm -rf "$DEST"; mkdir -p "$DEST/bundle" "$DEST/data" "$DEST/manifest" "$DEST/h8"
git -C "$WT" bundle create "$DEST/bundle/hw.bundle" --branches='hw/*' >/dev/null
git -C "$WT" rev-parse HEAD > "$DEST/manifest/PIN_HEAD"
tar --zstd -cf "$DEST/data/gset.tar.zst" -C "$ROOT" 05_external_tools/open_source_implementations/benchmarks_and_eval_tools/gset
tar --zstd -cf "$DEST/data/qkp.tar.zst" -C "$ROOT" 09_next_phase/benchmarks/qkp_billionnet_soutif 09_next_phase/items_work/09/optima.json
tar --zstd -cf "$DEST/data/qubo_bridge.tar.zst" -C "$ROOT/sw_ref_wt" --exclude=.git --exclude=__pycache__ qubo
git -C "$ROOT/sw_ref" archive --format=tar HEAD experiments/d5c_qhinge | zstd -q -o "$DEST/data/d5c_qhinge.tar.zst"
# fairness arm ours.kc2c: included in the main TSVs automatically once docs/hw/results/baselines_v2/tuned.json carries its selection (plan_h8.kc2c_ready);
# otherwise a separate add-on TSV per tier is shipped (run it with go_h8.sh core-kc2c after the selection is committed and the payload rebuilt)
for t in core full; do
  "$PY" -I "$WT/scripts/testing/gen_jobs_h8.py" --tsv "$DEST/h8/jobs_h8_$t.tsv" --tier $t >/dev/null
  "$PY" -I "$WT/scripts/testing/gen_jobs_h8.py" --tsv "$DEST/h8/jobs_h8_${t}_kc2c.tsv" --tier $t --kc2c-addon >/dev/null
done
cp "$HERE"/*.sh "$HERE"/*.py "$DEST/h8/"
(cd "$DEST" && find bundle data manifest h8 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > manifest/SHA256SUMS)
echo "payload built at $DEST; pin $(cat "$DEST/manifest/PIN_HEAD"); core rows $(grep -vc '^#' "$DEST/h8/jobs_h8_core.tsv"), full rows $(grep -vc '^#' "$DEST/h8/jobs_h8_full.tsv")"
