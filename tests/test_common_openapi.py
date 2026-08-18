"""Swagger에 공통 422 검증 오류 계약이 노출되는지 검증합니다."""

import unittest

from app.main import app


class CommonOpenApiTest(unittest.TestCase):
    """자동 생성된 FastAPI 422 문서를 공통 오류 계약으로 바꾸는지 검증합니다."""

    def test_generated_validation_errors_use_common_error_schema(self) -> None:
        """태깅·이력·관리자 API의 422 문서는 공통 오류 모델을 사용합니다."""
        openapi = app.openapi()

        for path, method in (
            ("/tagging", "post"),
            ("/tagging/scenes/{scene_id}", "post"),
            ("/tagging/scenes/{scene_id}/recommendations", "post"),
            ("/tagging/scenes/{scene_id}", "put"),
            ("/history/results/{result_id}", "get"),
            ("/approvals", "get"),
            ("/product-image-submissions", "get"),
        ):
            with self.subTest(path=path, method=method):
                response = openapi["paths"][path][method]["responses"]["422"]
                content = response["content"]["application/json"]

                self.assertEqual(
                    content["schema"]["$ref"],
                    "#/components/schemas/ErrorResponse",
                )
                self.assertEqual(
                    content["example"]["error"]["code"],
                    "VALIDATION_ERROR",
                )
                self.assertEqual(
                    content["example"]["error"]["details"][0]["field"],
                    "request",
                )

        self.assertNotIn(
            "HTTPValidationError",
            openapi["components"]["schemas"],
        )
