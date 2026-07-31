# Python 코딩 컨벤션

## 기준

이 프로젝트의 `app/` 및 향후 추가되는 Python 코드는
[Google Python Style Guide 한글 번역](https://github.com/Yosseulsin-JOB/Google-Python-Style-Guide-kor)을
따릅니다. 번역 해석이 모호하거나 원문과 차이가 있을 때는
[Google Python Style Guide 원문](https://google.github.io/styleguide/pyguide.html)을 기준으로 합니다.

`kosa-poc-main/`은 수정하지 않는 참고 샘플이므로 이 규칙의 자동 검사 대상에서 제외합니다.

## 필수 규칙

- Python 3.10을 사용하고, 들여쓰기는 공백 4칸을 사용합니다.
- 최대 줄 길이는 80자입니다. URL, import, 긴 문자열 등 가독성을 해치는 경우만 예외로 합니다.
- 모듈과 함수는 `snake_case`, 클래스는 `PascalCase`, 상수는 `UPPER_CASE`로 작성합니다.
- import는 모듈 단위로 작성하며, 같은 프로젝트 모듈은 전체 패키지 경로를 사용합니다.
- 공개 모듈, 클래스, 함수에는 Google 형식 docstring을 작성합니다. 필요한 경우 `Args`, `Returns`, `Raises`를 포함합니다.
- 모든 새 함수와 메서드에는 타입 힌트를 작성합니다.
- 광범위한 예외 처리와 `pylint` 예외 해제는 이유를 주석으로 남기고, 오류를 숨기지 않습니다.
- API 키·비밀번호 등 민감정보는 `.env`에만 보관하며 코드와 로그에 기록하지 않습니다.

## 로컬 검사

의존성 설치 후 최초 한 번 Git 훅을 설치합니다.

```powershell
pre-commit install
```

커밋 전 또는 PR 생성 전 다음 검사를 통과해야 합니다.

```powershell
black --check app
isort --check-only app
pylint app
mypy app
pydocstyle app
```

Docker로도 같은 검사를 실행할 수 있습니다.

```powershell
docker compose exec api black --check app
docker compose exec api isort --check-only app
docker compose exec api pylint app
docker compose exec api mypy app
docker compose exec api pydocstyle app
```

자동 수정이 가능한 형식 문제는 다음 명령으로 정리합니다.

```powershell
black app
isort app
```

GitHub Actions의 `Python Style / python-style` 검사가 PR과 `main`·`dev` 브랜치 푸시에서 실행됩니다.
브랜치 Ruleset에서는 이 검사를 필수 상태 검사로 지정합니다. Git 훅은 커밋 전에 같은
오류를 빠르게 확인하는 보조 수단입니다.
