import sys

import pytest
from starlette.testclient import TestClient

import fastapi_jsonrpc as jsonrpc
from fastapi import Body
from typing import List


def test_basic(ep, app, app_client, openapi_compatible):
    # noinspection PyUnusedLocal
    @ep.method()
    def probe(
        data: List[str] = Body(..., examples=['111', '222']),
        amount: int = Body(..., gt=5, examples=[10]),
    ) -> List[int]:
        del data, amount
        return [1, 2, 3]

    app.bind_entrypoint(ep)

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
                '_Params[probe]': {
                    'properties': {
                        'amount': {
                            'examples': [10],
                            'exclusiveMinimum': 5.0,
                            'title': 'Amount',
                            'type': 'integer',
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
        },
    })


@pytest.fixture(params=['uniq-sig', 'same-sig'])
def api_package(request, pytester):
    """Create package with structure
        api \
            mobile.py
            web.py

    mobile.py and web.py has similar content except entrypoint path
    """

    # Re-use our infrastructure layer
    try:
        pytester.copy_example('tests/conftest.py')
    except LookupError:
        pytester.copy_example('conftest.py')

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
    {unique_param_name}: List[str] = Body(..., examples=['111', '222']),
    amount: int = Body(..., gt=5, examples=[10]),
) -> List[int]:
    return [1, 2, 3]
"""

    if request.param == 'uniq-sig':
        mobile_param_name = 'mobile_data'
        web_param_name = 'web_data'
    else:
        assert request.param == 'same-sig'
        mobile_param_name = web_param_name = 'data'

    api_dir = pytester.mkpydir('api')
    mobile_py = api_dir.joinpath('mobile.py')
    mobile_py.write_text(
        entrypoint_tpl.format(
            ep_path='/api/v1/mobile/jsonrpc',
            unique_param_name=mobile_param_name,
        ),
    )

    web_py = api_dir.joinpath('web.py')
    web_py.write_text(
        entrypoint_tpl.format(
            ep_path='/api/v1/web/jsonrpc',
            unique_param_name=web_param_name,
        ),
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
    resp_json = resp.json()

    paths = resp_json['paths']
    schemas = resp_json['components']['schemas']

    for path in (
        '/api/v1/mobile/jsonrpc/probe',
        '/api/v1/web/jsonrpc/probe',
    ):
        assert path in paths

    # Response model the same and deduplicated
    assert '_Response[probe]' in schemas

    if '_Params[probe]' not in schemas:
        for component_name in (
            'api__mobile___Params[probe]',
            'api__mobile___Request[probe]',
            'api__web___Params[probe]',
            'api__web___Request[probe]',
        ):
            assert component_name in schemas
''')

    # force reload module to drop component cache
    # it's more efficient than use pytest.runpytest_subprocess()
    sys.modules.pop('fastapi_jsonrpc')

    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=1)


def test_entrypoint_tags__append_to_method_tags(app, app_client):
    tagged_api = jsonrpc.Entrypoint('/tagged-entrypoint', tags=['jsonrpc'])

    @tagged_api.method()
    async def not_tagged_method(data: dict) -> dict:
        pass

    @tagged_api.method(tags=['method-tag'])
    async def tagged_method(data: dict) -> dict:
        pass

    app.bind_entrypoint(tagged_api)

    resp = app_client.get('/openapi.json')
    resp_json = resp.json()

    assert resp_json['paths']['/tagged-entrypoint']['post']['tags'] == ['jsonrpc']
    assert resp_json['paths']['/tagged-entrypoint/not_tagged_method']['post']['tags'] == ['jsonrpc']
    assert resp_json['paths']['/tagged-entrypoint/tagged_method']['post']['tags'] == ['jsonrpc', 'method-tag']


@pytest.mark.parametrize('fastapi_jsonrpc_components_fine_names', [True, False])
def test_no_entrypoints__ok(fastapi_jsonrpc_components_fine_names):
    app = jsonrpc.API(fastapi_jsonrpc_components_fine_names=fastapi_jsonrpc_components_fine_names)
    app_client = TestClient(app)
    resp = app_client.get('/openapi.json')
    resp.raise_for_status()
    assert resp.status_code == 200