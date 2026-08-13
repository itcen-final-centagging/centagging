"""공통 API 응답 규격을 OpenAPI 문서에 반영합니다."""

import copy
import typing

import fastapi
from fastapi.openapi.utils import get_openapi

_FASTAPI_VALIDATION_ERROR_SCHEMA = "#/components/schemas/HTTPValidationError"
_COMMON_ERROR_SCHEMA = "#/components/schemas/ErrorResponse"

_VALIDATION_ERROR_RESPONSE = {
    "description": "요청 값이 누락되었거나 형식이 올바르지 않은 경우입니다.",
    "content": {
        "application/json": {
            "schema": {"$ref": _COMMON_ERROR_SCHEMA},
            "example": {
                "status": "error",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "요청 값을 확인해 주세요.",
                    "details": [
                        {
                            "field": "request",
                            "reason": "invalid_value",
                            "message": "입력값을 확인해 주세요.",
                        }
                    ],
                },
                "meta": {"request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"},
            },
        }
    },
}


def _is_fastapi_validation_response(response: typing.Any) -> bool:
    """FastAPI가 자동 생성한 기본 422 응답인지 확인합니다."""
    if not isinstance(response, dict):
        return False
    content = response.get("content")
    if not isinstance(content, dict):
        return False
    json_content = content.get("application/json")
    if not isinstance(json_content, dict):
        return False
    schema = json_content.get("schema")
    return schema == {"$ref": _FASTAPI_VALIDATION_ERROR_SCHEMA}


def configure_common_response_openapi(application: fastapi.FastAPI) -> None:
    """자동 생성 422 문서를 공통 오류 응답 규격으로 교체합니다."""

    def custom_openapi() -> dict[str, typing.Any]:
        """공통 오류 계약을 반영한 OpenAPI 스키마를 생성합니다."""
        if application.openapi_schema is not None:
            return typing.cast(dict[str, typing.Any], application.openapi_schema)

        openapi_schema = typing.cast(
            dict[str, typing.Any],
            get_openapi(
                title=application.title,
                version=application.version,
                openapi_version=application.openapi_version,
                description=application.description,
                routes=application.routes,
            ),
        )
        for path in openapi_schema.get("paths", {}).values():
            for operation in path.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses")
                if not isinstance(responses, dict):
                    continue
                validation_response = responses.get("422")
                if _is_fastapi_validation_response(validation_response):
                    responses["422"] = copy.deepcopy(_VALIDATION_ERROR_RESPONSE)

        component_schemas = openapi_schema.get("components", {}).get("schemas")
        if isinstance(component_schemas, dict):
            component_schemas.pop("HTTPValidationError", None)
            component_schemas.pop("ValidationError", None)

        application.openapi_schema = openapi_schema
        return openapi_schema

    typing.cast(typing.Any, application).openapi = custom_openapi
