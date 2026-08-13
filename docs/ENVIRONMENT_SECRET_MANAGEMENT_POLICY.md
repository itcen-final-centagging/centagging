# CenTagging 환경 및 시크릿 관리 정책

## 1. 목적

본 문서는 CenTagging 프로젝트에서 사용하는 환경 변수와 시크릿의 분류, 저장, 주입, 접근 권한, 점검 및 유출 대응 기준을 정의한다.

실제 시크릿 값은 Git 저장소, Jira, Confluence, 로그, 오류 메시지 및 협업 도구에 기록하지 않는다.

## 2. 적용 범위와 운영 구조

본 정책은 다음 환경에 적용한다.

- `local`: 개발자 PC와 개발용 Docker Compose 실행 환경
- `deploy/prod`: GCP Compute Engine과 운영용 Docker Compose 실행 환경

현재 운영 구조는 다음을 기준으로 한다.

- Compute Engine VM에서 Nginx/Frontend, FastAPI 및 Cloud SQL Auth Proxy 컨테이너를 실행한다.
- Cloud SQL for PostgreSQL과 `pgvector`를 운영 데이터베이스로 사용한다.
- Cloud Storage 버킷을 VM에 Cloud Storage FUSE로 마운트해 이미지 저장 경로로 사용한다.
- 운영 시크릿의 원본은 GCP Secret Manager에 저장한다.
- GitHub Actions는 Workload Identity Federation으로 GCP에 인증한다.
- Pub/Sub과 비동기 Worker의 세부 권한은 비동기 리팩토링이 병합된 후 추가한다.

구체적인 생성·배포·검증·롤백 절차는 [GCP_VM_DEPLOYMENT.md](./GCP_VM_DEPLOYMENT.md)를 따른다.

## 3. 기본 원칙

1. 애플리케이션 설정과 시크릿을 구분한다.
2. 시크릿의 원본은 실행 환경 외부의 승인된 저장소에서 관리한다.
3. 저장소에는 변수명과 작동하지 않는 예시값만 유지한다.
4. 런타임과 배포 주체에는 필요한 최소한의 권한만 부여한다.
5. 시크릿을 로그, 오류 응답, 문서 또는 협업 도구에 노출하지 않는다.
6. 장기간 유효한 서비스 계정 JSON Key는 생성하거나 배포에 사용하지 않는다.
7. 노출이 의심되면 값 삭제보다 시크릿 폐기와 교체를 우선한다.

## 4. 환경별 관리 기준

| 환경          | 일반 설정                         | 시크릿                                  | 관리 기준 |
| ------------- | --------------------------------- | --------------------------------------- | --------- |
| `local`       | `.env`                            | `.env`                                  | Git에서 제외하고 개발자 PC에서만 관리한다. |
| Git 저장소    | `.env.example`, `.env.prod.example` | 저장 금지                               | 변수명, 설명 및 작동하지 않는 예시값만 유지한다. |
| `deploy/prod` | 권한을 `600`으로 제한한 `.env.prod` | Secret Manager와 `/run/centagging/secrets.env` | `.env.prod`에는 비시크릿 설정과 Secret ID·버전만 저장한다. |
| CI/CD         | GitHub Actions Workflow           | Secret Manager                          | WIF로 인증하며 서비스 계정 Key를 저장하지 않는다. |

### 4.1 로컬 환경

- 개발자는 `.env.example`을 복사해 `.env`를 생성한다.
- 실제 API Key, 비밀번호 및 로그인 정보는 `.env`에만 입력한다.
- `.env`, `.env.*`, `.streamlit/secrets.toml`은 Git 추적에서 제외한다.
- `.gitignore`에 등록되어 있어도 이미 추적된 파일은 자동으로 제외되지 않으므로 별도로 확인한다.
- 팀원 간 실제 시크릿을 메신저, Jira 또는 문서로 전달하지 않는다.

### 4.2 운영 환경

- `.env.prod`에는 프로젝트 ID, 리전, 이미지 주소, Secret ID와 Secret 버전 등 비시크릿 설정만 저장한다.
- `GEMINI_API_KEY`, `POSTGRES_PASSWORD`, `MVP_LOGIN_ID`, `MVP_LOGIN_PASSWORD`의 실제 값은 Secret Manager에 저장한다.
- 배포 직전에 VM 서비스 계정으로 지정된 Secret 버전을 조회해 `/run/centagging/secrets.env`를 생성한다.
- `/run/centagging/secrets.env`는 메모리 기반 경로에 권한 `600`으로 생성하며 Git 저장소 아래에 두지 않는다.
- Docker Compose에는 `.env.prod`를 먼저, `/run/centagging/secrets.env`를 나중에 전달해 시크릿 값이 빈 예시값을 덮어쓰게 한다.
- VM 재부팅이나 Secret 버전 변경 후에는 임시 시크릿 파일을 다시 생성한 뒤 컨테이너를 재생성한다.
- `docker compose config`는 해석된 시크릿을 출력할 수 있으므로 운영에서는 `config --quiet`만 사용한다.
- 컨테이너 환경 변수는 Docker 관리자에게 노출될 수 있으므로 Docker 그룹과 VM 관리자 권한을 최소 인원으로 제한한다.

## 5. 환경 변수 분류

현재 `.env.example`, `.env.prod.example`, `docker-compose.yml` 및 `docker-compose.prod.yml`을 기준으로 분류한다.

| 환경 변수 | 분류 | 설명 | local | deploy/prod |
| --------- | ---- | ---- | ----- | ----------- |
| `APP_ENV` | 일반 설정 | 실행 환경 구분 | `.env` | 운영 Compose에서 `prod` 고정 |
| `API_HOST`, `API_PORT` | 일반 설정 | API 내부 바인딩 | `.env` | 운영 Compose 내부값 고정 |
| `FRONTEND_PORT` | 일반 설정 | 개발용 Frontend 포트 | `.env` | 사용하지 않음 |
| `PUBLIC_HTTP_PORT` | 일반 설정 | VM 외부 공개 HTTP 포트 | 사용하지 않음 | `.env.prod` |
| `API_IMAGE`, `FRONTEND_IMAGE` | 일반 설정 | 배포 이미지 주소와 태그 | 사용하지 않음 | `.env.prod` |
| `GCP_PROJECT_ID`, `GCP_REGION` | 일반 설정 | GCP 프로젝트와 리전 | 필요 시 `.env` | `.env.prod` |
| `GCS_BUCKET_NAME`, `GCS_MOUNT_ROOT` | 일반 설정 | GCS 버킷과 VM 마운트 경로 | 로컬 경로 사용 | `.env.prod` |
| `CLOUD_SQL_INSTANCE_CONNECTION_NAME` | 민감 설정 | Cloud SQL 인스턴스 식별자 | 사용하지 않음 | `.env.prod` |
| `CLOUD_SQL_PROXY_IMAGE` | 일반 설정 | 고정된 Proxy 이미지 | 사용하지 않음 | `.env.prod` |
| `POSTGRES_DB`, `POSTGRES_USER` | 일반 설정 | DB 이름과 사용자 식별자 | `.env` | `.env.prod` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | 일반 설정 | DB 내부 연결 주소 | `.env` | 운영 Compose 내부값 고정 |
| `GEMINI_VLM_MODEL` | 일반 설정 | Gemini VLM 모델명 | `.env` | `.env.prod` |
| `GEMINI_EMBEDDING_MODEL` | 일반 설정 | Gemini 임베딩 모델명 | `.env` | `.env.prod` |
| `IMAGE_STORAGE_ROOT`, `SKU_IMAGE_ROOT` | 일반 설정 | 컨테이너 내부 이미지 경로 | `.env` | `.env.prod` |
| `GEMINI_API_KEY` | **시크릿** | Gemini API 인증 키 | `.env` | Secret Manager |
| `POSTGRES_PASSWORD` | **시크릿** | PostgreSQL 비밀번호 | `.env` | Secret Manager |
| `MVP_LOGIN_PASSWORD` | **시크릿** | MVP 고정 계정 비밀번호 | `.env` | Secret Manager |
| `MVP_LOGIN_ID` | **민감 설정** | MVP 고정 계정 ID | `.env` | Secret Manager |
| `VERTEX_API_KEY` | **시크릿** | 카탈로그 VLM 보조 도구용 키 | `.env` | 배치 도입 시 별도 Secret 검토 |
| `*_SECRET_ID`, `*_SECRET_VERSION` | 일반 설정 | Secret 리소스와 고정 버전 | 사용하지 않음 | `.env.prod` |

새 환경 변수를 추가할 때는 다음을 함께 변경한다.

1. 해당 환경의 예제 파일에 변수명, 설명 및 안전한 예시값을 추가한다.
2. 본 문서의 분류표를 갱신한다.
3. 필요한 컨테이너에만 변수를 주입한다.
4. 시크릿이라면 Secret Manager 리소스와 IAM 정책을 반영한다.
5. 배포 가이드와 자동화 명령의 환경 파일 전달 순서를 확인한다.

## 6. 저장소 관리 정책

### 6.1 환경변수 예제 파일

- `.env.example`은 로컬 개발 환경의 변수명과 용도를 정의한다.
- `.env.prod.example`은 운영 비시크릿 설정과 Secret Manager 참조 형식을 정의한다.
- 런타임 시크릿 변수는 이름만 유지하고 값은 비워둔다.
- 실제 API Key, 비밀번호, 토큰, 인증서, 개인키 및 운영 접속 문자열을 작성하지 않는다.
- 실제 시크릿처럼 오인될 수 있는 현실적인 예시값도 사용하지 않는다.

### 6.2 금지 대상

다음 위치에는 실제 시크릿을 기록하지 않는다.

- Git tracked 파일과 Git 커밋 이력
- `.env.example`, `.env.prod.example`
- README 및 `docs` 문서
- Jira 이슈, 댓글 및 첨부파일
- Confluence 문서
- Pull Request 설명과 리뷰 댓글
- 브랜치명과 커밋 메시지
- 애플리케이션과 GitHub Actions 로그
- 클라이언트에 전달되는 API 응답
- Docker 이미지와 Dockerfile

## 7. GCP Secret Manager 정책

### 7.1 시크릿 이름과 매핑

운영 시크릿은 다음 형식을 사용한다.

```text
centagging-{environment}-{purpose}
```

| Secret Manager 시크릿 | 애플리케이션 환경 변수 |
| --------------------- | ---------------------- |
| `centagging-prod-gemini-api-key` | `GEMINI_API_KEY` |
| `centagging-prod-postgres-password` | `POSTGRES_PASSWORD` |
| `centagging-prod-login-id` | `MVP_LOGIN_ID` |
| `centagging-prod-login-password` | `MVP_LOGIN_PASSWORD` |

이 이름은 리소스 식별자이며 실제 값을 포함하지 않는다.

### 7.2 버전과 수명 주기

- 배포 재현성을 위해 `.env.prod`에는 `latest` 대신 승인된 숫자 버전을 기록한다.
- 시크릿은 기존 값을 덮어쓰지 않고 새 버전을 추가하는 방식으로 교체한다.
- 새 버전 배포와 Smoke Test가 성공한 후 이전 버전을 비활성화한다.
- 담당자 변경, 외부 노출 의심, 권한 오부여 또는 공급자 권고가 있으면 즉시 회전한다.
- 시크릿 생성, 변경, 버전 활성화 및 폐기는 승인된 담당자만 수행한다.

## 8. 서비스 계정과 최소 권한

### 8.1 VM 런타임 서비스 계정

단일 Compute Engine VM에서는 VM에 연결된 서비스 계정이 IAM 신뢰 경계다. 일반 Docker Compose는 컨테이너별 GCP 서비스 계정을 제공하지 않으므로 컨테이너를 독립된 IAM 경계로 간주하지 않는다.

VM 런타임 서비스 계정에는 필요한 범위에서 다음 역할만 부여한다.

- `roles/cloudsql.client`
- 대상 GCS 버킷의 `roles/storage.objectUser`
- 대상 Secret 각각의 `roles/secretmanager.secretAccessor`
- Artifact Registry의 `roles/artifactregistry.reader`
- `roles/logging.logWriter`
- `roles/monitoring.metricWriter`

`Owner`, `Editor`, 프로젝트 전체 Storage Admin 및 프로젝트 전체 Secret Accessor 역할은 부여하지 않는다.

Nginx/Frontend 컨테이너에는 애플리케이션 시크릿 환경 변수를 전달하지 않는다. FastAPI 컨테이너에만 현재 동작에 필요한 시크릿 값을 전달한다.

### 8.2 배포 주체

- GitHub Actions 배포 주체와 VM 런타임 서비스 계정을 분리한다.
- 배포 주체는 Workload Identity Federation으로 단기 인증한다.
- 배포 주체에는 Artifact Registry Push와 승인된 VM 배포 실행에 필요한 권한만 부여한다.
- 배포 주체에는 원칙적으로 Secret 값 직접 조회 권한을 부여하지 않는다.
- VM 내부의 승인된 배포 명령이 VM 서비스 계정으로 Secret을 조회하도록 구성한다.

## 9. 서비스 간 통신 원칙

- 브라우저는 VM의 Nginx 공개 포트에만 접근한다.
- Nginx는 Docker 내부 네트워크를 통해 FastAPI를 호출한다.
- FastAPI는 Docker 내부의 Cloud SQL Auth Proxy를 통해 Cloud SQL에 접속한다.
- Cloud SQL은 Private IP만 사용하며 VM과 동일한 VPC에서 접근한다.
- GCS 버킷은 공개하지 않고 VM 서비스 계정과 Cloud Storage FUSE로 접근한다.
- FastAPI만 Gemini API 호출과 업무 처리를 담당한다.
- DB `5432`와 API `8000` 포트는 VM 외부에 공개하지 않는다.
- Pub/Sub 도입 시 Worker는 Pull Subscription을 사용하고 필요한 Topic·Subscription 권한만 추가한다.

## 10. 로그 및 오류 처리

- 환경 변수 전체, 설정 객체 전체 및 Secret Manager 응답을 로그에 출력하지 않는다.
- `Authorization`, Cookie, API Key, 비밀번호 및 DB 접속 문자열을 로그에 출력하지 않는다.
- DB URL을 기록해야 한다면 사용자명과 비밀번호를 제거한다.
- 외부 API 오류 응답에 요청 헤더나 인증정보가 포함되지 않도록 필터링한다.
- 사용자에게는 일반화된 오류 메시지를 반환하고 상세 원인은 내부 로그에 기록하되 시크릿은 마스킹한다.
- 마스킹 대상 키에는 최소한 `password`, `secret`, `token`, `api_key`, `authorization`, `cookie`를 포함한다.
- `/run/centagging/secrets.env`의 내용과 해석된 Compose 설정을 출력하지 않는다.

## 11. GitHub Actions 정책

- 장기간 유효한 GCP 서비스 계정 JSON Key를 GitHub Secrets에 저장하지 않는다.
- GitHub OIDC와 GCP Workload Identity Federation을 사용한다.
- 신뢰 범위는 승인된 GitHub 조직, 저장소와 `deploy` 브랜치 또는 승인된 Environment로 제한한다.
- 첫 배포 Workflow는 `workflow_dispatch` 수동 실행만 허용한다.
- 배포가 검증된 후 `deploy` 브랜치 Push 자동 실행을 추가한다.
- 이미지는 Commit SHA 불변 태그로 Artifact Registry에 Push한다.
- GitHub Actions 로그에 Secret 값, 액세스 토큰 및 해석된 환경 설정이 출력되지 않도록 검토한다.

## 12. 검증 절차

### 12.1 저장소 점검

```powershell
# 실제 환경 파일이 ignore 규칙을 적용받는지 확인한다.
git check-ignore -v .env .env.prod

# 출력이 없어야 한다.
git ls-files .env .env.prod

# 대표적인 Google API Key와 개인키 형식을 검사한다.
git grep -n -I -E '(AIza[0-9A-Za-z_-]{30,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)'
```

자동 검사는 모든 시크릿을 발견하지 못하므로 예제 파일, 문서, Compose 설정과 커밋 변경분을 수동으로 함께 검토한다.

### 12.2 VM 점검

```bash
stat -c '%a %n' \
  /opt/centagging/.env.prod \
  /run/centagging/secrets.env

docker compose \
  --env-file /opt/centagging/.env.prod \
  --env-file /run/centagging/secrets.env \
  -f /opt/centagging/docker-compose.prod.yml \
  config --quiet
```

두 환경 파일의 권한은 `600`이어야 한다. 시크릿 파일의 내용은 확인 명령의 출력에 포함하지 않는다.

PR 검토 시 다음 항목을 확인한다.

- 예제 파일에는 실제 시크릿이 아닌 빈 값과 안전한 예시값만 있는가?
- Docker 이미지, Compose, Workflow 및 문서에 실제 시크릿이 없는가?
- Secret 조회 권한이 개별 Secret 리소스로 제한됐는가?
- API와 DB 포트가 외부에 공개되지 않았는가?
- 로그와 오류 응답에 시크릿이 출력되지 않는가?
- GitHub Secret scanning과 Push protection을 활성화할 수 있는가?

## 13. 시크릿 유출 대응

시크릿 노출 또는 노출 의심이 발생하면 다음 순서로 대응한다.

1. 노출된 Secret 버전 또는 API Key를 즉시 비활성화한다.
2. 새로운 Secret 버전이나 인증 값을 발급한다.
3. `.env.prod`의 승인 버전 번호를 갱신한다.
4. VM의 임시 시크릿 파일을 다시 생성하고 컨테이너를 재배포한다.
5. 정상 동작과 이전 버전 미사용을 확인한다.
6. Secret Manager Audit Log, GCP Audit Log 및 공급자 로그에서 비정상 사용 여부를 확인한다.
7. Git, 로그, Jira, Confluence와 첨부파일의 노출 범위를 조사한다.
8. 원인과 재발 방지 조치를 기록하되 유출된 값 자체는 기록하지 않는다.

Git 커밋이나 문서에서 값을 삭제하는 것만으로 대응을 종료하지 않는다. 이미 노출된 시크릿은 사용된 것으로 간주하고 반드시 교체한다.

## 14. 문서 변경 관리

운영 구조, 환경 변수, Secret 이름, 서비스 계정 또는 배포 방식이 바뀌면 다음 파일을 같은 변경 단위에서 검토한다.

- `.env.example`
- `.env.prod.example`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `docs/ENVIRONMENT_SECRET_MANAGEMENT_POLICY.md`
- `docs/GCP_VM_DEPLOYMENT.md`
- 관련 GitHub Actions Workflow

## 15. 참고 자료

- [Secret Manager Secret 버전 접근](https://cloud.google.com/secret-manager/docs/access-secret-version)
- [Secret Manager IAM 접근 제어](https://cloud.google.com/secret-manager/docs/access-control)
- [Compute Engine 서비스 계정](https://cloud.google.com/compute/docs/access/service-accounts)
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy)
- [Cloud Storage FUSE 접근 권한](https://cloud.google.com/storage/docs/cloud-storage-fuse/mount-bucket)
- [배포 파이프라인용 Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Docker Compose 환경 변수](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [GitHub Push Protection](https://docs.github.com/code-security/secret-scanning/introduction/about-push-protection)
