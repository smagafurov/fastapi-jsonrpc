# `jsonrpc.BaseError`

Base class for JSON-RPC errors. Subclass it to define your own error types.

```python
class NotEnoughMoney(jsonrpc.BaseError):
    CODE = 6001
    MESSAGE = 'Not enough money'

    class DataModel(BaseModel):
        balance: int
        currency: str
```

## Class attributes

- **`CODE: int`** — JSON-RPC error code. Required.
- **`MESSAGE: str`** — human-readable message. Required.
- **`DataModel: type[BaseModel] | None`** — optional Pydantic model for the `error.data` payload. When set, the value passed to `raise MyError(data=...)` is validated against it.
- **`ErrorModel: type[BaseModel] | None`** — optional model for entries inside `error.data.errors` (used by `InvalidRequest` and `InvalidParams` to describe individual validation issues).
- **`data_required: bool`** — if `True`, the `data` field is required in the generated schema. Default: `False`.
- **`errors_required: bool`** — same, but for the `errors` list inside `data`. Default: `False`.

## Instance API

- **`__init__(data=None)`** — creates the error; `data` is validated through `DataModel` if one is set.
- **`get_resp() -> dict`** — builds the full JSON-RPC response dict (`{jsonrpc, id, error}`).
- **`get_resp_data()`** — returns the payload for `error.data`.

## Built-in errors

`fastapi_jsonrpc` exports the standard JSON-RPC 2.0 errors:

| Class            | Code    | Meaning                                       |
|------------------|---------|-----------------------------------------------|
| `ParseError`     | -32700  | Invalid JSON was received                     |
| `InvalidRequest` | -32600  | The JSON sent is not a valid Request object   |
| `MethodNotFound` | -32601  | The method does not exist / is not available  |
| `InvalidParams`  | -32602  | Invalid method parameter(s)                   |
| `InternalError`  | -32603  | Internal JSON-RPC error                       |

Any unhandled exception raised from a method becomes an `InternalError` and is logged via Python's `logging` module.
