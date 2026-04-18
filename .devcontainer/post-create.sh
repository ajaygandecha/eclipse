#!/usr/bin/env bash

set -euo pipefail

python3 -m pip install --user pre-commit commitizen
python3 -m pre_commit install --hook-type commit-msg

bash /workspace/.devcontainer/apply-guided-klee.sh

COREUTILS_DIR="/workspace/examples/coreutils"
CONFIG_STAMP="$COREUTILS_DIR/.eclipse-devcontainer-configured"
CONFIG_CC_MARKER="$COREUTILS_DIR/.eclipse-devcontainer-coreutils-cc"
COREUTILS_BUILD_JOBS="${COREUTILS_BUILD_JOBS:-1}"
COREUTILS_SETUP_CC="${COREUTILS_SETUP_CC:-wllvm}"
CURRENT_CONFIGURED_CC=""

if [[ -f "$CONFIG_CC_MARKER" ]]; then
  CURRENT_CONFIGURED_CC="$(cat "$CONFIG_CC_MARKER")"
fi

if [[ ! -f "$CONFIG_STAMP" \
   || "$COREUTILS_DIR/bootstrap" -nt "$CONFIG_STAMP" \
   || "$COREUTILS_DIR/configure.ac" -nt "$CONFIG_STAMP" \
   || "$CURRENT_CONFIGURED_CC" != "$COREUTILS_SETUP_CC" \
   || ! -f "$COREUTILS_DIR/lib/config.h" \
   || ! -f "$COREUTILS_DIR/Makefile" ]]; then
  cd "$COREUTILS_DIR"
  # README-hacking documents `make -f cfg.mk` as the all-in-one developer
  # bootstrap. It expands to bootstrap/configure/make, and we run the
  # equivalent steps directly here so the devcontainer can keep job counts
  # predictable and avoid the aggressive `nproc` parallelism from cfg.mk.
  ./bootstrap
  if [[ -f Makefile ]]; then
    make distclean >/dev/null 2>&1 || true
  fi
  if [[ "$COREUTILS_SETUP_CC" == "wllvm" ]]; then
    export LLVM_COMPILER=clang
    export CFLAGS="-g -O1 -Xclang -disable-llvm-passes -D__NO_STRING_INLINES -D_FORTIFY_SOURCE=0 -U__OPTIMIZE__"
  fi
  ./configure --quiet --disable-gcc-warnings --disable-nls CC="$COREUTILS_SETUP_CC"
  # `src/main.py` builds individual Coreutils programs on demand from this
  # prepared tree, so generate the common headers it depends on up front.
  make -j"$COREUTILS_BUILD_JOBS" lib/pthread.h lib/wctype.h
  touch "$CONFIG_STAMP"
  printf '%s\n' "$COREUTILS_SETUP_CC" > "$CONFIG_CC_MARKER"
fi
