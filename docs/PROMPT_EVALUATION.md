# Gemini 프롬프트 품질·효율 평가

## 목적

사람이 검수한 동일 이미지와 정답을 기준으로 객체 탐지와 속성 추출 프롬프트
v1·v2를 순차 실행합니다. 상세 응답은 실행 중에만 사용하고, 파일에는
공통·품질·효율 압축 지표와 버전 비교 결과만 CSV로 저장합니다.

일반 단위 테스트에서는 Gemini를 호출하지 않습니다. 라이브 평가 명령을
명시적으로 실행한 경우에만 API 호출과 비용이 발생합니다.

## 정답 데이터 작성

`data/evaluation/prompt_eval_dataset.example.csv`를 복사하여 평가 데이터셋을
작성합니다. 평가 입력과 결과 모두 CSV로 관리하며 JSON 파일은 사용하지 않습니다.

- `gt_bbox_xmin`, `gt_bbox_ymin`, `gt_bbox_xmax`, `gt_bbox_ymax`는
  `0~1000` 정규화 좌표로 사람이 직접 검수합니다.
- `gt_bbox_*`가 있으면 IoU 정답으로 우선 사용하고, 비어 있으면 기존
  `bbox_*` 좌표를 하위 호환 정답으로 사용합니다.
- `category`, `sub_category`, `attributes`는 카탈로그 허용값을 사용합니다.
- `attributes`에는 이미지에서 실제로 확인되는 전체 속성을 기록합니다.
- 검수가 끝난 케이스만 `verified` 열을 `true`로 변경합니다.
- 모델이 이전에 반환한 값을 그대로 정답으로 사용하지 않습니다.
- 객체는 `case_id`와 `object_idx`로 구분합니다.
- 동적 속성은 객체 정보를 반복하고 `attribute_key`, `attribute_value`에
  한 행씩 기록합니다.
- 속성이 없는 객체도 속성 두 열을 비운 한 행을 유지합니다.

## CSV 출력

평가기는 다음 두 파일만 생성합니다.

- `prompt_metrics_summary.csv`: 버전별 공통·품질·효율 압축 지표
- `prompt_version_comparison.csv`: v1 대비 v2 변화율과 우세 버전

공통 지표에는 성공률, P95 처리시간, 실제 토큰 사용량, 성공당 토큰,
재호출률과 토큰 계측률이 포함됩니다.

탐지 지표에는 F1, 평균 IoU, 누락률, 한글 근거 비율, 신뢰도 제공률,
1,000토큰당 정확한 객체 수와 정확한 객체당 처리시간이 포함됩니다.

속성 지표에는 key/value F1, 누락률, 오답 속성 비율, 카테고리 정확도,
1,000토큰당 정확한 속성 수와 정확한 속성당 처리시간이 포함됩니다.

CSV는 Excel에서 한글이 깨지지 않도록 UTF-8 BOM으로 저장합니다. Gemini 원시
응답과 케이스별 상세 결과는 파일로 저장하지 않습니다.

## 오프라인 단위 테스트

다음 테스트는 실제 Gemini를 호출하지 않습니다.

```powershell
python -m unittest tests.test_prompt_evaluation
```

## 라이브 v1·v2 평가

API 컨테이너가 현재 환경변수와 Vertex AI 인증을 사용하도록 실행합니다.

처음에는 보수적인 설정으로 1회만 실행해 현재 프로젝트의 쿼터를 확인합니다.

```powershell
docker compose exec -T api python -m app.evaluation.prompt_evaluator `
  --dataset /app/data/evaluation/prompt_eval_dataset.csv `
  --output-dir /app/uploads/evaluation/smoke-balanced `
  --repetitions 1 `
  --request-interval-seconds 10 `
  --max-concurrent-attribute-calls 1 `
  --max-request-interval-seconds 60 `
  --rate-limit-cooldown-seconds 60 `
  --recovery-success-count 3 `
  --max-rate-limit-events 3 `
  --version-order balanced `
  --confirm-live-calls
```

이 실행에서 `retry_rate`와 `generation_success_rate`가 안정적일 때만 다음의 전체
평가를 실행합니다.

```powershell
docker compose exec -T api python -m app.evaluation.prompt_evaluator `
  --dataset /app/data/evaluation/prompt_eval_dataset.csv `
  --output-dir /app/uploads/evaluation/run-01-balanced `
  --repetitions 3 `
  --request-interval-seconds 10 `
  --max-concurrent-attribute-calls 1 `
  --max-request-interval-seconds 60 `
  --rate-limit-cooldown-seconds 60 `
  --recovery-success-count 3 `
  --max-rate-limit-events 3 `
  --version-order balanced `
  --confirm-live-calls
```

`balanced` 일정은 첫 케이스를 v1→v2, 다음 케이스를 v2→v1 순으로 실행하고
반복이 바뀌어도 선행 버전을 교차합니다. 호출은 10초 간격과 동시성 1로 시작하며,
429가 발생하면 해당 재시도를 포함한 전체 평가를 최소 60초 멈춥니다. 이후 호출
간격은 최대 60초까지 두 배씩 늘리고, 재시도 없는 호출이 3회 연속 성공하면 절반씩
완화합니다. 429가 3회를 초과하면 결과를 계속 오염시키지 않고 평가를 중단합니다.
운영 서비스의 기본 재시도 정책은 변경되지 않습니다. `--confirm-live-calls`가
없으면 실행하지 않습니다.

현재 구현에서 예상 Gemini 호출 수는 다음과 같습니다.

```text
2 × (이미지 수 + 전체 정답 객체 수) × 반복 횟수
```

429 재호출이 발생하면 실제 호출 수는 더 증가할 수 있습니다. CSV의
`retry_rate`는 실제 재호출 여부를 반영하며, 토큰 값은 Gemini 응답의
`usage_metadata`를 사용합니다.

v1과 v2의 성공률 또는 재호출률 차이가 큰 실행은 품질 우열을 확정하는 데
사용하지 않습니다. 독립적으로 한 버전을 먼저 실행해야 할 때만 `v1-first` 또는
`v2-first`를 지정하며, 이 경우 `--version-cooldown-seconds`가 두 버전 사이에
적용됩니다.

완료 기준을 자동 검사하려면 `--fail-on-threshold`를 추가합니다. v1 또는 v2 중
하나라도 데이터셋에 정의한 최소 품질이나 최대 처리시간을 만족하지 못하면 종료
코드 `1`을 반환합니다.

검수 전 데이터로 CSV 구조만 확인할 때는 `--allow-unverified`를 사용할 수 있지만,
그 결과는 프롬프트 품질 판단에 사용하지 않습니다.

## XAI 라이브 스모크

XAI 운영 기본 프롬프트는 v2입니다. 다음 명령은 동일한 의자 이미지를 대상
crop과 SKU 후보로 사용하여 v2 응답 계약을 한 번 확인합니다.

```powershell
docker compose exec -T api python -m app.evaluation.xai_prompt_smoke `
  --crop-image /app/data/images/1050728_CHR-7DFE2E44_BLACK_m_001.png `
  --sku-code CHR-7DFE2E44 `
  --sku-image /app/data/images/1050728_CHR-7DFE2E44_BLACK_m_001.png `
  --prompt-versions v2 `
  --output /app/uploads/evaluation/xai-smoke-v2.csv `
  --confirm-live-calls
```

v1과 v2의 응답 계약을 같은 입력으로 확인하려면
`--prompt-versions v1 v2`를 사용합니다. 두 호출 사이에는 기본 10초 간격이
적용됩니다.

결과 CSV에는 성공 여부, 처리시간, crop·SKU 반환 여부, criteria 네 종류의
완전성 및 점수 범위, criteria 합계와 total_score 일치 여부, 70점 기준 상태
일치 여부, 객체 label과 vlm_mood 존재 여부가 기록됩니다.

이 명령은 호출과 응답 계약을 확인하는 스모크 테스트입니다. 프롬프트 품질을
판단하려면 별도의 사람이 검수한 crop·SKU 정답 데이터셋으로 Matched/Rejected
F1, 점수 오차와 후보 순위 지표를 평가해야 합니다.
