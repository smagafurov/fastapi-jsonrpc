import pytest
from fastapi import Body, HTTPException
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import fastapi_jsonrpc as jsonrpc
from fastapi_jsonrpc.contrib.opentelemetry import OpenTelemetryMiddleware


class MyError(jsonrpc.BaseError):
    CODE = 5000
    MESSAGE = 'My error'


@pytest.fixture
def span_exporter():
    return InMemorySpanExporter()


@pytest.fixture
def tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    yield provider
    provider.shutdown()


@pytest.fixture
def metric_reader():
    return InMemoryMetricReader()


@pytest.fixture
def meter_provider(metric_reader):
    provider = MeterProvider(metric_readers=[metric_reader])
    yield provider
    provider.shutdown()


@pytest.fixture
def finished_spans(span_exporter):
    def get():
        return span_exporter.get_finished_spans()

    return get


@pytest.fixture
def middleware_options():
    return {}


@pytest.fixture
def ep(ep_path, tracer_provider, middleware_options):
    ep = jsonrpc.Entrypoint(
        ep_path,
        middlewares=[OpenTelemetryMiddleware(tracer_provider=tracer_provider, **middleware_options)],
    )

    @ep.method()
    def echo(data: str = Body(...)) -> str:
        return data

    @ep.method()
    def traced_echo(data: str = Body(...)) -> str:
        with tracer_provider.get_tracer('test').start_as_current_span('inside method'):
            return data

    @ep.method(errors=[MyError])
    def fail_with_error() -> None:
        raise MyError()

    @ep.method()
    def fail_with_http_exception() -> None:
        raise HTTPException(403)

    return ep
