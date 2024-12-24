import uuid
from functools import wraps
from contextvars import ContextVar

from starlette.requests import Request
from sentry_sdk.integrations.asgi import _get_headers

sentry_asgi_context: ContextVar[dict] = ContextVar("_sentry_asgi_context")


def set_shared_sentry_context(cls):
    original_handle_body = cls.handle_body

    @wraps(original_handle_body)
    async def _patched_handle_body(self, http_request: Request, *args, **kwargs):
        headers = _get_headers(http_request.scope)
        sentry_asgi_context.set({"sampled_sentry_trace_id": uuid.uuid4(), "asgi_headers": headers})
        return await original_handle_body(self, http_request, *args, **kwargs)

    cls.handle_body = _patched_handle_body
