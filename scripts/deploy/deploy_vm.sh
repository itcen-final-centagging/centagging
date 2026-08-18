#!/usr/bin/env bash

set -euo pipefail

REPOSITORY_ROOT="${REPOSITORY_ROOT:-/opt/centagging}"
ENV_FILE="${ENV_FILE:-${REPOSITORY_ROOT}/.env.prod}"
SECRET_ENV_FILE="${SECRET_ENV_FILE:-/run/centagging/secrets.env}"
COMPOSE_FILE="${REPOSITORY_ROOT}/docker-compose.prod.yml"

API_IMAGE="${1:-}"
FRONTEND_IMAGE="${2:-}"

if [[ -z "${API_IMAGE}" || -z "${FRONTEND_IMAGE}" ]]; then
  echo "Usage: deploy_vm.sh API_IMAGE FRONTEND_IMAGE" >&2
  exit 1
fi

if [[ ! "${API_IMAGE}" =~ ^[a-z0-9.-]+-docker\.pkg\.dev/[a-z0-9:._/-]+$ ]]; then
  echo "Invalid Artifact Registry API image reference" >&2
  exit 1
fi

if [[ ! "${FRONTEND_IMAGE}" =~ ^[a-z0-9.-]+-docker\.pkg\.dev/[a-z0-9:._/-]+$ ]]; then
  echo "Invalid Artifact Registry frontend image reference" >&2
  exit 1
fi

cd "${REPOSITORY_ROOT}"

bash scripts/deploy/render_prod_secrets.sh \
  "${ENV_FILE}" \
  "${SECRET_ENV_FILE}"

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
# shellcheck disable=SC1090
source "${SECRET_ENV_FILE}"
set +a

if [[ -z "${GCP_REGION:-}" ]]; then
  echo "Required variable is not set: GCP_REGION" >&2
  exit 1
fi

if ! mountpoint -q "${GCS_MOUNT_ROOT}"; then
  echo "Cloud Storage FUSE is not mounted: ${GCS_MOUNT_ROOT}" >&2
  exit 1
fi

compose() {
  docker compose \
    --env-file "${ENV_FILE}" \
    --env-file "${SECRET_ENV_FILE}" \
    -f "${COMPOSE_FILE}" \
    "$@"
}

previous_api_image=""
previous_frontend_image=""

api_container_id="$(compose ps -q api 2>/dev/null || true)"
frontend_container_id="$(compose ps -q frontend 2>/dev/null || true)"

if [[ -n "${api_container_id}" ]]; then
  previous_api_image="$(docker inspect \
    --format '{{.Config.Image}}' \
    "${api_container_id}")"
fi

if [[ -n "${frontend_container_id}" ]]; then
  previous_frontend_image="$(docker inspect \
    --format '{{.Config.Image}}' \
    "${frontend_container_id}")"
fi

export API_IMAGE FRONTEND_IMAGE

gcloud auth configure-docker \
  "${GCP_REGION}-docker.pkg.dev" \
  --quiet > /dev/null

compose config --quiet
compose pull cloud-sql-proxy api ai-worker frontend

rollback() {
  if [[ -z "${previous_api_image}" || -z "${previous_frontend_image}" ]]; then
    echo "No previous images are available for automatic rollback." >&2
    return 1
  fi

  echo "Deployment failed. Restoring previous application images." >&2
  export API_IMAGE="${previous_api_image}"
  export FRONTEND_IMAGE="${previous_frontend_image}"
  compose up -d --no-build --remove-orphans
}

if ! compose up -d --no-build --remove-orphans; then
  rollback
  exit 1
fi

worker_container_id="$(compose ps -q ai-worker 2>/dev/null || true)"
if [[ -z "${worker_container_id}" ]]; then
  echo "AI worker container did not start." >&2
  compose logs --tail=100 ai-worker >&2 || true
  rollback
  exit 1
fi

health_check_passed=false

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error \
    --max-time 10 \
    http://127.0.0.1/health > /dev/null; then
    health_check_passed=true
    break
  fi

  sleep 10
done

if [[ "${health_check_passed}" != "true" ]]; then
  compose logs --tail=100 api ai-worker frontend >&2 || true
  rollback
  exit 1
fi

compose ps
echo "VM deployment and health check completed successfully."
