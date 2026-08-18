#!/usr/bin/env bash
# ============================================================
# DB 덤프 스크립트 (팀원 공유용)
# ------------------------------------------------------------
# docker compose로 띄운 centagging DB의 공유 시드 데이터를 UTF-8로 안전하게 덤프해서
# docker/db/init/ 폴더에 gzip으로 압축 저장합니다.
# postgres 공식 이미지는 컨테이너 최초 실행(볼륨이 비어있을 때)에
# docker-entrypoint-initdb.d 안의 .sql / .sql.gz 파일들을 알파벳
# 순서로 "자동 실행"하므로 (.sql.gz는 자동으로 gunzip 후 실행됨),
# 이 파일을 커밋해서 공유하면 팀원은 `docker compose up -d` 만
# 실행해도 schema.sql 적용 후 사용자·SKU·이미지·임베딩이 자동 복원됩니다.
#
# 실행 위치: 프로젝트 루트 (docker compose가 떠 있는 상태)에서
#   bash scripts/deploy/dump_db.sh
# ============================================================
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [ ! -f .env ]; then
  echo "❌ .env 파일이 없습니다. 프로젝트 루트에서 실행해주세요." >&2
  exit 1
fi

# .env 값 로드 (POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD)
set -a
source .env
set +a

DB="${POSTGRES_DB:-centagging}"
DB_USER="${POSTGRES_USER:-centagging}"
DB_PASSWORD="${POSTGRES_PASSWORD:-change-me}"

OUT_DIR="docker/db/init"
OUT_FILE="${OUT_DIR}/zz-sku-catalog-embeddings.sql.gz"
CONTAINER_SQL="/tmp/zz-sku-catalog-embeddings.sql"
CONTAINER_TMP="/tmp/zz-sku-catalog-embeddings.sql.gz"

mkdir -p "$OUT_DIR"

echo "▶ db 컨테이너 상태 확인..."
if [ -z "$(docker compose ps -q db 2>/dev/null)" ]; then
  echo "❌ db 컨테이너가 실행 중이 아닙니다. 먼저 'docker compose up -d db' 로 띄워주세요." >&2
  exit 1
fi

echo "▶ pg_dump 실행 후 컨테이너 내부에서 바로 gzip 압축 중 (UTF-8, 한글 깨짐 방지)..."
# 중요: SQL 생성과 gzip 압축을 컨테이너 안에서 순차 실행합니다. pg_dump가
# 실패하면 기존 호스트 덤프를 덮어쓰지 않으며, docker compose cp는 완성된
# 바이너리(.gz)만 바이트 그대로 복사합니다.
docker compose exec -T -e PGPASSWORD="$DB_PASSWORD" db sh -c \
  "set -e
  rm -f '$CONTAINER_SQL' '$CONTAINER_TMP'
  pg_dump -U '$DB_USER' -d '$DB' \
    --encoding=UTF8 \
    --no-owner --no-privileges \
    --data-only \
    --table=public.app_user \
    --table=public.sku_catalog \
    --table=public.sku_image \
    > '$CONTAINER_SQL'
  gzip -9 -n -c '$CONTAINER_SQL' > '$CONTAINER_TMP'
  rm -f '$CONTAINER_SQL'"

echo "▶ 컨테이너에서 호스트로 덤프 파일 복사 중..."
docker compose cp "db:${CONTAINER_TMP}" "$OUT_FILE"
docker compose exec -T db rm -f "$CONTAINER_TMP"

SIZE=$(du -h "$OUT_FILE" | cut -f1)
echo ""
echo "✅ 완료: $OUT_FILE (${SIZE})"
echo ""
echo "다음 단계:"
echo "  1) git add ${OUT_FILE}"
echo "  2) git commit -m \"chore: DB 덤프 추가 (자동 복원용)\""
echo "  3) git push"
echo ""
echo "팀원 사용법 (레포 clone 후):"
echo "  docker compose up -d      # DB 볼륨이 없으면 init 스크립트가 자동 실행되어 복원됨"
echo "  (이미 DB를 띄워본 적 있다면) docker compose down -v && docker compose up -d"
