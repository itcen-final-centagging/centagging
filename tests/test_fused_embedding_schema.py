"""융합 임베딩 저장 스키마 계약 테스트입니다."""

from pathlib import Path

from app.models.sku import SkuImage

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_sku_image_model_reuses_embedding_with_tracking_columns() -> None:
    """ORM이 기존 벡터와 융합 파이프라인 추적 컬럼을 노출한다."""
    column_names = set(SkuImage.__table__.columns.keys())

    assert {
        "embedding",
        "embedding_pipeline_version",
        "embedding_image_sha256",
    } <= (column_names)
    assert "fused_embedding" not in column_names


def test_initial_schema_and_migration_reuse_embedding_storage() -> None:
    """신규 DB와 기존 DB가 기존 벡터 컬럼을 융합 임베딩에 재사용한다."""
    initial_schema = (
        PROJECT_ROOT / "docker" / "db" / "init" / "schema.sql"
    ).read_text(encoding="utf-8")
    migration = (
        PROJECT_ROOT
        / "docker"
        / "db"
        / "migrations"
        / "20260821_fused_embedding.sql"
    ).read_text(encoding="utf-8")

    for sql in (initial_schema, migration):
        assert "embedding_pipeline_version" in sql
        assert "embedding_image_sha256" in sql
        assert "fused_embedding" not in sql


def test_migration_service_runs_all_versioned_migrations() -> None:
    """배포 시 새 마이그레이션이 기존 DB에도 적용된다."""
    compose_file = (PROJECT_ROOT / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    production_compose_file = (
        PROJECT_ROOT / "docker-compose.prod.yml"
    ).read_text(encoding="utf-8")

    assert "for migration in /migrations/*.sql" in compose_file
    assert "for migration in /migrations/*.sql" in production_compose_file
