import asyncio

import httpx
import pytest
from fastapi import Body
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import SpanKind
from starlette.testclient import TestClient

import fastapi_jsonrpc as jsonrpc
from fastapi_jsonrpc.contrib.opentelemetry import OpenTelemetryMiddleware

REQUESTS_COUNT = 5


@pytest.fixture
def app(app, tracer_provider):
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, exclude_spans=['receive', 'send'])
    yield app
    FastAPIInstrumentor.uninstrument_app(app)


@pytest.fixture
def split_spans(finished_spans):
    def split():
        http_spans, call_spans = [], []
        for span in finished_spans():
            if span.instrumentation_scope.name == 'fastapi_jsonrpc':
                call_spans.append(span)
            elif span.kind == SpanKind.SERVER:
                http_spans.append(span)
        return http_spans, call_spans

    return split


def test_call_spans_are_children_of_http_span(json_request, split_spans):
    json_request([
        {'id': 1, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'one'}},
        {'id': 2, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'two'}},
        {'id': 3, 'jsonrpc': '2.0', 'method': 'nope', 'params': {}},
    ])

    [http_span], call_spans = split_spans()
    assert len(call_spans) == 3
    assert {span.parent.span_id for span in call_spans} == {http_span.context.span_id}
    assert {span.context.trace_id for span in call_spans} == {http_span.context.trace_id}


@pytest.mark.parametrize('ep_options', [{'scheduler_kwargs': {'limit': 1}}])
def test_calls_queued_by_scheduler_keep_their_http_parent(app, ep, ep_path, split_spans):
    async def main():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            await asyncio.gather(*(
                client.post(ep_path, json={'id': i, 'jsonrpc': '2.0', 'method': 'slow', 'params': {}})
                for i in range(REQUESTS_COUNT)
            ))
        await ep.scheduler.wait_and_close()

    asyncio.run(main())

    http_spans, call_spans = split_spans()
    assert len(http_spans) == len(call_spans) == REQUESTS_COUNT
    assert sorted(span.parent.span_id for span in call_spans) == sorted(span.context.span_id for span in http_spans)
    http_trace_ids = {span.context.span_id: span.context.trace_id for span in http_spans}
    assert all(span.context.trace_id == http_trace_ids[span.parent.span_id] for span in call_spans)


def test_without_sdk_responses_are_unchanged(ep_path):
    assert isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider)

    def build_app(middlewares):
        ep = jsonrpc.Entrypoint(ep_path, middlewares=middlewares)

        @ep.method()
        def echo(data: str = Body(...)) -> str:
            return data

        app = jsonrpc.API()
        app.bind_entrypoint(ep)
        return app

    body = [
        {'id': 1, 'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'hi'}},
        {'id': 2, 'jsonrpc': '2.0', 'method': 'echo', 'params': {}},
        {'id': 3, 'jsonrpc': '2.0', 'method': 'nope', 'params': {}},
        {'jsonrpc': '2.0', 'method': 'echo', 'params': {'data': 'notification'}},
        1,
    ]
    responses = []
    for middlewares in ([], [OpenTelemetryMiddleware()]):
        with TestClient(build_app(middlewares)) as client:
            responses.append(client.post(ep_path, json=body).json())

    without_middleware, with_middleware = responses
    assert with_middleware == without_middleware
