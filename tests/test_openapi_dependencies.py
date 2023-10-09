from unittest.mock import ANY

import pytest
from fastapi import Body, Depends, Header
from typing import List

import fastapi_jsonrpc as jsonrpc


def get_auth_token(
    auth_token: str = Header(..., alias='auth-token'),
) -> str:
    return auth_token


def get_common_dep(
    common_dep: float = Body(...),
) -> float:
    return common_dep


@pytest.fixture
def ep(ep_path):
    ep = jsonrpc.Entrypoint(
        ep_path,
        dependencies=[Depends(get_auth_token)],
        common_dependencies=[Depends(get_common_dep)],
    )

    @ep.method()
    def probe(
        data: List[str] = Body(..., examples=['111', '222']),
    ) -> List[int]:
        del data
        return [1, 2, 3]

    def get_probe2_dep(
        probe2_dep: int = Body(...),
    ) -> int:
        return probe2_dep

    @ep.method()
    def probe2(
        auth_token: str = Depends(get_auth_token),
        probe2_dep: int = Depends(get_probe2_dep),
    ) -> int:
        del auth_token
        del probe2_dep
        return 1

    return ep


def test_basic(app_client, openapi_compatible):
    resp = app_client.get('/openapi.json')
    assert resp.json() == openapi_compatible({
        'components': {
            'schemas': {
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
                '_Params[entrypoint]': {
                    'properties': {
                        'common_dep': {
                            'title': 'Common Dep',
                            'type': 'number',
                        }
                    },
                    'required': ['common_dep'],
                    'title': '_Params[entrypoint]',
                    'type': 'object',
                },
                '_Params[probe2]': {
                    'properties': {
                        'common_dep': {
                            'title': 'Common Dep',
                            'type': 'number',
                        },
                        'probe2_dep': {
                            'title': 'Probe2 Dep',
                            'type': 'integer',
                        },
                    },
                    'required': ['common_dep', 'probe2_dep'],
                    'title': '_Params[probe2]',
                    'type': 'object',
                },
                '_Params[probe]': {
                    'properties': {
                        'common_dep': {
                            'title': 'Common Dep',
                            'type': 'number',
                        },
                        'data': {
                            'examples': ['111', '222'],
                            'items': {
                                'type': 'string',
                            },
                            'title': 'Data',
                            'type': 'array',
                        },
                    },
                    'required': ['data', 'common_dep'],
                    'title': '_Params[probe]',
                    'type': 'object',
                },
                '_Request[entrypoint]': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [{'type': 'string'}, {'type': 'integer'}],
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
                            'default': 'entrypoint',
                            'example': 'entrypoint',
                            'title': 'Method',
                            'type': 'string',
                        },
                        'params': {'$ref': '#/components/schemas/_Params[entrypoint]'}
                    },
                    'required': ['params'],
                    'title': '_Request[entrypoint]',
                    'type': 'object',
                },
                '_Request[probe2]': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [{'type': 'string'}, {'type': 'integer'}],
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
                        'params': {'$ref': '#/components/schemas/_Params[probe2]'},
                    },
                    'required': ['params'],
                    'title': '_Request[probe2]',
                    'type': 'object',
                },
                '_Request[probe]': {
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
                            'default': 'probe',
                            'example': 'probe',
                            'title': 'Method',
                            'type': 'string',
                        },
                        'params': {
                            '$ref': '#/components/schemas/_Params[probe]',
                        },
                    },
                    'required': ['params'],
                    'title': '_Request[probe]',
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
                '_Response[probe2]': {
                    'additionalProperties': False,
                    'properties': {
                        'id': {
                            'anyOf': [{'type': 'string'}, {'type': 'integer'}],
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
                            'type': 'integer',
                        }
                    },
                    'required': ['jsonrpc', 'id', 'result'],
                    'title': '_Response[probe2]',
                    'type': 'object',
                },
                '_Response[probe]': {
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
                            'items': {
                                'type': 'integer',
                            },
                            'title': 'Result',
                            'type': 'array',
                        },
                    },
                    'required': ['jsonrpc', 'id', 'result'],
                    'title': '_Response[probe]',
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
                    'parameters': [{
                        'in': 'header',
                        'name': 'auth-token',
                        'required': True,
                        'schema': {
                            'title': 'Auth-Token',
                            'type': 'string',
                        },
                    }],
                    'requestBody': {
                        'content': {
                            'application/json': {
                                'schema': {
                                    '$ref': '#/components/schemas/_Request[entrypoint]',
                                },
                            },
                        },
                        'required': True,
                    },
                    'responses': ANY,
                    'summary': 'Entrypoint',
                },
            },
            '/api/v1/jsonrpc/probe': {
                'post': {
                    'operationId': 'probe_api_v1_jsonrpc_probe_post',
                    'requestBody': {
                        'content': {
                            'application/json': {
                                'schema': {
                                    '$ref': '#/components/schemas/_Request[probe]',
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
                                        '$ref': '#/components/schemas/_Response[probe]',
                                    },
                                },
                            },
                            'description': 'Successful Response',
                        },
                    },
                    'summary': 'Probe',
                },
            },
            '/api/v1/jsonrpc/probe2': {
                'post': {
                    'operationId': 'probe2_api_v1_jsonrpc_probe2_post',
                    'parameters': [{
                        'in': 'header',
                        'name': 'auth-token',
                        'required': True,
                        'schema': {
                            'title': 'Auth-Token',
                            'type': 'string',
                        },
                    }],
                    'requestBody': {
                        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/_Request[probe2]'}}},
                        'required': True,
                    },
                    'responses': {
                        '200': {
                            'content': {
                                'application/json': {'schema': {'$ref': '#/components/schemas/_Response[probe2]'}},
                            },
                            'description': 'Successful Response',
                        }
                    },
                    'summary': 'Probe2',
                },
            },
        },
    })
