from json import dumps as json_dumps
from typing import List

import pytest
from fastapi import Body
from pydantic import BaseModel


@pytest.fixture
def echo(ep, method_request):
    class EchoInfo:
        def __init__(self):
            self.history = []

    echo_info = EchoInfo()

    @ep.method()
    def echo(
        data: str = Body(..., examples=['123']),
    ) -> str:
        echo_info.history.append(data)
        return data

    @ep.method()
    def no_params(
    ) -> str:
        return '123'

    class DataItem(BaseModel):
        inner_data: int

    @ep.method()
    def deep_data(
        data: List[DataItem] = Body(...),
    ) -> List[DataItem]:
        return data

    return echo_info


def test_no_params(echo, json_request):
    resp = json_request({
        'id': 111,
        'jsonrpc': '2.0',
        'method': 'no_params',
    })
    assert resp == {'id': 111, 'jsonrpc': '2.0', 'result': '123'}


@pytest.mark.parametrize('request_id', [111, 'qwe'])
def test_basic(echo, json_request, request_id):
    resp = json_request({
        'id': request_id,
        'jsonrpc': '2.0',
        'method': 'echo',
        'params': {'data': 'data-123'},
    })
    assert resp == {'id': request_id, 'jsonrpc': '2.0', 'result': 'data-123'}
    assert echo.history == ['data-123']


def test_notify(echo, raw_request):
    resp = raw_request(json_dumps({
        'jsonrpc': '2.0',
        'method': 'echo',
        'params': {'data': 'data-123'},
    }))
    assert not resp.content
    assert echo.history == ['data-123']


def test_batch_notify(echo, raw_request):
    resp = raw_request(json_dumps([
        {
            'jsonrpc': '2.0',
            'method': 'echo',
            'params': {'data': 'data-111'},
        },
        {
            'jsonrpc': '2.0',
            'method': 'echo',
            'params': {'data': 'data-222'},
        },
    ]))
    assert not resp.content
    assert set(echo.history) == {'data-111', 'data-222'}


def test_dict_error(echo, json_request):
    resp = json_request('qwe')
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [{
                'ctx': {'class_name': '_Request'},
                'input': 'qwe',
                'loc': [],
                'msg': 'Input should be a valid dictionary or instance of _Request',
                'type': 'model_type',
            }]},
        },
        'id': None,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_request_jsonrpc_validation_error(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '3.0',
        'method': 'echo',
        'params': {'data': 'data-123'},
    })
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [{
                'ctx': {'expected': "'2.0'"},
                'input': '3.0',
                'loc': ['jsonrpc'],
                'msg': "Input should be '2.0'",
                'type': 'literal_error',
            }]},
        },
        'id': 0,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_request_id_validation_error(echo, json_request):
    resp = json_request({
        'id': [123],
        'jsonrpc': '2.0',
        'method': 'echo',
        'params': {'data': 'data-123'},
    })
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [
                {'input': [123], 'loc': ['id', 'str'], 'msg': 'Input should be a valid string', 'type': 'string_type'},
                {'input': [123], 'loc': ['id', 'int'], 'msg': 'Input should be a valid integer', 'type': 'int_type'}
            ]},
        },
        'id': [123],
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_request_method_validation_error(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 123,
        'params': {'data': 'data-123'},
    })
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [
                {'input': 123, 'loc': ['method'], 'msg': 'Input should be a valid string', 'type': 'string_type'},
            ]},
        },
        'id': 0,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_request_params_validation_error(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'echo',
        'params': 123,
    })
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [
                {'input': 123, 'loc': ['params'], 'msg': 'Input should be a valid dictionary', 'type': 'dict_type'}]},
        },
        'id': 0,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_request_method_missing(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'params': {'data': 'data-123'},
    })
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [{
                'input': {'id': 0, 'jsonrpc': '2.0', 'params': {'data': 'data-123'}},
                'loc': ['method'],
                'msg': 'Field required',
                'type': 'missing'
            }]},
        },
        'id': 0,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_request_params_missing(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'echo',
    })
    assert resp == {
        'error': {
            'code': -32602,
            'message': 'Invalid params',
            'data': {'errors': [
                {'input': None, 'loc': ['data'], 'msg': 'Field required', 'type': 'missing'},
            ]},
        },
        'id': 0,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_request_extra(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'echo',
        'params': {'data': 'data-123'},
        'some_extra': 123,
    })
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [
                {
                    'input': 123,
                    'loc': ['some_extra'],
                    'msg': 'Extra inputs are not permitted',
                    'type': 'extra_forbidden',
                },
            ]},
        },
        'id': 0,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_method_not_found(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'echo-bla-bla',
        'params': {'data': 'data-123'},
    })
    assert resp == {
        'error': {'code': -32601, 'message': 'Method not found'},
        'id': 0,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_batch(echo, json_request):
    resp = json_request([
        {
            'id': 111,
            'jsonrpc': '2.0',
            'method': 'echo',
            'params': {'data': 'data-111'},
        },
        {
            'jsonrpc': '2.0',
            'method': 'echo',
            'params': {'data': 'data-notify'},
        },
        {
            'id': 'qwe',
            'jsonrpc': '2.0',
            'method': 'echo',
            'params': {'data': 'data-qwe'},
        },
        {
            'id': 'method-not-found',
            'jsonrpc': '2.0',
            'method': 'echo-bla-bla',
            'params': {'data': 'data-123'},
        },
    ])
    assert resp == [
        {'id': 111, 'jsonrpc': '2.0', 'result': 'data-111'},
        {'id': 'qwe', 'jsonrpc': '2.0', 'result': 'data-qwe'},
        {'id': 'method-not-found', 'jsonrpc': '2.0', 'error': {'code': -32601, 'message': 'Method not found'}},
    ]
    assert set(echo.history) == {'data-111', 'data-notify', 'data-qwe'}


def test_empty_batch(echo, json_request):
    resp = json_request([])
    assert resp == {
        'error': {
            'code': -32600,
            'message': 'Invalid Request',
            'data': {'errors': [{'loc': [], 'msg': 'rpc call with an empty array', 'type': 'value_error.empty'}]},
        },
        'id': None,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


@pytest.mark.parametrize('content', ['qwe', b'\xf1'], ids=['str', 'bytes'])
def test_non_json__parse_error(echo, raw_request, content):
    resp = raw_request(content).json()
    assert resp == {
        'error': {
            'code': -32700,
            'message': 'Parse error',
        },
        'id': None,
        'jsonrpc': '2.0',
    }
    assert echo.history == []


def test_deep_data_validation(echo, json_request):
    resp = json_request({
        'id': 0,
        'jsonrpc': '2.0',
        'method': 'deep_data',
        'params': {'data': [{}]},
    })
    assert resp == {
        'error': {
            'code': -32602,
            'message': 'Invalid params',
            'data': {'errors': [
                {
                    'input': {},
                    'loc': ['data', 0, 'inner_data'],
                    'msg': 'Field required',
                    'type': 'missing',
                },
            ]},
        },
        'id': 0,
        'jsonrpc': '2.0',
    }
