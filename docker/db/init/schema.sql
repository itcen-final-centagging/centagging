-- ============================================================
-- CenTagging MVP — 물리 스키마 v6 (PostgreSQL 16 + pgvector)
-- 총 6개 테이블 · 프로토타입 v4 기준 확정본
--
-- 실행
--   psql -U <user> -d <db> -f schema.sql
--   psql -U <user> -d <db> -f seed.sql      (데모 데이터, 선택)
--
-- v6 변경점
--   · xai_result 구조 확정 (프로토타입 루브릭 반영)
--       structure 30 / color 30 / detail 20 / context 20 = 100
--       70 이상 MATCH · 55~69 REVIEW · 55 미만 REJECT
--   · sku_image.embedding 을 NULL 허용으로 변경
--       상품·이미지 등록과 임베딩 색인 배치를 분리 실행하기 위함
--       HNSW 는 부분 인덱스(WHERE embedding IS NOT NULL)로 생성
--
-- 전제
--   · 분석은 동기 API (FT-IMG-002, 30s) — 진행 상태를 DB에 남기지 않음
--   · 재탐지 1회 제한은 애플리케이션 상수(MAX_RETRY)로 관리
--   · 카탈로그에 존재 = 사용 가능 (판매 상태 개념 없음)
--   · 대표 이미지는 sku_image.image_type='MAIN' 중 최소 id 사용
--   · 임베딩 유사도(벡터)와 루브릭 총점(VLM 채점)은 별개 신호
-- ============================================================

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
    scene_image_id BIGSERIAL    PRIMARY KEY,
    user_id        BIGINT       NOT NULL REFERENCES app_user(user_id),
    image_url      TEXT         NOT NULL,
    origin_name    VARCHAR(255) NOT NULL,
    mime_type      VARCHAR(20)  NOT NULL,
    file_size      INT          NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_scene_mime CHECK (mime_type IN ('image/jpeg','image/png')),
    CONSTRAINT ck_scene_size CHECK (file_size > 0 AND file_size <= 10485760)
);

CREATE INDEX idx_scene_user_created ON scene_image(user_id, created_at DESC);

COMMENT ON TABLE  scene_image             IS '업로드된 연출 이미지';
COMMENT ON COLUMN scene_image.image_url   IS '원본 이미지 경로/URL';
COMMENT ON COLUMN scene_image.origin_name IS '사용자가 올린 원래 파일명';
COMMENT ON COLUMN scene_image.mime_type   IS 'image/jpeg | image/png';
COMMENT ON COLUMN scene_image.file_size   IS 'byte, 10MB 이하';

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

-- ============================================================
-- 참고 쿼리
-- ============================================================

-- [1] Top-K 유사 SKU 조회 (category pre-filter + 벡터 유사도)
--     $1 = 크롭 패치 임베딩, $2 = 크롭에서 추출한 대분류
--
-- SET hnsw.iterative_scan = relaxed_order;   -- 필터로 후보가 비는 것을 완화
--
-- SELECT DISTINCT ON (si.sku_id)
--        si.sku_id, si.sku_image_id, sc.sku_code, sc.product_name,
--        1 - (si.embedding::halfvec(3072) <=> $1::halfvec(3072)) AS similarity
--   FROM sku_image si
--   JOIN sku_catalog sc ON sc.sku_id = si.sku_id
--  WHERE si.embedding IS NOT NULL
--    AND sc.category = $2                    -- 소분류는 필터에 쓰지 않음
--  ORDER BY si.sku_id,
--           si.embedding::halfvec(3072) <=> $1::halfvec(3072)
--  LIMIT 30;   -- 넉넉히 뽑아 SKU 단위 중복 제거 후 상위 5건 사용

-- [2] 대표 이미지 조회 (image_type='MAIN' 중 최소 id)
--
-- SELECT DISTINCT ON (sku_id) sku_id, sku_image_id, image_url
--   FROM sku_image WHERE image_type = 'MAIN'
--  ORDER BY sku_id, sku_image_id;

-- [3] 태깅 이력 조회 (FT-SAV-003, 본인 건 최신순)
--
-- SELECT tr.result_id, tr.created_at, si.origin_name,
--        do.category, do.crop_url, do.mood_summary,
--        sc.sku_code, sc.product_name,
--        tr.match_source, tr.similarity_score, tr.similarity_grade,
--        (tr.xai_result->>'total')::int   AS rubric_total,
--        tr.xai_result->>'verdict'        AS rubric_verdict,
--        au.user_name
--   FROM tagging_result tr
--   JOIN scene_image     si ON si.scene_image_id = tr.scene_image_id
--   JOIN detected_object do ON do.object_id      = tr.object_id
--   JOIN sku_catalog     sc ON sc.sku_id         = tr.sku_id
--   JOIN app_user        au ON au.user_id        = tr.created_by
--  WHERE tr.created_by = $1
--  ORDER BY tr.created_at DESC;

-- [4] 카탈로그 검색 (FT-CAT-002, 부분일치·대소문자 무시·이름 오름차순)
--
-- SELECT sku_id, sku_code, product_name, brand, price, space
--   FROM sku_catalog
--  WHERE lower(sku_code)     LIKE '%' || lower($1) || '%'
--     OR lower(product_name) LIKE '%' || lower($1) || '%'
--  ORDER BY product_name
--  LIMIT 10 OFFSET $2;

-- [5] 미색인 SKU 이미지 (임베딩 배치가 처리할 대상)
--
-- SELECT sku_image_id, image_url FROM sku_image
--  WHERE embedding IS NULL AND image_type IN ('MAIN','ANGLE')
--  ORDER BY sku_image_id LIMIT 100;

-- [6] 추천 품질 지표 — Top-3 적중률 / 추천 경유 비율
--
-- SELECT count(*)                                                   AS total,
--        count(*) FILTER (WHERE match_source = 'RECOMMEND')          AS via_recommend,
--        count(*) FILTER (WHERE match_rank <= 3)                     AS in_top3,
--        round(avg(similarity_score) FILTER (WHERE match_source='RECOMMEND'), 4) AS avg_sim,
--        round(avg((xai_result->>'total')::int), 1)                  AS avg_rubric
--   FROM tagging_result;
