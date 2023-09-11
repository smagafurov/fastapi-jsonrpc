import logging
import platform
from json import dumps as json_dumps
from unittest.mock import ANY

import packaging.version
import pydantic
import pytest
from _pytest.python_api import RaisesContext
from starlette.testclient import TestClient
import fastapi_jsonrpc as jsonrpc


# Workaround for osx systems
# https://stackoverflow.com/questions/58597334/unittest-performance-issue-when-using-requests-mock-on-osx
if platform.system() == 'Darwin':
    import socket
    socket.gethostbyname = lambda x: '127.0.0.1'


pytest_plugins = 'pytester'


@pytest.fixture(autouse=True)
def check_no_errors(caplog):
    yield
    for when in ('setup', 'call'):
        messages = [
            x.message for x in caplog.get_records(when) if x.levelno >= logging.ERROR
        ]
        if messages:
            pytest.fail(
                f"error messages encountered during testing: {messages!r}"
            )


@pytest.fixture
def assert_log_errors(caplog):
    def _assert_log_errors(*errors):
        error_messages = []
        error_raises = []
        for error in errors:
            if isinstance(error, str):
                error_messages.append(error)
                error_raises.append(None)
            else:
                assert isinstance(error, RaisesContext), "errors-element must be string or pytest.raises(...)"
                assert error_raises[-1] is None
                error_raises[-1] = error

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]

        assert [r.message for r in error_records] == error_messages

        for record, error_raises_ctx in zip(error_records, error_raises):
            if error_raises_ctx is not None:
                with error_raises_ctx:
                    raise record.exc_info[1]

        # clear caplog records
        for when in ('setup', 'call'):
            del caplog.get_records(when)[:]
        caplog.clear()

    return _assert_log_errors


@pytest.fixture
def ep_path():
    return '/api/v1/jsonrpc'


@pytest.fixture
def ep(ep_path):
    return jsonrpc.Entrypoint(ep_path)


@pytest.fixture
def app(ep):
    app = jsonrpc.API()
    app.bind_entrypoint(ep)
    return app


@pytest.fixture
def app_client(app):
    return TestClient(app)


@pytest.fixture
def raw_request(app_client, ep_path):
    def requester(body, path_postfix='', auth=None):
        resp = app_client.post(
            url=ep_path + path_postfix,
            content=body,
            auth=auth,
        )
        return resp
    return requester


@pytest.fixture
def json_request(raw_request):
    def requester(data, path_postfix=''):
        resp = raw_request(json_dumps(data), path_postfix=path_postfix)
        return resp.json()
    return requester


@pytest.fixture(params=[False, True])
def add_path_postfix(request):
    return request.param


@pytest.fixture
def method_request(json_request, add_path_postfix):
    def requester(method, params, request_id=0):
        if add_path_postfix:
            path_postfix = '/' + method
        else:
            path_postfix = ''
        return json_request({
            'id': request_id,
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
        }, path_postfix=path_postfix)
    return requester


@pytest.fixture
def openapi_compatible():
    supported_openapi_versions = [packaging.version.parse("3.0.2"), packaging.version.parse("3.1.0")]

    if packaging.version.parse(pydantic.VERSION) >= packaging.version.parse("1.10.0"):
        def _openapi_compatible(value: dict):
            assert packaging.version.parse(value['openapi']) in supported_openapi_versions
            value['openapi'] = ANY
            return value
    else:
        def _openapi_compatible(obj: dict):
            for k, v in obj.items():
                if isinstance(v, dict):
                    obj[k] = _openapi_compatible(obj[k])
            if 'const' in obj and 'default' in obj:
                del obj['default']

            assert packaging.version.parse(obj['openapi']) in supported_openapi_versions
            obj['openapi'] = ANY

            return obj
    return _openapi_compatible
