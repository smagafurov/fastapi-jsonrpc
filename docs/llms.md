# LLM Context (`llms.txt` / `llms-full.txt`)

The project ships two plain-text files designed to be fed into an AI coding assistant (Claude, Cursor, Copilot, ChatGPT, …) so that it has accurate, up-to-date context about `fastapi-jsonrpc` without having to crawl the whole site:

- [`llms.txt`](llms.txt) — short index. Title, one-paragraph description, and a curated list of links to every documentation page.
- [`llms-full.txt`](llms-full.txt) — full reference. Architecture, public API signatures, built-in errors, patterns, testing harness, wire protocol, common pitfalls.

Both files follow the [llmstxt.org](https://llmstxt.org) convention: Markdown, predictable top-level structure, no HTML chrome, no navigation noise. They are served from the documentation site root, so once the docs are deployed they are reachable at stable URLs:

```
https://smagafurov.github.io/fastapi-jsonrpc/llms.txt
https://smagafurov.github.io/fastapi-jsonrpc/llms-full.txt
```

## When to use which

| File | Size | Use for |
|------|------|---------|
| `llms.txt` | small | Navigation hint — let the agent discover which page to fetch next. |
| `llms-full.txt` | large | Drop-in context for answering a concrete question without any further fetches. |

If you are unsure, paste `llms-full.txt` — it is self-contained.

## Usage patterns

### Claude Code / Claude Desktop

Reference the file directly with `@` in your prompt, or save it into `CLAUDE.md` at the root of your project so every session picks it up:

```markdown
# CLAUDE.md

When working with fastapi-jsonrpc, use the patterns documented at
https://smagafurov.github.io/fastapi-jsonrpc/llms-full.txt
```

### Cursor / Windsurf / Continue

Add the URL as a custom documentation source. Most IDE integrations support `@Docs` or a similar mechanism that fetches and indexes external pages — point it at `llms-full.txt`.

### Raw prompt (ChatGPT, Gemini, local models)

Fetch the file once and paste it at the top of your conversation under a `# Reference` heading:

```
# Reference
<paste contents of llms-full.txt>

# Task
Implement a JSON-RPC method `transfer(src, dst, amount)` with a typed
`NotEnoughMoney` error using fastapi-jsonrpc.
```

### Programmatic fetch (CI, scripts, agents)

```python
import httpx

CTX = httpx.get(
    'https://smagafurov.github.io/fastapi-jsonrpc/llms-full.txt'
).text
```

## What's inside `llms-full.txt`

At a glance — the file is structured so an LLM can jump straight to the relevant section:

1. **Architecture** — module hierarchy, data flow, key abstractions (`API`, `Entrypoint`, `MethodRoute`, `JsonRpcContext`).
2. **Public API** — signatures of `API`, `Entrypoint`, `BaseError`, context helpers.
3. **Built-in errors** — table of JSON-RPC error codes shipped with the library.
4. **Key patterns** — declaring methods, dependency injection, per-call vs batch dependencies, middlewares, typed error `data`.
5. **OpenAPI / OpenRPC** — auto-generated schema, per-method Swagger routes, tags, component names.
6. **Testing** — pytest plugin (`JsonRpcTestClient`, `jsonrpc_client`, auto-validation fixture, opt-out marker), direct method calls.
7. **Sentry integration** — `FastApiJsonRPCIntegration`, transaction naming, batch spans.
8. **Wire protocol** — single / batch / notification request and response examples.
9. **Common pitfalls** — issues that bite integrators in production.

## Keeping the files fresh

Both files are hand-written Markdown committed to the repo under `docs/`. When the library changes — new public API, new built-in error, new fixture — update the corresponding section so that LLMs using the published files see the current reality. Outdated AI context is strictly worse than no context at all: it produces confident wrong answers.
