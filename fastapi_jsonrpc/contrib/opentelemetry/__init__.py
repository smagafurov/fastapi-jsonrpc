import importlib.metadata
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

from opentelemetry.trace import Span, SpanKind, Status, StatusCode, TracerProvider, get_tracer

from fastapi_jsonrpc import Entrypoint, JsonRpcContext, MethodRoute

__all__ = [
    'OpenTelemetryMiddleware',
]

RPC_SYSTEM_NAME = 'rpc.system.name'
RPC_METHOD = 'rpc.method'
RPC_METHOD_ORIGINAL = 'rpc.method_original'
RPC_STATUS_CODE = 'rpc.status_code'
ERROR_TYPE = 'error.type'
JSONRPC_PROTOCOL_VERSION = 'jsonrpc.protocol.version'
JSONRPC_REQUEST_ID = 'jsonrpc.request.id'

RPC_SYSTEM = 'jsonrpc'
OTHER_METHOD = '_OTHER'


class OpenTelemetryMiddleware:
    def __init__(self, *, tracer_provider: Optional[TracerProvider] = None):
        self._tracer = get_tracer(
            'fastapi_jsonrpc',
            importlib.metadata.version('fastapi-jsonrpc'),
            tracer_provider=tracer_provider,
        )

    @asynccontextmanager
    async def __call__(self, ctx: JsonRpcContext) -> AsyncGenerator[None, None]:
        raw_request = ctx.raw_request if isinstance(ctx.raw_request, dict) else {}
        span_name = RPC_SYSTEM
        attributes: Dict[str, str] = {
            RPC_SYSTEM_NAME: RPC_SYSTEM,
            JSONRPC_PROTOCOL_VERSION: '2.0',
        }

        requested_method = raw_request.get('method')
        if isinstance(requested_method, str):
            if _is_registered(ctx.entrypoint, requested_method):
                span_name = requested_method
                attributes[RPC_METHOD] = requested_method
            else:
                attributes[RPC_METHOD] = OTHER_METHOD
                attributes[RPC_METHOD_ORIGINAL] = requested_method

        request_id = raw_request.get('id')
        if request_id is not None:
            attributes[JSONRPC_REQUEST_ID] = str(request_id)

        with self._tracer.start_as_current_span(
            span_name,
            kind=SpanKind.SERVER,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield
            finally:
                _set_outcome(span, ctx)


def _is_registered(entrypoint: Entrypoint, method: str) -> bool:
    return any(isinstance(route, MethodRoute) and route.name == method for route in entrypoint.routes)


def _set_outcome(span: Span, ctx: JsonRpcContext) -> None:
    error: Optional[Dict[str, Any]] = (ctx.raw_response or {}).get('error')
    if error is not None:
        code = str(error['code'])
        span.set_attribute(ERROR_TYPE, code)
        span.set_attribute(RPC_STATUS_CODE, code)
        span.set_status(Status(StatusCode.ERROR, error['message']))
    elif ctx.exception is not None:
        exception_type = type(ctx.exception)
        span.set_attribute(ERROR_TYPE, f'{exception_type.__module__}.{exception_type.__qualname__}')
        span.set_status(Status(StatusCode.ERROR))
