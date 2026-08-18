"""탐지 객체별 SKU 확정 결과를 tagging_result에 저장하는 서비스입니다."""

import typing
import decimal
import logging

import sqlalchemy
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.models.app_user import AppUser
from app.models.scene_image import SceneImage
from app.models.sku import SkuImage
from app.models.tagging_result import TaggingResult
from app.schemas.tagging import SkuMatching
from app.repositories.scene_image_repository import add_detected_object_metadata
from app.repositories.tagging_history_repository import add_tagging_results

class SceneImageNotFoundError(RuntimeError):
    """존재하지 않는 scene_image_id로 확정을 시도한 경우입니다."""


class ObjectIndexOutOfRangeError(RuntimeError):
    """장면에 존재하지 않는 object_index를 확정하려는 경우입니다."""


class DuplicateObjectIndexError(RuntimeError):
    """한 요청에 같은 object_index가 두 번 들어온 경우입니다."""


class MatchingTargetNotFoundError(RuntimeError):
    """sku_id 또는 활성 사용자를 찾지 못한 경우입니다."""


_LOGGER = logging.getLogger(__name__)


# 확정 저장이라는 단일 책임만 갖는 서비스라 공개 메서드가 하나뿐입니다.
class SkuMatchService:  # pylint: disable=too-few-public-methods
    """탐지 객체와 SKU의 최종 매핑을 저장합니다."""

    def __init__(
        self,
        session: sqlalchemy_async.AsyncSession,
        settings: config.Settings,
    ) -> None:
        """서비스가 사용할 세션과 설정을 주입받습니다.

        Args:
            session: 요청 범위의 비동기 SQLAlchemy 세션입니다.
            settings: 고정 사용자 로그인 ID가 담긴 애플리케이션 설정입니다.
        """
        self.session = session
        self.settings = settings

    async def save_tagging_results(
        self,
        scene_id: int,
        tagging_results: list[SkuMatching],
    ) -> list[int]:
        """객체 메타데이터를 갱신하고 확정 매핑을 저장합니다.

        Args:
            scene_id: 확정할 장면 이미지 ID입니다.
            tagging_results: 확정할 객체-SKU 매핑 목록입니다.

        Returns:
            저장된 tagging_result의 result_id 목록입니다.

        Raises:
            SceneImageNotFoundError: 장면 이미지가 없는 경우입니다.
            ObjectIndexOutOfRangeError: 장면에 없는 인덱스인 경우입니다.
            MatchingTargetNotFoundError: 활성 사용자가 없는 경우입니다.
        """
        async with self.session.begin():
            object_metadatas = []
            results = []
            user_result = await self.session.execute(
                sqlalchemy.select(AppUser.user_id).where(
                    AppUser.login_id == self.settings.mvp_login_id,
                    AppUser.is_active.is_(True),
                )
            )
            user_id = user_result.scalar_one_or_none()
            for tagging_result in tagging_results:
                object_metadatas.append(tagging_result.object_metadata.model_dump())
                results.append(TaggingResult(
                    scene_image_id=scene_id,
                    object_index=tagging_result.object_index,
                    sku_id=tagging_result.sku_id,
                    match_source="RECOMMEND",
                    match_rank=tagging_result.match_rank,
                    status="PENDING",
                    similarity_score=tagging_result.similarity_score / 100,
                    xai_result=tagging_result.xai_result.model_dump(),
                    vlm_mood=tagging_result.vlm_mood.model_dump(),
                    created_by=user_id
                ))
            await add_detected_object_metadata(
                self.session,
                scene_id,
                object_metadatas)
            return await add_tagging_results(self.session, results)