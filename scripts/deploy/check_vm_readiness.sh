#!/usr/bin/env bash

set -euo pipefail

repository_root="${REPOSITORY_ROOT:-/opt/centagging}"
env_file="${ENV_FILE:-${repository_root}/.env.prod}"

required_commands=(
  curl
  docker
  findmnt
  gcloud
  gcsfuse
  mountpoint
)

for command_name in "${required_commands[@]}"; do
  if ! command -v "${command_name}" > /dev/null 2>&1; then
    echo "Required command is not installed: ${command_name}" >&2
    exit 1
  fi
done

required_files=(
  "${repository_root}/docker-compose.prod.yml"
  "${repository_root}/scripts/deploy/deploy_vm.sh"
  "${repository_root}/scripts/deploy/render_prod_secrets.sh"
  "${env_file}"
)

for required_file in "${required_files[@]}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "Required deployment file is missing: ${required_file}" >&2
    exit 1
  fi
done

env_permissions="$(stat -c '%a' "${env_file}")"
if [[ "${env_permissions}" != "600" ]]; then
  echo "Production environment file permissions must be 600: ${env_file}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${env_file}"
set +a

required_variables=(
  CLOUD_SQL_INSTANCE_CONNECTION_NAME
  GCP_PROJECT_ID
  GCP_REGION
  GCS_BUCKET_NAME
  GCS_MOUNT_ROOT
  GEMINI_API_KEY_SECRET_ID
  GEMINI_API_KEY_SECRET_VERSION
  MVP_LOGIN_ID_SECRET_ID
  MVP_LOGIN_ID_SECRET_VERSION
  MVP_LOGIN_PASSWORD_SECRET_ID
  MVP_LOGIN_PASSWORD_SECRET_VERSION
  POSTGRES_DB
  POSTGRES_PASSWORD_SECRET_ID
  POSTGRES_PASSWORD_SECRET_VERSION
  POSTGRES_USER
)

for variable_name in "${required_variables[@]}"; do
  variable_value="${!variable_name:-}"
  if [[ -z "${variable_value}" ]]; then
    echo "Required production variable is not set: ${variable_name}" >&2
    exit 1
  fi

  if [[ "${variable_value}" == replace-with-* ]]; then
    echo "Production placeholder has not been replaced: ${variable_name}" >&2
    exit 1
  fi
done

runtime_secret_variables=(
  GEMINI_API_KEY
  MVP_LOGIN_ID
  MVP_LOGIN_PASSWORD
  POSTGRES_PASSWORD
)

for variable_name in "${runtime_secret_variables[@]}"; do
  if [[ -n "${!variable_name:-}" ]]; then
    echo "Runtime secret must remain empty in ${env_file}: ${variable_name}" >&2
    exit 1
  fi
done

if [[ "${GCS_MOUNT_ROOT}" != "/mnt/centagging-gcs" ]]; then
  echo "Unexpected GCS mount root: ${GCS_MOUNT_ROOT}" >&2
  exit 1
fi

if ! mountpoint -q "${GCS_MOUNT_ROOT}"; then
  echo "Cloud Storage FUSE is not mounted: ${GCS_MOUNT_ROOT}" >&2
  exit 1
fi

mounted_type="$(findmnt -n -o FSTYPE --target "${GCS_MOUNT_ROOT}")"
if [[ "${mounted_type}" != "fuse.gcsfuse" && "${mounted_type}" != "gcsfuse" ]]; then
  echo "Unexpected filesystem at ${GCS_MOUNT_ROOT}: ${mounted_type}" >&2
  exit 1
fi

for storage_path in \
  "${GCS_MOUNT_ROOT}/uploads" \
  "${GCS_MOUNT_ROOT}/sku-images"; do
  if [[ ! -d "${storage_path}" || ! -r "${storage_path}" || ! -w "${storage_path}" ]]; then
    echo "GCS storage path is not ready: ${storage_path}" >&2
    exit 1
  fi
done

docker info > /dev/null
docker compose version > /dev/null
gcloud auth print-access-token --quiet > /dev/null

echo "VM deployment readiness check passed."
