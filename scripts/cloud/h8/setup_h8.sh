#!/usr/bin/env bash
# H8 fresh-instance setup: ZERO manual steps. Idempotent (also a safe update). Installs apt basics, Miniforge, the pinned `swref` env and the `eda` env
# (Verilator 5.050), unpacks the repository from the git bundle at the pinned commit, restores the data (G-set, qubo bridge, d5c), writes
# env_h8.sh (PATH incl. the eda env, VERILATOR_BIN, HW_RTL_ROOT) and verifies versions + a numba JIT check. Run as: bash setup_h8.sh  (payload dir = this dir's parent).
# SETUP_OFFLINE=1 skips apt / download / pip (only unpack + version checks; for the local clean-unpack test, MD_CONDA pointing at an existing conda).
# Env: MD_ROOT (default $HOME/md, or the legacy root when root), MD_CONDA (default $HOME/miniforge3).
set -Eeuo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PAYLOAD=${H8_PAYLOAD:-$(cd "$HERE/.." && pwd)}                 # contains bundle/ data/ manifest/ and h8/ (this dir)
LEGACY_ROOT=$PROJECT
if [ "$(id -u)" = 0 ]; then ROOT=${MD_ROOT:-$LEGACY_ROOT}; else ROOT=${MD_ROOT:-$HOME/md}; fi
REPO=$ROOT/hw; WT=$ROOT/hw_wt/hw-p5b; RUN=$ROOT/00_admin/h8_run
CONDA=${MD_CONDA:-$HOME/miniforge3}; PY=$CONDA/envs/swref/bin/python; EDA=$CONDA/envs/eda/bin
mkdir -p "$RUN"
log() { printf '[%s] %s\n' "$(date -u '+%F %T UTC')" "$*" | tee -a "$RUN/setup.log"; }
fail() { log "REFUSED: $*"; exit 2; }
[ -f "$PAYLOAD/manifest/SHA256SUMS" ] || fail "manifest missing in $PAYLOAD"
(cd "$PAYLOAD" && sha256sum --quiet -c manifest/SHA256SUMS) || fail "payload checksum mismatch"
SUDO=""; [ "$(id -u)" = 0 ] || { command -v sudo >/dev/null 2>&1 && SUDO="sudo -n"; }
if [ -z "${SETUP_OFFLINE:-}" ] && command -v apt-get >/dev/null 2>&1 && { [ "$(id -u)" = 0 ] || [ -n "$SUDO" ]; }; then
  $SUDO apt-get update -qq || log "WARN: apt-get update failed (non-fatal if the tools below exist)"
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq git curl ca-certificates zstd util-linux time procps bzip2 >/dev/null \
    || log "WARN: apt-get install failed (non-fatal if the tools below exist)"
fi
for c in git zstd flock xargs timeout nice; do command -v $c >/dev/null || fail "$c missing"; done
[ -n "${SETUP_OFFLINE:-}" ] || command -v curl >/dev/null || fail "curl missing"
# the code hard-codes the legacy root in places: make it resolve to $ROOT
if [ "$ROOT" != "$LEGACY_ROOT" ] && [ ! -e "$LEGACY_ROOT" ] && [ ! -L "$LEGACY_ROOT" ]; then
  $SUDO mkdir -p "$(dirname "$LEGACY_ROOT")" && $SUDO ln -s "$ROOT" "$LEGACY_ROOT" || true
  [ -e "$LEGACY_ROOT" ] || fail "cannot create the symlink $LEGACY_ROOT -> $ROOT (needs root or passwordless sudo)"
fi
PIN=$(cat "$PAYLOAD/manifest/PIN_HEAD")
mkdir -p "$ROOT/hw_wt"
[ -d "$REPO/.git" ] || git init -q "$REPO"
git -C "$REPO" config user.name h8-cloud; git -C "$REPO" config user.email h8-cloud@localhost
git -C "$REPO" fetch -q "$PAYLOAD/bundle/hw.bundle" '+refs/heads/hw/*:refs/remotes/bundle/*'
[ "$(git -C "$REPO" rev-parse refs/remotes/bundle/p4-baselines)" = "$PIN" ] || fail "bundle hw/p4-baselines is not at the pinned commit $PIN"
if [ -e "$WT/.git" ]; then
  [ -z "$(git -C "$WT" status --porcelain --untracked-files=no)" ] || fail "$WT has tracked changes"
  [ "$(git -C "$WT" rev-parse HEAD)" = "$PIN" ] || { log "moving $WT to the pin ${PIN:0:7}"; git -C "$WT" checkout -q -B hw/p4-baselines "$PIN"; }
else
  git -C "$REPO" worktree add -q -B hw/p4-baselines "$WT" "$PIN"
fi
[ "$(git -C "$WT" rev-parse HEAD)" = "$PIN" ] || fail "$WT HEAD differs from the pin"
DATA_SUM=$(cd "$PAYLOAD" && sha256sum data/*.tar.zst | sha256sum | cut -d' ' -f1)
if [ "$(cat "$ROOT/.restored_data" 2>/dev/null)" != "$DATA_SUM" ]; then
  for a in gset qkp; do tar --zstd -xf "$PAYLOAD/data/$a.tar.zst" -C "$ROOT"; done
  mkdir -p "$ROOT/sw_ref"; tar --zstd -xf "$PAYLOAD/data/d5c_qhinge.tar.zst" -C "$ROOT/sw_ref"
  mkdir -p "$ROOT/sw_ref_wt"; tar --zstd -xf "$PAYLOAD/data/qubo_bridge.tar.zst" -C "$ROOT/sw_ref_wt"
  echo "$DATA_SUM" > "$ROOT/.restored_data"; log "data restored"
else log "data unchanged"; fi
# --- environments (pinned; identical to the local swref environment and to cloud_cpu/payload/setup.sh) ---
if [ ! -x "$CONDA/bin/conda" ] && [ -z "${SETUP_OFFLINE:-}" ]; then
  curl -fsSL -o /tmp/Miniforge3.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash /tmp/Miniforge3.sh -b -p "$CONDA"
fi
[ -x "$PY" ] || [ -n "${SETUP_OFFLINE:-}" ] || "$CONDA/bin/conda" create -q -y -n swref python=3.12.15
[ -n "${SETUP_OFFLINE:-}" ] || "$PY" -m pip install -q --no-input 'numpy==2.3.5' 'numba==0.68.0' 'llvmlite==0.50.0' 'scipy==1.18.1' 'pandas==3.0.6' \
  'networkx==3.7' 'dimod==0.12.22' 'dwave-samplers==1.8.0' 'PyYAML==6.0.3' 'pytest==9.1.1'
[ -x "$CONDA/envs/eda/bin/verilator" ] || [ -n "${SETUP_OFFLINE:-}" ] || \
  "$CONDA/bin/conda" create -q -y -n eda -c conda-forge --override-channels 'verilator=5.050' make cxx-compiler
"$EDA/verilator" --version | grep -q '^Verilator 5.050' || fail "verilator 5.050 missing in the eda env"
"$PY" - <<'PYV'
import importlib.metadata as m, sys
want = {"numpy": "2.3.5", "numba": "0.68.0", "llvmlite": "0.50.0", "scipy": "1.18.1", "pandas": "3.0.6", "networkx": "3.7",
        "dimod": "0.12.22", "dwave-samplers": "1.8.0", "PyYAML": "6.0.3", "pytest": "9.1.1"}
bad = {k: (m.version(k), v) for k, v in want.items() if m.version(k) != v}
assert not bad, f"environment mismatch: {bad}"
assert sys.version_info[:2] == (3, 12), sys.version
print("env: versions match the pinned swref environment")
PYV
cat > "$RUN/env_h8.sh" <<EOF
export PATH="$EDA:\$PATH"
export VERILATOR_BIN="$EDA/verilator"
export HW_RTL_ROOT="$WT"
export H8_ROOT="$ROOT" H8_WT="$WT" H8_RUN="$RUN" H8_PY="$PY"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 NUMBA_CACHE_DIR="$WT/sim/out/numba_cache"
EOF
# 2-second JIT check on this CPU before any billed job
(source "$RUN/env_h8.sh"; cd "$WT" && "$PY" -I scripts/golden/int_float_diag.py --smoke >/dev/null) || fail "int_float_diag smoke failed"
date -u '+setup ok %F %T UTC' > "$RUN/SETUP_OK"; echo "$PIN" > "$RUN/SETUP_PIN"
log "setup complete (pin $PIN, $(nproc) vCPU, $(awk '/MemTotal/{printf "%d", $2/1048576}' /proc/meminfo) GB RAM)"
