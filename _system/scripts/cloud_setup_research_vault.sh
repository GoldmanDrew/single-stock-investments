#!/usr/bin/env bash
# Cloud agent VM setup: ensure RESEARCH_VAULT_ROOT points at a readable vault tree.
# Supersedes cloud_setup_hk_vault.sh for unified vault checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEFAULT="${RESEARCH_VAULT_ROOT:-$ROOT/_external/research-vault}"
REPO_URL="${RESEARCH_VAULT_REPO_URL:-${HK_PDFS_REPO_URL:-}}"

mkdir -p "$(dirname "$DEFAULT")"

if [ -d "$DEFAULT/superinvestor-letters" ] || [ -d "$DEFAULT/investment-wisdom" ]; then
  echo "Research vault already present at $DEFAULT"
elif [ -n "$REPO_URL" ]; then
  echo "Cloning research vault from RESEARCH_VAULT_REPO_URL into $DEFAULT"
  git clone --depth 1 "$REPO_URL" "$DEFAULT"
elif [ -d "$ROOT/../research-vault/superinvestor-letters" ]; then
  echo "Linking sibling research-vault -> $DEFAULT"
  ln -sfn "$ROOT/../research-vault" "$DEFAULT"
else
  echo "WARN: Research vault not found. Set RESEARCH_VAULT_ROOT or RESEARCH_VAULT_REPO_URL."
  mkdir -p "$DEFAULT"
fi

export RESEARCH_VAULT_ROOT="$DEFAULT"

# HK PDFs: prefer vault/investment-wisdom/horizon-kinetics/pdfs, else legacy HK_PDFS_ROOT
HK_DEFAULT="${HK_PDFS_ROOT:-/opt/cursor/hk_pdfs}"
if [ -z "${HK_PDFS_ROOT:-}" ]; then
  if [ -d "$DEFAULT/investment-wisdom/horizon-kinetics/pdfs" ]; then
    export HK_PDFS_ROOT="$DEFAULT/investment-wisdom/horizon-kinetics/pdfs"
  elif [ -d "$HK_DEFAULT/book/build/text" ] || [ -d "$HK_DEFAULT" ]; then
    export HK_PDFS_ROOT="$HK_DEFAULT"
  fi
fi

grep -q 'RESEARCH_VAULT_ROOT' ~/.bashrc 2>/dev/null || echo "export RESEARCH_VAULT_ROOT=\"$DEFAULT\"" >> ~/.bashrc
if [ -n "${HK_PDFS_ROOT:-}" ]; then
  grep -q 'HK_PDFS_ROOT' ~/.bashrc 2>/dev/null || echo "export HK_PDFS_ROOT=\"$HK_PDFS_ROOT\"" >> ~/.bashrc
fi

echo "RESEARCH_VAULT_ROOT=${RESEARCH_VAULT_ROOT:-$DEFAULT}"
echo "HK_PDFS_ROOT=${HK_PDFS_ROOT:-unset}"

# Drive key: Cloud Agents inject JSON; Python clients need a file path.
bash "$ROOT/_system/scripts/cloud_setup_drive_credentials.sh"
if [ -f "${SSI_CLOUD_ENV_SNIPPET:-/tmp/ssi-cloud-env.sh}" ]; then
  # shellcheck disable=SC1090
  . "${SSI_CLOUD_ENV_SNIPPET:-/tmp/ssi-cloud-env.sh}"
fi
