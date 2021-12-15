import pytest

import fastapi_jsonrpc as jsonrpc


class MyUnhandledException(Exception):
    pass


class MyErrorToUnhandledException(jsonrpc.BaseError):
    CODE = 5000
    MESSAGE = 'My error'


class MyErrorToConvert(jsonrpc.BaseError):
    CODE = 5001
    MESSAGE = 'My error to convert'


class MyConvertedError(jsonrpc.BaseError):
    CODE = 5002
    MESSAGE = 'My converted error'


@pytest.fixture
def ep(ep_path):
    class Entrypoint(jsonrpc.Entrypoint):
        async def handle_exception(self, exc):
            if isinstance(exc, MyErrorToUnhandledException):
                raise MyUnhandledException('My unhandled exception')
            elif isinstance(exc, MyErrorToConvert):
                raise MyConvertedError
            else:
                raise NotImplementedError

    ep = Entrypoint(ep_path)

    @ep.method()
    def unhandled_exception() -> int:
        raise MyErrorToUnhandledException()

    @ep.method()
    def convert_error() -> int:
        raise MyErrorToConvert()

    return ep


def test_unhandled_exception(ep, json_request, assert_log_errors):
    resp = json_request({
        'id': 111,
        'jsonrpc': '2.0',
        'method': 'unhandled_exception',
        'params': {},
    })

    assert resp == {
        'jsonrpc': '2.0',
        'id': 111,
        'error': {
            'code': -32603,
            'message': 'Internal error',
        },
    }

    assert_log_errors('My unhandled exception', pytest.raises(MyUnhandledException))


def test_convert_error(ep, json_request, assert_log_errors):
    resp = json_request({
        'id': 111,
        'jsonrpc': '2.0',
        'method': 'convert_error',
        'params': {},
    })

    assert resp == {
        'jsonrpc': '2.0',
        'id': 111,
        'error': {
            'code': 5002,
            'message': 'My converted error',
        },
    }
