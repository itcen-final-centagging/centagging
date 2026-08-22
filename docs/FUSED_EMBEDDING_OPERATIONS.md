# 융합 임베딩 운영 절차

SKU 검색 벡터는 `sku_image.embedding` 컬럼을 재사용한다. 벡터는 다음 입력을
하나의 Gemini 임베딩 요청으로 생성한다.

```text
SKU: 정규화 메타데이터 + 보정 RGB + 보정 그레이
연출 객체: VLM 추출 속성 + 보정 RGB + 보정 그레이
```

`EMBEDDING_PIPELINE_VERSION`이 같은 벡터와 `embedding_image_sha256`이 있는
SKU 이미지만 추천 검색 후보가 된다. 따라서 새 버전 배포 뒤에는 카탈로그
재색인이 끝나기 전까지 일부 또는 전체 후보가 비어 있을 수 있다.

## 1. 배포 전 확인

- `.env` 또는 `.env.prod`에 현재 배포할 `EMBEDDING_PIPELINE_VERSION`을 정한다.
- `GEMINI_API_KEY` 또는 운영 Vertex AI 인증이 유효한지 확인한다.
- `docker/db/migrations/20260821_fused_embedding.sql`이 배포 대상에 포함됐는지
  확인한다.

파이프라인 규칙, 임베딩 모델, 이미지 최대 크기, 보정 기준을 변경했다면
반드시 `EMBEDDING_PIPELINE_VERSION`을 올린다. 같은 버전에 서로 다른 입력
규칙을 사용하면 재색인 판별과 검색 호환성이 깨진다.

## 2. DB 마이그레이션

기존 로컬 DB에는 다음 명령을 한 번 실행한다.

```powershell
docker compose --profile migration run --rm db-migrate
```

운영 VM 배포는 `scripts/deploy/deploy_vm.sh`가 `db-migrate`를 먼저 실행한다.
마이그레이션은 멱등적이며 `docker/db/migrations/*.sql`을 순서대로 적용한다.

## 3. SKU 카탈로그 전체 재색인

마이그레이션 뒤, API와 같은 환경 변수 및 DB 연결 정보가 설정된 셸에서
실행한다.

```powershell
python -m scripts.embedding.build_embeddings --skip-text --force-images
```

- 이 명령은 Gemini 호출과 DB 쓰기를 수행한다.
- SKU 이미지마다 전처리, 메타데이터 조립, 융합 임베딩, 벡터 저장을 수행한다.
- 실패한 이미지는 `embedding`이 비어 있거나 현재 버전·해시와 일치하지 않는
  상태로 남는다. 같은 명령을 다시 실행해 재시도할 수 있다.

`--force-images` 없이 실행해도 구 벡터는 버전·해시가 달라 재색인 대상이 된다.
운영 전환 시에는 처리 의도를 명확히 하기 위해 `--force-images` 사용을 권장한다.

## 4. 완료 여부 점검

```powershell
python -m scripts.embedding.build_embeddings --check-image-index
```

이 명령은 Gemini 호출이나 DB 변경 없이 집계만 수행한다.

| 결과 | 의미 |
| --- | --- |
| 종료 코드 `0`, 재색인 필요 `0건` | 현재 파이프라인으로 전체 색인 완료 |
| 종료 코드 `1`, 재색인 필요 `1건 이상` | 검색에서 제외되는 SKU 이미지가 남아 있음 |

재색인 대상이 남으면 3단계를 다시 실행한다. 반복 실패 시 파일 경로, Gemini
인증·할당량, 이미지 디코딩 오류를 확인한다.

## 5. 승인 이미지 자동 색인

다음 승인 경로는 승인 DB 트랜잭션을 확정한 뒤 자동으로 융합 임베딩을 생성한다.

- 관리자 제품 이미지 등록 승인
- 태깅 결과의 스타일링 SKU 이미지 승인

자동 색인 실패는 승인 자체를 취소하지 않는다. 해당 이미지는 미색인 상태로
남으며 3단계의 배치 재색인이 복구 경로다.

## 5-1. 승인 시 SKU 텍스트 임베딩 자동 재생성

최종 관리자가 태깅 결과를 승인(`POST /approvals/{request_id}/confirm`)하면,
이미지 색인과 별도로 해당 SKU 1건의 `sku_catalog.text_embedding`도 자동으로
다시 만든다(`app.services.approval_service._reindex_sku_text_embedding`).

- 상품명·카테고리·속성·특징에, 그 SKU에 대해 지금까지 ACTIVE로 승인된 모든
  `tagging_res연출 이미지에서 반복 승인되면 공간 분위기·스타일 태그가
  누적되며, 중복은ult.vlm_mood`(공간 분위기 `summary`, 스타일 태그 `tags`)를
  더해 텍스트를 다시 조립하고 임베딩한다.
- 같은 SKU가 다른  제거한다(`app.services.sku_text_embedding`).
- 별도 DB 컬럼에 누적 결과를 저장하지 않고, 승인마다 `tagging_result`를 다시
  모아 계산한다.
- 재생성 실패는 승인 자체를 취소하지 않는다. 해당 SKU는 이전
  `text_embedding` 상태로 남으며, 아래 3단계의 `--force-text` 배치가 복구
  경로다. 이 배치도 같은 방식으로 승인된 `vlm_mood`를 반영하므로 온라인
  트리거와 같은 결과를 재현한다.

## 6. 정확도 확인

추천 결과 JSON을 준비한 뒤 지표를 계산한다.

```powershell
python -m scripts.evaluation.evaluate_retrieval results.json
```

입력에는 `pipeline_version`, 각 객체의 `expected_sku_code`, 추천 순서의
`candidate_sku_codes`를 넣는다. 결과의 Top-1, Top-5, 후보 누락률을 기록해
버전별로 비교한다.

## 7. 전환 및 되돌림 제약

구 이미지 임베딩은 별도 컬럼에 보존하지 않는다. 따라서 애플리케이션 코드만
이전 버전으로 되돌려도 과거 벡터가 자동 복원되지는 않는다. 이전 입력 규칙으로
되돌려야 한다면 해당 규칙의 새 파이프라인 버전을 정하고 전체 SKU를 다시
색인한다.
