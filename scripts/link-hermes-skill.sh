#!/usr/bin/env bash
set -euo pipefail

# Idempotently point Hermes lit-review skill to this repo's canonical skill folder.

if [[ -n "${LITREVIEW_ROOT:-}" ]]; then
  repo_root="${LITREVIEW_ROOT}"
else
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

skill_source="${repo_root}/skills/lit-review"
skill_target="${HOME}/.hermes/skills/research/lit-review"

if [[ ! -d "${skill_source}" ]]; then
  echo "Error: canonical skill not found at ${skill_source}" >&2
  exit 1
fi

mkdir -p "${HOME}/.hermes/skills/research"
ln -sfn "${skill_source}" "${skill_target}"

echo "Linked Hermes skill:"
echo "  ${skill_target} -> ${skill_source}"
echo "Verify with:"
echo "  ls -la \"${skill_target}\""
