-- 기존 DB에 AI 분석용 영속 작업 큐를 추가하는 비파괴 마이그레이션입니다.
BEGIN;

CREATE TABLE IF NOT EXISTS ai_job (
    job_id          UUID        PRIMARY KEY,
    scene_image_id  BIGINT      NOT NULL
                                REFERENCES scene_image(scene_image_id)
                                ON DELETE CASCADE,
    job_type        VARCHAR(30) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    input_payload   JSONB       NOT NULL DEFAULT '{}'::jsonb,
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
    CONSTRAINT ck_ai_job_type CHECK (
        job_type IN ('DETECT_SCENE', 'RECOMMEND_SKU')
    ),
    CONSTRAINT ck_ai_job_status CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')
    ),
    CONSTRAINT ck_ai_job_attempts CHECK (
        attempt_count >= 0
        AND max_attempts > 0
        AND attempt_count <= max_attempts
    )
);

CREATE INDEX IF NOT EXISTS idx_ai_job_pending_created
    ON ai_job(status, created_at)
    WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_ai_job_scene_created
    ON ai_job(scene_image_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_job_active_scene_type
    ON ai_job(scene_image_id, job_type)
    WHERE status IN ('PENDING', 'RUNNING');

COMMENT ON TABLE ai_job IS 'AI 분석용 영속 작업 큐';
COMMENT ON COLUMN ai_job.job_id IS '클라이언트가 조회할 AI 작업 UUID';
COMMENT ON COLUMN ai_job.scene_image_id IS '분석 대상 연출 이미지';
COMMENT ON COLUMN ai_job.job_type IS 'DETECT_SCENE | RECOMMEND_SKU';
COMMENT ON COLUMN ai_job.status IS 'PENDING | RUNNING | SUCCEEDED | FAILED';
COMMENT ON COLUMN ai_job.input_payload IS '작업 실행에 필요한 입력값';
COMMENT ON COLUMN ai_job.result_payload IS '완료된 작업의 결과값';
COMMENT ON COLUMN ai_job.attempt_count IS '현재까지 실행을 시도한 횟수';
COMMENT ON COLUMN ai_job.max_attempts IS '재시도를 포함한 최대 실행 횟수';
COMMENT ON COLUMN ai_job.worker_id IS '작업을 선점한 Worker 식별자';
COMMENT ON COLUMN ai_job.locked_at IS 'Worker가 작업을 선점한 시각';

COMMIT;
