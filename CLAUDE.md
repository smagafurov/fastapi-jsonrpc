# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`fastapi-jsonrpc` — JSON-RPC 2.0 server on top of FastAPI. Methods are written like FastAPI endpoints and OpenAPI / Swagger UI / OpenRPC are generated automatically. Supports batch requests, notifications, typed errors with Pydantic `DataModel`, async context-manager middlewares, and a Sentry integration.

Python `>=3.10`, FastAPI `>=0.123,<0.135`, Pydantic `>=2.7,<3`, Starlette `<1.0`. Dependency management via **uv** (PEP 621 `[project]` + PEP 735 `[dependency-groups]`, build backend `hatchling`). The fastapi/starlette upper bounds are compatibility fixes pending — see the `compat fix pending` comments in `pyproject.toml`.

## Commands

```bash
# Install dev dependencies (CI uses the same)
uv sync --frozen --group dev

# Run the whole test suite
uv run --frozen python -m pytest

# Run a single file / test
uv run --frozen python -m pytest tests/test_jsonrpc.py
uv run --frozen python -m pytest tests/test_jsonrpc.py::test_name -x

# Docs (optional group)
uv sync --group docs
uv run zensical serve    # live preview
uv run zensical build    # static site → ./site

# Regenerate the lockfile after changing dependencies
uv lock
```

Use `--no-sync` instead of `--frozen` when you deliberately upgraded a package with `uv pip install --upgrade ...` and do not want `uv run` to revert it (mirrors what the "latest fastapi/pydantic" CI matrix does).

There is no configured linter or formatter in `pyproject.toml`; CI runs only `pytest` across Python 3.10–3.14 (`.github/workflows/tests.yml`). `mypy` is the ad-hoc type checker used when validating changes.

## Architecture

### Single-file core

The **entire public API and all core logic** lives in `fastapi_jsonrpc/__init__.py` (~1.6 kLOC). Do not expect helpers under submodules — follow the class graph inside this one file:

- `BaseError(Exception)` — root of the typed-error hierarchy. Subclasses set `CODE: int` and `MESSAGE: str`, optionally declare an inner `DataModel(BaseModel)` that gets threaded into OpenAPI/OpenRPC. Built-ins: `ParseError`, `InvalidRequest`, `MethodNotFound`, `InvalidParams`, `InternalError`.
- `JsonRpcContext` — per-call context object held in a `contextvars.ContextVar`. Exposes `raw_request`, `raw_response`, `method_route`, and is what middlewares see. Retrieved anywhere via `get_jsonrpc_context()` / `get_jsonrpc_request_id()` / `get_jsonrpc_method()`.
- `MethodRoute(APIRoute)` — one JSON-RPC method. Holds `errors` (list of `BaseError` subclasses declared on the method) and `middlewares` (per-method async CMs). Created by `Entrypoint.method(...)`.
- `EntrypointRoute(APIRoute)` — the single HTTP POST route that backs one entrypoint. Stores entrypoint-wide `errors`. **This is where entrypoint-level errors actually live** — `method_route.entrypoint.entrypoint_route.errors`, not `Entrypoint.errors`.
- `Entrypoint(APIRouter)` — user-facing object. Registers methods via `@entrypoint.method(errors=[...])`, owns `dependencies` (batch-level), `common_dependencies` (per-call), and `middlewares` (per-call async CMs). Internally creates one `EntrypointRoute`.
- `API(FastAPI)` — drop-in FastAPI subclass. `app.bind_entrypoint(entrypoint)` attaches an entrypoint and re-generates OpenAPI/OpenRPC.

### Request pipeline

```
HTTP POST /api/v1/jsonrpc
 → EntrypointRoute.handle_http_request
 → parse body → list | dict
 → solve shared deps (Entrypoint.dependencies)  [once per batch]
 → aiojobs scheduler (concurrent per-request jobs)
 → per request: JsonRpcContext.__aenter__ (sets contextvars)
 → Entrypoint.middlewares (async context managers)
 → MethodRoute matched by name → MethodRoute.middlewares → solve deps → call method
 → BaseError caught → JSON-RPC error response (non-BaseError → InternalError)
```

### `contrib/`

- `contrib/pytest_plugin/conftest.py` — pytest harness. Exports: `JsonRpcTestClient` (TestClient subclass with `.jsonrpc(method, params, *, url, headers, request_id)` helper), `jsonrpc_client` fixture (entered as context manager so lifespan events fire), `all_captured_jsonrpc_error_responses` (captures JSON-RPC errors via injected middleware, guarded by marker), `_check_all_captured_jsonrpc_error_responses_listed_in_method_errors` (teardown validator — every captured error code must be declared in `MethodRoute.errors + entrypoint_route.errors`), marker `jsonrpcapi_no_tracking_middleware` (opt-out). User's own `conftest.py` must override the placeholder `app` fixture.
- `contrib/sentry/` — `FastApiJsonRPCIntegration` for `sentry-sdk >=2.0`: JSON-RPC method name as transaction name, each batch call as a span inside one transaction.

## Test conventions

- `tests/conftest.py` registers an **autouse `check_no_errors` fixture** that fails the test if any `ERROR`-level log record is produced during `setup`/`call`. If you intentionally generate errors, consume them with `assert_log_errors(...)`.
- `pytest_plugins = 'pytester'` is enabled — tests that need to run inner tests in isolation (e.g. `tests/test_pytest_plugin.py`) use the `pytester` fixture.
- Tests asserting JSON-RPC response shapes use dict literals like `{'id': 1, 'jsonrpc': '2.0', 'result': ...}` — JSON-RPC 2.0 responses are exactly those three keys (or `error` instead of `result`).
- `tests/sentry/` covers the Sentry contrib in isolation.

## Feature workflow

Non-trivial changes are planned under `features/FEAT-XXXX-<slug>/` with `README.md` (scope, motivation, acceptance criteria) and `ARCHITECTURE.md` (decisions + rationale). See `features/FEAT-0001-pytest-plugin-upgrade/` as the canonical example. Follow this convention for multi-stage work; small fixes do not need it.

## Docs

- Site generator: **Zensical** (not mkdocs). Config: `zensical.toml`. Source: `docs/`. Output: `site/`.
- `docs/llms.txt` and `docs/llms-full.txt` follow the [llmstxt.org](https://llmstxt.org) convention and are served from the site root. Keep them in sync with the real API when adding/changing public surface — outdated LLM context is worse than none.
- `docs/llms.md` is the human-facing page explaining how to consume those files; it is linked from the site navigation (`zensical.toml`).

## Things that bite

- **Do not assume `Entrypoint.errors` exists as an attribute** for error-code collection. The declared classes live on `EntrypointRoute.errors` and are reached via `method_route.entrypoint.entrypoint_route.errors`.
- **`Entrypoint.middlewares` is typed as `Sequence` but is a `list` at runtime.** Tests and the pytest plugin rely on `.insert(0, ...)` / `.remove(...)`. When the type checker complains, assert `isinstance(ep.middlewares, list)` rather than changing the runtime type.
- **`app.bind_entrypoint(...)` must be called after all methods are registered on the entrypoint** — it freezes the OpenAPI/OpenRPC schemas.
- Non-`BaseError` exceptions raised inside a method are converted to `InternalError`. The pytest harness turns this into a hard test failure by default — opt out with `@pytest.mark.jsonrpcapi_no_tracking_middleware` for tests that intentionally probe the fallback.
