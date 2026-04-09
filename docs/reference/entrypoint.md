# `jsonrpc.Entrypoint`

A JSON-RPC entrypoint. Subclass of `fastapi.APIRouter`.

```python
api_v1 = jsonrpc.Entrypoint(
    path='/api/v1/jsonrpc',
    name='api_v1',
    errors=[...],
    dependencies=[Depends(...)],         # resolved once per batch
    common_dependencies=[Depends(...)],  # resolved once per request
    middlewares=[...],
    request_class=jsonrpc.JsonRpcRequest,
)
```

## Key arguments

- **`path`** — HTTP path the entrypoint is mounted on. Method routes are mounted as `{path}/{method_name}`.
- **`errors`** — list of `BaseError` subclasses that can be raised from any method on this entrypoint. Defaults to `Entrypoint.default_errors` (the JSON-RPC 2.0 spec errors).
- **`dependencies`** — FastAPI dependencies resolved **once per batch request**. See [Dependencies](../usage/dependencies.md).
- **`common_dependencies`** — FastAPI dependencies resolved **once per request inside a batch**.
- **`middlewares`** — list of `JsonRpcMiddleware` callables (async context managers that accept a `JsonRpcContext`). See [Middlewares](../usage/middlewares.md).
- **`scheduler_factory` / `scheduler_kwargs`** — customise the aiojobs scheduler used to run requests.
- **`request_class`** — custom `JsonRpcRequest` subclass, e.g. to add extra top-level fields beyond the JSON-RPC 2.0 spec.

## Registering methods

```python
@api_v1.method(errors=[MyError])
def echo(data: str = Body(...)) -> str:
    return data
```

`@entrypoint.method(**kwargs)` accepts the same keyword arguments as `fastapi.APIRouter.add_api_route` (`summary`, `description`, `tags`, `responses`, `dependencies`, …), plus a JSON-RPC-specific `errors=`.

## Class attributes

- **`Entrypoint.default_errors`** — `[InvalidParams, MethodNotFound, ParseError, InvalidRequest, InternalError]`. Extend it when composing custom `errors` lists.
