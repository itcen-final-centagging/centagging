"""크롤러 공통 설정값입니다. / Shared crawler configuration values."""

import pathlib

# 상품 상세 페이지 주소 형식입니다. / Product detail page URL format.
GOODS_URL_TEMPLATE = "https://store.ohou.se/goods/{goods_id}"

# 앱 메타데이터를 제공하는 Airbridge 설정 주소입니다. / Airbridge config URL.
AIRBRIDGE_CONFIG_URL = "https://config.airbridge.io/v1/web/apps/ohouse"

# Airbridge 웹 토큰을 읽는 환경변수 이름입니다. / Env var for the web token.
AIRBRIDGE_TOKEN_ENV = "OHOUSE_AIRBRIDGE_WEB_TOKEN"

# Next.js가 상품 데이터를 담아두는 script 태그 id입니다. / Next.js data id.
NEXT_DATA_SCRIPT_ID = "__NEXT_DATA__"

# 상품 데이터를 담은 react-query 캐시 키입니다. / react-query cache key.
GOODS_QUERY_KEY = "goods"

# 수집 결과 기본 저장 경로입니다. / Default output directory for results.
DEFAULT_OUTPUT_DIR = pathlib.Path("resource/crawl")

# TLS 지문을 흉내 낼 브라우저입니다. / Browser profile used for TLS.
IMPERSONATE_BROWSER = "chrome"

# HTTP 요청 제한 시간(초)입니다. / HTTP request timeout in seconds.
REQUEST_TIMEOUT_SECONDS = 20

# 서버 부하를 줄이기 위한 요청 간격(초)입니다. / Delay between requests.
REQUEST_DELAY_SECONDS = 1.0

# 한 상품에서 내려받을 최대 이미지 수입니다. / Max images per product.
DEFAULT_IMAGE_LIMIT = 30

# 일반 브라우저와 동일한 요청 헤더입니다. / Browser-like request headers.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

# 이미지 요청 헤더입니다. AVIF를 제외해 JPEG·PNG로 받습니다.
# / Image request headers; AVIF is excluded so JPEG or PNG is returned.
IMAGE_HEADERS = {"Accept": "image/jpeg,image/png,image/gif;q=0.9,*/*;q=0.8"}
