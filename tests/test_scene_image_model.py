"""연출 이미지 ORM 모델의 참조 테이블 등록을 검증합니다."""

import unittest

from app.models.scene_image import SceneImage
from app.models.sku import Base


class SceneImageModelTest(unittest.TestCase):
    """Worker처럼 제한된 모델만 가져오는 실행 경로를 검증합니다."""

    def test_registers_referenced_app_user_table(self) -> None:
        """scene_image 외래키가 참조하는 app_user 테이블도 등록됩니다."""
        self.assertIn("scene_image", Base.metadata.tables)
        self.assertIn("app_user", Base.metadata.tables)
        self.assertIsNotNone(SceneImage.__table__.foreign_keys)


if __name__ == "__main__":
    unittest.main()
