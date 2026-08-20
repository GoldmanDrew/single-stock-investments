#!/usr/bin/env bash
# Materialize GOOGLE_APPLICATION_CREDENTIALS_JSON into a file the Drive client can use.
# Source /tmp/ssi-cloud-env.sh afterwards (see .cursor/environment.json start).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export SSI_DRIVE_CREDENTIALS_PATH="${SSI_DRIVE_CREDENTIALS_PATH:-/tmp/ssi-google-service-account.json}"
export SSI_CLOUD_ENV_SNIPPET="${SSI_CLOUD_ENV_SNIPPET:-/tmp/ssi-cloud-env.sh}"

if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT/_system/scripts/materialize_drive_credentials.py"
elif command -v python >/dev/null 2>&1; then
  python "$ROOT/_system/scripts/materialize_drive_credentials.py"
else
  if [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]; then
    printf 'export GOOGLE_APPLICATION_CREDENTIALS=%q\n' "$GOOGLE_APPLICATION_CREDENTIALS" > "$SSI_CLOUD_ENV_SNIPPET"
    echo "drive_credentials=existing path=$GOOGLE_APPLICATION_CREDENTIALS"
  elif [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]; then
    printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > "$SSI_DRIVE_CREDENTIALS_PATH"
    chmod 600 "$SSI_DRIVE_CREDENTIALS_PATH" 2>/dev/null || true
    printf 'export GOOGLE_APPLICATION_CREDENTIALS=%q\n' "$SSI_DRIVE_CREDENTIALS_PATH" > "$SSI_CLOUD_ENV_SNIPPET"
    echo "drive_credentials=materialized path=$SSI_DRIVE_CREDENTIALS_PATH"
  else
    echo "drive_credentials=unset path=unset"
  fi
fi
