-- SCRUM-170: 기존 embedding 컬럼을 융합 임베딩으로 전환하기 위한 추적 정보
-- 벡터는 기존 컬럼을 재사용하고, 재색인 여부 판단에 필요한 정보만 추가한다.
BEGIN;

ALTER TABLE sku_image
    ADD COLUMN IF NOT EXISTS embedding_pipeline_version VARCHAR(50),
    ADD COLUMN IF NOT EXISTS embedding_image_sha256 TEXT;

COMMENT ON COLUMN sku_image.embedding
    IS '보정 RGB·그레이·메타데이터 융합 벡터';
COMMENT ON COLUMN sku_image.embedding_pipeline_version
    IS 'embedding 생성 파이프라인 버전';
COMMENT ON COLUMN sku_image.embedding_image_sha256
    IS 'embedding 생성에 사용한 보정 이미지 SHA-256';

COMMIT;
