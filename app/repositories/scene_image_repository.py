"""장면 이미지 조회와 객체 메타데이터 저장소입니다.

NOTE: 기존 저장소 모듈에 태깅 편집 결과 저장 기능을 추가한 변경입니다.
"""

import typing

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scene_image import SceneImage


class SceneImageNotFoundError(RuntimeError):
    """존재하지 않는 scene_image_id로 조회한 경우입니다."""


async def get_scene_image(
    session: AsyncSession, scene_image_id: int
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


async def update_scene_object_metadata(
    session: AsyncSession,
    scene_image_id: int,
    objects: list[dict[str, typing.Any]],
) -> SceneImage:
    """편집된 탐지 객체 목록을 장면 이미지에 저장합니다.

    ``object_idx``는 object_metadata 배열의 위치와 항상 일치하도록 서버에서
    다시 부여합니다. 이후 SKU 추천과 확정 API가 같은 인덱스를 사용합니다.
    """
    scene_image = await get_scene_image(session, scene_image_id)
    scene_image.object_metadata = [
        {
            "object_idx": object_index,
            "bbox_coord": {
                "xmin": object["bbox"]["xmin"],
                "ymin": object["bbox"]["ymin"],
                "xmax": object["bbox"]["xmax"],
                "ymax": object["bbox"]["ymax"],
            },
            "attribute": {"label": object["label"]},
        }
        for object_index, object in enumerate(objects)
    ]
    scene_image.analysis_status = "detected"
    scene_image.analysis_error = None
    await session.commit()
    return scene_image
