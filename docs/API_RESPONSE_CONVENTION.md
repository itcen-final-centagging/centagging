# 공통 API 응답 규격

## 목적

JSON API의 성공·오류 응답 구조를 통일해 프런트엔드가 API별 응답 형식을
개별 처리하지 않도록 한다. 오류 코드는 동작 분기에, 오류 메시지는 사용자
안내에 사용하며, `request_id`로 응답과 서버 로그를 연결한다.

## 적용 범위

- 적용 대상: 인증, 태깅, 이력, SKU·카탈로그 JSON API
- 제외 대상: 정적 파일, 이미지·파일 다운로드, 스트리밍 응답, `204 No Content`
- HTTP 상태 코드는 기존 의미를 유지한다. 공통 응답 본문은 HTTP 상태 코드를
  대체하지 않는다.

## 성공 응답

모든 적용 대상 API는 성공 시 아래 구조를 반환한다.

```json
{
  "status": "success",
  "data": {
    "user_id": 1,
    "login_id": "user"
  },
  "meta": {
    "request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `status` | Y | 항상 `success` |
| `data` | Y | API별 실제 응답 데이터. 객체·배열·문자열·`null`을 사용할 수 있음 |
| `meta.request_id` | Y | 요청을 식별하는 UUID. 서버 로그 조회에 사용 |

목록 API의 페이지 정보는 `data`가 아닌 `meta.pagination`에 둔다.

```json
{
  "status": "success",
  "data": {
    "items": []
  },
  "meta": {
    "request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0",
    "pagination": {
      "page": 1,
      "size": 20,
      "total": 0
    }
  }
}
```

## 오류 응답

모든 적용 대상 API는 실패 시 아래 구조를 반환한다.

```json
{
  "status": "error",
  "error": {
    "code": "AUTH_SESSION_INVALID",
    "message": "인증 세션이 유효하지 않습니다.",
    "details": []
  },
  "meta": {
    "request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `status` | Y | 항상 `error` |
| `error.code` | Y | 프런트 분기와 운영 분석에 사용하는 고정 오류 코드 |
| `error.message` | Y | 사용자에게 표시 가능한 한국어 메시지 |
| `error.details` | Y | 입력 오류 상세 목록. 해당 사항이 없으면 빈 배열 |
| `meta.request_id` | Y | 요청을 식별하는 UUID |

`error.code`는 영문 대문자 스네이크 케이스를 사용한다. 프런트는
`error.message` 문구가 아닌 `error.code`로 동작을 분기한다.

## 입력 검증 오류

입력 검증 실패는 HTTP 422와 `VALIDATION_ERROR`를 사용한다. FastAPI 기본
`loc`, `msg`, `ctx` 구조를 외부로 그대로 반환하지 않는다.

```json
{
  "status": "error",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 값을 확인해 주세요.",
    "details": [
      {
        "field": "login_id",
        "reason": "min_length",
        "message": "아이디를 입력해 주세요."
      }
    ]
  },
  "meta": {
    "request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"
  }
}
```

| 필드 | 설명 |
| --- | --- |
| `field` | 오류가 발생한 요청 필드명. 중첩 필드는 점 표기법 사용 |
| `reason` | `required`, `min_length`, `max_length`, `invalid_format` 등의 처리용 사유 |
| `message` | 입력 칸 아래에 바로 표시할 수 있는 한국어 메시지 |

## HTTP 상태 코드와 오류 코드

| HTTP 상태 | 오류 코드 | 사용 기준 |
| --- | --- | --- |
| 400 | `BAD_REQUEST` | 요청 형식은 맞지만 업무 규칙에 맞지 않음 |
| 401 | `AUTH_CREDENTIALS_INVALID` | 아이디 또는 비밀번호가 일치하지 않음 |
| 401 | `AUTH_SESSION_INVALID` | 세션이 없거나 유효하지 않음 |
| 403 | `AUTH_FORBIDDEN` | 인증됐지만 해당 작업 권한이 없음 |
| 404 | `RESOURCE_NOT_FOUND` | 요청한 리소스가 없음 |
| 409 | `RESOURCE_CONFLICT` | 중복 SKU 등 리소스 충돌 |
| 422 | `VALIDATION_ERROR` | 필수값·형식·길이 검증 실패 |
| 500 | `INTERNAL_SERVER_ERROR` | 예상하지 못한 서버 오류 |
| 502 | `UPSTREAM_ERROR` | 외부 AI·연동 서비스 오류 |
| 503 | `SERVICE_UNAVAILABLE` | 서비스 또는 필수 의존성이 일시적으로 사용 불가 |

신규 오류 코드는 이 문서의 목록과 구현 코드의 오류 코드 정의에 함께 추가한다.
응답에는 시크릿, 개인정보, SQL 원문, 외부 서비스 원문 오류를 넣지 않는다.

## request_id 규칙

- 요청을 받으면 서버가 UUID를 생성한다.
- 모든 적용 대상 성공·오류 응답의 `meta.request_id`에 같은 값을 넣는다.
- 서버 로그에는 같은 `request_id`를 포함한다.
- 클라이언트는 장애 문의와 로그 추적을 위해 응답의 `request_id`를 보존한다.

## 구현 전환 원칙

1. 공통 Pydantic 모델, 오류 코드, request ID 미들웨어를 추가한다.
2. 전역 예외 처리기에서 `HTTPException`, `RequestValidationError`, 예상하지 못한
   예외를 공통 오류 응답으로 변환한다.
3. 인증 API와 프런트 공통 요청 함수를 먼저 전환한다.
4. 태깅·이력 API, SKU·카탈로그 API 순서로 전환한다.
5. 각 전환 시 Swagger 예시와 API 계약 테스트를 함께 갱신한다.

전환 전 API의 응답 형식을 한 번에 변경하지 않는다. API군 단위로 백엔드와
프런트 변경을 함께 배포해 호환성 문제를 방지한다.
