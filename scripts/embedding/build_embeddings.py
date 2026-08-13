"""data/catalog/answer/sku.json + data/images -> sku_catalog/sku_image 적재·임베딩.

실행:
    python -m scripts.embedding.build_embeddings
    python -m scripts.embedding.build_embeddings --limit 5 --dry-run
    python -m scripts.embedding.build_embeddings --skip-images
    python -m scripts.embedding.build_embeddings --force-text --force-images

단계:
    1. sku.json 로드
    2. sku_catalog 메타데이터 적재(upsert), sku_id 시퀀스 동기화
    3. 텍스트 임베딩: sku.json 기준으로 문장을 만들어 Gemini로 임베딩,
       sku_catalog.text_embedding에 저장
    4. 이미지 임베딩: data/images/{sku_id}/main.* 를 Gemini로 임베딩,
       sku_image(MAIN)에 적재하며 sku_id로 sku_catalog와 연관관계를 맺음

기존에 임베딩이 이미 있는 SKU는 기본적으로 건너뛴다(--force-* 로 재계산 가능).
한 건이 실패해도 전체가 멈추지 않고, 실패 목록을 마지막에 정리해서 보여준다.
"""

from __future__ import annotations

import argparse
import dataclasses
import json

from PIL import Image

from app.services.sku_image_storage import SkuImageStorage
from scripts.embedding import db, gemini_embed, storage
from scripts.embedding.text_builder import build_embedding_text


@dataclasses.dataclass
class RunResult:
    """파이프라인 실행 결과 요약입니다."""

    total_skus: int = 0
    metadata_inserted: int = 0
    metadata_skipped_existing: int = 0
    metadata_failed: list[tuple[int, str]] = dataclasses.field(default_factory=list)

    text_skipped_existing: int = 0
    text_embedded: int = 0
    text_failed: list[tuple[int, str]] = dataclasses.field(default_factory=list)

    image_skipped_existing: int = 0
    image_skipped_missing_file: int = 0
    image_embedded: int = 0
    image_failed: list[tuple[int, str]] = dataclasses.field(default_factory=list)


def _format_error(error: BaseException) -> str:
    """예외의 __cause__ 체인을 풀어서 실제 원인까지 이어붙인다.

    gemini_embed.embed_text/GeminiService.embed_image는 원인을
    GeminiEmbeddingError로 감싸서 raise ... from error 하기 때문에,
    str(error)만 보면 "Gemini 텍스트 임베딩에 실패했습니다." 같은
    포장 메시지만 남고 진짜 원인(레이트리밋, 인증 오류 등)이 가려진다.

    Args:
        error: 실패 지점에서 잡은 예외입니다.

    Returns:
        "겉 메시지 <- 원인1 <- 원인2 ..." 형태의 문자열입니다.
    """
    parts = [f"{type(error).__name__}: {error}"]
    cause = error.__cause__
    while cause is not None:
        parts.append(f"{type(cause).__name__}: {cause}")
        cause = cause.__cause__
    return " <- ".join(parts)


def load_skus(limit: int | None) -> list[dict]:
    """sku.json을 읽는다.

    Args:
        limit: 앞에서부터 몇 건만 쓸지입니다. None이면 전체입니다.

    Returns:
        sku.json의 항목 리스트입니다.
    """
    with storage.SKU_JSON_PATH.open("r", encoding="utf-8") as file:
        skus: list[dict] = json.load(file)
    if limit is not None:
        skus = skus[:limit]
    return skus


def upsert_metadata(
    conn, skus: list[dict], result: RunResult, dry_run: bool
) -> None:
    """모든 SKU의 메타데이터를 sku_catalog에 적재한다.

    이미 존재하는 sku_id는 건드리지 않는다(ON CONFLICT DO NOTHING).
    새로 추가되는 SKU만 삽입된다.
    """
    for sku in skus:
        sku_id = sku["sku_id"]
        try:
            if dry_run:
                result.metadata_inserted += 1
                continue

            inserted = db.upsert_sku_metadata(conn, sku)
            if inserted:
                result.metadata_inserted += 1
            else:
                result.metadata_skipped_existing += 1
        except Exception as error:  # noqa: BLE001 - 한 건 실패로 전체를 멈추지 않는다
            message = _format_error(error)
            result.metadata_failed.append((sku_id, message))
            print(f"[실패][메타데이터] sku_id={sku_id}: {message}")

    if not dry_run:
        db.sync_sku_sequence(conn)
        conn.commit()


def embed_texts(
    conn,
    skus: list[dict],
    settings,
    result: RunResult,
    dry_run: bool,
    force: bool,
) -> None:
    """sku.json 기준으로 텍스트 임베딩을 만들어 저장한다."""
    already_done = set() if force or dry_run else db.fetch_text_embedded_sku_ids(conn)

    for sku in skus:
        sku_id = sku["sku_id"]
        if sku_id in already_done:
            result.text_skipped_existing += 1
            continue

        try:
            text = build_embedding_text(sku)
            if dry_run:
                result.text_embedded += 1
                continue

            embedding = gemini_embed.embed_text(settings, text)
            db.update_text_embedding(conn, sku_id, embedding)
            conn.commit()
            result.text_embedded += 1
        except Exception as error:  # noqa: BLE001
            conn.rollback()
            message = _format_error(error)
            result.text_failed.append((sku_id, message))
            print(f"[실패][텍스트 임베딩] sku_id={sku_id}: {message}")


def embed_images(
    conn,
    skus: list[dict],
    settings,
    result: RunResult,
    dry_run: bool,
    force: bool,
) -> None:
    """data/images/{sku_id}/main.* 이미지를 임베딩해 sku_image(MAIN)에 적재한다."""
    already_done = set() if force or dry_run else db.fetch_image_embedded_sku_ids(conn)
    embedder = None if dry_run else gemini_embed.make_image_embedder(settings)
    image_storage = SkuImageStorage(storage.IMAGES_DIR)

    for sku in skus:
        sku_id = sku["sku_id"]
        if sku_id in already_done:
            result.image_skipped_existing += 1
            continue

        image_path = storage.main_image_path(sku_id)
        if image_path is None:
            result.image_skipped_missing_file += 1
            continue

        try:
            if dry_run:
                result.image_embedded += 1
                continue

            with Image.open(image_path) as image:
                image.load()
                embedding = embedder.embed_image(image)

            relative_url = image_storage.storage_key(image_path)
            inserted = db.upsert_sku_image(
                conn, sku_id, relative_url, embedding, overwrite=force
            )
            conn.commit()
            if inserted:
                result.image_embedded += 1
            else:
                result.image_skipped_existing += 1
        except Exception as error:  # noqa: BLE001
            conn.rollback()
            message = _format_error(error)
            result.image_failed.append((sku_id, message))
            print(f"[실패][이미지 임베딩] sku_id={sku_id}: {message}")


def print_summary(result: RunResult) -> None:
    """실행 결과를 한국어로 요약 출력한다."""
    print("\n=== 적재 결과 ===")
    print(f"전체 SKU: {result.total_skus}")
    print(f"메타데이터 적재: 신규 {result.metadata_inserted}건, "
          f"이미 있어서 건너뜀: {result.metadata_skipped_existing}건, "
          f"실패: {len(result.metadata_failed)}건")

    print("\n=== 텍스트 임베딩 ===")
    print(f"신규: {result.text_embedded}건, 이미 있어서 건너뜀: "
          f"{result.text_skipped_existing}건, 실패: {len(result.text_failed)}건")

    print("\n=== 이미지 임베딩 ===")
    print(f"신규: {result.image_embedded}건, 이미 있어서 건너뜀: "
          f"{result.image_skipped_existing}건, "
          f"이미지 파일 없어서 건너뜀: {result.image_skipped_missing_file}건, "
          f"실패: {len(result.image_failed)}건")

    for label, failures in (
        ("메타데이터", result.metadata_failed),
        ("텍스트 임베딩", result.text_failed),
        ("이미지 임베딩", result.image_failed),
    ):
        if failures:
            print(f"\n[{label} 실패 목록]")
            for sku_id, message in failures:
                print(f"  sku_id={sku_id}: {message}")


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N건만 처리")
    parser.add_argument("--skip-text", action="store_true", help="텍스트 임베딩 단계 건너뛰기")
    parser.add_argument("--skip-images", action="store_true", help="이미지 임베딩 단계 건너뛰기")
    parser.add_argument("--force-text", action="store_true", help="기존 텍스트 임베딩도 재계산")
    parser.add_argument("--force-images", action="store_true", help="기존 이미지 임베딩도 재계산")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB에 쓰지 않고 대상 건수만 확인",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = storage.get_settings()
    skus = load_skus(args.limit)

    result = RunResult(total_skus=len(skus))

    conn = None if args.dry_run else db.connect(settings.database)
    try:
        upsert_metadata(conn, skus, result, args.dry_run)

        if not args.skip_text:
            embed_texts(conn, skus, settings, result, args.dry_run, args.force_text)

        if not args.skip_images:
            embed_images(conn, skus, settings, result, args.dry_run, args.force_images)
    finally:
        if conn is not None:
            conn.close()

    print_summary(result)


if __name__ == "__main__":
    main()
