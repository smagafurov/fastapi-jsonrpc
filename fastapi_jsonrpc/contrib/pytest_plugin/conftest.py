import collections
import contextlib
import traceback
from collections.abc import Iterator

import fastapi_jsonrpc as jsonrpcapi
import pytest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# Marker registration
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register plugin-specific markers."""
    config.addinivalue_line(
        'markers',
        (
            'jsonrpcapi_no_tracking_middleware: '
            + 'disable auto-tracking of JSON-RPC error responses for this test '
            + '(use when the test intentionally provokes undeclared errors)'
        ),
    )


# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------


class JsonRpcTestClient(TestClient):
    """`starlette.testclient.TestClient` subclass with a JSON-RPC helper.

    Adds a single method `.jsonrpc(...)` which builds a JSON-RPC 2.0 envelope,
    POSTs it to the given URL and returns the decoded JSON response.

    Does not alter any `TestClient` behaviour and does not assert HTTP status
    (callers may legitimately test error paths).
    """

    def jsonrpc(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        url: str,
        headers: dict[str, str] | None = None,
        request_id: int = 0,
    ) -> dict[str, object]:
        envelope: dict[str, object] = {
            'id': request_id,
            'jsonrpc': '2.0',
            'method': method,
            'params': params if params is not None else {},
        }
        response = self.post(url, json=envelope, headers=headers)
        return response.json()


# ---------------------------------------------------------------------------
# app placeholder (user MUST override)
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    """Placeholder — the user MUST override this fixture in their own conftest.

    The plugin's `jsonrpc_client` fixture depends on `app` by name; without
    an override pytest would raise a cryptic "fixture not found" error.
    This stub fails fast with an actionable message instead.
    """
    pytest.fail(
        "Fixture 'app' is not defined. You must override the 'app' fixture "
        + 'in your own conftest.py and return an instance of '
        + '`fastapi_jsonrpc.API`.\n'
        + "Make sure 'fastapi_jsonrpc.contrib.pytest_plugin' is listed in "
        + "`pytest_plugins` of your root conftest.py (e.g. tests/conftest.py).\n"
        + 'Hint: https://docs.pytest.org/en/stable/how-to/fixtures.html'
        + '#overriding-fixtures-on-various-levels'
    )


# ---------------------------------------------------------------------------
# Error-tracking fixture (extended with marker guard)
# ---------------------------------------------------------------------------


@pytest.fixture()
def all_captured_jsonrpc_error_responses(
    app: jsonrpcapi.API,
    request: pytest.FixtureRequest,
):
    errors: 'collections.defaultdict[jsonrpcapi.MethodRoute, list[dict[str, object]]]' = (
        collections.defaultdict(list)
    )

    # Marker guard: skip middleware injection entirely if the test opts out.
    if request.node.get_closest_marker('jsonrpcapi_no_tracking_middleware'):
        yield errors
        return

    @contextlib.asynccontextmanager
    async def tracking_middleware(ctx: jsonrpcapi.JsonRpcContext):
        try:
            yield
        except Exception as exc:
            if not isinstance(exc, jsonrpcapi.BaseError):
                exc_traceback = traceback.format_exception(
                    None,  # python >=3.5: The exc argument is ignored and inferred from the type of value.
                    value=exc,
                    tb=exc.__traceback__,
                    limit=30,
                )
                pytest.fail(
                    'Method should raise `jsonrpcapi.BaseError`. '
                    'Common exception raised instead: \n' + ''.join(exc_traceback)
                )
            raise
        finally:
            if (
                ctx.raw_response
                and 'result' not in ctx.raw_response
                and ctx.method_route is not None
            ):
                errors[ctx.method_route].append(ctx.raw_response)

    entrypoints = {r.entrypoint for r in app.routes if isinstance(r, jsonrpcapi.MethodRoute)}

    for ep in entrypoints:
        # `middlewares` is declared as Sequence but is always a list at runtime;
        # assert keeps both the runtime contract and the type checker honest.
        assert isinstance(ep.middlewares, list)
        ep.middlewares.insert(0, tracking_middleware)

    try:
        yield errors
    finally:
        for ep in entrypoints:
            assert isinstance(ep.middlewares, list)
            ep.middlewares.remove(tracking_middleware)


# ---------------------------------------------------------------------------
# Auto-validation: every captured error must be declared
# ---------------------------------------------------------------------------


def _collect_declared_codes(method_route: jsonrpcapi.MethodRoute) -> set[int]:
    """Return the set of declared error codes visible from a MethodRoute.

    Union of method-level errors and entrypoint-level errors. Classes with
    `CODE is None` are filtered to keep the set homogeneous.
    """
    entrypoint_route = method_route.entrypoint.entrypoint_route
    declared_classes = (*method_route.errors, *entrypoint_route.errors)
    return {cls.CODE for cls in declared_classes if cls.CODE is not None}


@pytest.fixture()
def _check_all_captured_jsonrpc_error_responses_listed_in_method_errors(
    all_captured_jsonrpc_error_responses,
) -> Iterator[None]:
    """Teardown-time validator: every captured JSON-RPC error response must
    correspond to an error class declared on the method or its entrypoint.

    On mismatch, aggregates all offenders across the test and calls
    `pytest.fail` once with a consolidated report.
    """
    yield

    undeclared: list[tuple[str, int, list[int]]] = []
    for method_route, responses in all_captured_jsonrpc_error_responses.items():
        declared_codes = _collect_declared_codes(method_route)
        for raw_response in responses:
            error = raw_response.get('error') or {}
            code = error.get('code')
            if code is None:
                continue
            if code not in declared_codes:
                undeclared.append(
                    (method_route.name, code, sorted(declared_codes)),
                )

    if not undeclared:
        return

    lines = ['Undeclared JSON-RPC errors leaked during test:']
    for method_name, code, declared in undeclared:
        lines.append(
            f"  - method {method_name!r} returned error code {code} "
            f'(not in declared: {declared})'
        )
    lines.append(
        'Declare these errors via @entrypoint.method(errors=[...]) '
        'or Entrypoint(errors=[...]).'
    )
    pytest.fail('\n'.join(lines))


# ---------------------------------------------------------------------------
# High-level client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def jsonrpc_client(
    app: jsonrpcapi.API,
    _check_all_captured_jsonrpc_error_responses_listed_in_method_errors,
) -> Iterator[JsonRpcTestClient]:
    """Function-scoped JSON-RPC test client with auto-validation enabled.

    Enters the `TestClient` context manager so FastAPI startup/shutdown
    events fire. Depends on the declared-errors checker, which in turn
    installs the tracking middleware via `all_captured_jsonrpc_error_responses`.
    """
    with JsonRpcTestClient(app) as client:
        yield client
