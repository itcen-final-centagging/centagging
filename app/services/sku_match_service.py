"""탐지 객체별 SKU 확정 결과를 tagging_result에 저장하는 서비스입니다."""

import json
import logging

import sqlalchemy
from sqlalchemy.ext import asyncio as sqlalchemy_async

from app.core import config
from app.schemas.tagging import SkuMatching


class SceneImageNotFoundError(RuntimeError):
    """존재하지 않는 scene_image_id로 확정을 시도한 경우입니다."""


class ObjectIndexOutOfRangeError(RuntimeError):
    """장면에 존재하지 않는 object_index를 확정하려는 경우입니다."""


class DuplicateObjectIndexError(RuntimeError):
    """한 요청에 같은 object_index가 두 번 들어온 경우입니다."""


class MatchingTargetNotFoundError(RuntimeError):
    """sku_code 또는 활성 사용자를 찾지 못한 경우입니다."""


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
        tagging_result.xai_status,
        tagging_result.xai_fallback_reason,
        tagging_result.vlm_mood,
        tagging_result.created_by
    ) IS DISTINCT FROM ROW(
        EXCLUDED.sku_id,
        EXCLUDED.sku_image_id,
        EXCLUDED.match_source,
        EXCLUDED.match_rank,
        EXCLUDED.similarity_score,
        EXCLUDED.xai_result,
        EXCLUDED.xai_status,
        EXCLUDED.xai_fallback_reason,
        EXCLUDED.vlm_mood,
        EXCLUDED.created_by
    )
"""

# sku_code -> sku_id, 대표 이미지, 작업자를 조인 한 번으로 채워 넣습니다.
# sku_image는 MAIN을 우선하고 없으면 가장 낮은 ID를 대표로 씁니다.
_UPSERT_TAGGING_RESULT = sqlalchemy.text(f"""
    INSERT INTO tagging_result (
        scene_image_id,
        object_index,
        sku_id,
        sku_image_id,
        match_source,
        match_rank,
        similarity_score,
        xai_result,
        xai_status,
        xai_fallback_reason,
        vlm_mood,
        created_by
    )
    SELECT :scene_image_id,
           :object_index,
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
           :xai_status,
           :xai_fallback_reason,
           CAST(:vlm_mood AS jsonb),
           au.user_id
      FROM sku_catalog sc
      CROSS JOIN app_user au
     WHERE sc.sku_code = :sku_code
       AND au.login_id = :login_id
       AND au.is_active = TRUE
    ON CONFLICT (scene_image_id, object_index)
    DO UPDATE SET
        sku_id = EXCLUDED.sku_id,
        sku_image_id = EXCLUDED.sku_image_id,
        match_source = EXCLUDED.match_source,
        match_rank = EXCLUDED.match_rank,
        similarity_score = EXCLUDED.similarity_score,
        xai_result = EXCLUDED.xai_result,
        xai_status = EXCLUDED.xai_status,
        xai_fallback_reason = EXCLUDED.xai_fallback_reason,
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

    async def confirm_matching(
        self,
        scene_id: int,
        matching: list[SkuMatching],
    ) -> list[int]:
        """요청받은 객체-SKU 매핑을 확정하고 result_id를 반환합니다.

        중간에 실패하면 전체를 롤백해 부분 저장을 남기지 않습니다.

        Args:
            scene_id: 확정할 장면 이미지 ID입니다.
            matching: 확정할 객체-SKU 매핑 목록입니다.

        Returns:
            저장된 tagging_result의 result_id 목록입니다. 요청과 같은
            순서로 돌려줍니다.

        Raises:
            SceneImageNotFoundError: 장면 이미지가 없는 경우입니다.
            DuplicateObjectIndexError: object_index가 중복된 경우입니다.
            ObjectIndexOutOfRangeError: 장면에 없는 인덱스인 경우입니다.
            MatchingTargetNotFoundError: sku_code나 활성 사용자를 찾지
                못한 경우입니다.
        """
        try:
            object_count = await self._get_object_count(scene_id)
            self._validate_object_indexes(matching, object_count)

            result_ids = []
            for item in matching:
                result_ids.append(await self._upsert_matching(scene_id, item))

            await self._mark_scene_completed(scene_id)
            await self.session.commit()

            return result_ids
        # 부분 저장을 남기지 않도록 어떤 실패든 롤백 후 다시 던집니다.
        except Exception:  # pylint: disable=broad-exception-caught
            await self._rollback()
            raise

    async def _get_object_count(self, scene_id: int) -> int:
        """장면 이미지의 탐지 객체 개수를 조회합니다.

        Args:
            scene_id: 조회할 장면 이미지 ID입니다.

        Returns:
            object_metadata 배열의 길이입니다.

        Raises:
            SceneImageNotFoundError: 장면 이미지가 없는 경우입니다.
        """
        result = await self.session.execute(
            _SELECT_SCENE,
            {"scene_image_id": scene_id},
        )
        row = result.mappings().first()
        if row is None:
            raise SceneImageNotFoundError(scene_id)

        return int(row["object_count"] or 0)

    @staticmethod
    def _validate_object_indexes(
        matching: list[SkuMatching],
        object_count: int,
    ) -> None:
        """object_index의 중복과 범위를 검증합니다.

        Args:
            matching: 확정할 객체-SKU 매핑 목록입니다.
            object_count: 장면에 탐지된 객체 개수입니다.

        Raises:
            DuplicateObjectIndexError: object_index가 중복된 경우입니다.
            ObjectIndexOutOfRangeError: 장면에 없는 인덱스인 경우입니다.
        """
        indexes = [item.object_index for item in matching]
        duplicates = {i for i in indexes if indexes.count(i) > 1}
        if duplicates:
            raise DuplicateObjectIndexError(sorted(duplicates))

        out_of_range = [i for i in indexes if i >= object_count]
        if out_of_range:
            raise ObjectIndexOutOfRangeError(sorted(out_of_range))

    async def _upsert_matching(
        self,
        scene_id: int,
        item: SkuMatching,
    ) -> int:
        """매핑 1건을 저장하거나 갱신하고 result_id를 반환합니다.

        Args:
            scene_id: 확정할 장면 이미지 ID입니다.
            item: 확정할 객체-SKU 매핑 1건입니다.

        Returns:
            새로 생성하거나 기존에 유지한 tagging_result의 result_id입니다.

        Raises:
            MatchingTargetNotFoundError: sku_code가 없거나 활성 사용자를
                찾지 못해 INSERT 대상이 0건인 경우입니다.
        """
        result = await self.session.execute(
            _UPSERT_TAGGING_RESULT,
            {
                "scene_image_id": scene_id,
                "object_index": item.object_index,
                "sku_code": item.sku_code,
                "login_id": self.settings.mvp_login_id,
                "match_source": "RECOMMEND",
                "match_rank": item.match_rank,
                "similarity_score": item.similarity_score / 100,
                "xai_result": json.dumps(
                    item.xai_result.model_dump(exclude={"vlm_mood"}),
                    ensure_ascii=False,
                ),
                "xai_status": item.xai_status,
                "xai_fallback_reason": item.xai_fallback_reason,
                "vlm_mood": json.dumps(
                    item.vlm_mood.model_dump(), ensure_ascii=False
                ),
            },
        )
        result_id = result.scalar_one_or_none()
        if result_id is None:
            raise MatchingTargetNotFoundError(item.sku_code)

        return int(result_id)

    async def _mark_scene_completed(self, scene_id: int) -> None:
        """태깅 결과가 저장된 연출 이미지의 처리를 완료합니다.

        Args:
            scene_id: 완료 상태로 변경할 장면 이미지 ID입니다.
        """
        await self.session.execute(
            _UPDATE_SCENE_COMPLETED,
            {
                "scene_image_id": scene_id,
                "analysis_status": "completed",
                "analysis_error": None,
            },
        )

    async def _rollback(self) -> None:
        """실패한 트랜잭션을 안전하게 되돌립니다."""
        try:
            await self.session.rollback()
        # 원래 오류를 유지하되 rollback 실패도 로그로 남깁니다.
        except Exception:  # pylint: disable=broad-exception-caught
            _LOGGER.exception("SKU 확정 트랜잭션 rollback에 실패했습니다.")
