# 센태깅 프론트엔드

CenTagging의 연출 이미지 가구 자동 태깅 프론트엔드 프로젝트입니다. 이미지 업로드부터 객체 선택, SKU 후보 검증, HITL 검수 이력까지의 작업 흐름을 제공합니다.

## 기술 스택

| 분류                 | 라이브러리                         |
| -------------------- | ---------------------------------- |
| 프레임워크           | React 19 + TypeScript 5.9 + Vite 7 |
| 라우팅               | React Router v7                    |
| 클라이언트 상태 관리 | React Context + Custom Hook        |
| HTTP 클라이언트      | Fetch API                          |
| 스타일링             | Tailwind CSS v4                    |
| 아이콘               | Lucide React                       |
| 코드 품질            | ESLint v9 + Prettier v3            |

## 시작하기

```bash
# frontend 디렉터리에서 실행
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev

# 프로덕션 빌드
npm run build

# 린트
npm run lint

# 포맷 적용
npm run prettier:write
```

개발 서버는 `/api`, `/tagging`, `/history/results`, `/uploads`, `/sku-images`, `/auth` 요청을 `http://localhost:8000`으로 프록시합니다. API·PostgreSQL·프론트를 함께 실행하려면 저장소 루트에서 `docker compose up --build`를 사용합니다.

## 환경 변수

기본 개발 환경에서는 Vite 프록시를 사용하므로 별도 환경 변수가 필요하지 않습니다. 다른 API 서버를 직접 호출해야 할 경우 `frontend/.env`를 만들고 아래처럼 설정할 수 있습니다.

```env
VITE_API_BASE_URL=https://your-api-base-url.com
```

> 현재 API 호출은 동일 출처의 `/api` 경로를 기준으로 합니다. 외부 API 주소를 적용할 때는 `features/tagging/api/`의 API 클라이언트와 함께 설정합니다.

## 디렉터리 구조

```text
src/
├── commons/                         # 여러 feature에서 재사용하는 UI·테마·상수
│   ├── components/                  # Button, Header, Layout, SideBar
│   ├── constants/                   # 공통 메뉴 등
│   └── theme/                       # 팔레트와 시맨틱 토큰
│
├── features/                        # 도메인별 비즈니스 기능
│   └── tagging/
│       ├── api/                     # 태깅 API 요청 및 응답 매핑
│       ├── components/              # 태깅 화면 전용 UI
│       ├── constants/               # 업로드 제한·기본 태그
│       ├── hooks/                   # useTaggingWorkflow 상태·액션
│       ├── utils/                   # 이미지 유효성 검사
│       └── types.ts                 # 도메인 타입
│
├── pages/                           # 라우트 단위 화면
│   ├── TaggingPage.tsx
│   └── HistoryPage.tsx
│
├── router/                          # React Router 라우트 정의
├── lib/                             # 공통 유틸리티
├── App.tsx                          # 앱 조합과 전역 Provider 적용
├── main.tsx                         # React 진입점
└── index.css                        # Tailwind import와 전역 디자인 토큰
```

### 구조 원칙

- **`pages`**: 라우트에 1:1 대응하는 화면입니다. 화면 전환과 feature UI 조합만 담당합니다.
- **`features`**: 도메인별 API, 상태 훅, UI, 유틸, 타입을 함께 둡니다. 태깅에만 쓰이는 코드는 `features/tagging` 밖으로 옮기지 않습니다.
- **`commons`**: 두 개 이상의 feature에서 실제로 재사용하는 컴포넌트·상수·테마만 둡니다.
- **`api`**: 서버 snake_case 응답을 화면에서 사용할 camelCase 도메인 타입으로 변환합니다. 컴포넌트에서 API 응답을 직접 가공하지 않습니다.

## 코드 컨벤션

### 네이밍

- 컴포넌트: `PascalCase`
- 함수·변수·이벤트 핸들러: `camelCase`
- 상수: `UPPER_SNAKE_CASE`
- 타입·인터페이스: `PascalCase`
- Props 타입: 컴포넌트명 + `Props`
  - 예: `RecommendationPanelProps`

### API / 상태 훅

```ts
// HTTP 동작이 드러나는 API 함수
export const analyzeImage = async () => {};
export const searchCatalogItems = async () => {};
export const saveTaggingReview = async () => {};

// feature 상태와 이벤트 처리는 커스텀 훅에 둡니다.
export const useTaggingWorkflow = () => {};
```

- 서버 요청·응답 타입은 API 모듈에서 명시적으로 선언합니다.
- 화면에서 쓰는 타입과 서버 응답 타입의 형태가 다르면 API 모듈에서 매핑합니다.
- API 요청 이후의 상태 전환, 저장, 오류 처리는 `hooks`에 두고 컴포넌트는 렌더링에 집중합니다.

### 이벤트 핸들러

```tsx
const handleSubmitTagging = () => {};

<TaggingForm onSubmitTagging={handleSubmitTagging} />;
```

- 컴포넌트 내부 핸들러는 `handle` 접두사를 사용합니다.
- 자식 컴포넌트에 전달하는 이벤트 prop은 `on` 접두사를 사용합니다.

### import 순서

ESLint 설정에 맞춰 아래 순서를 유지합니다.

```text
1. external    (react, npm 패키지)
2. internal    (@/ alias)
3. parent      (../)
4. sibling     (./)
5. type import
```

## 리팩토링 가이드

### 1. 컴포넌트는 UI 렌더링에 집중합니다.

데이터 가공, API 호출 이후 처리, 길어진 상태 전환은 `hooks` 또는 `utils`로 분리합니다.

### 2. 도메인 코드는 feature 안에 둡니다.

태깅 전용 컴포넌트·유틸·상수·타입은 `features/tagging`에 둡니다. 다른 도메인에서도 재사용할 근거가 있을 때만 `commons`로 이동합니다.

### 3. 반복 UI는 컴포넌트로 분리합니다.

같은 구조가 두 번 이상 나타나면 feature 전용 컴포넌트 또는 공통 컴포넌트 분리를 검토합니다. 컴포넌트 props에는 렌더링에 필요한 값만 전달합니다.

### 4. API 응답은 변환 후 사용합니다.

서버의 snake_case 데이터와 화면 도메인 모델을 분리합니다. 변환은 `features/tagging/api/tagging.ts`에서 수행합니다.

## 머지 전 체크리스트

- [ ] 컴포넌트에 긴 비즈니스 로직이 남아 있지 않은가?
- [ ] feature 전용 코드가 `commons`에 섞이지 않았는가?
- [ ] API 응답을 화면에서 직접 복잡하게 가공하지 않는가?
- [ ] 반복 UI를 재사용 가능한 컴포넌트로 분리했는가?
- [ ] 이벤트 핸들러와 props 이름이 컨벤션에 맞는가?
- [ ] `npm run prettier:check`를 통과하는가?
- [ ] `npm run lint`를 통과하는가?
- [ ] `npm run build`를 통과하는가?
