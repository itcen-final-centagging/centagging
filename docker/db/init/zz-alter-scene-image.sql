-- Existing database migration for SCRUM-60 US-02-T2.
-- Every statement is safe to run repeatedly.

ALTER TABLE scene_image
    ADD COLUMN IF NOT EXISTS width_px INT;

ALTER TABLE scene_image
    ADD COLUMN IF NOT EXISTS height_px INT;

ALTER TABLE scene_image
    ADD COLUMN IF NOT EXISTS analysis_status VARCHAR(20)
        NOT NULL DEFAULT 'PENDING';

ALTER TABLE scene_image
    ADD COLUMN IF NOT EXISTS analysis_error TEXT;
