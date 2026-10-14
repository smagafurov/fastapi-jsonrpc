import importlib.metadata
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Optional

from opentelemetry.trace import SpanKind, TracerProvider, get_tracer

from fastapi_jsonrpc import JsonRpcContext

__all__ = [
    'OpenTelemetryMiddleware',
]

RPC_SYSTEM_NAME = 'rpc.system.name'
RPC_METHOD = 'rpc.method'
JSONRPC_PROTOCOL_VERSION = 'jsonrpc.protocol.version'
JSONRPC_REQUEST_ID = 'jsonrpc.request.id'


class OpenTelemetryMiddleware:
    def __init__(self, *, tracer_provider: Optional[TracerProvider] = None):
        self._tracer = get_tracer(
            'fastapi_jsonrpc',
            importlib.metadata.version('fastapi-jsonrpc'),
            tracer_provider=tracer_provider,
        )

    @asynccontextmanager
    async def __call__(self, ctx: JsonRpcContext) -> AsyncGenerator[None, None]:
        method = ctx.raw_request['method']
        attributes: Dict[str, str] = {
            RPC_SYSTEM_NAME: 'jsonrpc',
            RPC_METHOD: method,
            JSONRPC_PROTOCOL_VERSION: '2.0',
        }
        request_id = ctx.raw_request.get('id')
        if request_id is not None:
            attributes[JSONRPC_REQUEST_ID] = str(request_id)

        with self._tracer.start_as_current_span(
            method,
            kind=SpanKind.SERVER,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ):
            yield
