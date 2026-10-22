import asyncio

import httpx
import pytest
from opentelemetry.trace import StatusCode

SLOW_SECONDS = 0.2


@pytest.fixture
def method_started():
    return asyncio.Event()


@pytest.fixture
def finalized_spans():
    return []


@pytest.fixture
def middleware_options(finalized_spans):
    return {'response_hook': lambda span, _ctx: finalized_spans.append(span.get_span_context().span_id)}


@pytest.fixture
def ep(ep, method_started):
    @ep.method()
    async def hang() -> None:
        method_started.set()
        await asyncio.sleep(10)

    @ep.method()
    async def survive_cancellation() -> str:
        method_started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return 'recovered'
        return 'not cancelled'

    @ep.method()
    async def time_out_inside() -> None:
        await asyncio.wait_for(asyncio.sleep(10), 0.01)

    @ep.method()
    async def take_a_while() -> str:
        await asyncio.sleep(SLOW_SECONDS)
        return 'done'

    return ep


@pytest.fixture
def run(app, ep_path):
    def run_(scenario):
        async def main():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                def post(method):
                    return client.post(ep_path, json={'id': 1, 'jsonrpc': '2.0', 'method': method, 'params': {}})

                return await scenario(post)

        return asyncio.run(main())

    return run_


def assert_finalized_once_without_error(finished_spans, duration_points, finalized_spans):
    [span] = finished_spans()
    assert finalized_spans == [span.context.span_id]
    assert span.status.status_code == StatusCode.UNSET
    assert 'error.type' not in span.attributes
    assert 'rpc.status_code' not in span.attributes
    assert span.events == ()
    [(_, point)] = duration_points()
    assert point.count == 1
    assert 'error.type' not in point.attributes
    return span, point


def test_cancelled_call_propagates_and_finalizes_once(
    run, ep, method_started, finished_spans, duration_points, finalized_spans,
):
    async def scenario(post):
        request = asyncio.ensure_future(post('hang'))
        await method_started.wait()
        await ep.scheduler.close()
        [outcome] = await asyncio.gather(request, return_exceptions=True)
        return outcome

    assert isinstance(run(scenario), asyncio.CancelledError)

    assert_finalized_once_without_error(finished_spans, duration_points, finalized_spans)


def test_method_catching_cancellation_succeeds(
    run, ep, method_started, finished_spans, duration_points, finalized_spans,
):
    async def scenario(post):
        request = asyncio.ensure_future(post('survive_cancellation'))
        await method_started.wait()
        await ep.scheduler.close()
        return await request

    assert run(scenario).json() == {'id': 1, 'jsonrpc': '2.0', 'result': 'recovered'}

    assert_finalized_once_without_error(finished_spans, duration_points, finalized_spans)


def test_timeout_inside_the_boundary_is_an_internal_error(
    run, ep, finished_spans, duration_points, finalized_spans, assert_log_errors,
):
    async def scenario(post):
        response = await post('time_out_inside')
        await ep.scheduler.wait_and_close()
        return response

    assert run(scenario).json()['error'] == {'code': -32603, 'message': 'Internal error'}
    assert_log_errors('', pytest.raises(asyncio.TimeoutError))

    [span] = finished_spans()
    assert finalized_spans == [span.context.span_id]
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes['error.type'] == '-32603'
    [(_, point)] = duration_points()
    assert point.attributes['error.type'] == '-32603'


def test_timeout_outside_the_boundary_is_not_seen(
    run, ep, finished_spans, duration_points, finalized_spans,
):
    async def scenario(post):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(post('take_a_while'), SLOW_SECONDS / 4)
        assert finished_spans() == ()
        await ep.scheduler.wait_and_close()

    run(scenario)

    _, point = assert_finalized_once_without_error(finished_spans, duration_points, finalized_spans)
    assert point.sum >= SLOW_SECONDS
