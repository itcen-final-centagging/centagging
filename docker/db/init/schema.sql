CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------
-- 1. app_user : 고정 POC 사용자 계정 (FT-ACC-001 · 하드코딩, P3)
-- ------------------------------------------------------------
CREATE TABLE app_user (
    user_id       BIGSERIAL    PRIMARY KEY,
    login_id      VARCHAR(50)  NOT NULL UNIQUE,
    user_name     VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255),
    session       VARCHAR(255) UNIQUE,
    role          VARCHAR(20)  NOT NULL DEFAULT 'USER',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_app_user_role CHECK (
        role IN ('USER', 'ADMIN', 'SUPER_ADMIN')
    )
);

COMMENT ON TABLE  app_user           IS '고정 POC 사용자 계정';
COMMENT ON COLUMN app_user.login_id  IS '로그인 아이디, 중복 불가';
COMMENT ON COLUMN app_user.user_name IS '화면에 표시할 작업자 이름';
COMMENT ON COLUMN app_user.session   IS 'POC 인증에 사용하는 고정 세션';
COMMENT ON COLUMN app_user.role      IS '사용자 역할: USER | ADMIN | SUPER_ADMIN';

-- ------------------------------------------------------------
-- 2. scene_image : 업로드된 연출 이미지
--    파일 검증(형식·용량·해상도)은 업로드 시점에 수행, 통과분만 저장
-- ------------------------------------------------------------
CREATE TABLE scene_image (
    scene_image_id  BIGSERIAL    PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES app_user(user_id),
    image_url       TEXT         NOT NULL,
    origin_name     VARCHAR(255) NOT NULL,
    mime_type       VARCHAR(20)  NOT NULL,
    file_size       INT          NOT NULL,
    analysis_error  TEXT,
    analysis_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    object_metadata JSONB        NOT NULL DEFAULT '[]'::jsonb,
    width_px        INT          NOT NULL,
    height_px       INT          NOT NULL,
    CONSTRAINT ck_scene_mime CHECK (mime_type IN ('image/jpeg','image/png')),
    CONSTRAINT ck_scene_size CHECK (file_size > 0 AND file_size <= 10485760),
    CONSTRAINT ck_scene_dimensions CHECK (width_px > 0 AND height_px > 0),
    -- 개별 좌표의 길이와 범위는 탐지 결과 저장 단계에서 검증한다.
    CONSTRAINT ck_scene_object_metadata_array CHECK (
        jsonb_typeof(object_metadata) = 'array'
    ),
    CONSTRAINT ck_scene_analysis_status CHECK (
        analysis_status IN (
            'pending', 'detected', 'embedded', 'completed', 'failed'
        )
    )
);

CREATE INDEX idx_scene_user_created ON scene_image(user_id, created_at DESC);

COMMENT ON TABLE  scene_image                      IS '업로드된 연출 이미지';
COMMENT ON COLUMN scene_image.scene_image_id       IS '연출 이미지 고유 번호';
COMMENT ON COLUMN scene_image.user_id              IS '업로드한 사용자';
COMMENT ON COLUMN scene_image.image_url            IS '연출 이미지 경로';
COMMENT ON COLUMN scene_image.origin_name          IS '업로드된 연출 이미지 파일명';
COMMENT ON COLUMN scene_image.mime_type            IS '연출 이미지 파일 MIME 타입: image/jpeg | image/png';
COMMENT ON COLUMN scene_image.file_size            IS '연출 이미지 파일 크기(byte), 10MB 이하';
COMMENT ON COLUMN scene_image.analysis_error       IS '탐지·임베딩·SKU 후보 생성 실패 사유';
COMMENT ON COLUMN scene_image.analysis_status      IS '태깅 처리 상태: pending | detected | embedded | completed | failed';
COMMENT ON COLUMN scene_image.created_at           IS '연출 이미지 업로드 일시';
COMMENT ON COLUMN scene_image.object_metadata      IS '탐지 객체 메타데이터 배열 [{object_idx,bbox_coord:{xmin,ymin,xmax,ymax},attribute:{label}}, ...]';
COMMENT ON COLUMN scene_image.width_px             IS '이미지 너비(pixel)';
COMMENT ON COLUMN scene_image.height_px            IS '이미지 높이(pixel)';

-- ------------------------------------------------------------
-- 4. sku_catalog : 상품 마스터 + 속성 (FT-CAT-002/003)
-- ------------------------------------------------------------
CREATE TABLE sku_catalog (
    sku_id       BIGSERIAL    PRIMARY KEY,
    sku_code     VARCHAR(50)  NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    category     VARCHAR(50),
    sub_category VARCHAR(50),
    brand        VARCHAR(50),
    price        INTEGER,
    key_features JSONB        NOT NULL DEFAULT '[]'::jsonb,
    attributes   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    text_embedding VECTOR(3072),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_sku_key_features_array CHECK (
        jsonb_typeof(key_features) = 'array'
    ),
    CONSTRAINT ck_sku_attributes_object CHECK (
        jsonb_typeof(attributes) = 'object'
    )
);

-- 부분일치·대소문자 무시 검색 (FT-CAT-002)
CREATE INDEX idx_sku_name_trgm ON sku_catalog USING GIN (lower(product_name) gin_trgm_ops);
CREATE INDEX idx_sku_code_trgm ON sku_catalog USING GIN (lower(sku_code) gin_trgm_ops);
CREATE INDEX idx_sku_attr      ON sku_catalog USING GIN (attributes jsonb_path_ops);
CREATE INDEX idx_sku_category  ON sku_catalog(category);
CREATE INDEX idx_sku_text_embedding_hnsw ON sku_catalog
    USING hnsw ((text_embedding::halfvec(3072)) halfvec_cosine_ops)
    WHERE text_embedding IS NOT NULL;

COMMENT ON TABLE  sku_catalog              IS '상품 마스터 + 속성';
COMMENT ON COLUMN sku_catalog.sku_code     IS '상품 코드, 중복 불가 - 검색 대상';
COMMENT ON COLUMN sku_catalog.product_name IS '상품명 - 부분일치 검색 대상';
COMMENT ON COLUMN sku_catalog.category     IS '상품 대분류 - Top-K 필터 조건';
COMMENT ON COLUMN sku_catalog.key_features IS '상품 핵심 특징 목록';
COMMENT ON COLUMN sku_catalog.attributes   IS '상품 속성 - 객체 속성과 같은 키 체계';
COMMENT ON COLUMN sku_catalog.text_embedding IS '상품 메타데이터 텍스트 임베딩';

-- ------------------------------------------------------------
-- 5. sku_image : SKU 이미지 + 벡터 임베딩 (색인 단위)
--    SKU 1건 : 이미지 N건, 각 이미지가 자기 벡터를 소유
--    embedding 은 NULL 허용 — 이미지 등록 후 색인 배치가 채움
-- ------------------------------------------------------------
CREATE TABLE sku_image (
    sku_image_id BIGSERIAL   PRIMARY KEY,
    sku_id       BIGINT      NOT NULL REFERENCES sku_catalog(sku_id) ON DELETE CASCADE,
    image_url    TEXT        NOT NULL,
    image_type   VARCHAR(20) NOT NULL DEFAULT 'MAIN'
                 CHECK (image_type IN ('MAIN','ANGLE')),
    embedding    VECTOR(3072),
    indexed_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_skuimg_sku ON sku_image(sku_id);
-- 원본 VECTOR(3072)는 유지하고 검색 인덱스만 halfvec으로 변환한다.
-- pgvector의 halfvec HNSW 인덱스는 최대 4,000차원을 지원한다.
CREATE INDEX idx_skuimg_hnsw ON sku_image
    USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
    WHERE embedding IS NOT NULL;
-- 미색인 이미지 조회용 (색인 배치가 사용)
CREATE INDEX idx_skuimg_pending ON sku_image(sku_image_id) WHERE embedding IS NULL;

COMMENT ON TABLE  sku_image            IS 'SKU 이미지 + 벡터 (색인 단위)';
COMMENT ON COLUMN sku_image.image_type IS 'MAIN | ANGLE | DETAIL | STYLING — 색인 대상 선별에 사용';
COMMENT ON COLUMN sku_image.embedding  IS '이미지 벡터 - 검색 대상. NULL 이면 미색인';
COMMENT ON COLUMN sku_image.indexed_at IS '임베딩 생성 완료 일시';

-- ------------------------------------------------------------
-- 6. tagging_result : 최종 객체-SKU 매핑 + 검수 이력
--    scene_image.object_metadata 배열의 object_index로 탐지 객체를 식별한다.
--    이미지 1장에서 객체 N개를 태깅하면 N행이 생성됨
--
--    xai_result 구조 (현재 API 응답·저장 계약)
--      { "summary": "구조와 색상이 유사합니다.",
--        "criteria": [
--          { "label": "구조", "score": 29, "comment": "..." }
--        ] }
-- ------------------------------------------------------------
CREATE TABLE tagging_result (
    result_id        BIGSERIAL   PRIMARY KEY,
    scene_image_id   BIGINT      NOT NULL REFERENCES scene_image(scene_image_id),
    object_index     SMALLINT    NOT NULL,
    sku_id           BIGINT      NOT NULL REFERENCES sku_catalog(sku_id),
    sku_image_id     BIGINT      REFERENCES sku_image(sku_image_id),
    match_source     VARCHAR(20) NOT NULL
                     CHECK (match_source IN ('RECOMMEND','SEARCH')),
    match_rank       SMALLINT,
    similarity_score NUMERIC(6,4),
    similarity_grade CHAR(1)     CHECK (similarity_grade IN ('상','중','하')),
    xai_result       JSONB,
    status           VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING', 'ACTIVE', 'DEACTIVE')),
    vlm_mood         JSONB,
    created_by       BIGINT      NOT NULL REFERENCES app_user(user_id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_result_scene_object UNIQUE (scene_image_id, object_index),
    -- 검색 경유는 순위·유사도·근거가 없고, 추천 경유는 순위·유사도가 반드시 있어야 함
    CONSTRAINT ck_result_source CHECK (
        (match_source = 'SEARCH'
             AND match_rank IS NULL AND similarity_score IS NULL AND xai_result IS NULL)
     OR (match_source = 'RECOMMEND'
             AND match_rank IS NOT NULL AND similarity_score IS NOT NULL)
    ),
    CONSTRAINT ck_result_score CHECK (similarity_score IS NULL OR similarity_score BETWEEN 0 AND 1),
    -- 루브릭이 기록됐다면 현재 summary/criteria 구조여야 한다.
    CONSTRAINT ck_result_xai CHECK (
        xai_result IS NULL OR (
            jsonb_typeof(xai_result) = 'object'
        AND xai_result ? 'summary'
        AND xai_result ? 'criteria'
        AND jsonb_typeof(xai_result->'summary') = 'string'
        AND jsonb_typeof(xai_result->'criteria') = 'array'
        )
    )
);

CREATE INDEX idx_result_user_created ON tagging_result(created_by, created_at DESC);
CREATE INDEX idx_result_scene        ON tagging_result(scene_image_id);
CREATE INDEX idx_result_sku          ON tagging_result(sku_id);

COMMENT ON TABLE  tagging_result                  IS '최종 객체-SKU 매핑 + 검수 이력';
COMMENT ON COLUMN tagging_result.object_index     IS 'scene_image.object_metadata 배열의 객체 인덱스';
COMMENT ON COLUMN tagging_result.sku_image_id     IS '매칭 근거가 된 SKU 이미지';
COMMENT ON COLUMN tagging_result.match_source     IS 'RECOMMEND(추천 경유) | SEARCH(카탈로그 검색 경유)';
COMMENT ON COLUMN tagging_result.match_rank       IS '선택 시점의 추천 순위';
COMMENT ON COLUMN tagging_result.similarity_score IS '선택 시점의 임베딩 유사도 (0~1)';
COMMENT ON COLUMN tagging_result.similarity_grade IS '화면 표시용 등급 상/중/하';
COMMENT ON COLUMN tagging_result.xai_result       IS '루브릭 채점 결과 - 위 주석의 JSON 구조 참고';
COMMENT ON COLUMN tagging_result.status           IS '최종 관리자 검수 상태: PENDING | ACTIVE | DEACTIVE';
COMMENT ON COLUMN tagging_result.vlm_mood         IS '연출 이미지 분위기 요약과 태그';

-- ------------------------------------------------------------
-- 7. approval : 객체-SKU 매칭(tagging_result) 단위 승인 요청
--    현재 스키마는 객체를 scene_image.object_metadata의 배열 인덱스로
--    식별하므로 tagging_result와 object_index를 함께 보관한다.
-- ------------------------------------------------------------
CREATE TABLE approval (
    request_id        BIGSERIAL   PRIMARY KEY,
    tagging_result_id BIGINT      NOT NULL REFERENCES tagging_result(result_id) ON DELETE CASCADE,
    scene_image_id    BIGINT      NOT NULL REFERENCES scene_image(scene_image_id) ON DELETE CASCADE,
    object_index      SMALLINT    NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    requested_by      BIGINT      NOT NULL REFERENCES app_user(user_id),
    requested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by       BIGINT      REFERENCES app_user(user_id),
    reviewed_at       TIMESTAMPTZ,
    reject_reason     VARCHAR(255),
    CONSTRAINT ck_approval_status CHECK (status IN ('PENDING','ACTIVE','REJECTED')),
    CONSTRAINT ck_approval_reviewed CHECK (
        (status = 'PENDING'  AND reviewed_by IS NULL AND reviewed_at IS NULL AND reject_reason IS NULL)
     OR (status = 'ACTIVE'   AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
     OR (status = 'REJECTED' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
                             AND reject_reason IS NOT NULL)
    )
);

-- 같은 확정 결과에 PENDING은 1건만. 반려 후 재요청은 허용된다.
CREATE UNIQUE INDEX uq_approval_pending
    ON approval(tagging_result_id) WHERE status = 'PENDING';

CREATE INDEX idx_approval_status_req ON approval(status, requested_at DESC);
CREATE INDEX idx_approval_scene       ON approval(scene_image_id);

COMMENT ON TABLE  approval               IS '객체-SKU 매칭(tagging_result) 단위 승인 요청';
COMMENT ON COLUMN approval.request_id    IS '승인 요청 고유 번호';
COMMENT ON COLUMN approval.object_index  IS '승인 대상 탐지 객체의 object_metadata 배열 인덱스';
COMMENT ON COLUMN approval.status        IS 'PENDING | ACTIVE | REJECTED';
COMMENT ON COLUMN approval.requested_by  IS '태깅을 저장한 작업자';
COMMENT ON COLUMN approval.reviewed_by   IS '승인·반려를 수행한 사용자';

-- ------------------------------------------------------------
-- 8. product_image_submission : 관리자 제품 이미지 등록 요청
--    업로드한 제품 이미지는 최종 승인 전까지 SKU 카탈로그와 분리한다.
--    APPROVED 전이에서만 sku_catalog / sku_image에 실제 반영된다.
-- ------------------------------------------------------------
CREATE TABLE product_image_submission (
    submission_id       BIGSERIAL    PRIMARY KEY,
    target_type         VARCHAR(20)  CHECK (target_type IN ('EXISTING', 'NEW')),
    target_sku_id       BIGINT       REFERENCES sku_catalog(sku_id),
    proposed_sku_code   VARCHAR(50),
    proposed_product_name VARCHAR(200),
    proposed_brand      VARCHAR(100),
    proposed_price      INT          CHECK (proposed_price IS NULL OR proposed_price >= 0),
    proposed_space      VARCHAR(50),
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

CREATE INDEX idx_product_submission_requester_status
    ON product_image_submission(requested_by, status, requested_at DESC);
CREATE INDEX idx_product_submission_status
    ON product_image_submission(status, requested_at DESC);

COMMENT ON TABLE product_image_submission IS '관리자의 제품 이미지 신규/기존 SKU 등록 승인 요청';
COMMENT ON COLUMN product_image_submission.target_type IS 'EXISTING: 기존 SKU 이미지 추가, NEW: 신규 SKU 생성';
COMMENT ON COLUMN product_image_submission.status IS 'DRAFT | PENDING | APPROVED | REJECTED';
COMMENT ON COLUMN product_image_submission.final_sku_id IS '최종 승인으로 연결 또는 생성된 SKU';

-- sku_image 멱등성 인덱스: confirm이 두 번 호출돼도 같은 크롭이 중복 등록되지 않는다.
CREATE UNIQUE INDEX uq_sku_image_sku_url ON sku_image(sku_id, image_url);
