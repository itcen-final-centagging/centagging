#!/usr/bin/env bash

set -euo pipefail

ENV_FILE="${1:-/opt/centagging/.env.prod}"
OUTPUT_FILE="${2:-/run/centagging/secrets.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Production environment file not found: ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

required_variables=(
  GCP_PROJECT_ID
  GEMINI_API_KEY_SECRET_ID
  GEMINI_API_KEY_SECRET_VERSION
  POSTGRES_PASSWORD_SECRET_ID
  POSTGRES_PASSWORD_SECRET_VERSION
  MVP_LOGIN_ID_SECRET_ID
  MVP_LOGIN_ID_SECRET_VERSION
  MVP_LOGIN_PASSWORD_SECRET_ID
  MVP_LOGIN_PASSWORD_SECRET_VERSION
)

for variable_name in "${required_variables[@]}"; do
  if [[ -z "${!variable_name:-}" ]]; then
    echo "Required variable is not set: ${variable_name}" >&2
    exit 1
  fi
done

output_directory="$(dirname "${OUTPUT_FILE}")"
sudo install -d -m 0700 \
  -o "$(id -u)" \
  -g "$(id -g)" \
  "${output_directory}"

umask 077
secret_file_tmp="$(mktemp "${output_directory}/secrets.env.XXXXXX")"
trap 'rm -f "${secret_file_tmp}"' EXIT

fetch_secret() {
  local env_name="$1"
  local secret_id="$2"
  local secret_version="$3"
  local secret_value

  if ! secret_value="$(gcloud secrets versions access "${secret_version}" \
    --secret="${secret_id}" \
    --project="${GCP_PROJECT_ID}" \
    --quiet)"; then
    echo "${env_name}: failed to access Secret Manager" >&2
    return 1
  fi

  if [[ ! "${secret_value}" =~ ^[A-Za-z0-9_./:@%+=,-]+$ ]]; then
    echo "${env_name}: secret contains unsupported dotenv characters" >&2
    return 1
  fi

  printf '%s=%s\n' "${env_name}" "${secret_value}"
}

{
  fetch_secret GEMINI_API_KEY \
    "${GEMINI_API_KEY_SECRET_ID}" \
    "${GEMINI_API_KEY_SECRET_VERSION}"
  fetch_secret POSTGRES_PASSWORD \
    "${POSTGRES_PASSWORD_SECRET_ID}" \
    "${POSTGRES_PASSWORD_SECRET_VERSION}"
  fetch_secret MVP_LOGIN_ID \
    "${MVP_LOGIN_ID_SECRET_ID}" \
    "${MVP_LOGIN_ID_SECRET_VERSION}"
  fetch_secret MVP_LOGIN_PASSWORD \
    "${MVP_LOGIN_PASSWORD_SECRET_ID}" \
    "${MVP_LOGIN_PASSWORD_SECRET_VERSION}"
} > "${secret_file_tmp}"

if [[ "$(wc -l < "${secret_file_tmp}")" -ne 4 ]]; then
  echo "Unexpected number of rendered secrets" >&2
  exit 1
fi

chmod 600 "${secret_file_tmp}"
mv "${secret_file_tmp}" "${OUTPUT_FILE}"
trap - EXIT

echo "Production secrets rendered successfully."
