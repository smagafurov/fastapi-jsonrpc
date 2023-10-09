import pytest
from pydantic import BaseModel, Field
from typing import List


class Balance(BaseModel):
    """Account balance"""
    amount: int = Field(..., examples=[100])
    currency: str = Field(..., examples=['USD'])


@pytest.fixture
def ep(ep):
    @ep.method()
    def probe1(
        data: List[Balance],
    ) -> List[Balance]:
        return data

    @ep.method()
    def probe2(
        data: List[Balance],
    ) -> List[Balance]:
        return data

    return ep


def test_basic(json_request):
    resp = json_request({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe1',
        'params': {'data': [
            {'amount': 1, 'currency': 'USD'},
            {'amount': 2, 'currency': 'RUB'},
        ]},
    })
    assert resp == {'id': 1, 'jsonrpc': '2.0', 'result': [
        {'amount': 1, 'currency': 'USD'},
        {'amount': 2, 'currency': 'RUB'},
    ]}

    resp = json_request({
        'id': 1,
        'jsonrpc': '2.0',
        'method': 'probe2',
        'params': {'data': [
            {'amount': 3, 'currency': 'USD'},
            {'amount': 4, 'currency': 'RUB'},
        ]},
    })
    assert resp == {'id': 1, 'jsonrpc': '2.0', 'result': [
        {'amount': 3, 'currency': 'USD'},
        {'amount': 4, 'currency': 'RUB'},
    ]}


def test_openapi(app_client, openapi_compatible):
    resp = app_client.get('/openapi.json')
    assert resp.json() == openapi_compatible({
        'components': {
            'schemas': {
                'Balance': {
                    'description': 'Account balance',
                    'properties': {
                        'amount': {
                            'examples': [100],
                            'title': 'Amount',
                            'type': 'integer',
                        },
                        'currency': {
                            'examples': ['USD'],
                            'title': 'Currency',
                            'type': 'string',
                        }
                    },
                    'required': ['amount', 'currency'],
                    'title': 'Balance',
                    'type': 'object',
                },
                'InternalError': {
                    'properties': {
                        'code': {
                            'default': -32603,
                            'example': -32603,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'message': {
                            'default': 'Internal error',
                            'example': 'Internal error',
                            'title': 'Message',
                            'type': 'string',
                        },
                    },
                    'title': 'InternalError',
                    'type': 'object',
                },
                'InvalidParams': {
                    'properties': {
                        'code': {
                            'default': -32602,
                            'example': -32602,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'data': {'anyOf': [
                            {'$ref': '#/components/schemas/_ErrorData[_Error]', },
                            {'type': 'null'}
                        ]},
                        'message': {
                            'default': 'Invalid params',
                            'example': 'Invalid params',
                            'title': 'Message',
                            'type': 'string',
                        },
                    },
                    'title': 'InvalidParams',
                    'type': 'object',
                },
                'InvalidRequest': {
                    'properties': {
                        'code': {
                            'default': -32600,
                            'example': -32600,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'data': {'anyOf': [
                            {'$ref': '#/components/schemas/_ErrorData[_Error]', },
                            {'type': 'null'}
                        ]},
                        'message': {
                            'default': 'Invalid Request',
                            'example': 'Invalid Request',
                            'title': 'Message',
                            'type': 'string',
                        },
                    },
                    'title': 'InvalidRequest',
                    'type': 'object',
                },
                'MethodNotFound': {
                    'properties': {
                        'code': {
                            'default': -32601,
                            'example': -32601,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'message': {
                            'default': 'Method not found',
                            'example': 'Method not found',
                            'title': 'Message',
                            'type': 'string',
                        },
                    },
                    'title': 'MethodNotFound',
                    'type': 'object',
                },
                'ParseError': {
                    'properties': {
                        'code': {
                            'default': -32700,
                            'example': -32700,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'message': {
                            'default': 'Parse error',
                            'example': 'Parse error',
                            'title': 'Message',
                            'type': 'string',
                        },
                    },
                    'title': 'ParseError',
                    'type': 'object',
                },
                '_Error': {
                    'properties': {
                        'ctx': {
                            'title': 'Ctx',
                            'anyOf': [{'type': 'object'}, {'type': 'null'}],
                        },
                        'loc': {
                            'items': {'anyOf': [
                                {'type': 'string'},
                                {'type': 'integer'},
                            ]},
                            'title': 'Loc',
                            'type': 'array',
                        },
                        'msg': {
                            'title': 'Msg',
                            'type': 'string',
                        },
                        'type': {
                            'title': 'Type',
                            'type': 'string',
                        },
                    },
                    'required': ['loc', 'msg', 'type'],
                    'title': '_Error',
                    'type': 'object',
                },
                '_ErrorData[_Error]': {
                    'properties': {
                        'errors': {
                            'anyOf': [
                                {'items': {'$ref': '#/components/schemas/_Error'}, 'type': 'array'},
                                {'type': 'null'}
                            ],
                            'title': 'Errors',
                        },
                    },
                    'title': '_ErrorData[_Error]',
                    'type': 'object',
                },
                '_ErrorResponse[InternalError]': {
                    'additionalProperties': False,
                    'properties': {
                        'error': {
                            '$ref': '#/components/schemas/InternalError',
                        },
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[InternalError]',
                    'type': 'object',
                },
                '_ErrorResponse[InvalidParams]': {
                    'additionalProperties': False,
                    'properties': {
                        'error': {
                            '$ref': '#/components/schemas/InvalidParams',
                        },
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[InvalidParams]',
                    'type': 'object',
                },
                '_ErrorResponse[InvalidRequest]': {
                    'additionalProperties': False,
                    'properties': {
                        'error': {
                            '$ref': '#/components/schemas/InvalidRequest',
                        },
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[InvalidRequest]',
                    'type': 'object',
                },
                '_ErrorResponse[MethodNotFound]': {
                    'additionalProperties': False,
                    'properties': {
                        'error': {
                            '$ref': '#/components/schemas/MethodNotFound',
                        },
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[MethodNotFound]',
                    'type': 'object',
                },
                '_ErrorResponse[ParseError]': {
                    'additionalProperties': False,
                    'properties': {
                        'error': {
                            '$ref': '#/components/schemas/ParseError',
                        },
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[ParseError]',
                    'type': 'object',
                },
                '_Params[probe1]': {
                    'properties': {
                        'data': {
                            'items': {'$ref': '#/components/schemas/Balance'},
                            'title': 'Data',
                            'type': 'array',
                        },
                    },
                    'required': ['data'],
                    'title': '_Params[probe1]',
                    'type': 'object',
                },
                '_Params[probe2]': {
                    'properties': {
                        'data': {
                            'items': {'$ref': '#/components/schemas/Balance'},
                            'title': 'Data',
                            'type': 'array',
                        },
                    },
                    'required': ['data'],
                    'title': '_Params[probe2]',
                    'type': 'object',
                },
                '_Request': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                        'method': {
                            'title': 'Method',
                            'type': 'string',
                        },
                        'params': {
                            'title': 'Params',
                            'type': 'object',
                        },
                    },
                    'required': ['method'],
                    'title': '_Request',
                    'type': 'object',
                },
                '_Request[probe1]': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                        'method': {
                            'default': 'probe1',
                            'example': 'probe1',
                            'title': 'Method',
                            'type': 'string',
                        },
                        'params': {
                            '$ref': '#/components/schemas/_Params[probe1]',
                        },
                    },
                    'required': ['params'],
                    'title': '_Request[probe1]',
                    'type': 'object',
                },
                '_Request[probe2]': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                        'method': {
                            'default': 'probe2',
                            'example': 'probe2',
                            'title': 'Method',
                            'type': 'string',
                        },
                        'params': {
                            '$ref': '#/components/schemas/_Params[probe2]',
                        },
                    },
                    'required': ['params'],
                    'title': '_Request[probe2]',
                    'type': 'object',
                },
                '_Response': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                        'result': {
                            'title': 'Result',
                            'type': 'object',
                        },
                    },

                    'required': ['jsonrpc', 'id', 'result'],
                    'title': '_Response',
                    'type': 'object',
                },
                '_Response[probe1]': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                        'result': {
                            'items': {'$ref': '#/components/schemas/Balance'},
                            'title': 'Result',
                            'type': 'array',
                        },
                    },
                    'required': ['jsonrpc', 'id', 'result'],
                    'title': '_Response[probe1]',
                    'type': 'object',
                },
                '_Response[probe2]': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [
                                {
                                    'type': 'string',
                                },
                                {
                                    'type': 'integer',
                                },
                            ],
                            'example': 0,
                            'title': 'Id',
                        },
                        'jsonrpc': {
                            'const': '2.0',
                            'default': '2.0',
                            'example': '2.0',
                            'title': 'Jsonrpc',
                        },
                        'result': {
                            'items': {'$ref': '#/components/schemas/Balance'},
                            'title': 'Result',
                            'type': 'array',
                        },
                    },
                    'required': ['jsonrpc', 'id', 'result'],
                    'title': '_Response[probe2]',
                    'type': 'object',
                },
            },
        },
        'info': {
            'title': 'FastAPI', 'version': '0.1.0',
        },
        'openapi': '3.0.2',
        'paths': {
            '/api/v1/jsonrpc': {
                'post': {
                    'operationId': 'entrypoint_api_v1_jsonrpc_post',
                    'requestBody': {
                        'content': {
                            'application/json': {
                                'schema': {
                                    '$ref': '#/components/schemas/_Request',
                                },
                            },
                        },
                        'required': True,
                    },
                    'responses': {
                        '200': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_Response',
                                    },
                                },
                            },
                            'description': 'Successful Response',
                        },
                        '210': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse[InvalidParams]',
                                    },
                                },
                            },
                            'description': '[-32602] Invalid params\n\nInvalid method parameter(s)',
                        },
                        '211': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse[MethodNotFound]',
                                    },
                                },
                            },
                            'description': '[-32601] Method not found\n\nThe method does not exist / is not available',
                        },
                        '212': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse[ParseError]',
                                    },
                                },
                            },
                            'description': '[-32700] Parse error\n\nInvalid JSON was received by the server',
                        },
                        '213': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse[InvalidRequest]',
                                    },
                                },
                            },
                            'description': '[-32600] Invalid Request\n\nThe JSON sent is not a valid Request object',
                        },
                        '214': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse[InternalError]',
                                    },
                                },
                            },
                            'description': '[-32603] Internal error\n\nInternal JSON-RPC error',
                        },
                    },
                    'summary': 'Entrypoint',
                },
            },
            '/api/v1/jsonrpc/probe1': {
                'post': {
                    'operationId': 'probe1_api_v1_jsonrpc_probe1_post',
                    'requestBody': {
                        'content': {
                            'application/json': {
                                'schema': {
                                    '$ref': '#/components/schemas/_Request[probe1]',
                                },
                            },
                        },
                        'required': True,
                    },
                    'responses': {
                        '200': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_Response[probe1]',
                                    },
                                },
                            },
                            'description': 'Successful Response',
                        },
                    },
                    'summary': 'Probe1',
                },
            },
            '/api/v1/jsonrpc/probe2': {
                'post': {
                    'operationId': 'probe2_api_v1_jsonrpc_probe2_post',
                    'requestBody': {
                        'content': {
                            'application/json': {
                                'schema': {
                                    '$ref': '#/components/schemas/_Request[probe2]',
                                },
                            },
                        },
                        'required': True,
                    },
                    'responses': {
                        '200': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_Response[probe2]',
                                    },
                                },
                            },
                            'description': 'Successful Response',
                        },
                    },
                    'summary': 'Probe2',
                },
            },
        },
    })
