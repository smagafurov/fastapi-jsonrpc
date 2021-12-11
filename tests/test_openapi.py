import pytest
from fastapi import Body
from typing import List


def test_basic(ep, app, app_client):
    @ep.method()
    def probe(
        data: List[str] = Body(..., example=['111', '222']),
        amount: int = Body(..., gt=5, example=10),
    ) -> List[int]:
        del data, amount
        return [1, 2, 3]

    app.bind_entrypoint(ep)

    resp = app_client.get('/openapi.json')
    assert resp.json() == {
        'components': {
            'schemas': {
                'InternalError': {
                    'properties': {
                        'code': {
                            'const': -32603,
                            'example': -32603,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'message': {
                            'const': 'Internal error',
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
                            'const': -32602,
                            'example': -32602,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'data': {
                            '$ref': '#/components/schemas/_ErrorData__Error_',
                        },
                        'message': {
                            'const': 'Invalid params',
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
                            'const': -32600,
                            'example': -32600,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'data': {
                            '$ref': '#/components/schemas/_ErrorData__Error_',
                        },
                        'message': {
                            'const': 'Invalid Request',
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
                            'const': -32601,
                            'example': -32601,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'message': {
                            'const': 'Method not found',
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
                            'const': -32700,
                            'example': -32700,
                            'title': 'Code',
                            'type': 'integer',
                        },
                        'message': {
                            'const': 'Parse error',
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
                            'type': 'object',
                        },
                        'loc': {
                            'items': {
                                'type': 'string',
                            },
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
                '_ErrorData__Error_': {
                    'properties': {
                        'errors': {
                            'items': {
                                '$ref': '#/components/schemas/_Error',
                            },
                            'title': 'Errors',
                            'type': 'array',
                        },
                    },
                    'title': '_ErrorData[_Error]',
                    'type': 'object',
                },
                '_ErrorResponse_InternalError_': {
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[InternalError]',
                    'type': 'object',
                },
                '_ErrorResponse_InvalidParams_': {
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[InvalidParams]',
                    'type': 'object',
                },
                '_ErrorResponse_InvalidRequest_': {
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[InvalidRequest]',
                    'type': 'object',
                },
                '_ErrorResponse_MethodNotFound_': {
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[MethodNotFound]',
                    'type': 'object',
                },
                '_ErrorResponse_ParseError_': {
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                    },
                    'required': ['error'],
                    'title': '_ErrorResponse[ParseError]',
                    'type': 'object',
                },
                '_Params_probe_': {
                    'properties': {
                        'amount': {
                            'example': 10,
                            'exclusiveMinimum': 5.0,
                            'title': 'Amount',
                            'type': 'integer',
                        },
                        'data': {
                            'example': ['111', '222'],
                            'items': {
                                'type': 'string',
                            },
                            'title': 'Data',
                            'type': 'array',
                        },
                    },
                    'required': ['data', 'amount'],
                    'title': '_Params[probe]',
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
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
                    'required': ['method', 'params'],
                    'title': '_Request',
                    'type': 'object',
                },
                '_Request_probe_': {
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                        'method': {
                            'const': 'probe',
                            'example': 'probe',
                            'title': 'Method',
                            'type': 'string',
                        },
                        'params': {
                            '$ref': '#/components/schemas/_Params_probe_',
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                        'result': {
                            'title': 'Result',
                            'type': 'object',
                        },
                    },
                    'required': ['result'],
                    'title': '_Response',
                    'type': 'object',
                },
                '_Response_probe_': {
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
                            'example': '2.0',
                            'title': 'Jsonrpc',
                            'type': 'string',
                        },
                        'result': {
                            'items': {
                                'type': 'integer',
                            },
                            'title': 'Result',
                            'type': 'array',
                        },
                    },
                    'required': ['result'],
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
                        '200 ': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse_InvalidParams_',
                                    },
                                },
                            },
                            'description': '[-32602] Invalid params\n\nInvalid method parameter(s)',
                        },
                        '200  ': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse_MethodNotFound_',
                                    },
                                },
                            },
                            'description': '[-32601] Method not found\n\nThe method does not exist / is not available',
                        },
                        '200   ': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse_ParseError_',
                                    },
                                },
                            },
                            'description': '[-32700] Parse error\n\nInvalid JSON was received by the server',
                        },
                        '200    ': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse_InvalidRequest_',
                                    },
                                },
                            },
                            'description': '[-32600] Invalid Request\n\nThe JSON sent is not a valid Request object',
                        },
                        '200     ': {
                            'content': {
                                'application/json': {
                                    'schema': {
                                        '$ref': '#/components/schemas/_ErrorResponse_InternalError_',
                                    },
                                },
                            },
                            'description': '[-32603] Internal error\n\nInternal JSON-RPC error',
                        },
                    },
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
                                    '$ref': '#/components/schemas/_Request_probe_',
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
                                        '$ref': '#/components/schemas/_Response_probe_',
                                    },
                                },
                            },
                            'description': 'Successful Response',
                        },
                    },
                    'summary': 'Probe',
                },
            },
        },
    }


@pytest.fixture
def api_package(pytester):
    """Create package with structure
        api \
            mobile.py
            web.py

    mobile.py and web.py has similar content except entrypoint path
    """

    # Re-use our infrastructure layer
    pytester.copy_example('tests/conftest.py')

    # Create api/web.py and api/mobile.py files with same methods
    entrypoint_tpl = """
from fastapi import Body
from typing import List


import fastapi_jsonrpc as jsonrpc

api_v1 = jsonrpc.Entrypoint(
    '{ep_path}',
)

@api_v1.method()
def probe(
    data: List[str] = Body(..., example=['111', '222']),
    amount: int = Body(..., gt=5, example=10),
) -> List[int]:
    return [1, 2, 3]
"""

    api_dir = pytester.mkpydir('api')
    mobile_py = api_dir.joinpath('mobile.py')
    mobile_py.write_text(
        entrypoint_tpl.format(ep_path='/api/v1/mobile/jsonrpc'),
    )

    web_py = api_dir.joinpath('web.py')
    web_py.write_text(
        entrypoint_tpl.format(ep_path='/api/v1/web/jsonrpc'),
    )
    return api_dir


def test_component_name_isolated_by_their_path(pytester, api_package):
    """Test we can mix methods with same names in one openapi.json schema
    """

    pytester.makepyfile('''
import pytest
import fastapi_jsonrpc as jsonrpc


# override conftest.py `app` fixture
@pytest.fixture
def app():
    from api.web import api_v1 as api_v1_web
    from api.mobile import api_v1 as api_v1_mobile

    app = jsonrpc.API()
    app.bind_entrypoint(api_v1_web)
    app.bind_entrypoint(api_v1_mobile)
    return app


def test_no_collide(app_client):
    resp = app_client.get('/openapi.json')
    schemas = resp.json()['components']['schemas']

    for component_name in (
        'api__mobile___Params[probe]',
        'api__mobile___Request[probe]',
        'api__mobile___Response[probe]',
        'api__web___Params[probe]',
        'api__web___Request[probe]',
        'api__web___Response[probe]',
    ):
        assert component_name in schemas  
''')

    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=1)
