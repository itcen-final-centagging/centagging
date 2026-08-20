"""Vertex AI의 일시적인 요청 한도 응답을 제한적으로 재시도합니다."""

import logging
import time
import typing

from google.genai import errors

_LOGGER = logging.getLogger(__name__)
_RATE_LIMIT_RETRY_DELAYS_SECONDS = (1.0, 2.0)
_Result = typing.TypeVar("_Result")


def call_with_rate_limit_retry(
    operation: typing.Callable[[], _Result],
    *,
    operation_name: str,
) -> _Result:
    """429 응답만 짧은 지수 백오프로 재시도해 결과를 반환합니다.

    마지막 시도도 429이면 원본 예외를 다시 발생시켜 호출자가 기존
    도메인 오류 및 폴백 정책으로 처리하게 합니다.
    """
    for retry_delay in _RATE_LIMIT_RETRY_DELAYS_SECONDS:
        try:
            return operation()
        except errors.ClientError as error:
            if getattr(error, "code", None) != 429:
                raise
            _LOGGER.warning(
                "Vertex AI 요청 한도 초과로 재시도합니다: operation=%s "
                "delay_seconds=%s",
                operation_name,
                retry_delay,
            )
            time.sleep(retry_delay)

    return operation()
