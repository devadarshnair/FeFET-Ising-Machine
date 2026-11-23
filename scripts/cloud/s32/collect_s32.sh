#!/usr/bin/env bash
# collect_h8.sh <label>: tar raw outputs + logs + provenance with checksums. Safe at any time.
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ "$(id -u)" = 0 ]; then ROOT=${MD_ROOT:-$PROJECT}; else ROOT=${MD_ROOT:-$HOME/md}; fi
RUN=$ROOT/00_admin/s32_run; source "$RUN/env_s32.sh"
OUT=$ROOT/00_admin/s32_return/$(date -u '+%Y%m%dT%H%M%SZ')_${1:-manual}; mkdir -p "$OUT"
git -C "$S32_WT" rev-parse HEAD > "$OUT/worktree_head.txt"; git -C "$S32_WT" status --porcelain=v1 > "$OUT/worktree_status.txt"
"$S32_PY" -m pip freeze > "$OUT/pip-freeze.txt" 2>&1 || true; nproc > "$OUT/nproc.txt"; lscpu > "$OUT/lscpu.txt" 2>&1 || true
cp -a "$RUN/." "$OUT/run/" 2>/dev/null || true
cd "$S32_WT"; tar --zstd -cf "$OUT/raw_outputs.tar.zst" $(ls -d sim/out/hw/s32 sim/out/hw/s32_smoke 2>/dev/null)
(cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
echo "collected at $OUT ($(du -sh "$OUT" | cut -f1)); download with scp -r"
