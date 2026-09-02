## v4.0.0 (2026-09-02)

### Feat

- **openrpc**: describe each method's entrypoint servers
- make the shipped package mypy-compatible
- declare the sentry extra and refuse sentry-sdk 1.x explicitly
- drop support for sentry-sdk 1.x

### Fix

- **openrpc**: type-check the OpenRPC generator and close what it exposed
- **openrpc**: reject a blank server name like a blank url
- say which route options the protocol owns
- say which Params arguments the protocol owns
- create an Entrypoint from code that belongs to no module
- honour dependency_overrides for methods registered after bind_entrypoint
- engage the implicit Sentry integration only when Sentry is initialized
- stop calling deprecated `asyncio.iscoroutinefunction`
- make the shared-dependencies params check actually fire
- drop dependency on fastapi's removed `get_flat_dependant`
- stop forwarding unset `example` to fastapi.params.Body

### Refactor

- drop the dead `_normalize_errors` shim

## v3.5.0 (2026-04-17)

### Feat

- support Starlette 1.0 and FastAPI 0.135+

## v3.4.3 (2026-04-15)

### Feat

- **pytest_plugin**: ship full test harness with auto-validation
- support fastapi >=0.123 + drop python 3.9

## v3.4.2 (2025-12-08)

### Fix

- fastapi<0.123
- schema generation with type keyword (#84)

## v3.4.1 (2025-04-24)

### Fix

- sentry-sdk ^2.23 support (#81)

## v3.4.0 (2025-03-14)

### Fix

- run notifications in background

## v3.3.0 (2025-01-09)

### Feat

- **sentry**: added explicit integration
- **sentry**: no more deprecation warning for sentry_sdk 2.x; now fill a transaction source when modify event data

### Fix

- propagating exceptions from integration middleware
- simplified no sentry-sdk installed corner case
- handling no sentry-sdk installed corner case
- changed integration class alias -  `identifier = "FastApiJsonRPCIntegration"`
- moved out sentry integration import from root of `contrib` package
- fixed py3.9 compatibility

### Refactor

- minor review issues
- **tests**: fixes according to review comments

## v3.2.1 (2024-09-25)

### Fix

- fastapi>=0.112.4, pydantic>=2.7.0

## v3.2.0 (2024-09-25)

### Feat

- Support current versions of dependencies - pydantic-2.9.2 and fastapi-0.115.0

## v3.1.2 (2024-09-25)

### Fix

- correct restore fine schema names

## v3.1.1 (2024-03-12)

### Fix

- solve deprecated

## v3.1.0 (2024-01-08)

### Feat

- support fastapi >= 0.106.0

## v3.0.2 (2024-01-08)

## v3.0.1 (2023-12-10)

### Fix

- reset scheduler correctly when Entrypoint shutdown; now Entrypoint can be reused correctly in tests

## v3.0.0 (2023-10-24)

### BREAKING CHANGE

- DROP PYDANTIC V1 SUPPORT

### Feat

- support Pydantic v2.4
- support PydanticV2

### Fix

- **openrpc**: pydantic v2 compatibility
- generate openapi even without Entrypoint (regression fix)
- restore components fine names

## v2.7.0 (2023-10-19)

### Feat

- **openrpc**: add openrpc_url option, which allow control path to schema and disable it
- **openrpc**: Support for mergeable errors
- **openrpc**: Add OpenRPC schema generator

## v2.6.1 (2023-09-20)

### Fix

- new fastapi validation error processing

## v2.6.0 (2023-09-15)

### Feat

- **openapi**: pass tags from Entrypoint to all entire methods (see #52)
- use aiojobs.Scheduler for any incoming requests instead batch

### Fix

- **openapi**: now swagger correctly substitute error schema in methods for fastapi >=0.99  (backport swagger 5.0 ui fix from 3.0.0b)
- now incorrect Unicode body trigger ParseError instead InternalError (fixes #48)

## v2.5.2 (2023-09-07)

### Fix

- pydantic<2.0.0

## v2.5.1 (2023-09-07)

### Fix

- pydantic<=1.10.12

## v2.5.0 (2023-07-03)

### Feat

- **fastapi**: allow use BaseModel's as `examples` items

## v2.4.1 (2022-11-09)

### Fix

- params is not required

## v2.4.0 (2022-11-09)

### Feat

- new fastapi 0.83.0

## v2.3.0 (2022-08-05)

### Feat

- fastapi = ">0.55,<0.80"

## v2.2.2 (2022-05-13)

### Fix

- **deps**: Upgrade fastapi and starlette (#39)

## v2.2.1 (2022-05-12)

## v2.2.0 (2022-01-22)

### Feat

- make Entrypoint, EntrypointRoute and MethodRoute hashable for convenience
- preserve error classes in separate property for `EntrypointRoute.errors` and `MethodRoute.errors`

### Fix

- **ci**: try to fix job name v2
- **ci**: try to fix job name

## v2.1.6 (2022-01-01)

## v2.1.5 (2021-12-15)

### Fix

- dependencies

## v2.1.4 (2021-12-15)

### Fix

- convert error on handle_exception

## v2.1.3 (2021-12-11)

### Fix

- setup.py
- openapi 'example' now works again
- use new dependencies (fastapi, pydantic)
- allow new aiojobs
- Params args
- problem hiding in handle_exception

## v2.1.2 (2021-07-27)

### Fix

- **sentry**: now `transaction` contains correct value - original method function instead inner dummy endpoint

## v2.1.1 (2021-07-12)

### Feat

- allow using custom request class (#21)
- now middlewares can handle exceptions
- http info in middlewares (JsonRpcContext), basic auth tests
- do not convert HTTPException to json rpc error
- jsonrpc middlewares
- support http sub response
- get_jsonrpc_request_id, get_jsonrpc_method

### Fix

- **openapi**: no more conflicts in openapi components which leads to missing models in openapi.json or openapi generation error in rare cases
- fix unhandled exception logging (2)
- fix unhandled exception logging
- response_model_exclude_unset transit to fastapi (#13)
- fastapi = ">0.55"

### Refactor

- jsonrpc_middlewares -> middlewares
