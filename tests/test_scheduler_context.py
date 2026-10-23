import asyncio
import contextvars
import gc
import warnings

import aiojobs
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


@pytest.mark.parametrize('notification,suffix', [
    (False, ''),
    (True, ''),
    (True, '/notify'),
], ids=['generic-call', 'generic-notification', 'dedicated-notification'])
def test_http_requests_do_not_create_context_trampoline_tasks(app, ep, ep_path, notified_tags, notification, suffix):
    async def main():
        loop = asyncio.get_running_loop()
        previous_factory = loop.get_task_factory()
        trampoline_tasks = []

        def record_task(loop, coro, **kwargs):
            # Count only the context trampoline: HTTP and scheduler housekeeping
            # may legitimately create other tasks, independently of RPC execution.
            if getattr(coro, '__name__', None) == '_run_in_context':
                trampoline_tasks.append(coro.__name__)
            if previous_factory is not None:
                return previous_factory(loop, coro, **kwargs)
            return asyncio.Task(coro, loop=loop, **kwargs)

        body: dict[str, object] = {'jsonrpc': '2.0', 'method': 'notify' if notification else 'seen_tag'}
        if notification:
            body['params'] = {'sent_tag': 'single'}
        else:
            body['id'] = 1

        loop.set_task_factory(record_task)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post(ep_path + suffix, json=body, headers={'X-Request-Tag': 'single'})
            # Notifications outlive the HTTP response, so include their execution
            # in the observation window rather than relying on event-loop timing.
            await ep.scheduler.wait_and_close()
        finally:
            try:
                await ep.shutdown()
            finally:
                loop.set_task_factory(previous_factory)

        assert response.status_code == 200
        if notification:
            assert response.content == b''
            assert notified_tags == [('single', 'single')]
        else:
            assert response.json() == {'id': 1, 'jsonrpc': '2.0', 'result': 'single'}
        assert trampoline_tasks == []

    asyncio.run(main())


def test_notification_closed_before_first_step_does_not_leak_coroutine(ep_path):
    async def main():
        closed_jobs = []
        entered = []

        class CloseBeforeStartScheduler(aiojobs.Scheduler):
            async def spawn(self, coro, name=None):
                job = await super().spawn(coro, name=name)
                # With free capacity and the default lazy task factory, spawn
                # does not yield before close cancels the job's first step.
                await job.close()
                closed_jobs.append(job.closed)
                return job

        ep = jsonrpc.Entrypoint(ep_path, scheduler_factory=CloseBeforeStartScheduler)

        @ep.method()
        async def notify_closed_before_start() -> None:
            entered.append(True)

        app = jsonrpc.API()
        app.bind_entrypoint(ep)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', RuntimeWarning)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    # The dedicated route schedules just the notification body;
                    # cancelling a generic-route response job would cancel HTTP too.
                    response = await client.post(
                        ep_path + '/notify_closed_before_start',
                        json={'jsonrpc': '2.0', 'method': 'notify_closed_before_start'},
                    )
            finally:
                await ep.shutdown()
            gc.collect()

        assert response.status_code == 200
        assert response.content == b''
        assert closed_jobs == [True]
        assert entered == []
        assert not [str(w.message) for w in caught if 'was never awaited' in str(w.message)]

    asyncio.run(main())
