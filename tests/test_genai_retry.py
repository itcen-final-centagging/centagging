"""Vertex AI 429 재시도 정책을 검증합니다."""

import unittest
from unittest import mock

from google.genai import errors

from app.services.genai_retry import call_with_rate_limit_retry


class GenAiRetryTest(unittest.TestCase):
    """429에만 제한된 재시도가 적용되는지 검증합니다."""

    def test_retries_rate_limit_with_exponential_delays(self) -> None:
        """429 두 번 뒤 성공하면 1초와 2초를 기다린 뒤 결과를 반환합니다."""
        operation = mock.Mock(
            side_effect=[
                errors.ClientError(429, {"error": {"message": "busy"}}),
                errors.ClientError(429, {"error": {"message": "busy"}}),
                "success",
            ]
        )

        with mock.patch("app.services.genai_retry.time.sleep") as sleep:
            result = call_with_rate_limit_retry(
                operation,
                operation_name="test",
            )

        self.assertEqual(result, "success")
        self.assertEqual(operation.call_count, 3)
        sleep.assert_has_calls([mock.call(1.0), mock.call(2.0)])

    def test_does_not_retry_non_rate_limit_client_error(self) -> None:
        """429가 아닌 클라이언트 오류는 즉시 호출자에게 전달합니다."""
        operation = mock.Mock(
            side_effect=errors.ClientError(
                403,
                {"error": {"message": "forbidden"}},
            )
        )

        with self.assertRaises(errors.ClientError):
            call_with_rate_limit_retry(operation, operation_name="test")

        self.assertEqual(operation.call_count, 1)

    def test_accepts_evaluation_backoff_and_jitter(self) -> None:
        """평가 전용 재시도 간격과 jitter를 실제 대기에 반영합니다."""
        operation = mock.Mock(
            side_effect=[
                errors.ClientError(429, {"error": {"message": "busy"}}),
                errors.ClientError(429, {"error": {"message": "busy"}}),
                "success",
            ]
        )

        with (
            mock.patch(
                "app.services.genai_retry.random.uniform",
                side_effect=[0.5, 1.5],
            ),
            mock.patch("app.services.genai_retry.time.sleep") as sleep,
        ):
            result = call_with_rate_limit_retry(
                operation,
                operation_name="evaluation",
                retry_delays_seconds=(5.0, 15.0, 30.0),
                jitter_seconds=2.0,
            )

        self.assertEqual(result, "success")
        sleep.assert_has_calls([mock.call(5.5), mock.call(16.5)])

    def test_rate_limit_callback_can_extend_retry_delay(self) -> None:
        """평가 전체 cooldown이 개별 재시도 대기에도 적용됩니다."""
        operation = mock.Mock(
            side_effect=[
                errors.ClientError(429, {"error": {"message": "busy"}}),
                "success",
            ]
        )
        rate_limit_callback = mock.Mock(return_value=60.0)

        with mock.patch("app.services.genai_retry.time.sleep") as sleep:
            result = call_with_rate_limit_retry(
                operation,
                operation_name="evaluation",
                retry_delays_seconds=(5.0,),
                rate_limit_callback=rate_limit_callback,
            )

        self.assertEqual(result, "success")
        rate_limit_callback.assert_called_once_with(5.0)
        sleep.assert_called_once_with(60.0)
