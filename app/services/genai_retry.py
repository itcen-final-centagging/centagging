"""Vertex AI의 일시적인 요청 한도 응답을 제한적으로 재시도합니다."""

import logging
import random
import time
import typing
from collections.abc import Sequence

from google.genai import errors

_LOGGER = logging.getLogger(__name__)
_RATE_LIMIT_RETRY_DELAYS_SECONDS = (1.0, 2.0)
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 503})
_Result = typing.TypeVar("_Result")
RateLimitCallback = typing.Callable[[float], float | None]


def call_with_rate_limit_retry(
    operation: typing.Callable[[], _Result],
    *,
    operation_name: str,
    retry_delays_seconds: Sequence[float] | None = None,
    jitter_seconds: float = 0.0,
    rate_limit_callback: RateLimitCallback | None = None,
) -> _Result:
    """일시적인 Vertex AI 오류를 지정된 백오프로 재시도해 결과를 반환합니다.

    마지막 시도도 429이면 원본 예외를 다시 발생시켜 호출자가 기존
    도메인 오류 및 폴백 정책으로 처리하게 합니다.
    """
    delays = (
        _RATE_LIMIT_RETRY_DELAYS_SECONDS
        if retry_delays_seconds is None
        else tuple(retry_delays_seconds)
    )
    if jitter_seconds < 0 or any(delay < 0 for delay in delays):
        raise ValueError("재시도 지연 시간은 0 이상이어야 합니다.")

    for retry_delay in delays:
        try:
            return operation()
        except errors.APIError as error:
            status_code = getattr(error, "code", None)
            if status_code not in _RETRYABLE_STATUS_CODES:
                raise
            actual_delay = retry_delay + random.uniform(0, jitter_seconds)
            if status_code == 429 and rate_limit_callback is not None:
                callback_delay = rate_limit_callback(actual_delay)
                if callback_delay is not None:
                    actual_delay = max(actual_delay, callback_delay)
            _LOGGER.warning(
                "Vertex AI 일시 오류로 재시도합니다: operation=%s "
                "status_code=%s delay_seconds=%s",
                operation_name,
                status_code,
                round(actual_delay, 2),
            )
            time.sleep(actual_delay)

    return operation()
