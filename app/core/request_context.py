"""요청 단위 추적에 사용하는 request_id 컨텍스트를 관리합니다."""

import collections.abc
import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def create_request_id() -> str:
    """새 UUID 형식의 요청 ID를 생성합니다."""
    return str(uuid.uuid4())


def get_request_id() -> str | None:
    """현재 요청 컨텍스트의 요청 ID를 반환합니다."""
    return _request_id_context.get()


def get_or_create_request_id() -> str:
    """현재 요청 ID가 없으면 생성한 뒤 반환합니다."""
    request_id = get_request_id()
    if request_id is not None:
        return request_id

    request_id = create_request_id()
    _request_id_context.set(request_id)
    return request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """요청마다 request_id를 만들고 응답 헤더에 전달합니다."""

    async def dispatch(
        self,
        request: Request,
        call_next: collections.abc.Callable[
            [Request], collections.abc.Awaitable[Response]
        ],
    ) -> Response:
        """요청 컨텍스트와 응답에 동일한 요청 ID를 설정합니다."""
        request_id = create_request_id()
        request.state.request_id = request_id
        context_token = _request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _request_id_context.reset(context_token)
