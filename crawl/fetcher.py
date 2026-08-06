"""HTTP 요청을 담당하는 모듈입니다. / Module that performs HTTP requests.

오늘의집은 TLS 지문으로 자동화 요청을 차단하므로, 브라우저 TLS를 흉내 내는
curl_cffi를 사용합니다. / ohou.se blocks by TLS fingerprint, so curl_cffi is
used to impersonate a browser handshake.
"""

import time
from typing import Any, Optional

from curl_cffi import requests as curl_requests

from crawl import config


class Fetcher:
    """요청 간격을 지키며 페이지와 파일을 내려받습니다. / Polite HTTP client."""

    def __init__(
        self,
        delay_seconds: float = config.REQUEST_DELAY_SECONDS,
        timeout_seconds: int = config.REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """세션과 요청 정책을 초기화합니다.

        Args:
            delay_seconds: 연속 요청 사이에 기다릴 시간(초)입니다.
            timeout_seconds: 요청 하나의 제한 시간(초)입니다.
        """
        self._session: curl_requests.Session = curl_requests.Session(
            headers=config.DEFAULT_HEADERS,
            impersonate=config.IMPERSONATE_BROWSER,
            timeout=timeout_seconds,
        )
        self._delay_seconds = delay_seconds
        self._last_request_at: Optional[float] = None

    def fetch_text(self, url: str) -> str:
        """HTML 등 텍스트 응답을 가져옵니다.

        Args:
            url: 요청할 주소입니다.

        Returns:
            응답 본문 문자열입니다.

        Raises:
            curl_cffi.requests.RequestsError: 요청이 실패했을 때 발생합니다.
        """
        return self._request(url, params=None).text

    def fetch_json(
        self, url: str, params: Optional[dict[str, str]] = None
    ) -> Any:
        """JSON 응답을 가져옵니다.

        Args:
            url: 요청할 주소입니다.
            params: 질의 문자열로 붙일 값입니다.

        Returns:
            파싱한 JSON 값입니다.

        Raises:
            curl_cffi.requests.RequestsError: 요청이 실패했을 때 발생합니다.
        """
        return self._request(url, params=params).json()

    def fetch_image(self, url: str) -> tuple[bytes, str]:
        """이미지를 내려받고 응답 형식을 함께 돌려줍니다.

        Args:
            url: 이미지 주소입니다.

        Returns:
            이미지 바이트와 Content-Type 문자열 쌍입니다.

        Raises:
            curl_cffi.requests.RequestsError: 요청이 실패했을 때 발생합니다.
        """
        response = self._request(url, params=None, headers=config.IMAGE_HEADERS)
        content_type = str(response.headers.get("Content-Type", ""))
        return response.content, content_type

    def close(self) -> None:
        """내부 세션을 정리합니다."""
        self._session.close()

    def _request(
        self,
        url: str,
        params: Optional[dict[str, str]],
        headers: Optional[dict[str, str]] = None,
    ) -> curl_requests.Response:
        """요청 간격을 지킨 뒤 GET 요청을 보냅니다.

        Args:
            url: 요청할 주소입니다.
            params: 질의 문자열로 붙일 값입니다.
            headers: 기본 헤더에 덧씌울 값입니다.

        Returns:
            성공한 응답 객체입니다.

        Raises:
            curl_cffi.requests.RequestsError: 요청이 실패했을 때 발생합니다.
        """
        self._wait_for_next_request()
        response: curl_requests.Response = self._session.get(
            url, params=params, headers=headers
        )
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response

    def _wait_for_next_request(self) -> None:
        """직전 요청 이후 설정한 간격만큼 대기합니다."""
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
