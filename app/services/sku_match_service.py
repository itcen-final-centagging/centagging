"""탐지 객체별 SKU 확정 결과를 tagging_result에 저장하는 서비스입니다."""

import logging

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.models.app_user import AppUser
from app.models.tagging_result import TaggingResult
from app.repositories.scene_image_repository import add_detected_object_metadata
from app.repositories.tagging_history_repository import add_tagging_results
from app.schemas.tagging import SkuMatching


class SceneImageNotFoundError(RuntimeError):
    """존재하지 않는 scene_image_id로 확정을 시도한 경우입니다."""


class ObjectIdxOutOfRangeError(RuntimeError):
    """장면에 존재하지 않는 object_idx를 확정하려는 경우입니다."""


class DuplicateObjectIdxError(RuntimeError):
    """한 요청에 같은 object_idx가 두 번 들어온 경우입니다."""


class MatchingTargetNotFoundError(RuntimeError):
    """sku_id 또는 활성 사용자를 찾지 못한 경우입니다."""


_SELECT_SCENE = sqlalchemy.text("""
    SELECT jsonb_array_length(object_metadata) AS object_count
      FROM scene_image
     WHERE scene_image_id = :scene_image_id
    """)

_UPDATE_SCENE_COMPLETED = sqlalchemy.text("""
    UPDATE scene_image
       SET analysis_status = :analysis_status,
           analysis_error = :analysis_error
     WHERE scene_image_id = :scene_image_id
    """)

_MATCHING_CHANGED_SQL = """
    ROW(
        tagging_result.sku_id,
        tagging_result.sku_image_id,
        tagging_result.match_source,
        tagging_result.match_rank,
        tagging_result.similarity_score,
        tagging_result.xai_result,
        tagging_result.vlm_mood,
        tagging_result.created_by
    ) IS DISTINCT FROM ROW(
        EXCLUDED.sku_id,
        EXCLUDED.sku_image_id,
        EXCLUDED.match_source,
        EXCLUDED.match_rank,
        EXCLUDED.similarity_score,
        EXCLUDED.xai_result,
        EXCLUDED.vlm_mood,
        EXCLUDED.created_by
    )
"""

# sku_code -> sku_id, 대표 이미지, 작업자를 조인 한 번으로 채워 넣습니다.
# sku_image는 MAIN을 우선하고 없으면 가장 낮은 ID를 대표로 씁니다.
_UPSERT_TAGGING_RESULT = sqlalchemy.text(f"""
    INSERT INTO tagging_result (
        scene_image_id,
        object_idx,
        sku_id,
        sku_image_id,
        match_source,
        match_rank,
        similarity_score,
        xai_result,
        vlm_mood,
        created_by
    )
    SELECT :scene_image_id,
           :object_idx,
           sc.sku_id,
           (
               SELECT si.sku_image_id
                 FROM sku_image si
                WHERE si.sku_id = sc.sku_id
                ORDER BY (si.image_type <> 'MAIN'), si.sku_image_id
                LIMIT 1
           ),
           :match_source,
           :match_rank,
           :similarity_score,
           CAST(:xai_result AS jsonb),
           CAST(:vlm_mood AS jsonb),
           au.user_id
      FROM sku_catalog sc
      CROSS JOIN app_user au
     WHERE sc.sku_code = :sku_code
       AND au.login_id = :login_id
       AND au.is_active = TRUE
    ON CONFLICT (scene_image_id, object_idx)
    DO UPDATE SET
        sku_id = EXCLUDED.sku_id,
        sku_image_id = EXCLUDED.sku_image_id,
        match_source = EXCLUDED.match_source,
        match_rank = EXCLUDED.match_rank,
        similarity_score = EXCLUDED.similarity_score,
        xai_result = EXCLUDED.xai_result,
        vlm_mood = EXCLUDED.vlm_mood,
        created_by = EXCLUDED.created_by,
        similarity_grade = CASE
            WHEN {_MATCHING_CHANGED_SQL}
            THEN NULL
            ELSE tagging_result.similarity_grade
        END,
        status = CASE
            WHEN {_MATCHING_CHANGED_SQL}
            THEN 'PENDING'
            ELSE tagging_result.status
        END
    RETURNING result_id
    """)

_CREATE_PENDING_APPROVAL = sqlalchemy.text("""
    INSERT INTO approval (
        tagging_result_id,
        scene_image_id,
        object_idx,
        requested_by,
        status
    )
    SELECT tr.result_id,
           tr.scene_image_id,
           tr.object_idx,
           tr.created_by,
           'PENDING'
      FROM tagging_result tr
     WHERE tr.result_id = :result_id
    ON CONFLICT DO NOTHING
    """)

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
            ObjectIdxOutOfRangeError: 장면에 없는 인덱스인 경우입니다.
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
                object_metadatas.append(
                    tagging_result.object_metadata.model_dump()
                )
                results.append(
                    TaggingResult(
                        scene_image_id=scene_id,
                        object_idx=tagging_result.object_idx,
                        sku_id=tagging_result.sku_id,
                        sku_image_id=tagging_result.sku_image_id,
                        match_source=tagging_result.match_source,
                        match_rank=tagging_result.match_rank,
                        status="PENDING",
                        similarity_score=(
                            tagging_result.similarity_score / 100
                            if tagging_result.similarity_score is not None
                            else None
                        ),
                        xai_result=(
                            tagging_result.xai_result.model_dump()
                            if tagging_result.xai_result is not None
                            else None
                        ),
                        vlm_mood=tagging_result.vlm_mood.model_dump(),
                        created_by=user_id,
                    )
                )
            await add_detected_object_metadata(
                self.session, scene_id, object_metadatas
            )
            return await add_tagging_results(self.session, results)
