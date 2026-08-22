"""전체 SKU에 데모용 공간 분위기·스타일 태그를 채우는 일회성 시드 스크립트입니다.

승인(ACTIVE) 이력이 없는 SKU는 검색 결과·상세 페이지에 공간 분위기·스타일
태그가 빈 상태로 보인다. 데모 목적으로, SKU마다 Gemini가 상품 정보만 보고
그럴듯한 공간 분위기 요약과 스타일 태그를 지어내게 한 뒤, 그 값을 담은
tagging_result·approval(ACTIVE) 이력을 새로 만든다.

별도 DB 컬럼은 추가하지 않는다 — 기존 tagging_result.vlm_mood 구조
({"summary": str, "tags": [str, ...]})를 그대로 재사용하며, 이는
app.services.approval_service._reindex_sku_text_embedding이 승인 시점에
읽는 것과 같은 소스다.

이 스크립트는 vlm_mood만 채운다. sku_catalog.text_embedding에 반영하려면
실행이 끝난 뒤 반드시 아래 명령을 이어서 실행한다(기존 배치 재색인 경로):

    python -m scripts.embedding.build_embeddings --skip-images --force-text

주의:
    - 이 스크립트가 만드는 승인 이력은 실제 연출 이미지 없이 만든 가짜
      데이터이며, "검수 이력" 화면에 실제 이력과 함께 섞여 보인다.
    - 데모/PoC 용도로만 사용한다. Gemini 호출 비용이 SKU 수만큼 발생한다.

실행:
    python -m scripts.seed.seed_demo_vlm_moods
    python -m scripts.seed.seed_demo_vlm_moods --limit 20
    python -m scripts.seed.seed_demo_vlm_moods --dry-run
    python -m scripts.seed.seed_demo_vlm_moods --force
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime

import psycopg
from google import genai
from google.genai import types
from psycopg.types.json import Json

from app.core import config, genai_client
from app.schemas.tagging import VlmMood
from app.services.fused_metadata import build_metadata_text
from app.services.genai_retry import call_with_rate_limit_retry
from scripts.embedding import db, storage

# 고정 POC 사용자(app.services.user_seed) 중 승인 이력의 요청자·검토자로
# 쓸 계정입니다. 실제 최종 승인 화면과 같은 이름으로 보이도록 최종
# 관리자 계정을 그대로 씁니다.
_SEED_REVIEWER_LOGIN_ID = "super-admin"

_MOOD_PROMPT_TEMPLATE = """\
당신은 인테리어 스타일링 전문가입니다. 아래 가구 상품이 어느 공간에
연출된 사진을 봤다고 가정하고, 그 공간의 분위기와 상품의 스타일을
설명해 주세요. 실제 사진은 없으니 상품 정보만 보고 자연스럽게 어울릴
법한 분위기를 상상해서 답하세요.

[상품 정보]
{metadata_text}

요구사항:
- summary: 이 상품이 놓인 공간의 분위기를 한국어 한 문장으로
  서술하세요. (예: "따뜻하고 아늑한 톤의 거실")
- tags: 이 상품의 스타일을 나타내는 한국어 단어 정확히 5~7개 배열
  (5개 미만은 안 됩니다). 각 태그는 2~6자의 짧은 단어로 만드세요.
  (예: ["모던", "미니멀", "우드톤", "내추럴", "따뜻한"])
"""


@dataclasses.dataclass
class _SkuRow:
    """시드 대상 SKU 1건의 프롬프트 조립에 필요한 정보입니다."""

    sku_id: int
    sku_code: str
    product_name: str
    category: str | None
    sub_category: str | None
    brand: str | None
    price: int | None
    attributes: dict
    key_features: list


@dataclasses.dataclass
class _RunResult:
    """실행 결과 집계입니다."""

    total_skus: int = 0
    skipped_existing: int = 0
    seeded: int = 0
    failed: list[tuple[int, str]] = dataclasses.field(default_factory=list)


def fetch_all_skus(conn: psycopg.Connection) -> list[_SkuRow]:
    """카탈로그의 모든 SKU를 프롬프트 조립에 필요한 필드만 읽어옵니다."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT sku_id, sku_code, product_name, category, sub_category,
                   brand, price, attributes, key_features
              FROM sku_catalog
             ORDER BY sku_id
            """)
        return [
            _SkuRow(
                sku_id=row[0],
                sku_code=row[1],
                product_name=row[2],
                category=row[3],
                sub_category=row[4],
                brand=row[5],
                price=row[6],
                attributes=row[7] or {},
                key_features=row[8] or [],
            )
            for row in cur.fetchall()
        ]


def fetch_seed_reviewer_user_id(conn: psycopg.Connection) -> int:
    """가짜 승인 이력의 요청자·검토자로 쓸 고정 POC 사용자를 찾습니다."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT user_id FROM app_user WHERE login_id = %s",
            (_SEED_REVIEWER_LOGIN_ID,),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "고정 POC 사용자를 찾을 수 없습니다: "
            f"login_id={_SEED_REVIEWER_LOGIN_ID}. "
            "먼저 API 서버를 한 번 기동해 고정 사용자를 준비하세요."
        )
    return int(row[0])


def _build_prompt_text(sku: _SkuRow) -> str:
    """SKU 메타데이터를 프롬프트에 넣을 텍스트로 만듭니다.

    build_metadata_text는 catalog_spec에 정의된 카테고리가 아니면 빈
    문자열을 돌려준다. 그런 SKU도 시드는 계속 진행할 수 있도록, 상품명
    중심의 최소 설명으로 대체한다.
    """
    metadata_text = build_metadata_text(
        category=sku.category,
        sub_category=sku.sub_category,
        product_name=sku.product_name,
        brand=sku.brand,
        price=sku.price,
        attributes=sku.attributes,
    )
    if metadata_text.strip():
        return metadata_text
    fallback_parts = [
        part for part in (sku.product_name, sku.category, sku.brand) if part
    ]
    return " · ".join(fallback_parts) or sku.sku_code


def generate_vlm_mood(
    client: genai.Client, settings: config.Settings, sku: _SkuRow
) -> VlmMood:
    """SKU 메타데이터만 보고 그럴듯한 공간 분위기·스타일 태그를 지어냅니다."""
    prompt = _MOOD_PROMPT_TEMPLATE.format(metadata_text=_build_prompt_text(sku))

    response = call_with_rate_limit_retry(
        lambda: client.models.generate_content(
            model=settings.gemini_vlm_model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VlmMood,
            ),
        ),
        operation_name="seed_demo_vlm_mood",
    )
    if not response.text:
        raise RuntimeError("Gemini 응답이 비어 있습니다.")
    return VlmMood.model_validate_json(response.text)


def insert_seed_approval(
    conn: psycopg.Connection,
    *,
    sku_id: int,
    sku_code: str,
    reviewer_user_id: int,
    mood: VlmMood,
) -> None:
    """SKU 1건에 대한 가짜 연출 이미지·태깅 결과·ACTIVE 승인을 만듭니다.

    실제 이미지 크롭·임베딩 없이, 검색·상세 화면이 읽는
    tagging_result.vlm_mood + approval.status='ACTIVE' 조합만
    구성한다. SKU 1건마다 전용 scene_image를 새로 만들어 object_idx는
    항상 0을 쓴다(scene_image, object_idx 조합의 유일 제약을 단순하게
    지키기 위함이다).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scene_image (
                user_id, image_url, origin_name, mime_type, file_size,
                analysis_status, width_px, height_px
            )
            VALUES (%s, %s, %s, 'image/jpeg', 1, 'completed', 1, 1)
            RETURNING scene_image_id
            """,
            (
                reviewer_user_id,
                f"/uploads/seed/vlm-mood-seed-{sku_id}.jpg",
                f"seed-{sku_code}.jpg",
            ),
        )
        scene_row = cur.fetchone()
        assert scene_row is not None
        scene_image_id = scene_row[0]

        cur.execute(
            """
            INSERT INTO tagging_result (
                scene_image_id, object_idx, sku_id, match_source,
                vlm_mood, created_by
            )
            VALUES (%s, 0, %s, 'SEARCH', %s, %s)
            RETURNING result_id
            """,
            (
                scene_image_id,
                sku_id,
                Json(mood.model_dump()),
                reviewer_user_id,
            ),
        )
        result_row = cur.fetchone()
        assert result_row is not None
        result_id = result_row[0]

        cur.execute(
            """
            INSERT INTO approval (
                tagging_result_id, scene_image_id, object_index, status,
                requested_by, reviewed_by, reviewed_at
            )
            VALUES (%s, %s, 0, 'ACTIVE', %s, %s, %s)
            """,
            (
                result_id,
                scene_image_id,
                reviewer_user_id,
                reviewer_user_id,
                now,
            ),
        )


def print_summary(result: _RunResult) -> None:
    """실행 결과를 사람이 읽기 쉬운 형태로 출력합니다."""
    print("=== 데모 공간 분위기·스타일 태그 시드 결과 ===")
    print(f"전체 SKU: {result.total_skus}건")
    print(f"이미 ACTIVE 승인 있어 건너뜀: {result.skipped_existing}건")
    print(f"새로 시드함: {result.seeded}건")
    if result.failed:
        print(f"실패: {len(result.failed)}건")
        for sku_id, message in result.failed:
            print(f"  - sku_id={sku_id}: {message}")
    if result.seeded:
        print(
            "\n다음 명령으로 sku_catalog.text_embedding에 반영하세요:\n"
            "    python -m scripts.embedding.build_embeddings "
            "--skip-images --force-text"
        )


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=None, help="앞에서부터 N건만 처리"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 ACTIVE 승인된 vlm_mood가 있는 SKU도 새로 추가 시드",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Gemini 호출·DB 쓰기 없이 대상 건수만 확인",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = storage.get_settings()

    conn = db.connect(settings.database)
    try:
        skus = fetch_all_skus(conn)
        if args.limit is not None:
            skus = skus[: args.limit]

        already_active_sku_ids = (
            set()
            if args.force
            else set(db.fetch_active_vlm_moods_by_sku_id(conn).keys())
        )
        targets = [
            sku for sku in skus if sku.sku_id not in already_active_sku_ids
        ]
        result = _RunResult(
            total_skus=len(skus),
            skipped_existing=len(skus) - len(targets),
        )

        if args.dry_run:
            print(f"(dry-run) 시드 대상: {len(targets)}건")
            print_summary(result)
            return

        reviewer_user_id = fetch_seed_reviewer_user_id(conn)
        client = genai_client.create_client(settings)

        for index, sku in enumerate(targets, start=1):
            try:
                mood = generate_vlm_mood(client, settings, sku)
                insert_seed_approval(
                    conn,
                    sku_id=sku.sku_id,
                    sku_code=sku.sku_code,
                    reviewer_user_id=reviewer_user_id,
                    mood=mood,
                )
                conn.commit()
                result.seeded += 1
                print(
                    f"[{index}/{len(targets)}] sku_id={sku.sku_id} "
                    f"({sku.sku_code}) 완료: summary={mood.summary!r} "
                    f"tags={mood.tags}"
                )
            except (
                Exception
            ) as error:  # noqa: BLE001 - 한 건 실패해도 계속 진행한다
                conn.rollback()
                result.failed.append((sku.sku_id, str(error)))
                print(
                    f"[{index}/{len(targets)}] sku_id={sku.sku_id} 실패: "
                    f"{error}"
                )

        print_summary(result)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
