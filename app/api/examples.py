"""OpenAPI 응답 예시 상수입니다."""

from app.core import error_codes
from app.schemas import common as common_schema

# ------------------ Detail --------------------
INVALID_CREDENTIALS_DETAIL = {
    "code": error_codes.ErrorCode.AUTH_CREDENTIALS_INVALID.value,
    "message": "아이디 또는 비밀번호가 올바르지 않습니다.",
}

UNAUTHORIZED_DETAIL = {
    "code": error_codes.ErrorCode.AUTH_SESSION_INVALID.value,
    "message": "인증 세션이 유효하지 않습니다.",
}


# ------------------ Example --------------------
_SUCCESS_RESPONSE_EXAMPLE = {
    "status": "success",
    "data": {
        "user_id": 1,
        "login_id": "user",
        "user_name": "일반 사용자",
        "role": "USER",
        "session": "centagging-poc-user-session",
    },
    "meta": {"request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"},
}

# ------------------ Response --------------------
LOGIN_SUCCESS_RESPONSE = {
    "description": "공통 성공 응답으로 사용자 정보와 고정 세션을 반환합니다.",
    "content": {"application/json": {"example": _SUCCESS_RESPONSE_EXAMPLE}},
}

ME_SUCCESS_RESPONSE = {
    "description": "공통 성공 응답으로 현재 사용자 정보를 반환합니다.",
    "content": {"application/json": {"example": _SUCCESS_RESPONSE_EXAMPLE}},
}

LOGIN_UNAUTHORIZED_RESPONSE = {
    "model": common_schema.ErrorResponse,
    "description": "아이디 또는 비밀번호가 일치하지 않은 경우입니다.",
    "content": {
        "application/json": {
            "example": {
                "status": "error",
                "error": {
                    "code": "AUTH_CREDENTIALS_INVALID",
                    "message": "아이디 또는 비밀번호가 올바르지 않습니다.",
                    "details": [],
                },
                "meta": {"request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"},
            }
        }
    },
}

SESSION_UNAUTHORIZED_RESPONSE = {
    "model": common_schema.ErrorResponse,
    "description": (
        "Bearer 세션이 없거나 형식이 잘못되었거나 "
        "DB 값과 일치하지 않은 경우입니다."
    ),
    "content": {
        "application/json": {
            "example": {
                "status": "error",
                "error": {
                    "code": "AUTH_SESSION_INVALID",
                    "message": "인증 세션이 유효하지 않습니다.",
                    "details": [],
                },
                "meta": {"request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"},
            }
        }
    },
}

LOGIN_VALIDATION_ERROR_RESPONSE = {
    "model": common_schema.ErrorResponse,
    "description": "아이디 또는 비밀번호가 없거나 형식이 올바르지 않은 경우입니다.",
    "content": {
        "application/json": {
            "example": {
                "status": "error",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "요청 값을 확인해 주세요.",
                    "details": [
                        {
                            "field": "login_id",
                            "reason": "min_length",
                            "message": "입력값이 너무 짧습니다.",
                        }
                    ],
                },
                "meta": {"request_id": "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"},
            }
        }
    },
}


# =====================================================================
# 공통 헬퍼
# =====================================================================
_REQUEST_ID_EXAMPLE = "f4a2c15c-2d9e-4b4f-90e6-3ad7c1c93bf0"
_META_EXAMPLE = {"request_id": _REQUEST_ID_EXAMPLE}


def _success_example(data: dict | list) -> dict:
    """공통 성공 응답(SuccessResponse) 형태의 Swagger 예시를 만듭니다."""
    return {"status": "success", "data": data, "meta": _META_EXAMPLE}


def _error_example(
    code: str,
    message: str,
    details: list[dict] | None = None,
) -> dict:
    """공통 오류 응답(ErrorResponse) 형태의 Swagger 예시를 만듭니다."""
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        },
        "meta": _META_EXAMPLE,
    }


def _error_response(
    description: str,
    code: str,
    message: str,
    details: list[dict] | None = None,
) -> dict:
    """오류 상태 코드 1건에 대한 Swagger responses 항목을 만듭니다."""
    return {
        "model": common_schema.ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "example": _error_example(code, message, details),
            }
        },
    }


VALIDATION_ERROR_RESPONSE = _error_response(
    "요청 값의 형식 또는 필수 여부가 올바르지 않은 경우입니다.",
    error_codes.ErrorCode.VALIDATION_ERROR.value,
    error_codes.ErrorCode.VALIDATION_ERROR.default_message,
    [
        {
            "field": "request",
            "reason": "invalid_value",
            "message": "입력값을 확인해 주세요.",
        }
    ],
)

INTERNAL_SERVER_ERROR_RESPONSE = _error_response(
    "서버 내부 처리 중 예상하지 못한 오류가 발생한 경우입니다.",
    error_codes.ErrorCode.INTERNAL_SERVER_ERROR.value,
    error_codes.ErrorCode.INTERNAL_SERVER_ERROR.default_message,
)


# =====================================================================
# scene_images.py - 연출 이미지 업로드 및 가구 객체 탐지
# =====================================================================
SCENE_IMAGE_UPLOAD_SUCCESS_EXAMPLE = _success_example(
    {
        "scene_image": {
            "scene_image_id": 101,
            "image_url": (
                "/uploads/scene-images/"
                "3f0a1c58-9d2e-4f0b-8a11-6c4d2e7b9f01.jpg"
            ),
            "origin_name": "living_room.jpg",
            "mime_type": "image/jpeg",
            "file_size": 1843200,
            "analysis_status": "detected",
            "analysis_error": None,
            "width_px": 1920,
            "height_px": 1280,
            "created_at": "2026-08-18T10:24:31.482000+09:00",
        },
        "object_count": 2,
        "objects": [
            {
                "object_idx": 0,
                "category": "소파",
                "sub_category": None,
                "bbox_coord": {
                    "xmin": 120,
                    "ymin": 430,
                    "xmax": 640,
                    "ymax": 780,
                },
                "confidence": 94,
                "evidence": "3인용 좌석과 팔걸이가 뚜렷하게 보입니다.",
            },
            {
                "object_idx": 1,
                "category": "테이블",
                "sub_category": None,
                "bbox_coord": {
                    "xmin": 660,
                    "ymin": 600,
                    "xmax": 880,
                    "ymax": 760,
                },
                "confidence": 87,
                "evidence": "소파 앞에 낮은 상판과 다리 구조가 확인됩니다.",
            },
        ],
    }
)

SCENE_IMAGE_UPLOAD_SUCCESS_RESPONSE = {
    "description": (
        "업로드한 연출 이미지 정보와 탐지된 가구 객체 목록을 반환합니다."
    ),
    "content": {
        "application/json": {"example": SCENE_IMAGE_UPLOAD_SUCCESS_EXAMPLE}
    },
}

# 비동기 작업 큐 도입 이후 업로드 API는 탐지 결과 대신 작업 접수 정보를
# 즉시 반환합니다. 실제 탐지 결과는 GET /ai-jobs/{job_id}로 조회합니다.
SCENE_IMAGE_UPLOAD_ACCEPTED_RESPONSE = {
    "description": "연출 이미지를 저장하고 가구 탐지 작업을 접수했습니다.",
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "scene_image_id": 101,
                    "job_id": "f3d4a95c-0e40-4cbb-a8ed-f0b1b2098f12",
                    "status": "PENDING",
                }
            )
        }
    },
}

SCENE_IMAGE_TOO_LARGE_RESPONSE = _error_response(
    "이미지 파일 용량이 10MB를 초과한 경우입니다.",
    error_codes.ErrorCode.BAD_REQUEST.value,
    "이미지 파일은 10MB 이하여야 합니다.",
)

SCENE_IMAGE_UNSUPPORTED_TYPE_RESPONSE = _error_response(
    (
        "JPEG 또는 PNG가 아니거나, 파일의 실제 형식과 "
        "MIME 타입이 일치하지 않는 경우입니다."
    ),
    error_codes.ErrorCode.BAD_REQUEST.value,
    "JPEG 또는 PNG 이미지만 업로드할 수 있습니다.",
)

# NOTE: 아래 예시는 공통 422 검증 오류 계약(details[0].field == "request")을
#       그대로 따릅니다. 이미지 디코딩에 실패한 경우에도 같은 422가 반환되며,
#       이때 message는 "유효한 이미지 파일이 아닙니다."이고 details는 비어 있습니다.
SCENE_IMAGE_INVALID_IMAGE_RESPONSE = _error_response(
    (
        "요청 값이 올바르지 않거나, 이미지를 디코딩할 수 없어 "
        "파일이 손상된 것으로 판단한 경우입니다. "
        "디코딩 실패 시 message는 '유효한 이미지 파일이 아닙니다.'이며 "
        "details는 빈 배열입니다."
    ),
    error_codes.ErrorCode.VALIDATION_ERROR.value,
    error_codes.ErrorCode.VALIDATION_ERROR.default_message,
    [
        {
            "field": "request",
            "reason": "invalid_value",
            "message": "입력값을 확인해 주세요.",
        }
    ],
)

SCENE_IMAGE_UPLOAD_FAILED_RESPONSE = _error_response(
    "파일 저장 또는 DB 기록에 실패해 업로드를 되돌린 경우입니다.",
    error_codes.ErrorCode.INTERNAL_SERVER_ERROR.value,
    "이미지 업로드 처리에 실패했습니다.",
)

SCENE_IMAGE_DETECTION_FAILED_RESPONSE = _error_response(
    "이미지 저장은 성공했지만 VLM 가구 탐지에 실패한 경우입니다.",
    error_codes.ErrorCode.UPSTREAM_ERROR.value,
    "가구 탐지에 실패했습니다.",
)


# =====================================================================
# tagging.py - 객체 편집 저장, 유사 SKU 추천, 태깅 결과 확정
# =====================================================================
_XAI_RESULT_EXAMPLE = {
    "summary": (
        "좌석 구조와 팔걸이 형태가 거의 일치하며 색상 계열도 동일합니다."
    ),
    "criteria": [
        {
            "label": "구조",
            "score": 27,
            "comment": "3인용 좌석 분할이 같습니다.",
        },
        {"label": "색상", "score": 24, "comment": "베이지 톤이 유사합니다."},
        {
            "label": "디테일",
            "score": 21,
            "comment": "쿠션 봉제선 처리가 비슷합니다.",
        },
        {
            "label": "맥락",
            "score": 20,
            "comment": "거실 중앙 배치 용도가 같습니다.",
        },
    ],
    "vlm_mood": {
        "summary": "따뜻하고 내추럴한 거실 분위기입니다.",
        "tags": ["내추럴", "모던", "미니멀"],
    },
}

SCENE_OBJECT_UPDATE_REQUEST_EXAMPLE = {
    "objects": [
        {
            "object_idx": 0,
            "category": "소파",
            "bbox_coord": {
                "xmin": 120.0,
                "ymin": 430.0,
                "xmax": 640.0,
                "ymax": 780.0,
            },
        },
        {
            "object_idx": 1,
            "category": "테이블",
            "bbox_coord": {
                "xmin": 660.0,
                "ymin": 600.0,
                "xmax": 880.0,
                "ymax": 760.0,
            },
        },
    ]
}

SCENE_OBJECT_UPDATE_SUCCESS_RESPONSE = {
    "description": "저장된 탐지 객체 개수와 처리 상태를 반환합니다.",
    "content": {
        "application/json": {
            "example": _success_example(
                {"object_count": 2, "processing_status": "DETECTED"}
            )
        }
    },
}

SKU_RECOMMENDATION_SUCCESS_RESPONSE = {
    "description": (
        "탐지 객체별 유사 SKU 후보와 XAI 판정 근거 목록을 반환합니다."
    ),
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "processing_status": "RECOMMENDED",
                    "scene_image": {
                        "scene_image_id": 101,
                        "image_url": (
                            "/uploads/scene-images/"
                            "3f0a1c58-9d2e-4f0b-8a11-6c4d2e7b9f01.jpg"
                        ),
                        "origin_name": "living_room.jpg",
                        "mime_type": "image/jpeg",
                        "file_size": 1843200,
                        "width_px": 1920,
                        "height_px": 1280,
                    },
                    "objects": [
                        {
                            "object_idx": 0,
                            "label": "소파",
                            "bbox_coord": {
                                "xmin": 120.0,
                                "ymin": 430.0,
                                "xmax": 640.0,
                                "ymax": 780.0,
                            },
                            "confidence": 94,
                            "attrs": {
                                "색상": "베이지",
                                "소재": "패브릭",
                                "스타일": "모던",
                            },
                            "sku_candidates": [
                                {
                                    "sku_id": 1001,
                                    "sku_code": "SKU-1001",
                                    "product_name": "린넨 3인용 소파 (베이지)",
                                    "category": "소파",
                                    "sub_category": "패브릭 소파",
                                    "attrs": {
                                        "색상": "베이지",
                                        "소재": "린넨",
                                        "스타일": "모던",
                                    },
                                    "similarity_score": 92,
                                    "matched_sku_image": {
                                        "sku_image_id": 5001,
                                        "image_type": "MAIN",
                                        "image_url": (
                                            "/sku-images/SKU-1001/main.jpg"
                                        ),
                                    },
                                    "xai_result": _XAI_RESULT_EXAMPLE,
                                }
                            ],
                        }
                    ],
                }
            )
        }
    },
}

SKU_RECOMMENDATION_ACCEPTED_RESPONSE = {
    "description": "SKU 추천 작업을 접수했습니다. 작업 상태와 결과는 AI 작업 조회 API로 확인합니다.",
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "scene_image_id": 101,
                    "job_id": "ab862f06-46df-40b2-898e-cb155bc35faa",
                    "status": "PENDING",
                }
            )
        }
    },
}

AI_JOB_NOT_READY_RESPONSE = _error_response(
    "가구 탐지가 아직 완료되지 않아 SKU 추천 작업을 접수할 수 없는 경우입니다.",
    error_codes.ErrorCode.RESOURCE_CONFLICT.value,
    "가구 탐지가 완료된 이미지에 대해서만 SKU 추천을 요청할 수 있습니다.",
)

ACTIVE_AI_JOB_EXISTS_RESPONSE = _error_response(
    "같은 이미지에 대해 같은 종류의 AI 작업이 이미 진행 중인 경우입니다.",
    error_codes.ErrorCode.RESOURCE_CONFLICT.value,
    "이미 진행 중인 SKU 추천 작업이 있습니다.",
)

AI_JOB_STATUS_RESPONSE = {
    "description": "AI 작업의 현재 상태와 완료된 경우 결과 payload를 반환합니다.",
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "job_id": "f3d4a95c-0e40-4cbb-a8ed-f0b1b2098f12",
                    "scene_image_id": 101,
                    "job_type": "DETECT_SCENE",
                    "status": "SUCCEEDED",
                    "attempt_count": 1,
                    "max_attempts": 3,
                    "result_payload": {
                        "object_count": 2,
                        "objects": [],
                    },
                    "error_code": None,
                    "error_message": None,
                    "created_at": "2026-08-19T10:24:31+09:00",
                    "started_at": "2026-08-19T10:24:32+09:00",
                    "finished_at": "2026-08-19T10:24:38+09:00",
                    "updated_at": "2026-08-19T10:24:38+09:00",
                }
            )
        }
    },
}

AI_JOB_NOT_FOUND_RESPONSE = _error_response(
    "존재하지 않는 AI 작업 ID로 조회한 경우입니다.",
    error_codes.ErrorCode.RESOURCE_NOT_FOUND.value,
    "AI 분석 작업을 찾을 수 없습니다.",
)

PRODUCT_IMAGE_SUBMISSION_JOB_STATUS_RESPONSE = {
    "description": (
        "제품 이미지 등록 추천 작업의 현재 상태와 완료된 경우 결과"
        " payload를 반환합니다."
    ),
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "job_id": "f3d4a95c-0e40-4cbb-a8ed-f0b1b2098f12",
                    "submission_id": 123,
                    "status": "SUCCEEDED",
                    "attempt_count": 1,
                    "max_attempts": 3,
                    "result_payload": {
                        "proposed_category": "소파",
                        "proposed_sub_category": "3인용",
                        "proposed_attributes": {
                            "color": "베이지",
                            "material": "패브릭",
                        },
                        "sku_candidates": [],
                    },
                    "error_code": None,
                    "error_message": None,
                    "created_at": "2026-08-25T00:00:00+09:00",
                    "started_at": "2026-08-25T00:00:01+09:00",
                    "finished_at": "2026-08-25T00:00:05+09:00",
                    "updated_at": "2026-08-25T00:00:05+09:00",
                }
            )
        }
    },
}

PRODUCT_IMAGE_SUBMISSION_JOB_NOT_FOUND_RESPONSE = _error_response(
    "존재하지 않는 제품 이미지 등록 추천 작업 ID로 조회한 경우입니다.",
    error_codes.ErrorCode.RESOURCE_NOT_FOUND.value,
    "제품 이미지 등록 추천 작업을 찾을 수 없습니다.",
)

SKU_MATCHING_REQUEST_EXAMPLE = {
    "tagging_results": [
        {
            "object_idx": 0,
            "sku_id": 1001,
            "match_rank": 1,
            "similarity_score": 92,
            "object_metadata": {
                "object_idx": 0,
                "category": "소파",
                "sub_category": "패브릭 소파",
                "bbox_coord": {
                    "xmin": 120.0,
                    "ymin": 430.0,
                    "xmax": 640.0,
                    "ymax": 780.0,
                },
                "attrs": {
                    "color": "베이지",
                    "material": "린넨",
                    "style": "모던",
                },
            },
            "xai_result": _XAI_RESULT_EXAMPLE,
            "vlm_mood": {
                "summary": "따뜻하고 내추럴한 거실 분위기입니다.",
                "tags": ["내추럴", "모던", "미니멀"],
            },
        }
    ]
}

TAGGING_RESULT_SAVE_SUCCESS_RESPONSE = {
    "description": "확정 처리 상태와 저장된 태깅 결과 ID 목록을 반환합니다.",
    "content": {
        "application/json": {
            "example": _success_example(
                {"processing_status": "CONFIRMED", "result_ids": [501, 502]}
            )
        }
    },
}

SEARCH_CANDIDATE_MOOD_REQUEST_EXAMPLE = {
    "object": {
        "object_idx": 0,
        "category": "소파",
        "bbox_coord": {
            "xmin": 120.0,
            "ymin": 430.0,
            "xmax": 640.0,
            "ymax": 780.0,
        },
    },
    "sku_code": "SKU-1001",
}

SEARCH_CANDIDATE_MOOD_SUCCESS_RESPONSE = {
    "description": "VLM이 크롭에서 읽어낸 공간 분위기 요약과 스타일 태그를 반환합니다.",
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "vlm_mood": {
                        "summary": "따뜻하고 내추럴한 거실 분위기입니다.",
                        "tags": ["내추럴", "우드톤", "아늑함"],
                    }
                }
            )
        }
    },
}

# NOTE: 태깅 라우터는 서비스 예외를 `detail=str(error)`로 그대로 전달하므로
#       message에 안내 문구가 아닌 원본 값(scene_image_id 등)이 담깁니다.
SCENE_IMAGE_NOT_FOUND_RESPONSE = _error_response(
    (
        "scene_id에 해당하는 연출 이미지가 없는 경우입니다. "
        "message에는 조회에 실패한 scene_image_id가 그대로 담깁니다."
    ),
    error_codes.ErrorCode.RESOURCE_NOT_FOUND.value,
    "101",
)

TAGGING_TARGET_NOT_FOUND_RESPONSE = _error_response(
    (
        "연출 이미지 또는 확정 대상 SKU를 찾지 못한 경우입니다. "
        "message에는 서비스 예외의 원본 값이 그대로 담깁니다."
    ),
    error_codes.ErrorCode.RESOURCE_NOT_FOUND.value,
    "101",
)

TAGGING_RESULT_UNPROCESSABLE_RESPONSE = _error_response(
    (
        "object_idx가 중복되었거나 장면에 존재하지 않는 인덱스인 경우입니다. "
        "message에는 문제가 된 object_idx가 그대로 담깁니다."
    ),
    error_codes.ErrorCode.VALIDATION_ERROR.value,
    "0",
)


# =====================================================================
# sku_search.py - SKU 임베딩 검색 및 상세 조회
# =====================================================================
# NOTE: 검색 API는 공통 SuccessResponse가 아닌 자체 응답 모델을 사용하므로
#       성공 예시에 meta 필드가 없습니다.
SKU_SEARCH_SUCCESS_RESPONSE = {
    "description": "유사도 내림차순으로 정렬된 SKU 검색 결과(최대 5건)입니다.",
    "content": {
        "application/json": {
            "example": {
                "status": "success",
                "data": {
                    "skus": [
                        {
                            "sku_code": "SKU-1001",
                            "product_name": "린넨 3인용 소파 (베이지)",
                            "category": "소파",
                            "sub_category": "패브릭 소파",
                            "image_url": "/sku-images/SKU-1001/main.jpg",
                            "brand": "센스홈",
                            "price": 899000,
                            "similarity_score": 0.8721,
                        },
                        {
                            "sku_code": "SKU-1042",
                            "product_name": "코지 4인용 패브릭 소파 (그레이)",
                            "category": "소파",
                            "sub_category": "패브릭 소파",
                            "image_url": "/sku-images/SKU-1042/main.jpg",
                            "brand": "리빙플러스",
                            "price": 1150000,
                            "similarity_score": 0.8134,
                        },
                    ]
                },
            }
        }
    },
}

SKU_DETAIL_SUCCESS_RESPONSE = {
    "description": (
        "SKU 기본 정보와 카테고리별 속성(attrs)을 함께 반환합니다. "
        "image_url은 MAIN 타입 이미지만 포함합니다."
    ),
    "content": {
        "application/json": {
            "example": {
                "status": "success",
                "data": {
                    "sku_code": "SKU-1001",
                    "product_name": "린넨 3인용 소파 (베이지)",
                    "brand": "센스홈",
                    "price": 899000,
                    "category": "소파",
                    "sub_category": "패브릭 소파",
                    "attrs": {
                        "색상": "베이지",
                        "소재": "린넨",
                        "스타일": "모던",
                        "인원수": "3인용",
                    },
                    "image_url": "/sku-images/SKU-1001/main.jpg",
                },
            }
        }
    },
}

SKU_SEARCH_INVALID_QUERY_RESPONSE = _error_response(
    "검색어(q)가 비어 있거나 공백만 입력된 경우입니다.",
    error_codes.ErrorCode.INVALID_QUERY.value,
    error_codes.ErrorCode.INVALID_QUERY.default_message,
)

SKU_NOT_FOUND_RESPONSE = _error_response(
    "요청한 SKU 코드가 존재하지 않는 경우입니다.",
    error_codes.ErrorCode.SKU_NOT_FOUND.value,
    error_codes.ErrorCode.SKU_NOT_FOUND.default_message,
)

SKU_SEARCH_UPSTREAM_ERROR_RESPONSE = _error_response(
    "임베딩 생성 또는 유사도 조회가 실패한 경우입니다.",
    error_codes.ErrorCode.UPSTREAM_ERROR.value,
    "검색어 처리 중 오류가 발생했습니다.",
)

SKU_SEARCH_UNAVAILABLE_RESPONSE = _error_response(
    "Gemini 인증 정보가 설정되지 않아 검색을 사용할 수 없는 경우입니다.",
    error_codes.ErrorCode.SERVICE_UNAVAILABLE.value,
    "검색 기능이 아직 설정되지 않았습니다.",
)


# =====================================================================
# history.py - 태깅 이력 목록 및 상세 조회
# =====================================================================
HISTORY_LIST_SUCCESS_RESPONSE = {
    "description": "최신순으로 정렬된 태깅 이력 목록을 반환합니다.",
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "items": [
                        {
                            "result_id": 501,
                            "sku_code": "SKU-1001",
                            "product_name": "린넨 3인용 소파 (베이지)",
                            "object_name": "소파",
                            "similarity_score": 92,
                            "created_by": "일반 사용자",
                            "created_at": "2026-08-18T10:31:07+09:00",
                            "approval_status": "ACTIVE",
                            "style_tags": ["내추럴", "모던"],
                            "scene_image": {
                                "image_url": (
                                    "/uploads/scene-images/"
                                    "3f0a1c58-9d2e-4f0b-8a11-6c4d2e7b9f01.jpg"
                                ),
                                "origin_name": "living_room.jpg",
                                "bbox": {
                                    "xmin": 120,
                                    "ymin": 430,
                                    "xmax": 640,
                                    "ymax": 780,
                                },
                            },
                        },
                        {
                            "result_id": 502,
                            "sku_code": "SKU-2007",
                            "product_name": "오크 원목 커피 테이블",
                            "object_name": "테이블",
                            "similarity_score": 85,
                            "created_by": "일반 사용자",
                            "created_at": "2026-08-18T10:31:07+09:00",
                            "approval_status": "PENDING",
                            "style_tags": ["내추럴"],
                            "scene_image": {
                                "image_url": (
                                    "/uploads/scene-images/"
                                    "3f0a1c58-9d2e-4f0b-8a11-6c4d2e7b9f01.jpg"
                                ),
                                "origin_name": "living_room.jpg",
                                "bbox": {
                                    "xmin": 660,
                                    "ymin": 600,
                                    "xmax": 880,
                                    "ymax": 760,
                                },
                            },
                        },
                    ]
                }
            )
        }
    },
}

HISTORY_DETAIL_SUCCESS_RESPONSE = {
    "description": (
        "연출 이미지, 탐지 객체, 확정 SKU와 XAI 근거를 함께 반환합니다."
    ),
    "content": {
        "application/json": {
            "example": _success_example(
                {
                    "result_id": 501,
                    "created_by": "일반 사용자",
                    "created_at": "2026-08-18T10:31:07+09:00",
                    "similarity_score": 92,
                    "scene_image": {
                        "image_url": (
                            "/uploads/scene-images/"
                            "3f0a1c58-9d2e-4f0b-8a11-6c4d2e7b9f01.jpg"
                        ),
                        "origin_name": "living_room.jpg",
                    },
                    "detected_object": {
                        "category": "소파",
                        "sub_category": "패브릭 소파",
                        "attrs": {
                            "color": "베이지",
                            "material": "린넨",
                            "style": "모던",
                        },
                        "bbox": {
                            "xmin": 120,
                            "ymin": 430,
                            "xmax": 640,
                            "ymax": 780,
                        },
                        "vlm_mood": {
                            "summary": "따뜻하고 내추럴한 거실 분위기입니다.",
                            "tags": ["내추럴", "모던", "미니멀"],
                        },
                    },
                    "matched_sku": {
                        "sku_code": "SKU-1001",
                        "product_name": "린넨 3인용 소파 (베이지)",
                        "brand": "센스홈",
                        "price": 899000,
                        "image_url": "/sku-images/SKU-1001/main.jpg",
                        "category": "소파",
                        "sub_category": "패브릭 소파",
                        "attrs": {
                            "색상": "베이지",
                            "소재": "린넨",
                            "스타일": "모던",
                        },
                    },
                    "xai_result": {
                        "summary": _XAI_RESULT_EXAMPLE["summary"],
                        "criteria": _XAI_RESULT_EXAMPLE["criteria"],
                    },
                }
            )
        }
    },
}

HISTORY_NOT_FOUND_RESPONSE = _error_response(
    "result_id에 해당하는 태깅 이력이 없는 경우입니다.",
    error_codes.ErrorCode.RESOURCE_NOT_FOUND.value,
    "태깅 이력을 찾을 수 없습니다.",
)
