# 오늘의집 상품 크롤러 (`crawl/`)

오늘의집 상품 상세 페이지에서 **VLM 태깅과 SKU 매칭에 쓸 수 있는 값만** 골라
JSON으로 저장하고, 상품 이미지를 내려받는 모듈입니다.

## 1. 실행 방법

```powershell
pip install -r requirements.txt
python -m crawl 329364
```

| 옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `goods_ids` | 수집할 상품 번호(여러 개 가능) | 필수 |
| `--output-dir` | 결과 저장 위치 | `resource/crawl` |
| `--images` | 이미지 파일도 내려받기 | 꺼짐 |
| `--image-limit` | 상품당 최대 이미지 수 | 30 |
| `--app-info` | Airbridge 앱 메타데이터도 저장 | 꺼짐 |

```powershell
python -m crawl 329364 1234567 --images --image-limit 20
```

## 2. 저장 구조

```text
resource/crawl/
├─ app_info.json          # --app-info 로 저장한 앱 메타데이터
└─ 329364/
   ├─ product.json        # 상품 정보
   └─ images/
      ├─ index.json       # 파일명 ↔ 원본 URL ↔ 용도 매핑
      ├─ 000_main.jpg
      ├─ 001_sub.jpg
      └─ 005_detail.jpg
```

`resource/`는 `.gitignore` 대상이므로 수집 결과는 커밋되지 않습니다.

## 3. 수집하는 값과 선정 기준

상세 페이지의 Next.js 초기 데이터(`__NEXT_DATA__`)에는 광고·배너·실험 설정까지
들어 있어, 아래 항목만 남깁니다.

| 필드 | 용도 |
| --- | --- |
| `goods_id`, `source_url`, `crawled_at` | 원본 추적과 재수집 기준 |
| `name`, `summary` | 텍스트 태깅·임베딩 입력 |
| `brand_id`, `brand_name` | 브랜드 단위 집계와 매칭 |
| `category_id`, `category_path` | 카테고리 분류 정답 라벨 |
| `first_option_name`, `second_option_name` | 옵션 축 이름(예: 사이즈/색상) |
| `selling_price`, `regular_price`, `discount_rate` | 가격대 속성 |
| `review_average`, `review_count`, `scrap_count` | 인기도 가중치 |
| `is_selling`, `is_sold_out` | 학습·서빙 대상 필터 |
| `ai_attributes` | 오늘의집이 제공하는 요약 속성 |
| `specifications` | 상품정보 고시(색상·소재·제조국 등) — 태그 정답에 가장 유용 |
| `options` | SKU 단위 옵션·가격·재고 |
| `images` | 이미지 URL과 용도(main/sub/detail/styling) |
| `styling_card_urls` | 유저 스타일링샷 원문 링크 |

이미지 용도는 네 가지입니다.

- `main`: 대표 이미지 1장. 상품 단독 컷이라 SKU 이미지 기준으로 적합합니다.
- `sub`: 추가 상품 컷.
- `detail`: 상세 설명 HTML에서 BeautifulSoup으로 추출한 이미지. 텍스트가 박힌
  홍보 이미지가 섞이므로 VLM 입력 전에 걸러 쓰는 편이 좋습니다.
- `styling`: 유저가 올린 실사용 공간 사진. 공간 태깅 학습 데이터로 유용합니다.

### 제외한 값

`badges`, `benefitBadges`, `promotions`, `advertiseSection`, `adCarousel`,
`todayDeal`, `experiments` 등은 시점에 따라 바뀌는 마케팅 노출 정보라
저장하지 않습니다. 리뷰 본문은 개인 작성물이라 통계값(평균·개수)만 남기고
작성자 정보는 저장하지 않습니다.

## 4. Airbridge 앱 설정(`--app-info`)

`https://config.airbridge.io/v1/web/apps/ohouse` 응답은 앱 설치 유도(딥링크)용
설정이라 **상품 태깅에 직접 쓸 값은 거의 없습니다.** `sdkFlag`,
`protectedAttributionWindowEnabled`, `deeplinkInTablet` 같은 값은 SDK 동작
플래그일 뿐입니다. 그래서 출처 표기에 쓸 만한 아래 값만 남깁니다.

`app_id`, `app_name`, `app_subdomain`, `web_landing`, `android_market`,
`ios_market`, `app_icon_image_url`

호출에는 웹 토큰이 필요하므로 `.env`에 아래 값을 넣고 실행합니다.

```dotenv
OHOUSE_AIRBRIDGE_WEB_TOKEN=<웹 토큰>
```

토큰이 없으면 경고만 남기고 상품 수집은 그대로 진행합니다.

## 5. 모듈 구성

| 파일 | 역할 |
| --- | --- |
| `config.py` | URL·헤더·저장 경로 등 설정값 |
| `fetcher.py` | 요청 간격을 지키는 HTTP 클라이언트 |
| `parser.py` | BeautifulSoup 기반 파싱과 필드 선별 |
| `models.py` | `Product`, `ProductOption`, `ProductImage`, `AppInfo` |
| `storage.py` | JSON·이미지 저장 |
| `ohouse_crawler.py` | 수집 흐름 조립 |
| `main.py` | 명령줄 진입점 |

## 6. 알아둘 점

- 오늘의집은 TLS 지문으로 자동화 요청을 차단합니다. 일반 `requests`는 403을
  받으므로 브라우저 핸드셰이크를 흉내 내는 `curl_cffi`를 사용합니다.
- 기본 요청 간격은 1초입니다(`config.REQUEST_DELAY_SECONDS`). 서버 부담을
  줄이기 위한 값이니 낮추지 않는 편이 좋습니다.
- 이미지 요청은 `Accept` 헤더에서 AVIF를 제외해 JPEG로 받습니다. 그대로 두면
  CDN이 AVIF를 내려주어 Pillow·VLM 전처리에서 문제가 생깁니다.
- 페이지 구조가 바뀌면 `parser.ParseError`가 발생합니다. 이때는
  `__NEXT_DATA__` 안의 `dehydratedState.queries` 구조를 다시 확인해야 합니다.
- 수집 데이터는 오늘의집에 저작권이 있습니다. 사내 검증·학습 목적 범위에서만
  사용하고 재배포하지 않습니다.
