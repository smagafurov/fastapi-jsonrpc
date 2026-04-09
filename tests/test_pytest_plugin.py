"""Tests for `fastapi_jsonrpc.contrib.pytest_plugin` (FEAT-0001).

Most tests use the `pytester` fixture to spin up an inner pytest run that
loads the plugin and executes a crafted test module; the outer test then
asserts the inner outcome. This is the only way to validate teardown-time
`pytest.fail` behaviour, which cannot be observed from inside the failing
test itself.

Inner test files must declare `pytest_plugins = ['fastapi_jsonrpc.contrib.pytest_plugin']`
to activate the plugin under test (R7).
"""
import textwrap

import fastapi_jsonrpc as jsonrpc
import pytest
from starlette.testclient import TestClient

from fastapi_jsonrpc.contrib.pytest_plugin.conftest import (
    JsonRpcTestClient,
    _collect_declared_codes,
)


INNER_PLUGIN_HEADER = "pytest_plugins = ['fastapi_jsonrpc.contrib.pytest_plugin']\n"


# ---------------------------------------------------------------------------
# Stage S1 — auto-validation fixture
# ---------------------------------------------------------------------------


def test_S1_a_declared_errors_path_from_method_route():
    """T-S1-a: union of MethodRoute.errors and
    method_route.entrypoint.entrypoint_route.errors is the declared set."""

    class EntrypointError(jsonrpc.BaseError):
        CODE = 5100
        MESSAGE = 'entrypoint-level error'

    class MethodError(jsonrpc.BaseError):
        CODE = 5200
        MESSAGE = 'method-level error'

    ep = jsonrpc.Entrypoint('/api/v1/jsonrpc', errors=[EntrypointError])

    @ep.method(errors=[MethodError])
    def probe() -> str:
        return 'ok'

    app = jsonrpc.API()
    app.bind_entrypoint(ep)

    method_routes = [r for r in app.routes if isinstance(r, jsonrpc.MethodRoute)]
    assert len(method_routes) == 1
    probe_route = method_routes[0]

    declared_codes = _collect_declared_codes(probe_route)

    assert 5100 in declared_codes, 'entrypoint-level error must be visible'
    assert 5200 in declared_codes, 'method-level error must be visible'
    # Confirms path traversal (if upstream renames, this test fails fast).
    assert probe_route.entrypoint.entrypoint_route.errors, (
        'Upstream moved entrypoint-level errors off EntrypointRoute.errors'
    )


def _make_inner_app_module() -> str:
    """A conftest.py fragment that defines `app` with one declared and one
    method-less-but-declared error set."""
    return textwrap.dedent(
        """
        import pytest
        import fastapi_jsonrpc as jsonrpc


        class DeclaredMethodError(jsonrpc.BaseError):
            CODE = 5500
            MESSAGE = 'declared on method'


        class DeclaredEntrypointError(jsonrpc.BaseError):
            CODE = 5600
            MESSAGE = 'declared on entrypoint'


        class UndeclaredError(jsonrpc.BaseError):
            CODE = 5999
            MESSAGE = 'undeclared anywhere'


        class OtherUndeclaredError(jsonrpc.BaseError):
            CODE = 5998
            MESSAGE = 'another undeclared'


        def _make_app():
            ep = jsonrpc.Entrypoint('/api', errors=[DeclaredEntrypointError])

            @ep.method(errors=[DeclaredMethodError])
            def do_declared_method() -> str:
                raise DeclaredMethodError()

            @ep.method(errors=[DeclaredMethodError])
            def do_declared_entrypoint() -> str:
                raise DeclaredEntrypointError()

            @ep.method()
            def do_undeclared() -> str:
                raise UndeclaredError()

            @ep.method()
            def do_other_undeclared() -> str:
                raise OtherUndeclaredError()

            @ep.method()
            def do_ok() -> str:
                return 'ok'

            app = jsonrpc.API()
            app.bind_entrypoint(ep)
            return app


        @pytest.fixture()
        def app():
            return _make_app()
        """
    )


def _write_inner(pytester, body: str, conftest_extra: str = '') -> None:
    pytester.makeconftest(_make_inner_app_module() + '\n' + conftest_extra)
    pytester.makepyfile(INNER_PLUGIN_HEADER + body)


def test_S1_b_declared_method_error_passes(pytester):
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                resp = jsonrpc_client.jsonrpc('do_declared_method', url='/api')
                assert resp['error']['code'] == 5500
            """
        ),
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


def test_S1_c_entrypoint_level_declared_error_passes(pytester):
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                resp = jsonrpc_client.jsonrpc('do_declared_entrypoint', url='/api')
                assert resp['error']['code'] == 5600
            """
        ),
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


def test_S1_d_undeclared_error_fails_with_method_and_code(pytester):
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                resp = jsonrpc_client.jsonrpc('do_undeclared', url='/api')
                assert resp['error']['code'] == 5999
            """
        ),
    )
    result = pytester.runpytest('-q')
    # pytest.fail in a fixture teardown surfaces as "error", not "failed".
    result.assert_outcomes(passed=1, errors=1)
    stdout = '\n'.join(result.outlines)
    assert 'Undeclared JSON-RPC errors' in stdout
    assert 'do_undeclared' in stdout
    assert '5999' in stdout
    assert '5600' in stdout  # declared entrypoint-level code listed


def test_S1_e_multiple_undeclared_errors_all_reported(pytester):
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                r1 = jsonrpc_client.jsonrpc('do_undeclared', url='/api')
                r2 = jsonrpc_client.jsonrpc('do_other_undeclared', url='/api')
                assert r1['error']['code'] == 5999
                assert r2['error']['code'] == 5998
            """
        ),
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1, errors=1)
    stdout = '\n'.join(result.outlines)
    assert '5999' in stdout
    assert '5998' in stdout
    assert 'do_undeclared' in stdout
    assert 'do_other_undeclared' in stdout


def test_S1_f_no_errors_captured_is_success(pytester):
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                resp = jsonrpc_client.jsonrpc('do_ok', url='/api')
                assert resp['result'] == 'ok'
            """
        ),
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# Stage S2 — marker + fixture extension
# ---------------------------------------------------------------------------


def test_S2_a_marker_registered(pytester):
    # For --markers to see the plugin, it must be loaded at config time.
    # `pytest_plugins` in a test file only activates at collection, so put
    # it in the inner conftest.
    pytester.makeconftest(
        "pytest_plugins = ['fastapi_jsonrpc.contrib.pytest_plugin']\n"
    )
    pytester.makepyfile('def test_dummy(): pass\n')
    result = pytester.runpytest('--markers')
    stdout = '\n'.join(result.outlines)
    assert 'jsonrpcapi_no_tracking_middleware' in stdout


def test_S2_b_marker_skips_middleware_injection(pytester):
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            import pytest

            @pytest.mark.jsonrpcapi_no_tracking_middleware
            def test_inner(jsonrpc_client, all_captured_jsonrpc_error_responses):
                # Undeclared error, but with marker => no middleware => empty dict,
                # and no teardown failure.
                resp = jsonrpc_client.jsonrpc('do_undeclared', url='/api')
                assert resp['error']['code'] == 5999
                assert all_captured_jsonrpc_error_responses == {}
            """
        ),
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


def test_S2_c_no_marker_tracks_as_before(pytester):
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            def test_inner(jsonrpc_client, all_captured_jsonrpc_error_responses):
                resp = jsonrpc_client.jsonrpc('do_declared_method', url='/api')
                assert resp['error']['code'] == 5500
                assert len(all_captured_jsonrpc_error_responses) == 1
            """
        ),
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


def test_S2_d_request_param_backward_compat_existing_consumer(pytester):
    """Legacy usage: depend on `all_captured_jsonrpc_error_responses` without
    going through `jsonrpc_client`. Contract must be unchanged."""
    _write_inner(
        pytester,
        textwrap.dedent(
            """
            from starlette.testclient import TestClient

            def test_inner(app, all_captured_jsonrpc_error_responses):
                with TestClient(app) as client:
                    resp = client.post('/api', json={
                        'id': 0,
                        'jsonrpc': '2.0',
                        'method': 'do_declared_method',
                        'params': {},
                    }).json()
                assert resp['error']['code'] == 5500
                assert len(all_captured_jsonrpc_error_responses) == 1
            """
        ),
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# Stage S3 — JsonRpcTestClient
# ---------------------------------------------------------------------------


@pytest.fixture()
def echo_app():
    """Minimal app with an echo method that returns its input."""
    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def echo(data: dict[str, object] | None = None) -> dict[str, object]:
        return {'received': data}

    app = jsonrpc.API()
    app.bind_entrypoint(ep)
    return app


def test_S3_a_jsonrpc_envelope_shape(echo_app):
    with JsonRpcTestClient(echo_app) as client:
        resp = client.jsonrpc('echo', {'data': {'msg': 'hi'}}, url='/api')
    assert resp['jsonrpc'] == '2.0'
    assert resp['id'] == 0
    assert resp['result'] == {'received': {'msg': 'hi'}}


def test_S3_b_jsonrpc_params_none_becomes_empty_dict():
    """When params is omitted, the envelope carries params={} (not null)."""
    captured_envelope: dict[str, object] | None = None

    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def ping() -> str:
        return 'pong'

    app = jsonrpc.API()
    app.bind_entrypoint(ep)

    # Patch post to capture the raw json body
    with JsonRpcTestClient(app) as client:
        original_post = client.post

        def capturing_post(url, **kwargs):
            nonlocal captured_envelope
            captured_envelope = kwargs.get('json')
            return original_post(url, **kwargs)

        client.post = capturing_post  # type: ignore[method-assign]
        resp = client.jsonrpc('ping', url='/api')

    assert captured_envelope is not None
    assert captured_envelope['params'] == {}
    assert resp['result'] == 'pong'


def test_S3_c_jsonrpc_custom_request_id(echo_app):
    with JsonRpcTestClient(echo_app) as client:
        resp = client.jsonrpc('echo', {'data': 1}, url='/api', request_id=42)
    assert resp['id'] == 42


def test_S3_d_jsonrpc_custom_headers_passthrough():
    from fastapi import Header

    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def get_header(x_foo: str = Header(default='missing')) -> str:
        return x_foo

    app = jsonrpc.API()
    app.bind_entrypoint(ep)

    with JsonRpcTestClient(app) as client:
        resp = client.jsonrpc(
            'get_header',
            url='/api',
            headers={'X-Foo': 'bar-value'},
        )

    assert resp['result'] == 'bar-value'


def test_S3_e_jsonrpc_client_is_testclient_subclass():
    assert issubclass(JsonRpcTestClient, TestClient)


def test_S3_f_jsonrpc_client_context_manager():
    startup_events: list[int] = []

    ep = jsonrpc.Entrypoint('/api')

    @ep.method()
    def noop() -> str:
        return 'ok'

    app = jsonrpc.API()
    app.bind_entrypoint(ep)

    @app.on_event('startup')
    async def _on_startup() -> None:
        startup_events.append(1)

    with JsonRpcTestClient(app) as client:
        resp = client.jsonrpc('noop', url='/api')
    assert resp['result'] == 'ok'
    assert startup_events == [1]


# ---------------------------------------------------------------------------
# Stage S4 — jsonrpc_client fixture + app placeholder
# ---------------------------------------------------------------------------


def _make_s4_conftest_with_startup_counter() -> str:
    return textwrap.dedent(
        """
        import pytest
        import fastapi_jsonrpc as jsonrpc


        class DeclaredError(jsonrpc.BaseError):
            CODE = 5700
            MESSAGE = 'declared'


        class UndeclaredError(jsonrpc.BaseError):
            CODE = 5799
            MESSAGE = 'undeclared'


        @pytest.fixture()
        def app():
            startup_hits = {'count': 0}

            ep = jsonrpc.Entrypoint('/api')

            @ep.method(errors=[DeclaredError])
            def do_declared() -> str:
                raise DeclaredError()

            @ep.method()
            def do_undeclared() -> str:
                raise UndeclaredError()

            @ep.method()
            def do_ok() -> str:
                return 'ok'

            app = jsonrpc.API()
            app.bind_entrypoint(ep)

            @app.on_event('startup')
            async def _on_startup() -> None:
                startup_hits['count'] += 1

            app.state_hits = startup_hits  # type: ignore[attr-defined]
            return app
        """
    )


def test_S4_a_jsonrpc_client_runs_startup_shutdown(pytester):
    pytester.makeconftest(_make_s4_conftest_with_startup_counter())
    pytester.makepyfile(
        INNER_PLUGIN_HEADER
        + textwrap.dedent(
            """
            def test_inner(app, jsonrpc_client):
                assert app.state_hits['count'] == 1
                resp = jsonrpc_client.jsonrpc('do_ok', url='/api')
                assert resp['result'] == 'ok'
            """
        )
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


def test_S4_b_jsonrpc_client_end_to_end_happy_path(pytester):
    pytester.makeconftest(_make_s4_conftest_with_startup_counter())
    pytester.makepyfile(
        INNER_PLUGIN_HEADER
        + textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                resp = jsonrpc_client.jsonrpc('do_declared', url='/api')
                assert resp['error']['code'] == 5700
            """
        )
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


def test_S4_c_jsonrpc_client_end_to_end_undeclared_fails_teardown(pytester):
    pytester.makeconftest(_make_s4_conftest_with_startup_counter())
    pytester.makepyfile(
        INNER_PLUGIN_HEADER
        + textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                resp = jsonrpc_client.jsonrpc('do_undeclared', url='/api')
                assert resp['error']['code'] == 5799
            """
        )
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1, errors=1)
    stdout = '\n'.join(result.outlines)
    assert 'Undeclared JSON-RPC errors' in stdout
    assert '5799' in stdout
    assert 'do_undeclared' in stdout


def test_S4_d_jsonrpc_client_with_marker_suppresses_checks(pytester):
    pytester.makeconftest(_make_s4_conftest_with_startup_counter())
    pytester.makepyfile(
        INNER_PLUGIN_HEADER
        + textwrap.dedent(
            """
            import pytest

            @pytest.mark.jsonrpcapi_no_tracking_middleware
            def test_inner(jsonrpc_client):
                resp = jsonrpc_client.jsonrpc('do_undeclared', url='/api')
                assert resp['error']['code'] == 5799
            """
        )
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=1)


def test_S4_e_jsonrpc_client_fixture_is_function_scoped(pytester):
    pytester.makeconftest(_make_s4_conftest_with_startup_counter())
    pytester.makepyfile(
        INNER_PLUGIN_HEADER
        + textwrap.dedent(
            """
            _seen_ids = []

            def test_first(jsonrpc_client, all_captured_jsonrpc_error_responses):
                _seen_ids.append(id(jsonrpc_client))
                assert all_captured_jsonrpc_error_responses == {}
                resp = jsonrpc_client.jsonrpc('do_declared', url='/api')
                assert resp['error']['code'] == 5700
                assert len(all_captured_jsonrpc_error_responses) == 1

            def test_second(jsonrpc_client, all_captured_jsonrpc_error_responses):
                _seen_ids.append(id(jsonrpc_client))
                # Fresh state on a new function-scoped fixture.
                assert all_captured_jsonrpc_error_responses == {}
                assert len(_seen_ids) == 2
                assert _seen_ids[0] != _seen_ids[1]
            """
        )
    )
    result = pytester.runpytest('-q')
    result.assert_outcomes(passed=2)


def test_S4_f_app_placeholder_fails_with_actionable_message(pytester):
    # Intentionally do NOT define an `app` fixture in the inner conftest.
    pytester.makeconftest('')
    pytester.makepyfile(
        INNER_PLUGIN_HEADER
        + textwrap.dedent(
            """
            def test_inner(jsonrpc_client):
                pass
            """
        )
    )
    result = pytester.runpytest('-q')
    # `app` fixture calls pytest.fail during setup → inner test errors (not failed).
    outcomes = result.parseoutcomes()
    assert outcomes.get('passed', 0) == 0, outcomes
    assert (outcomes.get('errors', 0) + outcomes.get('failed', 0)) >= 1, outcomes
    stdout = '\n'.join(result.outlines)
    assert "'app'" in stdout
    assert 'override' in stdout
