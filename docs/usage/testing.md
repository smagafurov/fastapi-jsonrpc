# Testing

The package ships a pytest plugin in `fastapi_jsonrpc.contrib.pytest_plugin`. It gives you a ready-made test harness: a JSON-RPC test client, automatic capture of error responses, and a teardown check that every error returned by a method is declared in its `errors=[...]` list.

## Enable the plugin

Add it to your root `conftest.py`:

```python
pytest_plugins = ['fastapi_jsonrpc.contrib.pytest_plugin']
```

You must provide your own `app` fixture that returns an instance of `fastapi_jsonrpc.API`:

```python
import pytest
import fastapi_jsonrpc as jsonrpc

@pytest.fixture
def app() -> jsonrpc.API:
    return build_my_app()
```

Without this override the plugin's placeholder `app` fixture fails fast with an actionable message.

## What the plugin provides

| Name | Kind | Purpose |
|------|------|---------|
| `JsonRpcTestClient` | class | `starlette.testclient.TestClient` subclass with a `.jsonrpc(...)` helper that builds the JSON-RPC 2.0 envelope and returns `response.json()` |
| `jsonrpc_client` | fixture | Function-scoped `JsonRpcTestClient(app)` entered as a context manager (so FastAPI `startup`/`shutdown` fire); auto-validation is enabled |
| `all_captured_jsonrpc_error_responses` | fixture | `defaultdict[MethodRoute, list[dict]]` of every error response produced during the test |
| `_check_all_captured_jsonrpc_error_responses_listed_in_method_errors` | fixture | Teardown validator — fails the test if any captured error code is not declared in `MethodRoute.errors` or `Entrypoint.errors` |
| `jsonrpcapi_no_tracking_middleware` | marker | Disables the tracking middleware for a single test (use when the test intentionally provokes undeclared errors) |

## Happy path: `jsonrpc_client`

```python
def test_echo(jsonrpc_client):
    resp = jsonrpc_client.jsonrpc('echo', {'data': 'hi'}, url='/api/v1/jsonrpc')
    assert resp == {'jsonrpc': '2.0', 'id': 0, 'result': 'hi'}
```

`jsonrpc_client` already enables the auto-validation fixture, so tests fail on teardown if a method returns an error whose code is not listed in `@entrypoint.method(errors=[...])` (or `Entrypoint(errors=[...])`). This is the single most valuable guard against schema drift — JSON-RPC error declarations can silently decay without it.

## Declared-errors path

```python
class NotEnoughMoney(jsonrpc.BaseError):
    CODE = 6001
    MESSAGE = 'Not enough money'

@entrypoint.method(errors=[NotEnoughMoney])
def withdraw(account_id: str, amount: int) -> int:
    ...

def test_withdraw_rejects_large_amount(jsonrpc_client):
    resp = jsonrpc_client.jsonrpc(
        'withdraw',
        {'account_id': '1.1', 'amount': 10**9},
        url='/api/v1/jsonrpc',
    )
    assert resp['error']['code'] == 6001
```

If `withdraw` returned an error code that was not in its `errors=[...]`, the test would fail on teardown with a consolidated report listing the method, the leaked code, and the set of declared codes.

## Opt out of tracking

Some tests intentionally exercise an undeclared error path (for example, verifying fallback to `InternalError`). Mark them:

```python
@pytest.mark.jsonrpcapi_no_tracking_middleware
def test_internal_error_fallback(jsonrpc_client):
    resp = jsonrpc_client.jsonrpc('boom', url='/api/v1/jsonrpc')
    assert resp['error']['code'] == -32603  # InternalError
```

When the marker is present, the plugin skips middleware injection entirely and `all_captured_jsonrpc_error_responses` yields an empty dict.

## Using `all_captured_jsonrpc_error_responses` directly

If you need to inspect or assert on captured errors inside the test body (not just rely on teardown validation), request the fixture explicitly:

```python
def test_withdraw_rejects_empty_balance(
    jsonrpc_client,
    all_captured_jsonrpc_error_responses,
):
    jsonrpc_client.jsonrpc(
        'withdraw',
        {'account_id': '1.1', 'amount': 1_000_000},
        url='/api/v1/jsonrpc',
    )
    assert all_captured_jsonrpc_error_responses, 'expected a JSON-RPC error'
```

If a method raises a plain Python exception (anything that is **not** a `BaseError`), the fixture fails the test immediately with the formatted traceback — it is very hard to accidentally let an `InternalError` slip into production.

## Entrypoint-bound callables

If your app exposes several entrypoints (web, mobile, private…), binding the URL and auth headers once with `functools.partial` keeps each test short:

```python
import functools
import pytest

@pytest.fixture()
def web_request(jsonrpc_client, web_session):
    return functools.partial(
        jsonrpc_client.jsonrpc,
        url='/api/v1/web/jsonrpc',
        headers={'x-session': web_session.token},
    )

def test_withdraw__not_enough_money(web_request, customer):
    resp = web_request('withdraw', {'account_id': customer.account_id, 'amount': 10**9})
    assert resp['error']['code'] == 6001
```

## Testing methods directly

JSON-RPC methods are ordinary Python functions — you can also call them directly in unit tests without going through the HTTP layer. Dependency injection then has to be wired manually (or via FastAPI's `app.dependency_overrides`).
