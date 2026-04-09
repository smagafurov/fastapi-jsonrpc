# Architecture Plan: Pytest Plugin Upgrade

**Feature ID:** FEAT-0001
**Status:** Architecture Design
**Architect:** Django/Python Architect Agent
**Date:** 2026-04-09

---

## Context (evidence base)

All line numbers below refer to commit `master` of the upstream repo.

- Plugin file today: `fastapi_jsonrpc/contrib/pytest_plugin/conftest.py` (54 lines, one fixture).
- Plugin package bootstrap: `fastapi_jsonrpc/contrib/pytest_plugin/__init__.py` — registers the conftest via `pytest_plugins = [f'{__package__}.conftest']`.
- Library public surface: `fastapi_jsonrpc/__init__.py` has no `__all__`; everything defined at module top level is de-facto public. Names we rely on (all from `fastapi_jsonrpc/__init__.py`):
  - `BaseError` — line 187. `CODE: Optional[int]` on line 188.
  - `JsonRpcContext` — line 544. Fields used: `raw_response` (line 597, `@property`), `method_route` (line 561).
  - `MethodRoute` — line 701.
    - `self.entrypoint = entrypoint` — line 759 (type: `'Entrypoint'`).
    - `self.errors = errors or []` — line 765.
  - `EntrypointRoute` — line 967.
    - `self.errors = errors or []` — line 1042.
  - `Entrypoint` (subclass of `APIRouter`) — line 1234.
    - `self.entrypoint_route = self.entrypoint_route_class(...)` — line 1265.
    - There is **no** `self.errors` on `Entrypoint`. Only two `self.errors` assignments exist in the whole module: line 765 (MethodRoute) and line 1042 (EntrypointRoute) — confirmed by grep.
  - `API` (subclass of `FastAPI`) — line 1370.
- Current plugin behaviour (`conftest.py`):
  - Line 20: fixture signature `all_captured_jsonrpc_error_responses(app: jsonrpcapi.API)`.
  - Line 21: `errors = collections.defaultdict(list)` — keyed by `MethodRoute` instance.
  - Lines 23–39: `tracking_middleware` raises `pytest.fail` if a non-`BaseError` leaks, re-raises `BaseError`, and on `finally` appends `ctx.raw_response` to the dict for the current `method_route`.
  - Line 44: collects unique entrypoints via `{r.entrypoint for r in app.routes if isinstance(r, jsonrpcapi.MethodRoute)}` — note this gives **`Entrypoint` instances**, not `EntrypointRoute`, because `MethodRoute.entrypoint` is typed `'Entrypoint'` (line 704/759).
  - Lines 46–53: installs the middleware into `Entrypoint.middlewares` (the list on the `Entrypoint` APIRouter, line 1259), yields, then removes it.

Important consequence for S1 design: a `MethodRoute`'s declared error set is `method_route.errors` (method-level, line 765) **plus** `method_route.entrypoint.entrypoint_route.errors` (entrypoint-level, line 1042). The README's proposed path `method_route.entrypoint.errors` does **not** exist — see "Open questions resolved" below.

---

## Review Findings Summary

There is no `review-request-changes/` directory for this feature yet; this is the first architectural pass.

---

## Decisions

### D1. File placement: single `conftest.py`, no extra modules

**Decision:** Keep everything in `fastapi_jsonrpc/contrib/pytest_plugin/conftest.py`. Do not split into `_client.py`, `_tracking.py`, etc.

**Rationale (Ontological Parsimony, Sharp Boundary):**
- The whole plugin after the change is ~150 lines. Splitting a 150-line file into 3 files adds navigation cost with no reuse benefit.
- The plugin is already registered via `__init__.py` → `pytest_plugins = [f'{__package__}.conftest']` (line 1). Adding sibling modules forces either more `pytest_plugins` entries or re-exports — extra moving parts for zero gain.
- `BoundedContext`: the plugin is one context — "test harness for `fastapi_jsonrpc.API`". Submodules imply multiple contexts that do not exist here.

**Consequence:** `JsonRpcTestClient`, `jsonrpc_client`, `all_captured_jsonrpc_error_responses`, `_check_...`, and `pytest_configure` all live in `conftest.py`.

### D2. `JsonRpcTestClient.jsonrpc()` contract — exactly matches README, `params` defaults to `{}`

**Decision:** Subclass `starlette.testclient.TestClient` (which is what `fastapi.testclient.TestClient` re-exports and what the library's own tests already use — see `tests/conftest.py` line 11). Add one method:

```python
def jsonrpc(
    self,
    method: str,
    params: dict | None = None,
    *,
    url: str,
    headers: dict | None = None,
    request_id: int = 0,
) -> dict:
```

Behaviour:
- Builds envelope `{"id": request_id, "jsonrpc": "2.0", "method": method, "params": params if params is not None else {}}`.
- `POST url` with `json=<envelope>`, passing `headers` through (merged by `TestClient` with its own defaults — no manual merge logic).
- Returns `response.json()`.
- Does **not** assert HTTP status — callers may test error paths that return 200 with `{"error": ...}` or 4xx/5xx envelopes; asserting would hide legitimate scenarios (Error Hiding).

**Rationale (Strict Distinction, Ontological Parsimony):**
- Keyword-only `url`, `headers`, `request_id` prevent positional-arg confusion (`method` vs `url` look similar).
- `params=None` → `{}` (AC3 explicit requirement). We store `{}` in the envelope, not `null`, because the JSON-RPC 2.0 spec allows `params` to be omitted but many servers (and the library's own dispatch) treat `null` as "params were provided and are null" vs "params omitted"; `{}` is the safest default for a test helper.
- Return type is `dict` — we deliberately do **not** wrap in a dataclass / Pydantic model. Adding a type is refactor-without-subtract (FPF A.11) when callers already handle raw dicts in existing suites.
- No `notify()` helper in this iteration — the README scope lists one method only. Future additions belong to a follow-up feature.

**Non-decision (deferred):** batch support (`list` of envelopes). Out of scope per README.

### D3. Declared-errors lookup path: `method_route.errors ∪ method_route.entrypoint.entrypoint_route.errors`

**Decision:** The set of declared error codes for a given `MethodRoute` is computed as:

```python
declared_codes: set[int] = {
    cls.CODE
    for cls in (*method_route.errors, *method_route.entrypoint.entrypoint_route.errors)
    if cls.CODE is not None
}
```

**Rationale (Evidence Graph):**
- Grep over `fastapi_jsonrpc/__init__.py` confirms only two `self.errors =` assignments: line 765 (`MethodRoute`) and line 1042 (`EntrypointRoute`).
- `Entrypoint.__init__` (line 1255) stores its `errors` argument by delegating into `EntrypointRoute(..., errors=errors, ...)` (line 1269), which lands on `entrypoint_route.errors` (line 1042).
- `MethodRoute.entrypoint` (line 759) is the `Entrypoint` APIRouter instance, not the route — confirmed by type annotation line 704 (`entrypoint: 'Entrypoint'`).
- Therefore `method_route.entrypoint.errors` (as in the README) does not exist; `method_route.entrypoint.entrypoint_route.errors` is the correct path.
- `BaseError.CODE` is typed `Optional[int]` (line 188) — we filter `None` to keep the set homogeneous and avoid a `None == None` match accidentally allowing undeclared errors.

**Guard:** implementer must verify at import time by reading the same lines (or writing a focused test, see T-S1-a).

### D4. Auto-validation fixture: opt-in, fail-fast, aggregated report

**Decision:**
- Name: `_check_all_captured_jsonrpc_error_responses_listed_in_method_errors` (underscore prefix — internal fixture, consumed only through dependency of `jsonrpc_client`; not `autouse`).
- Opt-in: only active when the user's `jsonrpc_client` (or a custom client fixture) lists it as a parameter. Tests that use only `all_captured_jsonrpc_error_responses` (legacy flow) are unaffected — see D5.
- Strategy: **collect all** undeclared errors across the whole test, then `pytest.fail` once with a consolidated message. Rationale: a single `pytest.fail` on the first offender hides follow-up issues and forces N test runs to clear N undeclared codes. "Fail-all" has no downside here — we already have the data.
- Message format (example):
  ```
  Undeclared JSON-RPC errors leaked during test:
    - method 'create_user' returned error code -32001 (not in declared: [-32602, -32603])
    - method 'login' returned error code -32010 (not in declared: [-32602, -32603, -32099])
  Declare these errors via @entrypoint.method(errors=[...]) or Entrypoint(errors=[...]).
  ```

**Rationale (Strict Distinction, Explicit Error Handling):**
- Opt-in, not `autouse`: the README explicitly forbids `autouse` (would break existing suites). An internal fixture depended on by `jsonrpc_client` gives opt-in by construction.
- Fail-all beats fail-fast here because there is no cost to finishing the scan — the `errors` dict is already populated.
- Underscore prefix signals "not a user-facing handle" per the style used in the npd source of truth.

### D5. `all_captured_jsonrpc_error_responses` — minimal surgical change (add `request` param + marker guard)

**Decision:** Modify the existing fixture only in two ways:

1. Add `request: pytest.FixtureRequest` as a parameter.
2. At the top of the fixture body, before creating the middleware: if the current test node has the marker `jsonrpcapi_no_tracking_middleware`, yield `collections.defaultdict(list)` and return immediately — no middleware injection, no teardown. (Teardown still trivially safe because we never inserted anything.)

Nothing else changes: the `defaultdict[MethodRoute, list[dict]]` return type stays identical; the `pytest.fail` on non-`BaseError` leakage stays identical; the iteration over `app.routes` stays identical.

**Rationale (Strict Distinction, Ontological Parsimony, Minimal changes):**
- Contract of the fixture (return type, keyed-by-MethodRoute semantic) is preserved — no breaking change for downstream suites.
- Adding a `request` parameter is not breaking because pytest resolves fixtures by name; users never call this fixture positionally.
- The marker check is a ~3-line addition, not a rewrite of the fixture.
- "Yield empty dict" rather than "skip yield" because the fixture's consumers expect to receive *something* — preserving the return-shape contract.

**What we explicitly do NOT change:**
- The `pytest.fail` on non-`BaseError` (lines 35–38 of current conftest). It is shouty but informative — per `code-change-discipline` §7, we do not remove information.
- The iteration strategy over `app.routes` (line 44).

### D6. `jsonrpc_client` fixture: context-managed, function-scoped, depends on the checker

**Decision:**

```python
@pytest.fixture()
def jsonrpc_client(
    app: API,
    _check_all_captured_jsonrpc_error_responses_listed_in_method_errors,
) -> Iterator[JsonRpcTestClient]:
    with JsonRpcTestClient(app) as client:
        yield client
```

**Rationale:**
- `with` block ensures FastAPI `startup`/`shutdown` events run (AC4). Matches the pattern already used in `tests/conftest.py` line 83–85 for `app_client`.
- Function scope is the only scope that composes correctly with per-test middleware injection in `all_captured_jsonrpc_error_responses` (which is itself function-scoped by default).
- Depending on `_check_...` rather than on `all_captured_jsonrpc_error_responses` directly lets the checker own the "look up declared errors and fail" logic, keeping `jsonrpc_client` a pure composition root.
- `app` is provided by the user (there is no default `app` fixture in the plugin today, and the README clarifies the user supplies it). The existing commented-out hint at lines 9–16 of `conftest.py` can be restored as an actionable error — see D7.

### D7. Re-introduce the `app` fixture placeholder as a fail-fast stub

**Decision:** Uncomment (and slightly update) the `app` placeholder fixture so that a user who forgets to override it gets a clear error instead of a cryptic `fixture 'app' not found` from pytest. Error message must instruct the user to define their own `app` fixture in their conftest.

**Rationale (Explicit Error Handling, fail-fast at boundary):**
- Currently the code is commented out, meaning the failure mode is "fixture not found" — technically works but the error is less actionable.
- The `jsonrpc_client` fixture depends on `app` by name; without the placeholder, the failure surfaces inside pytest's fixture resolver with no hint about where to define it.
- This is ~8 lines added; parsimonious.

**Open to reversal:** if the implementer finds that the placeholder collides with any existing user setup (it should not, since override semantics work), drop it. Tracked as a soft decision.

### D8. No public re-export of `JsonRpcTestClient` from `fastapi_jsonrpc` root

**Decision:** `JsonRpcTestClient` lives in `fastapi_jsonrpc.contrib.pytest_plugin.conftest` and is importable as `from fastapi_jsonrpc.contrib.pytest_plugin.conftest import JsonRpcTestClient` for users who want to instantiate it manually without the fixture. **Not** re-exported from `fastapi_jsonrpc/__init__.py`.

**Rationale (BoundedContext, Ontological Parsimony):**
- `fastapi_jsonrpc/__init__.py` is the *library* context (runtime server). `pytest_plugin` is the *test harness* context. Bleeding a test-only class into the runtime namespace breaks the boundary.
- Re-exports are trivial to add later if demand appears; removing them later is a breaking change.

**Soft follow-up:** if this becomes awkward, add a thin re-export at `fastapi_jsonrpc/contrib/pytest_plugin/__init__.py` level (still inside the plugin package) — cheap and scope-local.

### D9. `pytest_configure` hook for marker registration

**Decision:** Add a `pytest_configure(config)` function at module level in `conftest.py`:

```python
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "jsonrpcapi_no_tracking_middleware: "
        "disable auto-tracking of JSON-RPC error responses for this test "
        "(use when the test intentionally provokes undeclared errors)",
    )
```

**Rationale:** pytest requires explicit marker registration (in `strict-markers` mode this is mandatory; otherwise it still emits a warning). Single stable hook, ~5 lines.

---

## File map

| File | Action | Why |
|---|---|---|
| `fastapi_jsonrpc/contrib/pytest_plugin/conftest.py` | **Modify** | Add `pytest_configure`, `JsonRpcTestClient`, `_check_...`, `jsonrpc_client`, `app` placeholder; extend `all_captured_jsonrpc_error_responses` with `request` param + marker guard. |
| `fastapi_jsonrpc/contrib/pytest_plugin/__init__.py` | **Unchanged** | Still registers `conftest` via `pytest_plugins`. |
| `fastapi_jsonrpc/__init__.py` | **Unchanged** | D8 — no re-export. |
| `tests/test_pytest_plugin.py` | **Create** | New file hosting all S1–S4 tests for the plugin itself. Uses `pytester` (already enabled via `tests/conftest.py` line 18 `pytest_plugins = 'pytester'`) to run inner tests in isolation and assert outcomes. |
| `pyproject.toml` | **Unchanged** | The plugin is already discoverable as a pytest plugin via `pytest_plugins = [...]`. No entry-point registration needed. |

---

## Contracts

All signatures use Python 3.10+ `|` unions, since pyproject pins `python = "^3.10"` (pyproject line 15).

### Public

```python
from starlette.testclient import TestClient

class JsonRpcTestClient(TestClient):
    """TestClient subclass with a single-call JSON-RPC helper.

    Does not alter TestClient behaviour; only adds `.jsonrpc(...)`.
    """

    def jsonrpc(
        self,
        method: str,
        params: dict | None = None,
        *,
        url: str,
        headers: dict | None = None,
        request_id: int = 0,
    ) -> dict:
        ...
```

### Fixtures

```python
@pytest.fixture()
def app() -> "fastapi_jsonrpc.API":
    """Placeholder — user MUST override in their conftest.py.

    Raises pytest.fail with an instructive message if not overridden.
    """

@pytest.fixture()
def all_captured_jsonrpc_error_responses(
    app: "fastapi_jsonrpc.API",
    request: pytest.FixtureRequest,
) -> Iterator[defaultdict["MethodRoute", list[dict]]]:
    """Backward-compatible contract. New: respects marker
    `jsonrpcapi_no_tracking_middleware` — if present, yields an empty
    defaultdict and injects no middleware.
    """

@pytest.fixture()
def _check_all_captured_jsonrpc_error_responses_listed_in_method_errors(
    all_captured_jsonrpc_error_responses: defaultdict["MethodRoute", list[dict]],
) -> Iterator[None]:
    """Teardown-only check. After the test body, verifies every captured
    error response's code belongs to
    `method_route.errors ∪ method_route.entrypoint.entrypoint_route.errors`.
    On mismatch: pytest.fail with aggregated report (all offenders).
    """

@pytest.fixture()
def jsonrpc_client(
    app: "fastapi_jsonrpc.API",
    _check_all_captured_jsonrpc_error_responses_listed_in_method_errors: None,
) -> Iterator[JsonRpcTestClient]:
    """Function-scoped context-managed JsonRpcTestClient(app) with
    auto-validation enabled."""
```

### Hook

```python
def pytest_configure(config: pytest.Config) -> None:
    """Register the jsonrpcapi_no_tracking_middleware marker."""
```

---

## Test list

All tests live in `tests/test_pytest_plugin.py`. Most use the `pytester` fixture (already enabled in `tests/conftest.py` line 18) to spin up an inner pytest process that loads the plugin and runs a crafted test file; the outer test asserts the inner outcomes. This lets us test teardown-time `pytest.fail` correctly (a fixture that calls `pytest.fail` cannot be asserted from the same test function).

### Stage S1 — auto-validation fixture

- **T-S1-a `test_declared_errors_path_from_method_route`** — unit test: construct a real `Entrypoint('/api', errors=[E1])`, add a method with `errors=[E2]`, build an `API`, then locate the `MethodRoute` and assert that the union `method_route.errors + method_route.entrypoint.entrypoint_route.errors` equals `{E1, E2}`. Protects D3 against upstream refactors.

- **T-S1-b `test_declared_error_response_passes`** — `pytester` inner test: `jsonrpc_client` calls a method that raises a `BaseError` subclass declared in `@method(errors=[...])`. Outer asserts inner run passed (`result.assert_outcomes(passed=1)`).

- **T-S1-c `test_entrypoint_level_declared_error_passes`** — same as T-S1-b but the error is declared at `Entrypoint(errors=[...])` level, not on the method. Outer asserts passed.

- **T-S1-d `test_undeclared_error_fails_with_method_and_code`** — inner test method raises an error whose `CODE` is in neither `MethodRoute.errors` nor entrypoint errors. Outer asserts inner failed with message containing method name, the offending `CODE`, and the list of declared codes.

- **T-S1-e `test_multiple_undeclared_errors_all_reported`** — inner test triggers two different undeclared errors across two calls. Outer asserts the failure message mentions both codes (D4 fail-all).

- **T-S1-f `test_no_errors_captured_is_success`** — happy path test only makes successful calls. Outer asserts passed.

### Stage S2 — marker + fixture extension

- **T-S2-a `test_marker_registered`** — run inner pytest with `--markers` and assert the marker name appears in the output.

- **T-S2-b `test_marker_skips_middleware_injection`** — inner test uses `@pytest.mark.jsonrpcapi_no_tracking_middleware`, triggers an undeclared error, and asserts `all_captured_jsonrpc_error_responses == {}`. Outer asserts passed (no teardown failure).

- **T-S2-c `test_no_marker_tracks_as_before`** — inner test without marker, triggers a declared error, asserts `len(all_captured_jsonrpc_error_responses) == 1`. Outer asserts passed.

- **T-S2-d `test_request_param_backward_compat_existing_consumer`** — inner test depends on `all_captured_jsonrpc_error_responses` **without** using `jsonrpc_client`, exactly mirroring the pre-FEAT-0001 usage pattern. Outer asserts passed. Guards D5 contract preservation.

### Stage S3 — `JsonRpcTestClient`

- **T-S3-a `test_jsonrpc_envelope_shape`** — instantiate `JsonRpcTestClient` over a minimal `API` with one echo method. Call `client.jsonrpc('echo', {'data': 'hi'}, url='/api')`. Assert response structure and inspect request via the method's captured params that the envelope was `{"id": 0, "jsonrpc": "2.0", "method": "echo", "params": {"data": "hi"}}`.

- **T-S3-b `test_jsonrpc_params_none_becomes_empty_dict`** — call `client.jsonrpc('ping', url='/api')` (no `params`). Assert server received `params == {}`, not `null`.

- **T-S3-c `test_jsonrpc_custom_request_id`** — call with `request_id=42`. Assert returned envelope has `id == 42`.

- **T-S3-d `test_jsonrpc_custom_headers_passthrough`** — call with `headers={'X-Foo': 'bar'}`. The echo method inspects `http_request.headers` via a dependency and echoes `X-Foo`. Assert it matches.

- **T-S3-e `test_jsonrpc_client_is_testclient_subclass`** — `assert issubclass(JsonRpcTestClient, TestClient)`; trivial structural guard.

- **T-S3-f `test_jsonrpc_client_context_manager`** — `with JsonRpcTestClient(app): ...` works without raising; FastAPI startup event fires (use an event counter).

### Stage S4 — `jsonrpc_client` fixture

- **T-S4-a `test_jsonrpc_client_runs_startup_shutdown`** — inner test: `app` has `@app.on_event('startup')` incrementing a counter on an attribute; inside the test, the counter is `1`. Outer asserts passed.

- **T-S4-b `test_jsonrpc_client_end_to_end_happy_path`** — inner test calls a declared method via `client.jsonrpc(...)`. Outer asserts passed.

- **T-S4-c `test_jsonrpc_client_end_to_end_undeclared_fails_teardown`** — inner test calls a method that raises an undeclared error; test body itself does not `assert False`, but teardown should fail it. Outer asserts inner failed with undeclared-error message.

- **T-S4-d `test_jsonrpc_client_with_marker_suppresses_checks`** — inner test has the marker, raises undeclared error, passes. Outer asserts passed.

- **T-S4-e `test_jsonrpc_client_fixture_is_function_scoped`** — two inner tests share the same `app` fixture but get distinct `JsonRpcTestClient` instances and distinct `all_captured_jsonrpc_error_responses` dicts. Verified via `id()` capture written to a shared file or by asserting fresh state.

- **T-S4-f `test_app_placeholder_fails_with_actionable_message`** — inner conftest does *not* override `app`; inner test tries to use `jsonrpc_client`. Outer asserts inner failed with a message that mentions "override" and "app" (fail-fast at boundary).

### Coverage matrix vs Acceptance Criteria

| AC | Tests |
|---|---|
| AC1 | T-S1-b, T-S1-c, T-S1-d, T-S1-e, T-S1-f |
| AC2 | T-S2-a, T-S2-b, T-S2-c |
| AC3 | T-S3-a, T-S3-b, T-S3-c, T-S3-d |
| AC4 | T-S4-a, T-S4-b, T-S4-c |
| AC5 | T-S2-d, T-S3-e |

---

## Implementation order

Strict left-to-right dependency chain — each stage builds on the previous.

### Stage 1 — S1: declared-errors checker
**Depends on:** nothing (existing `all_captured_jsonrpc_error_responses` is the only input).
**Scope:** Add `_check_all_captured_jsonrpc_error_responses_listed_in_method_errors` fixture + unit test T-S1-a + pytester tests T-S1-b … T-S1-f.
**Exit criterion:** all S1 tests pass; zero changes to existing fixture yet.

### Stage 2 — S2: marker + fixture extension
**Depends on:** S1 must be green (so S2 regression tests have a reference).
**Scope:** Add `pytest_configure`; extend `all_captured_jsonrpc_error_responses` signature with `request: pytest.FixtureRequest` and add marker guard; tests T-S2-a … T-S2-d.
**Exit criterion:** S1 tests still pass AND new S2 tests pass. Regression gate: run the full existing `tests/` directory to confirm nothing broke (the current library test suite does not use this fixture today, so this is belt-and-braces).

### Stage 3 — S3: `JsonRpcTestClient`
**Depends on:** nothing from S1/S2 (isolated class).
**Scope:** Add `JsonRpcTestClient` class + tests T-S3-a … T-S3-f. Can be developed in parallel with S1/S2 if desired, but landed after S2 to keep a linear history.
**Exit criterion:** all S3 tests pass.

### Stage 4 — S4: `jsonrpc_client` fixture + `app` placeholder
**Depends on:** S1 (needs `_check_...`), S3 (needs `JsonRpcTestClient`).
**Scope:** Add `jsonrpc_client` fixture, `app` placeholder fixture; tests T-S4-a … T-S4-f.
**Exit criterion:** all S4 tests pass AND full `tests/` suite stays green.

---

## Risks & guards

| Risk | Impact | Guard |
|---|---|---|
| **R1. Upstream refactors `entrypoint_route` path** — if a future release moves errors off `EntrypointRoute`, D3 breaks silently. | Medium | Test T-S1-a asserts the path explicitly, so any rename surfaces immediately. |
| **R2. `BaseError.CODE` is `None`** for an edge-case subclass → `None` appears in `declared_codes` set and may "match" a `None` response code. | Low | Filter `cls.CODE is not None` when building the set (D3). Also reject `None` in the captured side if it ever occurs (defensive check in the checker). |
| **R3. Adding `request` param to existing fixture breaks user monkey-patches** that introspect the fixture signature. | Very Low | pytest fixtures are resolved by name, not signature. T-S2-d explicitly exercises the legacy usage pattern. |
| **R4. `pytest.fail` inside the middleware finalizer for non-`BaseError` now fires in tests that never declared the marker** — false positive in S2 flow. | Low | The existing line-35 `pytest.fail` is preserved (D5 — do not remove information). The marker D5 path returns *before* middleware is injected, so no finalizer runs — no collision. |
| **R5. Placeholder `app` fixture conflicts with user `app` fixture** — pytest override precedence. | Very Low | pytest's override mechanism prefers the closer conftest; a user-defined `app` in `tests/conftest.py` transparently shadows the plugin's stub. T-S4-f confirms the stub path; existing suites confirm the override path. |
| **R6. `with TestClient(app) as client` fails for users without startup events** — historically starlette raised in some versions. | Very Low | `tests/conftest.py` line 83–85 already uses the same pattern successfully, so we inherit its guarantees. |
| **R7. `pytester` inner tests cannot import the plugin** because the plugin module path depends on where the outer test runs. | Medium | Use `pytester.makepyprojecttoml(...)` or explicit `pytest_plugins = ['fastapi_jsonrpc.contrib.pytest_plugin']` line in the inner test file. Document the pattern once at the top of `test_pytest_plugin.py`. |
| **R8. `collections.defaultdict` vs plain `dict` in the marker branch** — consumers may call `.append` assuming a defaultdict. | Low | Return `collections.defaultdict(list)` in the marker branch, not `{}`, to preserve type shape. |

---

## Open questions resolved

### Q1. Where are entrypoint-level errors stored? How to access via `method_route.entrypoint`?

**Answer:** At `EntrypointRoute.errors` (line 1042 in `fastapi_jsonrpc/__init__.py`). `Entrypoint` has no `.errors` attribute of its own — grep over the file found exactly two `self.errors =` assignments: line 765 (`MethodRoute.__init__`) and line 1042 (`EntrypointRoute.__init__`).

Access path from a `MethodRoute`:
```python
method_route.entrypoint                    # the Entrypoint (APIRouter), set line 759
method_route.entrypoint.entrypoint_route   # the EntrypointRoute, set line 1265
method_route.entrypoint.entrypoint_route.errors  # List[Type[BaseError]], set line 1042
```

The README's proposed `method_route.entrypoint.errors` is incorrect.

### Q2. Do we need to handle `DataModel` / nested validation errors when checking declaration?

**Answer:** No. `BaseError.CODE` (line 188, `Optional[int]`) is the only identity used by the JSON-RPC envelope (`error.code` — see `BaseError.get_resp` lines 242–258). A captured response's error code matches a declared class iff they share `CODE`. `DataModel` carries payload structure, not identity; it is irrelevant to declaration checking. Implementation compares integers only; filter `None` codes defensively.

### Q3. One conftest.py vs multiple modules?

**Answer:** One `conftest.py`. See D1. Total added surface is ~100 lines; splitting adds navigation cost for zero reuse.

### Q4. Public re-export of `JsonRpcTestClient` from `fastapi_jsonrpc`?

**Answer:** No. See D8. Import from `fastapi_jsonrpc.contrib.pytest_plugin.conftest` for manual use. A re-export can be added later without breaking anyone; removing one is a breaking change.

---

## References

- Feature Brief: `features/FEAT-0001-pytest-plugin-upgrade/README.md`
- Current plugin: `fastapi_jsonrpc/contrib/pytest_plugin/conftest.py` (lines 1–54)
- Plugin registration: `fastapi_jsonrpc/contrib/pytest_plugin/__init__.py` (line 1)
- Key library types: `fastapi_jsonrpc/__init__.py` lines 187 (`BaseError`), 544 (`JsonRpcContext`), 701 (`MethodRoute`), 759 (`.entrypoint`), 765 (`.errors`), 967 (`EntrypointRoute`), 1042 (`.errors`), 1234 (`Entrypoint`), 1265 (`.entrypoint_route`)
- Existing `with TestClient` pattern: `tests/conftest.py` lines 82–85
- `pytester` already available: `tests/conftest.py` line 18

---

**Ready for Implementation:** Yes
**Estimated Complexity:** Low–Medium
**Estimated Time:** 1–1.5 days (including test suite via `pytester`)
