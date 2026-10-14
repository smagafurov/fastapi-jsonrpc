import asyncio
import contextvars

import httpx
import pytest
from fastapi import Body

import fastapi_jsonrpc as jsonrpc

request_tag: contextvars.ContextVar[str] = contextvars.ContextVar('request_tag')

REQUESTS_COUNT = 5


class RequestTagMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            request_tag.set(dict(scope['headers'])[b'x-request-tag'].decode())
        await self.app(scope, receive, send)


@pytest.fixture
def notified_tags():
    return []


@pytest.fixture
def ep(ep_path, notified_tags):
    ep =jsonrpc.Entrypoint(ep_path, scheduler_kwargs={'limit': 1})

    @ep.method()
    async def seen_tag() -> str:
        await asyncio.sleep(0.01)
        return request_tag.get()

    @ep.method()
    async def notify(sent_tag: str = Body(...)) -> None:
        await asyncio.sleep(0.01)
        notified_tags.append((sent_tag, request_tag.get()))

    return ep


@pytest.fixture
def app(app):
    app.add_middleware(RequestTagMiddleware)
    return app


@pytest.fixture
def send_concurrently(app, ep, ep_path):
    def send(make_body):
        async def main():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                responses = await asyncio.gather(*(
                    client.post(ep_path, json=make_body(f'req-{i}'), headers={'X-Request-Tag': f'req-{i}'})
                    for i in range(REQUESTS_COUNT)
                ))
            await ep.scheduler.wait_and_close()
            return responses

        return asyncio.run(main())

    return send


def test_queued_calls_see_own_request_context(send_concurrently):
    responses = send_concurrently(lambda tag: {'id': tag, 'jsonrpc': '2.0', 'method': 'seen_tag', 'params': {}})

    assert [resp.json() for resp in responses] == [
        {'id': f'req-{i}', 'jsonrpc': '2.0', 'result': f'req-{i}'}
        for i in range(REQUESTS_COUNT)
    ]


def test_queued_notifications_see_own_request_context(send_concurrently, notified_tags):
    send_concurrently(lambda tag: {'jsonrpc': '2.0', 'method': 'notify', 'params': {'sent_tag': tag}})

    assert sorted(notified_tags) == [(f'req-{i}', f'req-{i}') for i in range(REQUESTS_COUNT)]
