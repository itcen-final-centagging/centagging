-- 제품 이미지 등록에 AI 추천 파이프라인을 붙이기 위한 비파괴 마이그레이션입니다.
-- 상세 설계: docs/PRODUCT_IMAGE_REGISTRATION_REDESIGN_FINAL.md
BEGIN;

ALTER TABLE product_image_submission
    ADD COLUMN IF NOT EXISTS draft_embedding HALFVEC(3072),
    ADD COLUMN IF NOT EXISTS draft_embedding_pipeline_version VARCHAR(50),
    ADD COLUMN IF NOT EXISTS draft_embedding_image_sha256 TEXT;

COMMENT ON COLUMN product_image_submission.draft_embedding IS
    '업로드 시점(워커)에 계산한 융합 임베딩 캐시 — 승인 시 재계산 없이
     sku_image.embedding으로 그대로 복사한다';
COMMENT ON COLUMN product_image_submission.draft_embedding_pipeline_version IS
    'draft_embedding 생성 파이프라인 버전 — 승인 시 sku_image.embedding_pipeline_version으로 복사';
COMMENT ON COLUMN product_image_submission.draft_embedding_image_sha256 IS
    'draft_embedding 생성에 쓴 보정 이미지 SHA-256 — 승인 시 sku_image.embedding_image_sha256으로 복사';

-- ------------------------------------------------------------
-- product_image_submission_job : 제품 이미지 등록 추천 작업 큐
--    ai_job과 동일한 폴링 패턴(FOR UPDATE SKIP LOCKED)을 쓰되,
--    product_image_submission 전용이라 job_type/input_payload가 없다.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_image_submission_job (
    job_id          UUID        PRIMARY KEY,
    submission_id   BIGINT      NOT NULL
                                REFERENCES product_image_submission(submission_id)
                                ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    result_payload  JSONB,
    error_code      VARCHAR(50),
    error_message   TEXT,
    attempt_count   SMALLINT    NOT NULL DEFAULT 0,
    max_attempts    SMALLINT    NOT NULL DEFAULT 3,
    worker_id       VARCHAR(100),
    locked_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_product_image_submission_job_status CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')
    ),
    CONSTRAINT ck_product_image_submission_job_attempts CHECK (
        attempt_count >= 0
        AND max_attempts > 0
        AND attempt_count <= max_attempts
    )
);

CREATE INDEX IF NOT EXISTS idx_product_image_submission_job_pending_created
    ON product_image_submission_job(status, created_at)
    WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_product_image_submission_job_submission_created
    ON product_image_submission_job(submission_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_image_submission_job_active
    ON product_image_submission_job(submission_id)
    WHERE status IN ('PENDING', 'RUNNING');

COMMENT ON TABLE  product_image_submission_job IS '제품 이미지 등록 추천 작업 큐 (ai_job과 별도)';
COMMENT ON COLUMN product_image_submission_job.job_id IS '클라이언트가 조회할 작업 UUID';
COMMENT ON COLUMN product_image_submission_job.submission_id IS '분석 대상 제품 이미지 등록 요청';
COMMENT ON COLUMN product_image_submission_job.status IS 'PENDING | RUNNING | SUCCEEDED | FAILED';
COMMENT ON COLUMN product_image_submission_job.result_payload IS '완료된 작업의 결과값: {proposed_category, proposed_sub_category, proposed_attributes, sku_candidates}';
COMMENT ON COLUMN product_image_submission_job.attempt_count IS '현재까지 실행을 시도한 횟수';
COMMENT ON COLUMN product_image_submission_job.max_attempts IS '재시도를 포함한 최대 실행 횟수 (기본 3)';
COMMENT ON COLUMN product_image_submission_job.worker_id IS '작업을 선점한 Worker 식별자';
COMMENT ON COLUMN product_image_submission_job.locked_at IS 'Worker가 작업을 선점한 시각';

COMMIT;
