"""SQLAlchemy ORM 모델을 한 번에 등록합니다.

외래 키는 SQLAlchemy ``Base.metadata``에 대상 테이블이 등록된 뒤에만
해석됩니다. 이 패키지를 import하면 모든 ORM 모델이 같은 metadata에
등록되므로 import 순서에 따라 외래 키 해석이 실패하지 않습니다.
"""

# pylint: disable=unused-import
from app.models.app_user import AppUser
from app.models.scene_image import SceneImage
from app.models.sku import SkuCatalog, SkuImage
from app.models.tagging_result import TaggingResult

__all__ = [
    "AppUser",
    "SceneImage",
    "SkuCatalog",
    "SkuImage",
    "TaggingResult",
]
