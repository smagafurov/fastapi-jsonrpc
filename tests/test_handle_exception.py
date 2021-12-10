import pytest

import fastapi_jsonrpc as jsonrpc


class MyUnhandledException(Exception):
    pass


class MyError(jsonrpc.BaseError):
    CODE = 5000
    MESSAGE = 'My error'


@pytest.fixture
def ep(ep_path):
    class Entrypoint(jsonrpc.Entrypoint):
        async def handle_exception(self, exc):
            assert isinstance(exc, MyError)
            raise MyUnhandledException('My unhandled exception')

    ep = Entrypoint(ep_path)

    @ep.method()
    def probe() -> int:
        raise MyError()

    return ep


def test_unhandled_exception(ep, json_request, assert_log_errors):
    resp = json_request({
        'id': 111,
        'jsonrpc': '2.0',
        'method': 'probe',
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
