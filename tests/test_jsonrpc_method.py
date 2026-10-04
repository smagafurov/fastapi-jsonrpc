import asyncio
import functools
import threading

import pytest
from fastapi import Body, Depends

from fastapi_jsonrpc import get_jsonrpc_method


@pytest.fixture
def probe(ep):
    @ep.method()
    def probe(
        jsonrpc_method: str = Depends(get_jsonrpc_method),
    ) -> str:
        return jsonrpc_method

    @ep.method()
    def probe2(
        jsonrpc_method: str = Depends(get_jsonrpc_method),
    ) -> str:
        return jsonrpc_method

    return ep


def test_basic(probe, json_request):
    resp = json_request({
        'id': 123,
        'jsonrpc': '2.0',
        'method': 'probe',
        'params': {},
    })
    assert resp == {'id': 123, 'jsonrpc': '2.0', 'result': 'probe'}


def test_batch(probe, json_request):
    resp = json_request([
        {
            'id': 1,
            'jsonrpc': '2.0',
            'method': 'probe',
            'params': {},
        },
        {
            'id': 2,
            'jsonrpc': '2.0',
            'method': 'probe2',
            'params': {},
        },
    ])
    assert resp == [
        {'id': 1, 'jsonrpc': '2.0', 'result': 'probe'},
        {'id': 2, 'jsonrpc': '2.0', 'result': 'probe2'},
    ]


@pytest.fixture(params=["async", "async_partial", "sync", "sync_partial"])
def wrapped_method(ep, request):
    calls = []

    def wrapped_probe(data: str = Body(...)) -> str:
        calls.append((data, threading.get_ident()))
        return data

    class AsyncWrapper:
        def __init__(self, func):
            functools.update_wrapper(self, func)
            self.__annotations__ = func.__annotations__

        async def __call__(self, *args, **kwargs):
            await asyncio.sleep(0)
            return self.__wrapped__(*args, **kwargs)

    class SyncWrapper:
        def __init__(self, func):
            functools.update_wrapper(self, func)
            self.__annotations__ = func.__annotations__

        def __call__(self, *args, **kwargs):
            return self.__wrapped__(*args, **kwargs)

    is_async = request.param.startswith("async")
    wrapper = AsyncWrapper(wrapped_probe) if is_async else SyncWrapper(wrapped_probe)
    if request.param.endswith("partial"):
        wrapper = functools.update_wrapper(functools.partial(wrapper), wrapped_probe)
        wrapper.__annotations__ = wrapped_probe.__annotations__
    ep.method()(wrapper)
    return calls, is_async


def test_wrapped_method(wrapped_method, method_request, app_client):
    calls, is_async = wrapped_method
    response = method_request("wrapped_probe", {"data": "hello"}, request_id=123)
    assert response == {"id": 123, "jsonrpc": "2.0", "result": "hello"}
    assert len(calls) == 1
    assert calls[0][0] == "hello"
    loop_thread = app_client.portal.call(threading.get_ident)
    assert (calls[0][1] == loop_thread) == is_async


def test_wrapped_method_batch(wrapped_method, json_request, app_client):
    calls, is_async = wrapped_method
    response = json_request([
        {"id": 1, "jsonrpc": "2.0", "method": "wrapped_probe", "params": {"data": "one"}},
        {"id": 2, "jsonrpc": "2.0", "method": "wrapped_probe", "params": {"data": "two"}},
    ])
    assert response == [
        {"id": 1, "jsonrpc": "2.0", "result": "one"},
        {"id": 2, "jsonrpc": "2.0", "result": "two"},
    ]
    assert sorted(data for data, _ in calls) == ["one", "two"]
    loop_thread = app_client.portal.call(threading.get_ident)
    assert all((thread == loop_thread) == is_async for _, thread in calls)


@pytest.mark.parametrize("path_postfix", ["", "/wrapped_probe"])
def test_wrapped_method_notification(
    wrapped_method, app_client, ep_path, path_postfix, ep_wait_all_requests_done,
):
    calls, is_async = wrapped_method
    response = app_client.post(ep_path + path_postfix, json={
        "jsonrpc": "2.0", "method": "wrapped_probe", "params": {"data": "notification"},
    })
    assert response.status_code == 200
    assert response.content == b""
    ep_wait_all_requests_done()
    assert len(calls) == 1
    assert calls[0][0] == "notification"
    loop_thread = app_client.portal.call(threading.get_ident)
    assert (calls[0][1] == loop_thread) == is_async
