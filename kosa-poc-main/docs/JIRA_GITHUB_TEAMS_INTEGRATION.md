# Jira · GitHub · Teams 연동 가이드

> 개발 이력 추적과 알림을 위해 **Jira 이슈 ↔ GitHub 브랜치/커밋/PR ↔ Teams 알림**을
> 연동하는 방식과 설정 절차를 정리한 문서.

## 1. 목표

1. **Jira 티켓에 GitHub 리비전(커밋 SHA/PR)이 자동으로 남게 한다.**
   - 상세 기술 설명·논의는 **Jira 이슈**에 작성, GitHub에는 이슈 키 + 요약만.
2. **GitHub push/merge 시 Teams 채널에 봇 알림이 자동 전송되게 한다.**
   - (Slack의 GitHub 알림과 동일한 경험을 Teams에서 구현)
3. Jira 연동이 부담되는 경우, **Merge 시 개발 이력을 자동 메시지로 남기는 대안**도 제공.

## 2. 핵심 원칙 — "이슈 키는 브랜치로, 제목은 깔끔하게"

GitHub for Jira는 **브랜치명에 이슈 키가 있으면** 그 브랜치의 커밋·PR을 자동으로 엮는다.
따라서 이슈 키를 커밋/PR **제목에 넣을 필요가 없다.** 제목은 Conventional Commits로 깔끔하게 두고,
이슈 키는 **브랜치명에만** 남긴다.

| 위치 | 규약 | 예시 |
| --- | --- | --- |
| 브랜치명 | `<branch-type>/<ISSUE-KEY>-<short-title>` | `feature/PROJ-123-project-acl` |
| 커밋 제목 | `<type>: <요약>` (키 없음) | `feat: ProjectMembers ACL 추가` |
| PR 제목 | `<type>: <제목>` (키 없음) | `feat: 프로젝트 권한 ACL` |

> 이슈 키가 필요한 곳은 **브랜치명 하나**다(자동 링크 보장). PR 본문에 Jira 링크를 함께 남기면 추적이 더 명확하다.

### 2-1. 브랜치 타입

| 타입 | 용도 | 예시 |
| --- | --- | --- |
| `feature/` | 신규 기능 | `feature/PROJ-123-project-acl` |
| `fix/` | 버그 수정 | `fix/PROJ-145-login-500` |
| `refactor/` | 동작 변화 없는 구조 개선 | `refactor/PROJ-160-service-split` |
| `hotfix/` | 운영 긴급 수정 | `hotfix/PROJ-170-payment-down` |
| `docs/` / `chore/` | 문서 / 설정·잡무 | `chore/PROJ-180-ci-update` |

- 기준 브랜치: 기능/수정은 `develop`에서 분기 → PR로 병합. 긴급은 `main`에서 `hotfix/`.

### 2-2. 커밋 메시지 컨벤션 (Conventional Commits)

제목 형식: `<type>: <요약(한글, 명령형)>` — **이슈 키는 제목에 넣지 않는다.**
상세는 본문에 작성하고, 이슈 연결은 브랜치명이 담당한다. 원칙적으로 **AI 트레일러 금지**.

```
feat: 어드민 멤버 목록 API 추가

- 워크스페이스 멤버를 페이지네이션으로 반환
```

| type | 의미 | 제목 예시 |
| --- | --- | --- |
| `feat` | 신규 기능 | `feat: 어드민 멤버 목록 API 추가` |
| `fix` | 버그 수정 | `fix: 로그인 토큰 만료 처리 오류 수정` |
| `refactor` | 동작 변화 없는 리팩터 | `refactor: 권한 검증 헬퍼 분리` |
| `docs` | 문서 | `docs: 권한 정책 문서 추가` |
| `test` | 테스트 추가/수정 | `test: 접근 정책 단위 테스트 보강` |
| `chore` | 빌드·설정·잡무 | `chore: gitignore 정리` |
| `style` | 포맷/스타일(로직 무변경) | `style: import 정렬` |
| `perf` | 성능 개선 | `perf: 목록 쿼리 N+1 제거` |
| `build`/`ci` | 빌드 시스템/CI | `ci: Teams 알림 워크플로 추가` |

- **하나의 커밋 = 하나의 의미**. 서로 다른 type을 한 커밋에 섞지 않는다.
- 본문(선택): "왜/무엇을" 요약, breaking change는 `BREAKING CHANGE:` 명시.

### 2-3. PR 규약

- 제목: `<type>: <제목>` (키 없음, 작업 중이면 `[WIP]` 접두). 예: `feat: 프로젝트 권한 ACL`
- 본문 템플릿 (리뷰에 필요한 만큼 — **상세 스펙·설계는 Jira에**, PR은 "무엇을·어떻게 바꿨고 어떻게 검증했는지"):
  ```
  ## 관련 이슈
  - Jira: PROJ-123

  ## 변경 요약
  - (무엇을, 왜 바꿨는지 1~3줄)

  ## 상세 변경 내용
  - (주요 변경점 — 파일/모듈/API 단위로)

  ## 영향 범위 / 리스크
  - (호환성, DB 마이그레이션, 설정·환경 변경, Breaking change 여부)

  ## 테스트
  - [ ] 단위/통합 테스트 통과
  - [ ] 로컬/스테이징 검증 (방법·결과)

  ## 리뷰 포인트
  - (집중해서 봐야 할 부분 / 논의가 필요한 결정)

  ## 스크린샷 (UI 변경 시)
  - Before / After
  ```
- 체크리스트(머지 전): 빌드·린트 통과 / 문서·마이그레이션 반영 / Breaking change 명시.
- 필수는 **관련 이슈·변경 요약·테스트** 세 가지. 나머지는 변경 성격에 따라 생략 가능(문서 수정 등 소규모는 요약만).
- 이슈 연결은 **브랜치명 + PR 본문의 Jira 링크**로 보장된다(제목에 키 불필요).
- 병합 방식: 이력 추적을 위해 **Squash merge 권장**.

## 3. 전체 플로우

```
Jira 이슈 생성 (PROJ-123)
      │
      ▼
브랜치 feature/PROJ-123-... → 커밋 "feat: ..." → PR "feat: ..."
      │
      ├─▶ [GitHub for Jira]   커밋 SHA·브랜치·PR을 Jira 이슈 "Development" 패널에 자동 링크
      │                        (+ Smart Commit으로 코멘트/상태전이/작업시간 기록)
      │
      └─▶ [GitHub for Teams]  push / PR / merge 이벤트를 Teams 채널에 봇 알림
```

---

## 4. Jira ↔ GitHub 연동

### 4-1. GitHub for Jira 앱 (권장)
- Atlassian Marketplace의 **"GitHub for Jira"**(공식) 앱을 Jira에 설치하고 GitHub 조직을 연결한다.
- 이후 커밋/브랜치/PR 메시지에 **이슈 키만 포함**하면, 해당 Jira 이슈의 **Development 패널**에
  연결된 커밋(SHA=리비전), 브랜치, PR, 리뷰, 배포 상태가 자동으로 표시된다.
- 별도 수작업 없이 "이 티켓에 어떤 커밋이 반영됐는지"가 리비전 단위로 추적된다.

### 4-2. Smart Commits (선택 — 티켓에 명시적으로 남기기)
커밋 메시지에 지시어를 넣으면 Jira 이슈에 직접 반영된다.

| 지시어 | 기능 | 예시 |
| --- | --- | --- |
| `#comment` | 이슈에 코멘트 추가 | `PROJ-123 #comment 어드민 ACL 반영` |
| `#time` | 작업 시간 로깅 | `PROJ-123 #time 2h 30m` |
| `#<transition>` | 상태 전이 | `PROJ-123 #done` / `PROJ-123 #in-review` |

예:
```
PROJ-123 feat: ProjectMembers ACL 추가 #comment 프로젝트 단위 멤버십 도입, 리비전 abc1234 #time 3h
```
→ Jira 이슈 PROJ-123에 코멘트·작업시간이 기록되고, Development 패널에 커밋 abc1234가 링크된다.

### 4-3. 운영/개발 관점 정리
- **개발 상세는 Jira에**: 설계·의사결정·QA 노트는 Jira 이슈 본문/코멘트에 작성.
- **GitHub에는 최소 정보**: 이슈 키 + 한 줄 요약. 리비전 연결은 앱이 자동 처리.
- 릴리스 시 "이 버전에 포함된 티켓" 목록을 Jira Release(Fix Version)로 집계 가능.

### 4-4. Jira 티켓 작성 가이드 (상황·유형별)

#### 이슈 유형
| 유형 | 사용 시점 |
| --- | --- |
| **Story** | 사용자 관점 기능(가치) 단위 |
| **Task** | 기술 작업/개선(리팩터·인프라 등) |
| **Bug** | QA/운영에서 발견된 결함 |
| **Sub-task** | 위 항목을 쪼갠 실행 단위 |

#### 공통 본문 템플릿 (기능/작업 등록 시)
```
## 목적 (Why)
- 이 작업을 왜 하는가 / 기대 효과

## As-Is (현재)
- 현재 동작·문제점

## To-Be (변경 후)
- 바뀔 동작·목표 상태

## 상세 기술 내용
- 접근 방식, 주요 변경점, 영향 범위(모듈/API/DB)

## 완료 조건 (Acceptance Criteria)
- [ ] 검증 가능한 조건 1
- [ ] 검증 가능한 조건 2

## 참고
- 관련 이슈/문서 링크
```

#### 상황별 담아야 할 내용

| 상황 | 상태 전이 | 티켓에 남길 내용 |
| --- | --- | --- |
| **기능 개발 등록** | → To Do | 목적, As-Is, To-Be, 완료 조건, 영향 범위 |
| **개발 착수** | → In Progress | 담당자 지정, 접근 방식/설계 메모(필요 시) |
| **개발 완료** | → In Review | 상세 기술 내용(구현 요약), 변경 파일/API, **커밋 리비전·PR 링크**(GitHub for Jira 자동), 자체 테스트 결과 |
| **QA 이슈 등록(Bug)** | New/Open | 재현 절차, 기대 결과 vs 실제 결과, 환경(브랜치/버전/OS), 심각도·우선순위, 스크린샷/로그, 관련 원본 이슈 |
| **이슈 해결(Fix)** | → In Review | 원인(Root Cause), 조치 내용, 수정 리비전(SHA/PR), 재발 방지책, 영향 범위 |
| **검증/종료** | → Done/Closed | QA 검증 결과, 배포 버전(Fix Version), 최종 확인자 |

#### Bug 리포트 예시 (QA 등록)
```
## 재현 절차
1. 어드민 로그인 → 프로젝트 상세
2. 멤버 목록 조회

## 기대 결과
- 프로젝트 멤버만 표시(Owner 등)

## 실제 결과
- 500 에러 (trace_id: ...)

## 환경
- 브랜치/버전: feat/project-members-acl @ abc1234
- API: GET /api/v1/workspaces/{id}/admin/projects

## 심각도 / 우선순위
- Major / High

## 첨부
- 서버 로그, 스크린샷
```

#### 해결 코멘트 예시 (Fix 완료)
```
[원인] ProjectRole enum 이름/값 불일치로 조회 시 LookupError
[조치] values_callable로 소문자 값 저장·조회 통일 (PROJ-123 fix)
[리비전] 069347e (PR #42)
[재발방지] enum 값 매핑 단위 테스트 추가
```

> **원칙**: 상세 기술 서술·논의는 **Jira에**, GitHub 커밋/PR에는 **이슈 키 + 한 줄 요약**만.
> 커밋 리비전은 GitHub for Jira가 Development 패널에 자동 연결하므로 수동 복사는 최소화한다.

---

## 5. GitHub → Teams 알림

### 5-1. GitHub for Teams 앱 (권장, Slack과 동일 방식)
1. Teams 채널에 **"GitHub"** 앱 추가 → `@github signin`으로 계정 연결.
2. 채널에서 저장소 구독:
   ```
   @github subscribe <org>/<repo>
   @github subscribe <org>/<repo> commits          # push/커밋 알림
   @github subscribe <org>/<repo> pulls reviews     # PR·리뷰 알림
   @github subscribe <org>/<repo> commits:*         # 모든 브랜치 커밋(기본은 기본 브랜치)
   ```
3. 구독 해제/조정: `@github unsubscribe <org>/<repo> <feature>`

지원 이벤트: `issues`, `pulls`, `commits`, `reviews`, `comments`, `releases`, `deployments`,
`branches`, `discussions` 등. → Slack GitHub 앱과 사실상 동일.

### 5-2. 커스텀 알림 — GitHub Actions → Teams Incoming Webhook
merge 시 원하는 포맷(리비전·PR 링크·변경 요약)으로 보내고 싶을 때:

1. Teams 채널 → 커넥터 → **Incoming Webhook** 생성 → URL을 GitHub Secret `TEAMS_WEBHOOK_URL`로 저장.
2. 워크플로 예시 (`.github/workflows/notify-teams.yml`):

```yaml
name: Notify Teams on merge
on:
  pull_request:
    types: [closed]
    branches: [main, develop]
jobs:
  notify:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Post to Teams
        run: |
          curl -s -H "Content-Type: application/json" -d '{
            "text": "✅ **${{ github.event.pull_request.title }}** merged\n
                     - repo: ${{ github.repository }}\n
                     - by: ${{ github.event.pull_request.user.login }}\n
                     - PR: ${{ github.event.pull_request.html_url }}\n
                     - commit: ${{ github.event.pull_request.merge_commit_sha }}"
          }' "${{ secrets.TEAMS_WEBHOOK_URL }}"
```

> 참고: Office 365 Connector(Incoming Webhook)는 향후 Microsoft가 **Power Automate Workflows**로
> 이관을 안내 중이다. 신규 구성 시 Teams의 **Workflows(Power Automate)** "When a Teams webhook
> request is received" 트리거로 만드는 것을 권장(동일하게 URL POST 방식).

---

## 6. 부담 완화 대안 — Merge 시 개발 이력 자동 기록

Jira 앱 연동 없이도 개발 이력을 남기는 방식:

- **(A) Teams만**: 5-2의 Action으로 merge 시 리비전·PR·요약을 Teams에 자동 전송.
- **(B) Jira 코멘트 API**: merge 시 Action에서 커밋 메시지의 이슈 키를 파싱해 Jira REST API로
  해당 이슈에 "머지됨: `<sha>` (`<PR 링크>`)" 코멘트를 자동 추가.
  ```
  POST https://<your-domain>.atlassian.net/rest/api/3/issue/PROJ-123/comment
  Authorization: Basic <email:api_token>
  ```
- 개발자는 **커밋 메시지에 이슈 키만** 넣으면 되고, 리비전 기록·알림은 전부 자동화된다.

---

## 7. 사전 확인 사항 (도입 전 체크)

| 항목 | 확인 내용 |
| --- | --- |
| Jira 유형 | **Cloud** vs **Data Center/Server** — Cloud면 공식 앱이 가장 매끄러움. DC/Server는 DVCS 커넥터 또는 웹훅 방식 필요 |
| 앱 설치 권한 | Jira/Teams 테넌트 관리자 승인 필요 여부 |
| GitHub 조직 권한 | 앱이 조직 저장소에 접근하도록 조직 관리자 승인 |
| Teams 커넥터 정책 | Incoming Webhook/Workflows 사용 허용 여부(보안 정책) |
| 이슈 키 규약 | 브랜치/커밋/PR 네이밍 규칙 팀 합의 및 (선택) PR 제목 검증 Action |

## 8. 도입 체크리스트

- [ ] Jira 프로젝트 키 확정 및 브랜치/커밋/PR 네이밍 규약 공지
- [ ] GitHub for Jira 앱 설치 + GitHub 조직 연결
- [ ] Smart Commits 사용 여부 결정(코멘트/작업시간/상태전이)
- [ ] GitHub for Teams 앱 설치 + 채널 구독(`commits`, `pulls` 등)
- [ ] (선택) merge 알림 커스텀: Teams Webhook + `notify-teams.yml`
- [ ] (대안) Jira 코멘트 자동화 Action 구성
