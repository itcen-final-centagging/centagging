# CenTagging 환경 및 시크릿 관리 정책

## 1. 목적

본 문서는 CenTagging 프로젝트에서 사용하는 환경 변수와 시크릿의 분류, 저장, 주입, 접근 권한, 점검 및 유출 대응 기준을 정의한다.

실제 시크릿 값은 이 문서를 포함한 Git 저장소, Jira, Confluence, 로그 및 오류 메시지에 기록하지 않는다.

## 2. 적용 범위와 현재 전제

본 정책은 다음 환경에 적용한다.

- `local`: 개발자 PC 및 Docker Compose 기반 로컬 실행 환경
- `deploy/prod`: GCP에 배포되는 운영 환경

다음 항목은 아직 확정되지 않았으므로 이 문서에서 구현 구조를 단정하지 않는다.

- GCP 서비스 배치 구조
- Cloud Run 서비스 간 통신 및 인증 경로
- 운영 DB의 배포 방식과 네트워크 경로
- 운영 시크릿의 구체적인 주입 방식(환경 변수 또는 파일 마운트),“환경 변수 주입 우선 검토, 최종 확정은 아키텍처 결정 후”
- GitHub Actions 기반 CI/CD 도입 여부와 구성

위 항목이 확정되면 본 정책의 보안 원칙을 유지하면서 관련 절을 갱신한다.

## 3. 기본 원칙

1. 애플리케이션 설정과 시크릿을 구분한다.
2. 시크릿 값은 실행 환경 외부의 승인된 저장소에서 관리한다.
3. 저장소에는 변수명과 작동하지 않는 예시값만 유지한다.
4. 서비스에는 동작에 필요한 최소한의 시크릿과 권한만 부여한다.
5. 시크릿을 로그, 오류 응답, 문서 또는 협업 도구에 노출하지 않는다.
6. 노출이 의심되면 값 삭제보다 시크릿 폐기와 교체를 우선한다.

## 4. 환경별 관리 기준

| 환경          | 일반 설정                | 시크릿                        | 관리 기준                                                |
| ------------- | ------------------------ | ----------------------------- | -------------------------------------------------------- |
| `local`       | `.env`                   | `.env`                        | `.gitignore`로 제외하고 개발자 PC에서만 관리한다.        |
| Git 저장소    | `.env.example`           | 저장 금지                     | 변수명, 설명 및 작동하지 않는 예시값만 유지한다.         |
| `deploy/prod` | Cloud Run 일반 환경 변수 | GCP Secret Manager            | 런타임 서비스 계정에 필요한 시크릿 조회 권한만 부여한다. |
| CI/CD         | GitHub Actions 설정      | WIF 또는 승인된 시크릿 저장소 | 도입 시 별도 상세 설계를 작성한다.                       |

### 4.1 로컬 환경

- 개발자는 `.env.example`을 복사해 `.env`를 생성한다.
- 실제 API Key, 비밀번호 및 로그인 정보는 `.env`에만 입력한다.
- `.env`, `.env.*`, `.streamlit/secrets.toml`은 Git 추적에서 제외한다.
- `.gitignore`에 등록되어 있어도 이미 추적된 파일은 자동으로 제외되지 않으므로 별도로 확인한다.
- 팀원 간 실제 시크릿을 메신저, Jira 또는 문서로 전달하지 않는다.

### 4.2 운영 환경

- 일반 설정은 Cloud Run의 일반 환경 변수로 관리한다.
- `GEMINI_API_KEY`, DB 비밀번호와 같은 시크릿은 GCP Secret Manager에 저장한다.
- Cloud Run 설정, 컨테이너 이미지, 배포 스크립트에 시크릿 값을 직접 작성하지 않는다.
- Secret Manager의 시크릿을 환경 변수로 주입할 경우 재현 가능한 배포를 위해 특정 버전 참조를 우선한다.
- 시크릿 회전 방식과 무중단 반영이 중요해지면 파일 마운트 방식을 포함해 재검토한다.

## 5. 환경 변수 분류

현재 `.env.example`과 `docker-compose.yml`을 기준으로 분류한다.

| 환경 변수                | 분류          | 설명                          | local                      | deploy/prod                              |
| ------------------------ | ------------- | ----------------------------- | -------------------------- | ---------------------------------------- |
| `APP_ENV`                | 일반 설정     | 실행 환경 구분                | `.env`                     | Cloud Run 환경 변수                      |
| `API_HOST`               | 일반 설정     | API 바인딩 호스트             | `.env`                     | 배포 구조 확정 후 결정                   |
| `API_PORT`               | 일반 설정     | API 포트                      | `.env`                     | Cloud Run 런타임 기준 적용               |
| `FRONTEND_PORT`          | 일반 설정     | React/Nginx 포트              | `.env`                     | Cloud Run 런타임 기준 적용               |
| `VITE_API_BASE_URL`      | 일반 설정     | React에서 호출할 API 주소     | 빌드 환경 또는 `.env`      | 미설정 시 동일 출처 프록시 사용          |
| `GEMINI_VLM_MODEL`       | 일반 설정     | Gemini VLM 모델명             | `.env`                     | Cloud Run 환경 변수                      |
| `GEMINI_EMBEDDING_MODEL` | 일반 설정     | Gemini 임베딩 모델명          | `.env`                     | Cloud Run 환경 변수                      |
| `POSTGRES_DB`            | 일반 설정     | DB 이름                       | `.env`                     | Cloud Run 환경 변수                      |
| `POSTGRES_USER`          | 일반 설정     | DB 사용자 식별자              | `.env`                     | Cloud Run 환경 변수                      |
| `POSTGRES_HOST`          | 일반 설정     | DB 호스트                     | `.env`                     | 운영 DB 구조 확정 후 결정                |
| `POSTGRES_PORT`          | 일반 설정     | DB 포트                       | `.env`                     | 운영 DB 구조 확정 후 결정                |
| `GEMINI_API_KEY`         | **시크릿**    | Gemini API 인증 키            | `.env`                     | Secret Manager                           |
| `POSTGRES_PASSWORD`      | **시크릿**    | DB 비밀번호                   | `.env`                     | Secret Manager                           |
| `LOGIN_PASSWORD`         | **시크릿**    | MVP 고정 계정 비밀번호        | `.env`                     | Secret Manager                           |
| `LOGIN_ID`               | **민감 설정** | MVP 고정 계정 ID              | `.env`                     | 비밀번호와 함께 Secret Manager 관리 권장 |

`API_BASE_URL`은 환경에 따라 달라지는 팀 공통 설정이므로, Docker Compose의 고정값을 환경 변수로 전환할 때 `.env.example`에도 추가한다.

새 환경 변수를 추가할 때는 다음을 함께 변경한다.

1. `.env.example`에 변수명, 설명 및 안전한 예시값 추가
2. 본 문서의 분류표 갱신
3. 필요한 서비스에만 변수 주입
4. 시크릿이라면 Secret Manager와 IAM 정책 반영

## 6. 저장소 관리 정책

### 6.1 `.env.example`

- 팀 공통 변수의 이름과 용도를 정의하는 템플릿이다.
- 실제 환경에서 동작하지 않는 placeholder 또는 공개 가능한 기본값만 작성한다.
- 실제 API Key, 비밀번호, 토큰, 인증서, 개인키 및 운영 접속 문자열을 작성하지 않는다.
- 실제 시크릿처럼 오인될 수 있는 현실적인 예시값도 사용하지 않는다.

### 6.2 금지 대상

다음 위치에는 실제 시크릿을 기록하지 않는다.

- Git tracked 파일과 Git 커밋 이력
- `.env.example`
- README 및 `docs` 문서
- Jira 이슈, 댓글 및 첨부파일
- Confluence 문서
- Pull Request 설명과 리뷰 댓글
- 브랜치명과 커밋 메시지
- 애플리케이션 로그와 오류 메시지
- 클라이언트에 전달되는 API 응답

## 7. GCP Secret Manager 정책

### 7.1 시크릿 이름

운영 시크릿은 다음 형식을 권장한다.

```text
centagging-{environment}-{purpose}
```

예시는 이름 규칙을 설명하기 위한 것이며 실제 값을 포함하지 않는다.

```text
centagging-prod-gemini-api-key
centagging-prod-postgres-password
centagging-prod-login-password
```

애플리케이션에는 기존 환경 변수명으로 매핑한다.

| Secret Manager 시크릿      | 애플리케이션 환경 변수 |
| -------------------------- | ---------------------- |
| Gemini API Key 시크릿      | `GEMINI_API_KEY`       |
| PostgreSQL 비밀번호 시크릿 | `POSTGRES_PASSWORD`    |
| MVP 로그인 비밀번호 시크릿 | `LOGIN_PASSWORD`       |

### 7.2 수명 주기

- 시크릿 생성, 변경 및 폐기는 승인된 담당자만 수행한다.
- 시크릿은 버전을 추가하는 방식으로 교체한다.
- 더 이상 사용하지 않는 버전은 배포 반영 확인 후 비활성화 또는 폐기한다.
- 담당자 변경, 외부 노출 의심, 권한 오부여 또는 공급자 권고가 있으면 즉시 회전한다.
- 운영 절차 확정 시 시크릿별 담당자와 정기 회전 주기를 추가한다.

## 8. 서비스 계정과 최소 권한

- Cloud Run 런타임 서비스 계정과 배포용 계정을 분리한다.
- 가능하면 서비스별 런타임 서비스 계정을 사용한다.
- FastAPI 서비스에는 Gemini와 DB 등 실제로 사용하는 시크릿만 허용한다.
- React/Nginx 서비스에는 API 연결에 필요한 일반 설정만 제공하며 Gemini 및 DB 시크릿을 직접 제공하지 않는다.
- 배치 서비스가 도입되면 해당 배치가 사용하는 시크릿에만 접근하게 한다.
- 런타임 서비스 계정에는 `Owner`, `Editor` 등 광범위한 역할을 부여하지 않는다.
- Secret Manager 조회 권한은 가능한 한 프로젝트 전체가 아닌 개별 시크릿 리소스에 부여한다.
- 시크릿을 사용하는 서비스 계정에는 필요한 시크릿에 대한 `roles/secretmanager.secretAccessor`만 부여한다.
- 배포 권한이 Secret 조회 권한을 자동으로 의미하지 않도록 역할을 분리한다.

### 8.1 권장 접근 범위

| 주체                         | 허용 대상                                                             |
| ---------------------------- | --------------------------------------------------------------------- |
| React/Nginx 런타임 서비스 계정 | 일반 설정 및 FastAPI 호출에 필요한 구성                            |
| FastAPI 런타임 서비스 계정   | Gemini, DB 및 서버 로그인 처리에 필요한 시크릿                        |
| SKU 임베딩 배치 서비스 계정  | Gemini와 DB 중 배치 실행에 필요한 시크릿                              |
| 배포 주체                    | 배포에 필요한 최소 권한. 런타임 시크릿 값 직접 조회는 원칙적으로 금지 |
| 일반 사용자 브라우저         | 시크릿 접근 금지                                                      |

서비스 배치 구조가 확정되면 실제 서비스 계정명과 시크릿별 IAM 매핑표를 추가한다.

## 9. 서비스 간 통신 원칙

구체적인 GCP 통신 경로는 미확정이지만 다음 경계를 적용한다.

- 브라우저 또는 React/Nginx는 DB와 Secret Manager에 직접 접근하지 않는다.
- FastAPI가 Gemini 호출, DB 접근 및 업무 처리를 담당한다.
- 서비스 간 호출은 HTTPS와 GCP에서 승인한 인증 방식을 사용한다.
- 공개 접근, 내부 접근, Cloud Run 인증 및 네트워크 경로는 배포 아키텍처 확정 후 문서화한다.

## 10. 로그 및 오류 처리

- 환경 변수 전체 또는 설정 객체 전체를 로그에 출력하지 않는다.
- `Authorization`, Cookie, API Key, 비밀번호 및 DB 접속 문자열을 로그에 출력하지 않는다.
- DB URL을 기록해야 한다면 사용자명과 비밀번호를 제거한다.
- 외부 API 오류 응답에 요청 헤더나 인증정보가 포함되지 않도록 필터링한다.
- 사용자에게는 일반화된 오류 메시지를 반환하고 상세 원인은 내부 로그에 기록하되 시크릿은 마스킹한다.
- 마스킹 대상 키에는 최소한 `password`, `secret`, `token`, `api_key`, `authorization`, `cookie`를 포함한다.

## 11. GitHub Actions 도입 시 정책

CI/CD 구축은 현재 최하위 우선순위로 두며, 도입 시 다음 원칙을 적용한다.

- 장기간 유효한 GCP 서비스 계정 JSON Key 사용을 지양한다.
- GitHub OIDC와 GCP Workload Identity Federation 사용을 우선 검토한다.
- 신뢰 범위는 승인된 GitHub 조직, 저장소 및 필요한 브랜치 또는 환경으로 제한한다.
- 배포 주체와 Cloud Run 런타임 서비스 계정을 분리한다.
- GitHub Actions 로그에 시크릿이 출력되지 않도록 명령어와 디버그 설정을 검토한다.

## 12. 검증 절차

정책 문서 작성만으로 시크릿 미포함이 증명되지는 않는다. PR 생성 전 다음 검사를 수행하고 결과를 기록한다.

### 12.1 로컬 점검

```powershell
# .env가 ignore 규칙의 적용을 받는지 확인한다.
git check-ignore -v .env

# 출력이 없어야 한다.
git ls-files .env

# 대표적인 Google API Key와 개인키 형식이 tracked 파일에 없는지 확인한다.
git grep -n -I -E '(AIza[0-9A-Za-z_-]{30,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)'
```

자동 검사는 모든 종류의 시크릿을 발견하지 못하므로 `.env.example`, 문서, 설정 파일 및 커밋 변경분을 수동으로 함께 검토한다.

### 12.2 ※ 시크릿 점검 기준

PR 검토 시 다음 항목을 확인한다.

- `.env`가 Git에서 추적되지 않는지 확인한다.
- `.env.example`에는 실제 시크릿이 아닌 예시값만 사용한다.
- 변경된 코드와 문서에 API Key, 비밀번호 및 토큰이 없는지 확인한다.
- 로그와 오류 응답에 시크릿이 출력되지 않도록 검토한다.
- Jira와 Confluence에는 실제 시크릿을 기록하지 않는다.
- 가능하면 GitHub Secret scanning과 Push protection을 활성화한다.

GitHub 저장소 기능과 요금제가 지원하는 경우 Secret scanning과 Push protection을 활성화한다.

## 13. 시크릿 유출 대응

시크릿 노출 또는 노출 의심이 발생하면 다음 순서로 대응한다.

1. 노출된 시크릿을 즉시 폐기하거나 비활성화한다.
2. 새로운 시크릿 또는 버전을 발급한다.
3. 서비스가 새 버전을 사용하도록 반영하고 정상 동작을 확인한다.
4. Secret Manager 및 GCP Audit Log 등에서 비정상 사용 여부를 확인한다.
5. Git, 로그, Jira, Confluence 및 첨부파일의 노출 범위를 조사한다.
6. 필요한 경우 Git 이력과 캐시에서 노출 내용을 제거한다.
7. 원인과 재발 방지 조치를 기록하되 유출된 값 자체는 기록하지 않는다.

Git 커밋이나 문서에서 값을 삭제하는 것만으로 대응을 종료하지 않는다. 이미 노출된 시크릿은 사용된 것으로 간주하고 반드시 교체한다.

## 15. 참고 자료

- [Cloud Run에서 Secret Manager 시크릿 구성](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Secret Manager IAM 접근 제어](https://cloud.google.com/secret-manager/docs/access-control)
- [배포 파이프라인용 Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [GitHub Push Protection](https://docs.github.com/code-security/secret-scanning/introduction/about-push-protection)
