#!/usr/bin/env bash

set -euo pipefail

PATCH_FILE="${1:-/workspace/.devcontainer/klee-guided-search.patch}"
KLEE_SRC="${KLEE_SRC:-$(readlink -f /home/klee/klee_src)}"
KLEE_BUILD="${KLEE_BUILD:-$(readlink -f /home/klee/klee_build)}"
PATCH_HASH_FILE="${HOME}/.eclipse-guided-klee.patch-hash"
KLEE_BUILD_JOBS="${KLEE_BUILD_JOBS:-2}"

if [[ ! -f "${PATCH_FILE}" ]]; then
  echo "Guided KLEE patch not found at ${PATCH_FILE}" >&2
  exit 1
fi

PATCH_HASH="$(shasum -a 256 "${PATCH_FILE}" | awk '{print $1}')"
if [[ -f "${PATCH_HASH_FILE}" ]] && [[ "$(cat "${PATCH_HASH_FILE}")" == "${PATCH_HASH}" ]]; then
  exit 0
fi

if git -C "${KLEE_SRC}" apply --check "${PATCH_FILE}" >/dev/null 2>&1; then
  git -C "${KLEE_SRC}" apply "${PATCH_FILE}"
elif [[ -f "${KLEE_SRC}/lib/Core/GuidedSearcher.cpp" ]] \
  && grep -q 'GuidedSearcher.cpp' "${KLEE_SRC}/lib/Core/CMakeLists.txt" \
  && grep -q -- '-guidance.json' "${KLEE_SRC}/lib/Core/UserSearcher.cpp"; then
  :
elif git -C "${KLEE_SRC}" apply --reverse --check "${PATCH_FILE}" >/dev/null 2>&1; then
  :
else
  echo "Guided KLEE patch does not apply cleanly to ${KLEE_SRC}." >&2
  echo "Rebuild the devcontainer from a clean image if the upstream KLEE tree changed." >&2
  exit 1
fi

cmake --build "${KLEE_BUILD}" --target klee -- -j"${KLEE_BUILD_JOBS}"
printf '%s\n' "${PATCH_HASH}" > "${PATCH_HASH_FILE}"
