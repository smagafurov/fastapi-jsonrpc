# `jsonrpc.API`

`fastapi_jsonrpc.API` is a subclass of `fastapi.FastAPI`. It behaves exactly like a regular FastAPI app, plus it knows how to bind `Entrypoint` instances and expose the OpenRPC schema.

```python
app = jsonrpc.API(
    title='My service',
    openrpc_url='/openrpc.json',           # set to None to disable
    fastapi_jsonrpc_components_fine_names=True,
)
```

## Parameters

- `openrpc_url: str | None` — URL for the generated OpenRPC schema. Default: `/openrpc.json`. Pass `None` to turn it off.
- `fastapi_jsonrpc_components_fine_names: bool` — controls the naming strategy for generated Pydantic components in the OpenAPI schema. Default: `True`. Set to `False` if the default names collide with your own schemas. See `tests/test_openapi.py` for exact behaviour.
- Everything else is forwarded to `FastAPI`.

## Binding entrypoints

```python
api_v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')
app.bind_entrypoint(api_v1)
```

`bind_entrypoint` registers both the JSON-RPC entrypoint route and one POST route per method under it.

## Shutdown hooks

`API` adds a single `shutdown` handler that closes the aiojobs scheduler owned by every bound entrypoint. You can register your own shutdown callables via FastAPI's standard mechanisms (`lifespan=` or `add_event_handler`).
