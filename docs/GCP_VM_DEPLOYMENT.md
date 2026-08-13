# GCP Compute Engine 운영 배포 가이드

이 문서는 `deploy` 브랜치의 Centagging 서비스를 GCP Compute Engine VM에 수동으로 배포하고 검증·롤백하는 절차를 설명합니다.

## 1. 배포 범위와 구조

이번 단계에서는 Cloud Run과 외부 Load Balancer를 사용하지 않습니다.

```text
사용자
  -> Compute Engine VM:80
  -> Nginx + React 컨테이너
  -> FastAPI 컨테이너
     -> Cloud SQL Auth Proxy 컨테이너
     -> Cloud SQL for PostgreSQL + pgvector
     -> Cloud Storage FUSE 마운트
     -> Gemini API
```

- 외부에 공개하는 포트는 HTTP `80`뿐입니다.
- FastAPI `8000`, Cloud SQL Proxy `5432`는 Docker 내부 네트워크에서만 사용합니다.
- SSH `22`는 인터넷에 공개하지 않고 IAP TCP 터널만 허용합니다.
- Pub/Sub과 비동기 Worker는 비동기 리팩토링이 병합된 후 추가합니다.
- 현재 구성은 HTTP 수동 배포 검증용입니다. 실제 운영 데이터 투입 전에는 도메인과 TLS 구성을 별도 적용해야 합니다.

## 2. 준비 사항

- 결제가 연결된 GCP 프로젝트
- 프로젝트 리소스를 생성할 수 있는 IAM 권한
- Cloud Shell 또는 `gcloud` CLI
- GitHub 저장소의 `deploy` 브랜치 접근 권한
- 실제 운영용 Gemini API 키

아래 명령의 예시 값은 환경에 맞게 변경합니다.

```bash
export PROJECT_ID="replace-with-gcp-project-id"
export REGION="asia-northeast3"
export ZONE="asia-northeast3-a"
export VPC_NETWORK="centagging-prod-vpc"
export VPC_SUBNET="centagging-prod-subnet"
export VM_NAME="centagging-prod-vm"
export VM_SERVICE_ACCOUNT_NAME="centagging-prod-runtime"
export VM_SERVICE_ACCOUNT="${VM_SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export CLOUD_SQL_INSTANCE="centagging-prod-pg"
export GCS_BUCKET="${PROJECT_ID}-centagging-prod"
export ARTIFACT_REPOSITORY="centagging-prod"

gcloud config set project "${PROJECT_ID}"
```

## 3. GCP API 활성화

Cloud Shell에서 실행합니다.

```bash
gcloud services enable \
  compute.googleapis.com \
  sqladmin.googleapis.com \
  servicenetworking.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iap.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com
```

## 4. VPC와 Private Service Access 구성

VM과 Cloud SQL을 동일한 VPC에 배치합니다.

```bash
gcloud compute networks create "${VPC_NETWORK}" \
  --subnet-mode=custom

gcloud compute networks subnets create "${VPC_SUBNET}" \
  --network="${VPC_NETWORK}" \
  --region="${REGION}" \
  --range="10.10.0.0/24"
```

Cloud SQL Private IP에 사용할 관리형 서비스 범위를 예약하고 VPC Peering을 연결합니다.

```bash
gcloud compute addresses create centagging-prod-managed-services \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network="${VPC_NETWORK}"

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=centagging-prod-managed-services \
  --network="${VPC_NETWORK}"
```

이미 같은 이름의 네트워크나 연결이 있다면 새로 만들지 말고 기존 리소스를 확인합니다.

## 5. VM 런타임 서비스 계정 구성

서비스 계정 키 JSON 파일은 생성하지 않습니다. Compute Engine에 연결된 서비스 계정과 Application Default Credentials를 사용합니다.

```bash
gcloud iam service-accounts create "${VM_SERVICE_ACCOUNT_NAME}" \
  --display-name="Centagging production VM runtime"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${VM_SERVICE_ACCOUNT}" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${VM_SERVICE_ACCOUNT}" \
  --role="roles/artifactregistry.reader"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${VM_SERVICE_ACCOUNT}" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${VM_SERVICE_ACCOUNT}" \
  --role="roles/monitoring.metricWriter"
```

### 5.1 Secret Manager 구성

운영 시크릿은 Secret Manager를 원본 저장소로 사용합니다. 먼저 시크릿 리소스를 생성합니다.

```bash
gcloud secrets create centagging-prod-gemini-api-key \
  --replication-policy=automatic

gcloud secrets create centagging-prod-postgres-password \
  --replication-policy=automatic

gcloud secrets create centagging-prod-login-id \
  --replication-policy=automatic

gcloud secrets create centagging-prod-login-password \
  --replication-policy=automatic
```

각 값은 화면에 표시하거나 셸 기록에 직접 작성하지 않고 새 버전으로 등록합니다. 아래 절차를 시크릿마다 반복합니다.

```bash
read -r -s -p "Secret value: " SECRET_VALUE
echo
printf '%s' "${SECRET_VALUE}" \
  | gcloud secrets versions add SECRET_ID --data-file=-
unset SECRET_VALUE
```

VM 서비스 계정에는 네 개의 시크릿에 대해서만 조회 권한을 부여합니다.

```bash
for SECRET_ID in \
  centagging-prod-gemini-api-key \
  centagging-prod-postgres-password \
  centagging-prod-login-id \
  centagging-prod-login-password
do
  gcloud secrets add-iam-policy-binding "${SECRET_ID}" \
    --member="serviceAccount:${VM_SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"
done
```

프로젝트 전체 Secret 접근 권한은 부여하지 않습니다. 단일 VM 구조에서는 VM에 연결된 서비스 계정이 IAM 신뢰 경계이므로, VM에서 실행되는 컨테이너와 Docker 관리 권한을 가진 운영자를 동일한 보안 경계로 관리합니다.

## 6. Cloud Storage 버킷 구성

운영 이미지 버킷을 생성하고 VM 서비스 계정에 객체 사용 권한을 부여합니다.

```bash
gcloud storage buckets create "gs://${GCS_BUCKET}" \
  --location="${REGION}" \
  --uniform-bucket-level-access \
  --public-access-prevention

gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET}" \
  --member="serviceAccount:${VM_SERVICE_ACCOUNT}" \
  --role="roles/storage.objectUser"
```

버킷은 공개하지 않습니다. 현재 애플리케이션은 VM에 마운트된 다음 경로를 사용합니다.

```text
/mnt/centagging-gcs/uploads
/mnt/centagging-gcs/sku-images
```

## 7. Cloud SQL PostgreSQL 구성

다음 예시는 PostgreSQL 16 Enterprise, 1 vCPU, 3.75GB 메모리의 단일 영역 인스턴스입니다. 실제 부하와 예산에 맞게 CPU·메모리·가용성 옵션을 조정합니다.

```bash
gcloud sql instances create "${CLOUD_SQL_INSTANCE}" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --cpu=1 \
  --memory=3840MB \
  --region="${REGION}" \
  --network="projects/${PROJECT_ID}/global/networks/${VPC_NETWORK}" \
  --no-assign-ip \
  --storage-type=SSD \
  --storage-size=20 \
  --storage-auto-increase \
  --availability-type=ZONAL \
  --backup-start-time=18:00 \
  --enable-point-in-time-recovery
```

데이터베이스와 애플리케이션 사용자를 생성합니다. DB 사용자 비밀번호는 Secret Manager에 등록한 승인 버전과 동일한 값을 사용합니다.

```bash
gcloud sql databases create centagging \
  --instance="${CLOUD_SQL_INSTANCE}"

DB_PASSWORD="$(gcloud secrets versions access 1 \
  --secret=centagging-prod-postgres-password)"

gcloud sql users create centagging \
  --instance="${CLOUD_SQL_INSTANCE}" \
  --password="${DB_PASSWORD}"

unset DB_PASSWORD
```

인스턴스 연결 이름을 확인합니다. 이 값을 VM의 `.env.prod`에 입력합니다.

```bash
gcloud sql instances describe "${CLOUD_SQL_INSTANCE}" \
  --format="value(connectionName)"
```

## 8. Artifact Registry 구성

수동 최초 배포는 VM에서 이미지를 빌드할 수 있습니다. 이후 GitHub Actions가 이미지를 Push할 저장소를 미리 생성합니다.

```bash
gcloud artifacts repositories create "${ARTIFACT_REPOSITORY}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Centagging production container images"
```

운영 이미지 주소 형식은 다음과 같습니다.

```text
asia-northeast3-docker.pkg.dev/PROJECT_ID/centagging-prod/api:COMMIT_SHA
asia-northeast3-docker.pkg.dev/PROJECT_ID/centagging-prod/frontend:COMMIT_SHA
```

## 9. 방화벽과 Compute Engine VM 생성

웹 트래픽과 IAP SSH만 허용합니다.

```bash
gcloud compute firewall-rules create centagging-prod-allow-http \
  --network="${VPC_NETWORK}" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:80 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=centagging-prod-web

gcloud compute firewall-rules create centagging-prod-allow-iap-ssh \
  --network="${VPC_NETWORK}" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=centagging-prod-web
```

고정 외부 IP를 예약하고 Ubuntu 24.04 VM을 생성합니다.

```bash
gcloud compute addresses create centagging-prod-ip \
  --region="${REGION}"

export STATIC_IP="$(gcloud compute addresses describe centagging-prod-ip \
  --region="${REGION}" \
  --format='value(address)')"

gcloud compute instances create "${VM_NAME}" \
  --zone="${ZONE}" \
  --machine-type=e2-standard-4 \
  --subnet="${VPC_SUBNET}" \
  --address="${STATIC_IP}" \
  --service-account="${VM_SERVICE_ACCOUNT}" \
  --scopes=cloud-platform \
  --tags=centagging-prod-web \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-type=pd-balanced \
  --boot-disk-size=50GB \
  --metadata=enable-oslogin=TRUE
```

IAP로 접속합니다.

```bash
gcloud compute ssh "${VM_NAME}" \
  --zone="${ZONE}" \
  --tunnel-through-iap
```

## 10. VM에 Docker 설치

VM에서 실행합니다.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git rsync
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"${UBUNTU_CODENAME:-$VERSION_CODENAME}\") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

sudo usermod -aG docker "${USER}"
```

그룹 적용을 위해 SSH 연결을 종료하고 다시 접속한 뒤 확인합니다.

```bash
docker version
docker compose version
```

## 11. VM에 Google Cloud CLI와 Cloud Storage FUSE 설치 및 마운트

VM에서 실행합니다.

```bash
export PROJECT_ID="replace-with-gcp-project-id"
export GCS_BUCKET="replace-with-production-bucket-name"

sudo apt-get update
sudo apt-get install -y curl lsb-release

export GCSFUSE_REPO="gcsfuse-$(lsb_release -c -s)"
echo "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt ${GCSFUSE_REPO} main" \
  | sudo tee /etc/apt/sources.list.d/gcsfuse.list

echo "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt cloud-sdk main" \
  | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list

curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | sudo tee /usr/share/keyrings/cloud.google.asc > /dev/null

sudo apt-get update
sudo apt-get install -y gcsfuse google-cloud-cli
gcloud config set project "${PROJECT_ID}"
sudo mkdir -p /mnt/centagging-gcs

sudo mount -t gcsfuse \
  -o rw,allow_other,implicit_dirs \
  "${GCS_BUCKET}" \
  /mnt/centagging-gcs

sudo mkdir -p \
  /mnt/centagging-gcs/uploads \
  /mnt/centagging-gcs/sku-images
```

마운트를 확인합니다.

```bash
mount | grep centagging-gcs
ls -la /mnt/centagging-gcs
```

재부팅 후에도 자동 마운트하려면 `/etc/fstab`에 다음 한 줄을 추가합니다. `BUCKET_NAME`은 실제 버킷명으로 변경합니다.

```text
BUCKET_NAME /mnt/centagging-gcs gcsfuse rw,_netdev,allow_other,implicit_dirs 0 0
```

적용 전에 문법과 마운트를 검증합니다.

```bash
sudo mount -a
mount | grep centagging-gcs
```

## 12. 저장소와 운영 환경변수 준비

VM에서 저장소를 `/opt/centagging`에 배치합니다. Private 저장소 인증은 조직에서 승인한 GitHub Deploy Key 또는 GitHub App 방식을 사용합니다.

```bash
sudo mkdir -p /opt/centagging
sudo chown "${USER}:${USER}" /opt/centagging

git clone --branch deploy \
  https://github.com/itcen-final-centagging/centagging.git \
  /opt/centagging

cd /opt/centagging

# 최초 1회: 저장소의 SKU 이미지를 GCS 마운트로 복사합니다.
if [ -d data/images ]; then
  rsync -a data/images/ /mnt/centagging-gcs/sku-images/
fi

cp .env.prod.example .env.prod
chmod 600 .env.prod
```

`.env.prod`에는 비시크릿 운영 설정과 Secret Manager의 ID·버전만 입력합니다. 다음 네 개의 런타임 값은 비워둡니다.

```text
MVP_LOGIN_ID=
MVP_LOGIN_PASSWORD=
GEMINI_API_KEY=
POSTGRES_PASSWORD=
```

비시크릿 필수 확인 항목:

```text
GCP_PROJECT_ID
GCP_REGION
GCS_BUCKET_NAME
GCS_MOUNT_ROOT=/mnt/centagging-gcs
CLOUD_SQL_INSTANCE_CONNECTION_NAME
POSTGRES_DB
POSTGRES_USER
MVP_LOGIN_ID_SECRET_ID
MVP_LOGIN_ID_SECRET_VERSION
MVP_LOGIN_PASSWORD_SECRET_ID
MVP_LOGIN_PASSWORD_SECRET_VERSION
GEMINI_API_KEY_SECRET_ID
GEMINI_API_KEY_SECRET_VERSION
POSTGRES_PASSWORD_SECRET_ID
POSTGRES_PASSWORD_SECRET_VERSION
```

실제 `.env.prod`는 Git에 추가하지 않고 파일 권한을 `600`으로 유지합니다.

Secret Manager 값을 VM의 메모리 기반 `/run` 경로에 생성합니다. 시크릿 값은 공백 문자를 포함하지 않는 단일 행 값이어야 합니다.

```bash
cd /opt/centagging

set -euo pipefail
set -a
source .env.prod
set +a

sudo install -d -m 0700 \
  -o "${USER}" \
  -g "$(id -gn)" \
  /run/centagging

umask 077
SECRET_ENV_TMP="$(mktemp /run/centagging/secrets.env.XXXXXX)"
trap 'rm -f "${SECRET_ENV_TMP}"' EXIT

fetch_secret() {
  local env_name="$1"
  local secret_id="$2"
  local secret_version="$3"
  local secret_value

  if ! secret_value="$(gcloud secrets versions access "${secret_version}" \
    --secret="${secret_id}")"; then
    echo "${env_name}: failed to access Secret Manager" >&2
    return 1
  fi

  if [[ -z "${secret_value}" || "${secret_value}" =~ [[:space:]] ]]; then
    echo "${env_name}: empty or whitespace-containing secrets are not supported" >&2
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
} > "${SECRET_ENV_TMP}"

test "$(wc -l < "${SECRET_ENV_TMP}")" -eq 4
chmod 600 "${SECRET_ENV_TMP}"
mv "${SECRET_ENV_TMP}" /run/centagging/secrets.env
trap - EXIT
```

시크릿 파일 내용을 `cat`, `echo` 또는 `docker compose config`로 출력하지 않습니다. VM 재부팅이나 시크릿 버전 변경 후에는 위 절차로 `/run/centagging/secrets.env`를 다시 생성합니다.

## 13. Cloud SQL 스키마 초기화

Compose 설정을 검증하고 Cloud SQL Proxy만 먼저 실행합니다.

```bash
cd /opt/centagging

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  config --quiet

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  up -d cloud-sql-proxy

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  ps cloud-sql-proxy
```

초기화 SQL은 Cloud SQL에 한 번만 적용합니다.

```bash
docker run --rm \
  --network centagging_app_network \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -v "$(pwd)/docker/db/init:/init:ro" \
  postgres:16-alpine \
  sh -c 'export PGPASSWORD="$POSTGRES_PASSWORD"; psql -v ON_ERROR_STOP=1 -h cloud-sql-proxy -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /init/01-enable-vector.sql'

docker run --rm \
  --network centagging_app_network \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -v "$(pwd)/docker/db/init:/init:ro" \
  postgres:16-alpine \
  sh -c 'export PGPASSWORD="$POSTGRES_PASSWORD"; psql -v ON_ERROR_STOP=1 -h cloud-sql-proxy -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /init/schema.sql'

docker run --rm \
  --network centagging_app_network \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -v "$(pwd)/docker/db/init:/init:ro" \
  postgres:16-alpine \
  sh -c 'export PGPASSWORD="$POSTGRES_PASSWORD"; gzip -dc /init/zz-sku-catalog-embeddings.sql.gz | psql -v ON_ERROR_STOP=1 -h cloud-sql-proxy -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

이미 스키마와 초기 데이터가 존재하는 환경에서는 초기화 명령을 반복 실행하지 않습니다.

## 14. 최초 수동 배포

현재 소스 기준 이미지를 VM에서 빌드하고 실행합니다.

```bash
cd /opt/centagging

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  up -d --build
```

상태와 로그를 확인합니다.

```bash
docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  ps

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  logs --tail=200 cloud-sql-proxy api frontend
```

VM 내부 Smoke Test:

```bash
curl --fail --show-error http://127.0.0.1/health
curl --fail --show-error http://127.0.0.1/
```

외부에서 고정 IP로 확인합니다.

```bash
curl --fail --show-error "http://STATIC_IP/health"
```

정상 헬스 응답 예시:

```json
{"status":"ok"}
```

## 15. 수동 재배포

`deploy` 브랜치의 최신 변경을 가져온 후 Compose 설정을 검증하고 다시 빌드합니다.

```bash
cd /opt/centagging

git switch deploy
git fetch origin
git pull --ff-only origin deploy

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  config --quiet

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  up -d --build --remove-orphans

curl --fail --show-error http://127.0.0.1/health
```

## 16. 롤백

배포 전 정상 동작하던 Git Commit SHA를 기록합니다.

```bash
cd /opt/centagging
git rev-parse HEAD
```

애플리케이션 롤백은 정상 동작했던 Commit으로 이미지를 다시 빌드합니다.

```bash
git switch --detach VERIFIED_COMMIT_SHA

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  up -d --build --remove-orphans

curl --fail --show-error http://127.0.0.1/health
```

롤백 확인 후 다시 배포 흐름으로 복귀할 때 실행합니다.

```bash
git switch deploy
```

애플리케이션 롤백은 Cloud SQL 스키마를 자동으로 되돌리지 않습니다. 파괴적 DB 변경은 반드시 별도의 하위 호환 마이그레이션과 Cloud SQL 백업·PITR 복구 절차를 준비한 후 배포합니다.

## 17. 운영 확인과 장애 점검

```bash
docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  ps

docker compose \
  --env-file .env.prod \
  --env-file /run/centagging/secrets.env \
  -f docker-compose.prod.yml \
  logs --since=30m

docker stats --no-stream
df -h
mount | grep centagging-gcs
```

점검 순서:

1. `cloud-sql-proxy`가 healthy인지 확인합니다.
2. API 로그에서 DB 인증·스키마 오류를 확인합니다.
3. GCS FUSE 마운트와 `uploads`, `sku-images` 접근 권한을 확인합니다.
4. Frontend의 `/health`가 API까지 정상 전달되는지 확인합니다.
5. Gemini 호출 오류와 API 키 제한을 확인합니다.

VM 시스템 로그와 지표를 Cloud Logging·Monitoring으로 수집하려면 Ops Agent를 설치합니다.

## 18. 다음 자동화 단계

수동 배포와 롤백이 검증된 후 GitHub Actions를 추가합니다.

1. `deploy` 브랜치 Commit SHA로 API·Frontend 이미지를 빌드합니다.
2. Artifact Registry에 불변 태그로 Push합니다.
3. Workload Identity Federation으로 GCP에 인증합니다.
4. IAP SSH를 통해 VM에서 이미지를 Pull합니다.
5. Compose 재기동 후 `/health` Smoke Test를 수행합니다.
6. 실패하면 이전 Commit SHA 이미지로 롤백합니다.

첫 번째 GitHub Actions 버전은 `workflow_dispatch` 수동 실행만 허용합니다. 수동 실행이 안정화된 후 `deploy` 브랜치 Push 자동 실행을 추가합니다.

## 참고 문서

- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Compute Engine에서 Cloud SQL 연결](https://cloud.google.com/sql/docs/postgres/connect-compute-engine)
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy)
- [Cloud SQL Private IP 구성](https://cloud.google.com/sql/docs/postgres/configure-private-ip)
- [Cloud Storage FUSE 설치](https://cloud.google.com/storage/docs/cloud-storage-fuse/install)
- [Cloud Storage FUSE 마운트](https://cloud.google.com/storage/docs/cloud-storage-fuse/mount-bucket)
- [Artifact Registry Docker 인증](https://cloud.google.com/artifact-registry/docs/docker/authentication)
- [IAP TCP Forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
- [Ops Agent 설치](https://cloud.google.com/monitoring/agent/ops-agent/installation)
