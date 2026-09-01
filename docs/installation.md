# Installation

## Requirements

- Python **3.10+**
- FastAPI `>=0.135.2`
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

- **Sentry integration** — only sentry-sdk 2.x is supported:
  ```bash
  pip install 'fastapi-jsonrpc[sentry]'
  ```
  On sentry-sdk 1.x importing `fastapi_jsonrpc.contrib.sentry` raises, and the deprecated implicit integration stays off with a warning on import.
- **Pytest plugin** — bundled in `fastapi_jsonrpc.contrib.pytest_plugin`. It is **not** auto-registered; add it explicitly to your `conftest.py` — see [Testing](usage/testing.md).

## Verify

```bash
python -c "import fastapi_jsonrpc; print(fastapi_jsonrpc.__name__)"
```
