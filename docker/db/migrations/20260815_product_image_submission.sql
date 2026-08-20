-- 기존 개발 DB에 제품 이미지 등록 승인 대기열을 추가하는 비파괴 마이그레이션입니다.
BEGIN;

CREATE TABLE IF NOT EXISTS product_image_submission (
    submission_id       BIGSERIAL    PRIMARY KEY,
    target_type         VARCHAR(20)  CHECK (target_type IN ('EXISTING', 'NEW')),
    target_sku_id       BIGINT       REFERENCES sku_catalog(sku_id),
    proposed_sku_code   VARCHAR(50),
    proposed_product_name VARCHAR(200),
    proposed_brand      VARCHAR(100),
    proposed_price      INT          CHECK (proposed_price IS NULL OR proposed_price >= 0),
    proposed_category   VARCHAR(50),
    proposed_sub_category VARCHAR(50),
    proposed_attributes JSONB        NOT NULL DEFAULT '{}'::jsonb,
    image_url           TEXT         NOT NULL,
    image_type          VARCHAR(20)  NOT NULL DEFAULT 'MAIN'
                                  CHECK (image_type IN ('MAIN','ANGLE','DETAIL','STYLING')),
    status              VARCHAR(20)  NOT NULL DEFAULT 'DRAFT'
                                  CHECK (status IN ('DRAFT','PENDING','APPROVED','REJECTED')),
    requested_by        BIGINT       NOT NULL REFERENCES app_user(user_id),
    requested_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    submitted_at        TIMESTAMPTZ,
    reviewed_by         BIGINT       REFERENCES app_user(user_id),
    reviewed_at         TIMESTAMPTZ,
    reject_reason       VARCHAR(255),
    final_sku_id        BIGINT       REFERENCES sku_catalog(sku_id),
    final_sku_image_id  BIGINT       REFERENCES sku_image(sku_image_id),
    CONSTRAINT ck_product_image_submission_attributes CHECK (
        jsonb_typeof(proposed_attributes) = 'object'
    ),
    CONSTRAINT ck_product_image_submission_review CHECK (
        (status = 'DRAFT'
            AND reviewed_by IS NULL AND reviewed_at IS NULL
            AND reject_reason IS NULL AND final_sku_id IS NULL
            AND final_sku_image_id IS NULL AND submitted_at IS NULL)
     OR (status = 'PENDING'
            AND reviewed_by IS NULL AND reviewed_at IS NULL
            AND reject_reason IS NULL AND final_sku_id IS NULL
            AND final_sku_image_id IS NULL AND submitted_at IS NOT NULL)
     OR (status = 'APPROVED'
            AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
            AND final_sku_id IS NOT NULL AND final_sku_image_id IS NOT NULL
            AND reject_reason IS NULL AND submitted_at IS NOT NULL)
     OR (status = 'REJECTED'
            AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
            AND reject_reason IS NOT NULL AND final_sku_id IS NULL
            AND final_sku_image_id IS NULL AND submitted_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_product_submission_requester_status
    ON product_image_submission(requested_by, status, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_submission_status
    ON product_image_submission(status, requested_at DESC);

COMMIT;
