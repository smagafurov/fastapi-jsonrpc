import importlib.metadata
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Dict, Optional, Union

from opentelemetry.metrics import Histogram, MeterProvider, get_meter
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, TracerProvider, get_tracer

from fastapi_jsonrpc import Entrypoint, JsonRpcContext, MethodRoute

__all__ = [
    'ExceptionFilter',
    'OpenTelemetryMiddleware',
]

logger = logging.getLogger(__name__)

ExceptionFilter = Callable[[Exception], Optional[Exception]]

RPC_SYSTEM_NAME = 'rpc.system.name'
RPC_METHOD = 'rpc.method'
RPC_METHOD_ORIGINAL = 'rpc.method_original'
RPC_STATUS_CODE = 'rpc.status_code'
ERROR_TYPE = 'error.type'
JSONRPC_PROTOCOL_VERSION = 'jsonrpc.protocol.version'
JSONRPC_REQUEST_ID = 'jsonrpc.request.id'

RPC_SYSTEM = 'jsonrpc'
OTHER_METHOD = '_OTHER'

INSTRUMENTATION_NAME = 'fastapi_jsonrpc'
METRIC_ATTRIBUTES = (RPC_SYSTEM_NAME, RPC_METHOD)
DURATION_BUCKET_BOUNDARIES = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10]


class OpenTelemetryMiddleware:
    def __init__(
        self,
        *,
        tracer_provider: Optional[TracerProvider] = None,
        meter_provider: Optional[MeterProvider] = None,
        enable_metrics: bool = True,
        record_exception: Union[bool, ExceptionFilter] = False,
    ):
        version = importlib.metadata.version('fastapi-jsonrpc')
        self._tracer = get_tracer(INSTRUMENTATION_NAME, version, tracer_provider=tracer_provider)
        self._duration: Optional[Histogram] = None
        if enable_metrics:
            self._duration = get_meter(INSTRUMENTATION_NAME, version, meter_provider=meter_provider).create_histogram(
                'rpc.server.call.duration',
                unit='s',
                description='Measures the duration of an incoming Remote Procedure Call (RPC).',
                explicit_bucket_boundaries_advisory=DURATION_BUCKET_BOUNDARIES,
            )
        self._exception_filter: Optional[ExceptionFilter]
        if record_exception is True:
            self._exception_filter = _record_as_is
        elif record_exception is False:
            self._exception_filter = None
        else:
            self._exception_filter = record_exception

    @asynccontextmanager
    async def __call__(self, ctx: JsonRpcContext) -> AsyncGenerator[None, None]:
        started = time.perf_counter()
        raw_request =ctx.raw_request if isinstance(ctx.raw_request, dict) else {}
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
                outcome = _set_outcome(span, ctx)
                if ctx.is_unhandled_exception and ctx.exception is not None:
                    self._record_exception(span, ctx.exception)
                if self._duration is not None:
                    metric_attributes = {key: attributes[key] for key in METRIC_ATTRIBUTES if key in attributes}
                    self._duration.record(time.perf_counter() - started, {**metric_attributes, **outcome})

    def _record_exception(self, span: Span, exception: Exception) -> None:
        if self._exception_filter is None:
            return
        try:
            recorded = self._exception_filter(exception)
        except Exception:
            logger.warning('record_exception filter failed, the exception is not recorded', exc_info=True)
            return
        if recorded is not None:
            span.record_exception(recorded)


def _record_as_is(exception: Exception) -> Exception:
    return exception


def _is_registered(entrypoint: Entrypoint, method: str) -> bool:
    return any(isinstance(route, MethodRoute) and route.name == method for route in entrypoint.routes)


def _set_outcome(span: Span, ctx: JsonRpcContext) -> Dict[str, str]:
    outcome: Dict[str, str] = {}
    error: Optional[Dict[str, Any]] = (ctx.raw_response or {}).get('error')
    if error is not None:
        code = str(error['code'])
        outcome = {ERROR_TYPE: code, RPC_STATUS_CODE: code}
        span.set_status(Status(StatusCode.ERROR, error['message']))
    elif ctx.exception is not None:
        exception_type = type(ctx.exception)
        outcome = {ERROR_TYPE: f'{exception_type.__module__}.{exception_type.__qualname__}'}
        span.set_status(Status(StatusCode.ERROR))
    span.set_attributes(outcome)
    return outcome
