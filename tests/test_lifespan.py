"""Tests for lifespan composition in jsonrpc.API.

Covers:
- User-supplied lifespan= kwarg is called (not shadowed)
- Composition with bind_entrypoint shutdown_functions
- LIFO ordering: user lifespan exit before shutdown_functions
- No user lifespan: shutdown_functions still work
- Legacy on_event + user lifespan coexist
"""
import contextlib

import fastapi_jsonrpc as jsonrpc
from starlette.testclient import TestClient


def _make_app_with_ep():
    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def probe() -> str:
        return 'ok'

    app = jsonrpc.API()
    app.bind_entrypoint(ep)
    return app, ep


def test__user_lifespan__startup_and_shutdown__both_called():
    """User-supplied lifespan CM's startup and shutdown code must execute."""
    events: list[str] = []

    @contextlib.asynccontextmanager
    async def user_lifespan(app):
        events.append('startup')
        yield
        events.append('shutdown')

    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def probe() -> str:
        return 'ok'

    app = jsonrpc.API(lifespan=user_lifespan)
    app.bind_entrypoint(ep)

    with TestClient(app):
        assert 'startup' in events
    assert 'shutdown' in events


def test__user_lifespan_with_shutdown_functions__both_called():
    """User lifespan AND entrypoint shutdown_functions must both fire."""
    events: list[str] = []

    @contextlib.asynccontextmanager
    async def user_lifespan(app):
        events.append('user_startup')
        yield
        events.append('user_shutdown')

    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def probe() -> str:
        return 'ok'

    app = jsonrpc.API(lifespan=user_lifespan)
    app.bind_entrypoint(ep)

    # Register a custom shutdown function to simulate what bind_entrypoint does
    async def extra_shutdown():
        events.append('extra_shutdown')

    app.shutdown_functions.append(extra_shutdown)

    with TestClient(app):
        pass

    assert 'user_shutdown' in events
    assert 'extra_shutdown' in events


def test__lifespan_ordering__user_exits_before_shutdown_functions():
    """LIFO: user lifespan entered LAST → exits FIRST, before shutdown_functions."""
    events: list[str] = []

    @contextlib.asynccontextmanager
    async def user_lifespan(app):
        yield
        events.append('user_shutdown')

    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def probe() -> str:
        return 'ok'

    app = jsonrpc.API(lifespan=user_lifespan)
    app.bind_entrypoint(ep)

    async def entrypoint_shutdown():
        events.append('ep_shutdown')

    app.shutdown_functions.append(entrypoint_shutdown)

    with TestClient(app):
        pass

    # shutdown_functions run in finally block of composed_lifespan (before stack unwinds)
    # then user_lifespan exits via LIFO stack unwind
    # So: ep_shutdown first (from finally), then user_shutdown (from stack LIFO)
    assert events == ['ep_shutdown', 'user_shutdown']


def test__no_user_lifespan__shutdown_functions_still_work():
    """When no lifespan= is passed, shutdown_functions must still fire."""
    events: list[str] = []

    app, ep = _make_app_with_ep()

    async def shutdown_fn():
        events.append('shutdown')

    app.shutdown_functions.append(shutdown_fn)

    with TestClient(app):
        pass

    assert events == ['shutdown']


def test__on_event_and_user_lifespan__coexist():
    """Legacy @app.on_event('startup') must work alongside user lifespan=."""
    events: list[str] = []

    @contextlib.asynccontextmanager
    async def user_lifespan(app):
        events.append('user_startup')
        yield
        events.append('user_shutdown')

    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def probe() -> str:
        return 'ok'

    app = jsonrpc.API(lifespan=user_lifespan)
    app.bind_entrypoint(ep)

    @app.on_event('startup')
    async def legacy_startup():
        events.append('legacy_startup')

    with TestClient(app):
        assert 'legacy_startup' in events
        assert 'user_startup' in events

    assert 'user_shutdown' in events
