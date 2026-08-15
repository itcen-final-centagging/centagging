from sqlalchemy.ext.asyncio import AsyncSession
from app.models.scene_image import SceneImage

class SceneImageNotFoundError(RuntimeError):
    """존재하지 않는 scene_image_id로 조회한 경우입니다."""

async def get_scene_image(
        session: AsyncSession,
        scene_image_id: int
) -> SceneImage:
    """장면 이미지를 조회합니다.

    Args:
        session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
        scene_image_id: 조회할 장면 이미지 ID입니다.

    Returns:
        조회된 SceneImage 엔티티입니다.

    Raises:
        SceneImageNotFoundError: 해당 ID의 장면 이미지가 없는 경우입니다.
    """
    scene_image = await session.get(SceneImage, scene_image_id)

    if scene_image is None:
        raise SceneImageNotFoundError(scene_image_id)

    return scene_image