# FEAT-0001: Pytest Plugin Upgrade

## Задача

Расширить `fastapi_jsonrpc.contrib.pytest_plugin` набором generic-фикстур, которые выдержали проверку продакшеном (проект `tochka/npd`, тысячи JSON-RPC тестов поверх форка библиотеки), но сейчас каждый пользователь вынужден писать их сам.

## Мотивация

Текущий плагин экспортирует только `all_captured_jsonrpc_error_responses` и требует, чтобы пользователь сам:
- создал `JsonRpcTestClient` поверх `TestClient`
- собрал JSON-RPC envelope руками
- написал teardown-проверку, что все пойманные ошибки декларированы в `@method(errors=[...])`
- настроил маркер для отключения tracking в специальных тестах

Эти вещи не содержат доменной логики — только boilerplate. Унос их в плагин даёт библиотеке главное преимущество: пользователь получает готовый test harness в одну строку `pytest_plugins = ['fastapi_jsonrpc.contrib.pytest_plugin']` + собственная фикстура `app`.

## Scope (что входит)

### S1. Auto-validation фикстура — `_check_all_captured_jsonrpc_error_responses_listed_in_method_errors`

Teardown-фикстура: после каждого теста проверяет, что все пойманные `all_captured_jsonrpc_error_responses` ошибки задекларированы в `MethodRoute.errors + MethodRoute.entrypoint.errors`. При несоответствии — `pytest.fail` с подробным сообщением.

**Важно:** НЕ autouse. Opt-in через явное включение в пользовательский `jsonrpc_client` или собственный client fixture. Причина: autouse сломает существующие suites, где исторически ошибки недекларированы.

### S2. Маркер `jsonrpcapi_no_tracking_middleware`

Позволяет точечно отключать tracking middleware для тестов, которые намеренно ломают контракт (например, проверяют fallback на `InternalError`).

Изменения:
- `pytest_configure` — регистрация маркера
- `all_captured_jsonrpc_error_responses` принимает `request: pytest.FixtureRequest`, в начале проверяет маркер и при наличии yield-ит пустой dict без инъекции middleware

**Backward compatibility:** добавление параметра `request` в существующую фикстуру — не breaking (фикстуры не вызываются пользователем напрямую, pytest резолвит по имени параметра).

### S3. `JsonRpcTestClient` — обёртка над `fastapi.testclient.TestClient`

```python
class JsonRpcTestClient(TestClient):
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

Чистый boilerplate: формирует JSON-RPC envelope, делает POST, возвращает `resp.json()`. Никакой доменной логики.

### S4. Фикстура `jsonrpc_client`

Function-scoped. Создаёт `JsonRpcTestClient(app)`, входит в контекстный менеджер (для startup/shutdown событий FastAPI), включает auto-validation фикстуру S1 как зависимость.

```python
@pytest.fixture()
def jsonrpc_client(app, _check_all_captured_jsonrpc_error_responses_listed_in_method_errors):
    with JsonRpcTestClient(app) as client:
        yield client
```

## Out of scope (что НЕ входит)

- ❌ `web_request` / `private_request` / `mobile_request` и подобные — URL'ы и заголовки (сессии, auth) пользовательские, библиотека не знает маршрутов
- ❌ Параметризация `any_request` — список entrypoint'ов project-specific
- ❌ Ассерт-хелперы (`AnyDict`) — есть `dirty_equals`, `testfixtures`; расширять scope библиотеки ради ассертов — плохая сделка
- ❌ Изменение существующего поведения `all_captured_jsonrpc_error_responses` за пределами добавления маркера

## Evidence base

Реальные паттерны из `/Users/posokhinsvyatoslav/sources/tochka/npd`:
- `src/tests/fixtures/fixtures.py` — класс `APIClient`, фикстуры `api_app`, `api_client`, `api_request`
- `src/tests/fixtures/swagger.py` — `all_captured_jsonrpc_error_responses`, `_check_all_captured_jsonrpc_error_responses_listed_in_method_errors`, маркер `jsonrpcapi_no_tracking_middleware`
- `src/tests/conftest.py` — подключение через `pytest_plugins`

**Отличие при портировании:** форк `tochka_jsonrpcapi` имеет класс `APIError` (subclass of `BaseError` с семантикой "wraps ValidationError"). В upstream `fastapi_jsonrpc` такого класса НЕТ. Логика декларации ошибок в upstream упрощается: сравнение `resp['error']['code']` с `{cls.CODE for cls in expected_errors}` — достаточное условие.

Upstream API (проверено чтением `fastapi_jsonrpc/__init__.py`):
- `MethodRoute.errors` (line 765)
- `MethodRoute.entrypoint` (line 759)
- `Entrypoint.errors` — хранится в `EntrypointRoute.errors` (line 1042), доступ через `method_route.entrypoint.errors` (через `EntrypointRoute` или `Entrypoint`?) — требует уточнения в архитектурной фазе
- `BaseError.CODE: int`
- `JsonRpcContext.raw_response`, `JsonRpcContext.method_route`

## Acceptance criteria

### AC1. Auto-validation работает
- Тест, где метод возвращает декларированную ошибку → проходит
- Тест, где метод возвращает недекларированную ошибку → `pytest.fail` с сообщением, содержащим имя метода, код ошибки и список декларированных кодов
- Несколько undeclared errors в одном тесте → fail на первой (или со списком всех — уточнить в архитектуре)

### AC2. Marker отключает tracking
- Тест с маркером `@pytest.mark.jsonrpcapi_no_tracking_middleware` → middleware не инжектится, `all_captured_jsonrpc_error_responses` возвращает `{}`
- Тест без маркера → поведение как раньше

### AC3. `JsonRpcTestClient.jsonrpc()` формирует корректный envelope
- `client.jsonrpc('echo', {'data': 'hi'}, url='/rpc')` → POST `/rpc` с body `{"id": 0, "jsonrpc": "2.0", "method": "echo", "params": {"data": "hi"}}`
- Дефолт `params=None` → `"params": {}` (не `null`)
- Заголовки мержатся с TestClient дефолтными

### AC4. `jsonrpc_client` фикстура работает end-to-end
- Startup/shutdown events FastAPI срабатывают (проверить через счётчик в `@app.on_event`)
- Auto-validation активен по умолчанию
- Backward compat: существующий тест `all_captured_jsonrpc_error_responses` продолжает работать

### AC5. Backward compatibility
- Пользовательские suites, которые подключали только `all_captured_jsonrpc_error_responses` и не использовали новые фикстуры, работают без изменений
- Нет изменений в публичных сигнатурах существующих функций (только добавление параметра `request` в фикстуру — допустимо)

## TDD порядок реализации

Следуя Red-Green-Refactor:

1. **S1 first** — auto-validation фикстура самая ценная и наименее рискованная
2. **S2** — маркер (требует правки существующей фикстуры, лёгкий риск regression)
3. **S3** — `JsonRpcTestClient` (изолирован)
4. **S4** — `jsonrpc_client` (композиция S1 + S3)

Для каждого stage: RED (падающий тест) → GREEN (минимальный код) → REFACTOR.

## Открытые вопросы для архитектора

1. Где именно хранятся errors у Entrypoint — на `Entrypoint.errors` (из `APIRouter` наследования?) или на `EntrypointRoute.errors`? Чтение кода показало `self.errors = errors or []` на строке 1042 в `EntrypointRoute.__init__`. Как корректно получить их через `method_route.entrypoint`?
2. Нужно ли поддерживать `DataModel` errors (с вложенной валидацией) при проверке декларации, или достаточно сравнения по `CODE`?
3. Placement: оставить всё в одном `contrib/pytest_plugin/conftest.py` или разделить на модули (`_client.py`, `_tracking.py`)?
4. Нужен ли публичный re-export `JsonRpcTestClient` из `fastapi_jsonrpc.contrib.pytest_plugin` (для ручного использования без фикстуры)?
