import logging
import pytest
from pydantic import BaseModel

from fastapi_jsonrpc import BaseError, Entrypoint, ParseError


@pytest.fixture
def ep(ep_path):

    class MyError(BaseError):
        CODE = 5000
        MESSAGE = "My error"

        class DataModel(BaseModel):
            details: str

    ep = Entrypoint(
        ep_path,
        log_handled_exceptions_resp=logging.WARNING
    )

    @ep.method(errors=[ParseError])
    def parse_error() -> str:
        raise ParseError()

    @ep.method(errors=[MyError])
    def custom_error() -> str:
        raise MyError(data={'details': 'error'})

    return ep


def test_unexisting_method(ep, caplog, json_request):
    resp = json_request({
        'id': 111,
        'jsonrpc': '2.0',
        'method': 'foo',
        'params': {},
    })
    assert "{'code': -32601, 'message': 'Method not found'}" in caplog.text
    assert resp == {'jsonrpc': '2.0', 'error': {'code': -32601, 'message': 'Method not found'}, 'id': 111}


def test_parse_error(ep, caplog, json_request):
    resp = json_request({
        'id': 112,
        'jsonrpc': '2.0',
        'method': 'parse_error',
        'params': {},
    })
    assert "{'code': -32700, 'message': 'Parse error'}" in caplog.text
    assert resp == {'jsonrpc': '2.0', 'error': {'code': -32700, 'message': 'Parse error'}, 'id': 112}


def test_custom_error(ep, caplog, json_request):
    resp = json_request({
        'id': 113,
        'jsonrpc': '2.0',
        'method': 'custom_error',
        'params': {},
    })
    assert "{'code': 5000, 'message': 'My error', 'data': {'details': 'error'}}" in caplog.text
    assert resp == {'jsonrpc': '2.0', 'error': {'code': 5000, 'message': 'My error', 'data': {'details': 'error'}}, 'id': 113}