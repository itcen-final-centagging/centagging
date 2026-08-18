"""SQLAlchemy ORM 모델 등록을 검증합니다."""

import unittest

import app.models
from app.models.sku import Base


class ModelRegistryTest(unittest.TestCase):
    """외래 키 대상 모델이 metadata에 항상 등록되는지 검증합니다."""

    def test_registers_foreign_key_target_models(self) -> None:
        """scene_image 외래 키가 app_user 테이블을 해석할 수 있어야 합니다."""
        table_names = {table.name for table in Base.metadata.sorted_tables}

        self.assertIn("app_user", table_names)
        self.assertIn("scene_image", table_names)
