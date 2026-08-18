#!/usr/bin/env bash
# ============================================================
# DB 덤프 스크립트 (팀원 공유용)
# ------------------------------------------------------------
# docker compose로 띄운 centagging DB를 UTF-8로 안전하게 덤프해서
# docker/db/init/ 폴더에 gzip으로 압축 저장합니다.
# postgres 공식 이미지는 컨테이너 최초 실행(볼륨이 비어있을 때)에
# docker-entrypoint-initdb.d 안의 .sql / .sql.gz 파일들을 알파벳
# 순서로 "자동 실행"하므로 (.sql.gz는 자동으로 gunzip 후 실행됨),
# 이 파일을 커밋해서 공유하면 팀원은 `docker compose up -d` 만
# 해도 DB(스키마+데이터+임베딩)가 자동으로 복원됩니다.
#
# 중요(데이터 전용 덤프): 이 스크립트는 --data-only로 데이터(COPY)만
# 덤프합니다. 스키마(테이블/인덱스/제약조건)는 항상 schema.sql이
# 책임지므로, 스키마가 나중에 바뀌어도(예: 새 테이블/외래키 추가)
# 예전 덤프의 DROP/CREATE 구문이 최신 스키마와 충돌해 복원이 깨지는
# 일이 없습니다. (--clean으로 스키마까지 같이 덤프했을 때, 덤프
# 시점 이후 추가된 테이블이 기존 테이블의 PK를 참조하면 덤프의
# DROP CONSTRAINT가 실패해 초기화 전체가 멈추는 문제가 있었습니다.)
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

# 버전 관리용: 데이터가 크게 바뀌어 새 스냅샷을 남기고 싶을 때 이 값만
# v2, v3 ... 로 올려서 실행하세요. 단, 새 버전을 커밋할 때는 반드시
# docker/db/init/ 안의 이전 버전 파일(zz-...-v1.sql.gz 등)을 같이
# 삭제(git rm)해야 합니다. 옛 버전 파일이 남아있으면 docker가 초기화
# 시점에 여러 데이터 덤프를 전부 실행해버려서 같은 행을 중복으로
# INSERT하다가 PK 충돌로 복원이 깨집니다. (폴더 안에는 항상 데이터
# 덤프가 하나만 있어야 합니다.)
DUMP_VERSION="v1"

OUT_DIR="docker/db/init"
OUT_FILE="${OUT_DIR}/zz-sku-catalog-embeddings-${DUMP_VERSION}.sql.gz"
CONTAINER_TMP="/tmp/zz-sku-catalog-embeddings-${DUMP_VERSION}.sql.gz"

mkdir -p "$OUT_DIR"

echo "▶ db 컨테이너 상태 확인..."
if [ -z "$(docker compose ps -q db 2>/dev/null)" ]; then
  echo "❌ db 컨테이너가 실행 중이 아닙니다. 먼저 'docker compose up -d db' 로 띄워주세요." >&2
  exit 1
fi

echo "▶ pg_dump 실행 후 컨테이너 내부에서 바로 gzip 압축 중 (UTF-8, 한글 깨짐 방지)..."
# 중요: 콘솔로 리다이렉트(>)하지 않고 컨테이너 셸 안에서 pg_dump | gzip 을
# 그대로 실행해 바이너리(.gz) 파일을 만듭니다. 그 다음 docker compose cp로
# 바이트 그대로 복사해오므로, 호스트 터미널의 인코딩(특히 Windows
# PowerShell의 기본 UTF-16 리다이렉션)으로 인한 한글 깨짐이 원천 차단됩니다.
docker compose exec -T -e PGPASSWORD="$DB_PASSWORD" db sh -c \
  "pg_dump -U '$DB_USER' -d '$DB' \
    --encoding=UTF8 \
    --no-owner --no-privileges \
    --data-only --disable-triggers \
    | gzip -9 > '$CONTAINER_TMP'"

echo "▶ 컨테이너에서 호스트로 덤프 파일 복사 중..."
docker compose cp "db:${CONTAINER_TMP}" "$OUT_FILE"
docker compose exec -T db rm -f "$CONTAINER_TMP"

SIZE=$(du -h "$OUT_FILE" | cut -f1)
echo ""
echo "✅ 완료: $OUT_FILE (${SIZE})"
echo ""
echo "다음 단계:"
echo "  1) git add ${OUT_FILE}"
echo "     (이전 버전 파일이 docker/db/init/에 남아있다면 git rm으로 같이 제거하세요)"
echo "  2) git commit -m \"chore: DB 덤프 추가 (자동 복원용, ${DUMP_VERSION})\""
echo "  3) git push"
echo ""
echo "팀원 사용법 (레포 clone 후):"
echo "  docker compose up -d      # DB 볼륨이 없으면 init 스크립트가 자동 실행되어 복원됨"
echo "  (이미 DB를 띄워본 적 있다면) docker compose down -v && docker compose up -d"
echo ""
echo "참고: 이 덤프는 데이터 전용입니다. schema.sql이 먼저 실행돼"
echo "테이블/인덱스/제약조건을 만든 뒤, 이 파일이 데이터만 채워 넣습니다."
