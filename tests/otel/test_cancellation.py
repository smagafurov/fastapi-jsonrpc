import asyncio
import contextlib

import httpx
import pytest
from opentelemetry.trace import StatusCode

import fastapi_jsonrpc as jsonrpc

SAFETY_TIMEOUT_SECONDS = 5


@pytest.fixture
def method_started():
    return asyncio.Event()


@pytest.fixture
def method_released():
    return asyncio.Event()


@pytest.fixture
def method_cancelled():
    return asyncio.Event()


@pytest.fixture
def finalized_spans():
    return []


@pytest.fixture
def middleware_options(finalized_spans):
    return {'response_hook': lambda span, _ctx: finalized_spans.append(span.get_span_context().span_id)}


@pytest.fixture
def ep(ep, method_started, method_released, method_cancelled):
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
    async def wait_for_release() -> str:
        method_started.set()
        try:
            await method_released.wait()
        except asyncio.CancelledError:
            method_cancelled.set()
            raise
        return 'released'

    return ep


@contextlib.asynccontextmanager
async def time_out_quickly(_ctx: jsonrpc.JsonRpcContext):
    task = asyncio.current_task()
    assert task is not None
    timer = asyncio.get_running_loop().call_later(0.01, task.cancel)
    try:
        yield
    except asyncio.CancelledError:
        if hasattr(task, 'uncancel'):
            task.uncancel()
        raise asyncio.TimeoutError()
    finally:
        timer.cancel()


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


def test_cancelled_http_task_does_not_cancel_running_call(
    run, ep, method_started, method_released, method_cancelled, finished_spans, duration_points, finalized_spans,
):
    async def scenario(post):
        request = asyncio.ensure_future(post('wait_for_release'))
        try:
            await asyncio.wait_for(method_started.wait(), SAFETY_TIMEOUT_SECONDS)
            request.cancel()
            [outcome] = await asyncio.gather(request, return_exceptions=True)
            assert isinstance(outcome, asyncio.CancelledError)

            assert not method_cancelled.is_set()
            assert finished_spans() == ()
            assert finalized_spans == []
            assert duration_points() == []

            method_released.set()
            await asyncio.wait_for(ep.scheduler.wait_and_close(), SAFETY_TIMEOUT_SECONDS)
        finally:
            method_released.set()
            await ep.shutdown()

    run(scenario)

    assert not method_cancelled.is_set()
    assert_finalized_once_without_error(finished_spans, duration_points, finalized_spans)


@pytest.mark.parametrize('timeout_first, expected_status, expected_error_type', [
    (True, StatusCode.UNSET, None),
    (False, StatusCode.ERROR, '-32603'),
], ids=['[timeout, otel]', '[otel, timeout]'])
def test_timeout_in_jsonrpc_middleware_depends_on_order(
    ep, json_request, method_cancelled, finished_spans, duration_points, assert_log_errors,
    timeout_first, expected_status, expected_error_type,
):
    if timeout_first:
        ep.middlewares.insert(0, time_out_quickly)
    else:
        ep.middlewares.append(time_out_quickly)

    resp = json_request({'id': 1, 'jsonrpc': '2.0', 'method': 'wait_for_release', 'params': {}})

    assert resp['error'] == {'code': -32603, 'message': 'Internal error'}
    assert_log_errors('', pytest.raises(asyncio.TimeoutError))
    assert method_cancelled.is_set()
    [span] = finished_spans()
    assert span.status.status_code == expected_status
    assert span.attributes.get('error.type') == expected_error_type
    [(_, point)] = duration_points()
    assert point.attributes.get('error.type') == expected_error_type
