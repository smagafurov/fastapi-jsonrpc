# Installation

## Requirements

- Python **3.10+**
- FastAPI `>=0.123`
- Pydantic `>=2.7, <3`

## Install

```bash
pip install fastapi-jsonrpc
```

For running the examples in this documentation you also need an ASGI server, e.g. [uvicorn](https://www.uvicorn.org/):

```bash
pip install uvicorn
```

## Optional extras

- **Sentry integration** — requires `sentry-sdk >= 2.0`:
  ```bash
  pip install 'sentry-sdk>=2.0'
  ```
- **Pytest plugin** — bundled in `fastapi_jsonrpc.contrib.pytest_plugin`. It is **not** auto-registered; add it explicitly to your `conftest.py` — see [Testing](usage/testing.md).

## Verify

```bash
python -c "import fastapi_jsonrpc; print(fastapi_jsonrpc.__name__)"
```
