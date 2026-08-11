CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------
-- 1. app_user : 고정 관리자 계정 (FT-ACC-001 · 하드코딩, P3)
-- ------------------------------------------------------------
CREATE TABLE app_user (
    user_id       BIGSERIAL    PRIMARY KEY,
    login_id      VARCHAR(50)  NOT NULL UNIQUE,
    user_name     VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE  app_user           IS '고정 관리자 계정';
COMMENT ON COLUMN app_user.login_id  IS '로그인 아이디, 중복 불가';
COMMENT ON COLUMN app_user.user_name IS '화면에 표시할 작업자 이름';

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
    bbox_coord      JSONB        NOT NULL DEFAULT '[]'::jsonb,
    width_px        INT          NOT NULL,
    height_px       INT          NOT NULL,
    CONSTRAINT ck_scene_mime CHECK (mime_type IN ('image/jpeg','image/png')),
    CONSTRAINT ck_scene_size CHECK (file_size > 0 AND file_size <= 10485760),
    CONSTRAINT ck_scene_dimensions CHECK (width_px > 0 AND height_px > 0),
    -- 개별 좌표의 길이와 범위는 탐지 결과 저장 단계에서 검증한다.
    CONSTRAINT ck_scene_bbox_coord_array CHECK (
        jsonb_typeof(bbox_coord) = 'array'
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
COMMENT ON COLUMN scene_image.bbox_coord           IS '탐지 객체 좌표 배열 [{xmin,ymin,xmax,ymax}, ...]';
COMMENT ON COLUMN scene_image.width_px             IS '이미지 너비(pixel)';
COMMENT ON COLUMN scene_image.height_px            IS '이미지 높이(pixel)';

-- ------------------------------------------------------------
-- 3. detected_object : 탐지된 가구 객체 (크롭 패치 단위)
--
--    attributes 예시 (PRODUCT_ATTRIBUTE + COMMON_ATTRIBUTE 병합)
--      { "카테고리": {"value":"의자 > 오피스체어","confidence":1.0,"reason":"..."},
--        "주요 소재": {"value":"메쉬","confidence":0.95,"reason":"..."} }
--
--    mood_summary : "밝은 자연광이 드는 미니멀한 홈오피스에 어울리는 화이트 톤 워크체어입니다."
--    mood_tags    : ["미니멀","내추럴","홈오피스","밝은 톤"]
-- ------------------------------------------------------------
CREATE TABLE detected_object (
    object_id      BIGSERIAL    PRIMARY KEY,
    scene_image_id BIGINT       NOT NULL REFERENCES scene_image(scene_image_id) ON DELETE CASCADE,
    category       VARCHAR(50),
    sub_category   VARCHAR(50),
    category_meta  JSONB,
    confidence     NUMERIC(4,3) NOT NULL,
    bbox_ymin      SMALLINT     NOT NULL,
    bbox_xmin      SMALLINT     NOT NULL,
    bbox_ymax      SMALLINT     NOT NULL,
    bbox_xmax      SMALLINT     NOT NULL,
    attributes     JSONB,
    mood_summary   TEXT,
    mood_tags      JSONB,
    crop_url       TEXT,
    embedding      VECTOR(3072),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_object_bbox  CHECK (bbox_ymin < bbox_ymax AND bbox_xmin < bbox_xmax),
    CONSTRAINT ck_object_range CHECK (bbox_ymin >= 0 AND bbox_xmin >= 0
                                  AND bbox_ymax <= 1000 AND bbox_xmax <= 1000),
    CONSTRAINT ck_object_conf  CHECK (confidence BETWEEN 0 AND 1)
);

CREATE INDEX idx_object_scene ON detected_object(scene_image_id);

COMMENT ON TABLE  detected_object               IS '탐지된 가구 객체 = 크롭 패치';
COMMENT ON COLUMN detected_object.category      IS '대분류 - Top-K 검색의 필터 조건';
COMMENT ON COLUMN detected_object.sub_category  IS '소분류 - 화면 표시·점수 가중치용';
COMMENT ON COLUMN detected_object.category_meta IS '분류 신뢰도·근거 {"confidence":0.95,"reason":"..."}';
COMMENT ON COLUMN detected_object.confidence    IS '탐지 신뢰도, 0.5 미만은 저장하지 않음';
COMMENT ON COLUMN detected_object.bbox_ymin     IS '0~1000 정규화 좌표';
COMMENT ON COLUMN detected_object.attributes    IS '추출 속성 - sku_catalog.attributes 와 같은 키 체계';
COMMENT ON COLUMN detected_object.mood_summary  IS '객체 단위 분위기 한 줄 요약';
COMMENT ON COLUMN detected_object.mood_tags     IS '분위기 태그 배열';
COMMENT ON COLUMN detected_object.crop_url      IS '잘라낸 객체 이미지 경로/URL';
COMMENT ON COLUMN detected_object.embedding     IS '크롭 이미지 벡터 - 검색 쿼리로 사용 (인덱스 불필요)';

-- ------------------------------------------------------------
-- 4. sku_catalog : 상품 마스터 + 속성 (FT-CAT-002/003)
-- ------------------------------------------------------------
CREATE TABLE sku_catalog (
    sku_id       BIGSERIAL    PRIMARY KEY,
    sku_code     VARCHAR(50)  NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    brand        VARCHAR(100),
    price        INT,
    space        VARCHAR(50),
    category     VARCHAR(50),
    sub_category VARCHAR(50),
    attributes   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 부분일치·대소문자 무시 검색 (FT-CAT-002)
CREATE INDEX idx_sku_name_trgm ON sku_catalog USING GIN (lower(product_name) gin_trgm_ops);
CREATE INDEX idx_sku_code_trgm ON sku_catalog USING GIN (lower(sku_code) gin_trgm_ops);
CREATE INDEX idx_sku_attr      ON sku_catalog USING GIN (attributes jsonb_path_ops);
CREATE INDEX idx_sku_category  ON sku_catalog(category);

COMMENT ON TABLE  sku_catalog              IS '상품 마스터 + 속성';
COMMENT ON COLUMN sku_catalog.sku_code     IS '상품 코드, 중복 불가 - 검색 대상';
COMMENT ON COLUMN sku_catalog.product_name IS '상품명 - 부분일치 검색 대상';
COMMENT ON COLUMN sku_catalog.category     IS '상품 대분류 - Top-K 필터 조건';
COMMENT ON COLUMN sku_catalog.attributes   IS '상품 속성 - 객체 속성과 같은 키 체계';

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
                 CHECK (image_type IN ('MAIN','ANGLE','DETAIL','STYLING')),
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
--    detected_object 1 : 0..1  (object_id UNIQUE → 객체당 최대 1건)
--    이미지 1장에서 객체 N개를 태깅하면 N행이 생성됨
--
--    xai_result 구조 (루브릭 채점, PoC vlm_client.py 기준)
--      { "structure": 29, "color":  7, "detail": 17, "context": 15,
--        "total": 68, "verdict": "REVIEW",
--        "reason": "등받이 곡률·암레스트 각도 등 구조는 거의 동일하나
--                   연출샷은 화이트 바디, 해당 SKU 는 올 블랙 모델입니다." }
--      배점 : structure 30 / color 30 / detail 20 / context 20 = 100
--      판정 : total >= 70 MATCH · 55~69 REVIEW · 55 미만 REJECT
--      카탈로그 검색으로 직접 지정한 건은 채점을 돌리지 않으므로 NULL
-- ------------------------------------------------------------
CREATE TABLE tagging_result (
    result_id        BIGSERIAL   PRIMARY KEY,
    scene_image_id   BIGINT      NOT NULL REFERENCES scene_image(scene_image_id),
    object_id        BIGINT      NOT NULL UNIQUE REFERENCES detected_object(object_id),
    sku_id           BIGINT      NOT NULL REFERENCES sku_catalog(sku_id),
    sku_image_id     BIGINT      REFERENCES sku_image(sku_image_id),
    match_source     VARCHAR(20) NOT NULL
                     CHECK (match_source IN ('RECOMMEND','SEARCH')),
    match_rank       SMALLINT,
    similarity_score NUMERIC(6,4),
    similarity_grade CHAR(1)     CHECK (similarity_grade IN ('상','중','하')),
    xai_result       JSONB,
    created_by       BIGINT      NOT NULL REFERENCES app_user(user_id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 검색 경유는 순위·유사도·근거가 없고, 추천 경유는 순위·유사도가 반드시 있어야 함
    CONSTRAINT ck_result_source CHECK (
        (match_source = 'SEARCH'
             AND match_rank IS NULL AND similarity_score IS NULL AND xai_result IS NULL)
     OR (match_source = 'RECOMMEND'
             AND match_rank IS NOT NULL AND similarity_score IS NOT NULL)
    ),
    CONSTRAINT ck_result_score CHECK (similarity_score IS NULL OR similarity_score BETWEEN 0 AND 1),
    -- 루브릭이 기록됐다면 총점 0~100, 판정값은 3종 중 하나
    CONSTRAINT ck_result_xai CHECK (
        xai_result IS NULL OR (
            (xai_result->>'total')::int BETWEEN 0 AND 100
        AND xai_result->>'verdict' IN ('MATCH','REVIEW','REJECT')
        )
    )
);

CREATE INDEX idx_result_user_created ON tagging_result(created_by, created_at DESC);
CREATE INDEX idx_result_scene        ON tagging_result(scene_image_id);
CREATE INDEX idx_result_sku          ON tagging_result(sku_id);

COMMENT ON TABLE  tagging_result                  IS '최종 객체-SKU 매핑 + 검수 이력';
COMMENT ON COLUMN tagging_result.object_id        IS '대상 객체 - 객체당 1건만 (UNIQUE)';
COMMENT ON COLUMN tagging_result.sku_image_id     IS '매칭 근거가 된 SKU 이미지';
COMMENT ON COLUMN tagging_result.match_source     IS 'RECOMMEND(추천 경유) | SEARCH(카탈로그 검색 경유)';
COMMENT ON COLUMN tagging_result.match_rank       IS '선택 시점의 추천 순위';
COMMENT ON COLUMN tagging_result.similarity_score IS '선택 시점의 임베딩 유사도 (0~1)';
COMMENT ON COLUMN tagging_result.similarity_grade IS '화면 표시용 등급 상/중/하';
COMMENT ON COLUMN tagging_result.xai_result       IS '루브릭 채점 결과 - 위 주석의 JSON 구조 참고';

-- ------------------------------------------------------------
-- 7. approval : 객체-SKU 매칭(tagging_result) 단위 승인 요청
--    tagging_result와 마찬가지로 scene_image_id/object_id를 함께 FK로
--    가져와서, 목록/조인 시 detected_object를 거치지 않고도 어느
--    연출 이미지의 요청인지 바로 알 수 있게 한다.
-- ------------------------------------------------------------
CREATE TABLE approval (
    request_id     BIGSERIAL   PRIMARY KEY,
    scene_image_id BIGINT      NOT NULL REFERENCES scene_image(scene_image_id) ON DELETE CASCADE,
    object_id      BIGINT      NOT NULL REFERENCES detected_object(object_id) ON DELETE CASCADE,
    status         VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    requested_by   BIGINT      NOT NULL REFERENCES app_user(user_id),
    requested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by    BIGINT      REFERENCES app_user(user_id),
    reviewed_at    TIMESTAMPTZ,
    reject_reason  VARCHAR(255),
    CONSTRAINT ck_approval_status CHECK (status IN ('PENDING','ACTIVE','REJECTED','NO_SKU')),
    -- 처리된 건은 검수자·일시가 필수, 반려는 사유까지 필수
    -- NO_SKU는 매칭 대상 tagging_result가 없는 상태로 생길 수 있어
    -- 검수자·일시를 강제하지 않는다(태깅 시점에 바로 생길 수도 있음).
    CONSTRAINT ck_approval_reviewed CHECK (
        (status = 'PENDING'  AND reviewed_by IS NULL AND reviewed_at IS NULL AND reject_reason IS NULL)
     OR (status = 'ACTIVE'   AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
     OR (status = 'REJECTED' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
                             AND reject_reason IS NOT NULL)
     OR (status = 'NO_SKU')
    )
);

-- 같은 객체에 PENDING은 1건만. 반려 후 재요청은 허용된다.
CREATE UNIQUE INDEX uq_approval_pending
    ON approval(object_id) WHERE status = 'PENDING';

CREATE INDEX idx_approval_status_req ON approval(status, requested_at DESC);
CREATE INDEX idx_approval_scene       ON approval(scene_image_id);

COMMENT ON TABLE  approval               IS '객체-SKU 매칭(tagging_result) 단위 승인 요청';
COMMENT ON COLUMN approval.request_id    IS '승인 요청 고유 번호';
COMMENT ON COLUMN approval.object_id     IS '승인 대상 탐지 객체 - 객체 단위로 개별 승인/반려';
COMMENT ON COLUMN approval.status        IS 'PENDING | ACTIVE | REJECTED | NO_SKU';
COMMENT ON COLUMN approval.requested_by  IS '태깅을 저장한 작업자';
COMMENT ON COLUMN approval.reviewed_by   IS '승인·반려를 수행한 사용자';

-- sku_image 멱등성 인덱스: confirm이 두 번 호출돼도 같은 크롭이 중복 등록되지 않는다.
CREATE UNIQUE INDEX uq_sku_image_sku_url ON sku_image(sku_id, image_url);
