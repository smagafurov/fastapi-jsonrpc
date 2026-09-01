from typing import Dict, List, Optional

import copy

import pytest
from starlette.testclient import TestClient

import fastapi_jsonrpc as jsonrpc
from fastapi import Body
from pydantic import BaseModel, Field, ConfigDict


def test_basic(ep, app, app_client):
    @ep.method()
    def probe(
        data: List[str] = Body(..., examples=['111', '222']),
        amount: int = Body(..., gt=5, examples=[10]),
    ) -> List[int]:
        del data, amount
        return [1, 2, 3]

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')

    assert resp.json()['methods'] == [
        {
            'name': 'probe',
            'params': [
                {
                    'name': 'data',
                    'schema': {
                        'title': 'Data',
                        'examples': [
                            '111',
                            '222'
                        ],
                        'type': 'array',
                        'items': {
                            'type': 'string'
                        }
                    },
                    'required': True
                },
                {
                    'name': 'amount',
                    'schema': {
                        'title': 'Amount',
                        'exclusiveMinimum': 5,
                        'examples': [10],
                        'type': 'integer'
                    },
                    'required': True
                }
            ],
            'result': {
                'name': 'probe_Result',
                'schema': {
                    'title': 'Result',
                    'type': 'array',
                    'items': {
                        'type': 'integer'
                    }
                }
            },
            'tags': [],
            'errors': [],
            'servers': [
                {
                    'name': '/api/v1/jsonrpc',
                    'url': '/api/v1/jsonrpc',
                },
            ],
        }
    ]


def test_info_block(app, app_client):
    app.title = 'Test App'
    app.version = '1.2.3'
    app.servers = [{'url': 'https://test.dev'}]

    resp = app_client.get('/openrpc.json')

    assert resp.json() == {
        'openrpc': '1.2.6',
        'info': {
            'version': app.version,
            'title': app.title,
        },
        'servers': [{'name': 'https://test.dev', 'url': 'https://test.dev'}],
        'methods': [],
        'components': {
            'schemas': {},
            'errors': {},
        }
    }


def test_component_schemas(ep, app, app_client):
    class Input(BaseModel):
        x: int = Field(
            ...,
            title='x',
            description='X field',
            gt=1,
            lt=10,
            multiple_of=3,
        )
        y: Optional[str] = Field(
            None,
            alias='Y',
            min_length=1,
            max_length=5,
            pattern=r'^[a-z]{4}$',
        )
        model_config = ConfigDict(extra='forbid')

    class Output(BaseModel):
        result: List[int] = Field(
            ...,
            min_length=1,
            max_length=10,
        )

    @ep.method()
    def my_method(inp: Input) -> Output:
        return Output(result=[inp.x])

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['params'] == [
        {
            'name': 'inp',
            'schema': {
                '$ref': '#/components/schemas/Input'
            },
            'required': True
        }
    ]
    assert schema['methods'][0]['result'] == {
        'name': 'my_method_Result',
        'schema': {
            '$ref': '#/components/schemas/Output'
        }
    }

    assert schema['components']['schemas'] == {
        'Input': {
            'title': 'Input',
            'type': 'object',
            'properties': {
                'x': {
                    'title': 'x',
                    'description': 'X field',
                    'exclusiveMinimum': 1,
                    'exclusiveMaximum': 10,
                    'multipleOf': 3,
                    'type': 'integer'
                },
                'Y': {
                    'anyOf': [
                        {
                            'maxLength': 5,
                            'minLength': 1,
                            'pattern': '^[a-z]{4}$',
                            'type': 'string'
                        },
                        {'type': 'null'}
                    ],
                    'default': None,
                    'title': 'Y'
                }
            },
            'required': ['x'],
            'additionalProperties': False
        },
        'Output': {
            'title': 'Output',
            'type': 'object',
            'properties': {
                'result': {
                    'title': 'Result',
                    'minItems': 1,
                    'maxItems': 10,
                    'type': 'array',
                    'items': {
                        'type': 'integer'
                    }
                }
            },
            'required': ['result']
        }
    }


def test_tags(ep, app, app_client):
    @ep.method(tags=['tag1', 'tag2'])
    def my_method__with_tags() -> None:
        return None

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['tags'] == [
        {'name': 'tag1'},
        {'name': 'tag2'},
    ]


def test_errors(ep, app, app_client):
    class MyError(jsonrpc.BaseError):
        CODE = 5000
        MESSAGE = 'My error'

        class DataModel(BaseModel):
            details: str

    @ep.method(errors=[MyError])
    def my_method__with_errors() -> None:
        return None

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['errors'] == [
        {'$ref': '#/components/errors/5000'},
    ]
    assert schema['components']['errors']['5000'] == {
        'code': 5000,
        'message': 'My error',
        'data': {
            'title': 'MyError.Data',
            'type': 'object',
            'properties': {
                'details': {
                    'title': 'Details',
                    'type': 'string'
                }
            },
            'required': ['details']
        }
    }


def test_errors_merging(ep, app, app_client):
    class FirstError(jsonrpc.BaseError):
        CODE = 5000
        MESSAGE = 'My error'

        class DataModel(BaseModel):
            x: str

    class SecondError(jsonrpc.BaseError):
        CODE = 5000
        MESSAGE = 'My error'

        class DataModel(BaseModel):
            y: int

    @ep.method(errors=[FirstError, SecondError])
    def my_method__with_mergeable_errors() -> None:
        return None

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['errors'] == [{'$ref': '#/components/errors/5000'}]
    assert schema['components']['errors']['5000'] == {
        'code': 5000,
        'message': 'My error',
        'data': {
            'title': 'ERROR_5000',
            'anyOf': [
                # Module prefix removed when no collision detected
                {'$ref': '#/components/schemas/FirstError.Data'},
                {'$ref': '#/components/schemas/SecondError.Data'},
            ],
        }
    }
    assert schema['components']['schemas']['FirstError.Data'] == {
        'title': 'FirstError.Data',
        'type': 'object',
        'properties': {
            'x': {'type': 'string', 'title': 'X'},
        },
        'required': ['x']
    }
    assert schema['components']['schemas']['SecondError.Data'] == {
        'title': 'SecondError.Data',
        'type': 'object',
        'properties': {
            'y': {'type': 'integer', 'title': 'Y'},
        },
        'required': ['y']
    }


def test_type_hints(ep, app, app_client):
    Input = List[str]
    Output = Dict[str, List[List[float]]]

    @ep.method()
    def my_method__with_typehints(arg: Input) -> Output:
        return {}

    app.bind_entrypoint(ep)

    resp = app_client.get('/openrpc.json')
    schema = resp.json()

    assert len(schema['methods']) == 1
    assert schema['methods'][0]['params' ] == [
        {
            'name': 'arg',
            'schema': {
                'title': 'Arg',
                'type': 'array',
                'items': {
                    'type': 'string'
                }
            },
            'required': True
        }
    ]
    assert schema['methods'][0]['result'] == {
        'name': 'my_method__with_typehints_Result',
        'schema': {
            'title': 'Result',
            'type': 'object',
            'additionalProperties': {
                'type': 'array',
                'items': {
                    'type': 'array',
                    'items': {
                        'type': 'number'
                    }
                }
            }
        }
    }


@pytest.mark.parametrize('fastapi_jsonrpc_components_fine_names', [True, False])
def test_no_entrypoints__ok(fastapi_jsonrpc_components_fine_names):
    app = jsonrpc.API(fastapi_jsonrpc_components_fine_names=fastapi_jsonrpc_components_fine_names)
    app_client = TestClient(app)
    resp = app_client.get('/openrpc.json')
    resp.raise_for_status()
    assert resp.status_code == 200


def _openrpc_with_server(server):
    app = jsonrpc.API(servers=[server])
    ep = jsonrpc.Entrypoint('/rpc')

    @ep.method()
    def server_probe() -> int:
        return 1

    app.bind_entrypoint(ep)
    return app.get_openrpc()


def test_method_server_preserves_configured_server():
    server = {
        'name': 'production',
        'url': 'https://{region}.example.test/base/',
        'summary': 'Production',
        'description': 'Primary endpoint',
        'variables': {
            'region': {
                'default': 'eu',
                'enum': ['eu', 'us'],
                'description': 'Deployment region',
                'x-source': 'config',
            },
        },
        'x-owner': {'team': 'payments'},
    }
    original = copy.deepcopy(server)

    schema = _openrpc_with_server(server)

    assert schema['servers'] == [server]
    assert schema['methods'][0]['servers'] == [{
        **server,
        'url': 'https://{region}.example.test/base/rpc',
    }]
    assert server == original
    assert schema['servers'][0] is not server
    assert schema['servers'][0]['variables'] is not server['variables']


def test_openrpc_server_name_defaults_to_url():
    schema = _openrpc_with_server({
        'url': 'https://example.test',
        'description': 'Description is not a canonical name',
    })

    assert schema['servers'][0]['name'] == 'https://example.test'
    assert schema['methods'][0]['servers'][0]['name'] == 'https://example.test'


@pytest.mark.parametrize(
    ('base_url', 'expected'),
    [
        ('https://api.test', 'https://api.test/rpc'),
        ('https://api.test/', 'https://api.test/rpc'),
        ('https://api.test/base/', 'https://api.test/base/rpc'),
        ('https://api.test/base?q=1#docs', 'https://api.test/base/rpc?q=1#docs'),
        ('//api.test/base', '//api.test/base/rpc'),
        ('/base/', '/base/rpc'),
        ('base/', 'base/rpc'),
        ('https://{region}.test/{base}', 'https://{region}.test/{base}/rpc'),
        ('https://api.test/a//b/./c%2Fd', 'https://api.test/a//b/./c%2Fd/rpc'),
    ],
)
def test_method_server_url_composition(base_url, expected):
    schema = _openrpc_with_server({'name': 'server', 'url': base_url})

    assert schema['methods'][0]['servers'][0]['url'] == expected


@pytest.mark.parametrize(
    ('server', 'error', 'match'),
    [
        ('not-a-dict', TypeError, 'server 0'),
        ({}, ValueError, "server 0.*url"),
        ({'url': 123}, TypeError, "server 0.*url"),
        ({'url': '   '}, ValueError, "server 0.*url"),
        ({'url': 'https://example.test', 'name': 123}, TypeError, "server 0.*name"),
        ({'url': 'https://example.test', 'name': '   '}, ValueError, "server 0.*name"),
        ({'url': 'https://example.test', 'unknown': True}, ValueError, "server 0.*unknown"),
        ({'url': 'https://example.test', 'variables': []}, TypeError, "server 0.*variables"),
        ({
            'url': 'https://{region}.example.test',
            'variables': {'region': {}},
        }, ValueError, "server 0.*region.*default"),
        ({'url': 'mailto:rpc@example.test'}, ValueError, "server 0.*url"),
        ({'url': 'https:/broken'}, ValueError, "server 0.*url"),
    ],
)
def test_invalid_openrpc_server_fails_fast(server, error, match):
    app = jsonrpc.API(servers=[server])

    with pytest.raises(error, match=match):
        app.get_openrpc()


def test_distinct_methods_report_own_entrypoint():
    app = jsonrpc.API()
    v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')
    v2 = jsonrpc.Entrypoint('/api/v2/jsonrpc')

    @v1.method()
    def distinct_legacy_probe() -> int:
        return 1

    @v2.method()
    def distinct_current_probe() -> int:
        return 2

    app.bind_entrypoint(v1)
    app.bind_entrypoint(v2)
    schema = app.get_openrpc()

    servers_by_method = {method['name']: method['servers'] for method in schema['methods']}
    assert servers_by_method == {
        'distinct_legacy_probe': [{'name': '/api/v1/jsonrpc', 'url': '/api/v1/jsonrpc'}],
        'distinct_current_probe': [{'name': '/api/v2/jsonrpc', 'url': '/api/v2/jsonrpc'}],
    }


def test_compatible_duplicate_method_merges_servers():
    app = jsonrpc.API()
    v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')
    v2 = jsonrpc.Entrypoint('/api/v2/jsonrpc')

    def merged_probe(value: int = Body(...)) -> int:
        return value

    v1.add_method_route(merged_probe)
    v2.add_method_route(merged_probe)
    app.bind_entrypoint(v1)
    app.bind_entrypoint(v2)
    schema = app.get_openrpc()

    assert [method['name'] for method in schema['methods']] == ['merged_probe']
    assert schema['methods'][0]['servers'] == [
        {'name': '/api/v1/jsonrpc', 'url': '/api/v1/jsonrpc'},
        {'name': '/api/v2/jsonrpc', 'url': '/api/v2/jsonrpc'},
    ]


def test_duplicate_method_does_not_duplicate_identical_server():
    app = jsonrpc.API()
    first = jsonrpc.Entrypoint('/rpc')
    second = jsonrpc.Entrypoint('/rpc')

    def same_endpoint_probe() -> int:
        return 1

    first.add_method_route(same_endpoint_probe)
    second.add_method_route(same_endpoint_probe)
    app.bind_entrypoint(first)
    app.bind_entrypoint(second)
    schema = app.get_openrpc()

    assert schema['methods'][0]['servers'] == [{'name': '/rpc', 'url': '/rpc'}]


def test_incompatible_duplicate_method_fails_fast():
    app = jsonrpc.API()
    v1 = jsonrpc.Entrypoint('/api/v1/jsonrpc')
    v2 = jsonrpc.Entrypoint('/api/v2/jsonrpc')

    # Same wire method name declared by different modules: component names stay
    # distinct, so the clash only surfaces in the OpenRPC methods array
    def probe_v1(value: int = Body(...)) -> int:
        return value

    def probe_v2(value: str = Body(...)) -> str:
        return value

    probe_v1.__module__ = 'api.v1'
    probe_v2.__module__ = 'api.v2'
    v1.add_method_route(probe_v1, name='incompatible_probe')
    v2.add_method_route(probe_v2, name='incompatible_probe')
    app.bind_entrypoint(v1)
    app.bind_entrypoint(v2)

    with pytest.raises(RuntimeError, match="'incompatible_probe'.*/api/v1/jsonrpc.*/api/v2/jsonrpc"):
        app.get_openrpc()


def _openrpc_app(**api_kwargs):
    app = jsonrpc.API(**api_kwargs)
    ep = jsonrpc.Entrypoint('/rpc')

    @ep.method()
    def root_path_probe() -> int:
        return 1

    app.bind_entrypoint(ep)
    return app


def test_root_path_becomes_first_openrpc_server():
    schema = _openrpc_app(root_path='/proxy/').get_openrpc()

    assert schema['servers'] == [{'name': '/proxy', 'url': '/proxy'}]
    assert schema['methods'][0]['servers'] == [{'name': '/proxy', 'url': '/proxy/rpc'}]


def test_root_path_precedes_configured_server():
    schema = _openrpc_app(
        root_path='/proxy',
        servers=[{'url': 'https://api.test/base'}],
    ).get_openrpc()

    assert schema['servers'] == [
        {'name': '/proxy', 'url': '/proxy'},
        {'name': 'https://api.test/base', 'url': 'https://api.test/base'},
    ]
    assert schema['methods'][0]['servers'] == [
        {'name': '/proxy', 'url': '/proxy/rpc'},
        {'name': 'https://api.test/base', 'url': 'https://api.test/base/rpc'},
    ]


def test_configured_server_matching_root_path_is_not_duplicated():
    schema = _openrpc_app(
        root_path='/proxy',
        servers=[{'name': 'behind-proxy', 'url': '/proxy', 'description': 'Terminated by nginx'}],
    ).get_openrpc()

    assert schema['servers'] == [
        {'name': 'behind-proxy', 'url': '/proxy', 'description': 'Terminated by nginx'},
    ]
    assert schema['methods'][0]['servers'] == [
        {'name': 'behind-proxy', 'url': '/proxy/rpc', 'description': 'Terminated by nginx'},
    ]


def test_disabled_root_path_in_servers_keeps_configured_servers():
    schema = _openrpc_app(
        root_path='/proxy',
        root_path_in_servers=False,
        servers=[{'url': 'https://api.test'}],
    ).get_openrpc()

    assert schema['servers'] == [{'name': 'https://api.test', 'url': 'https://api.test'}]
    assert schema['methods'][0]['servers'] == [
        {'name': 'https://api.test', 'url': 'https://api.test/rpc'},
    ]


def test_disabled_root_path_in_servers_without_configured_servers():
    schema = _openrpc_app(root_path='/proxy', root_path_in_servers=False).get_openrpc()

    assert schema['servers'] == []
    assert schema['methods'][0]['servers'] == [{'name': '/rpc', 'url': '/rpc'}]


def test_request_root_path_does_not_pollute_cached_schema():
    app = _openrpc_app()

    proxied = TestClient(app, root_path='/proxy').get('/openrpc.json').json()
    direct = TestClient(app).get('/openrpc.json').json()

    assert proxied['servers'] == [{'name': '/proxy', 'url': '/proxy'}]
    assert proxied['methods'][0]['servers'] == [{'name': '/proxy', 'url': '/proxy/rpc'}]
    assert direct['servers'] == []
    assert direct['methods'][0]['servers'] == [{'name': '/rpc', 'url': '/rpc'}]
    assert app.openrpc_schema['servers'] == []
    assert proxied['components'] == direct['components']


def test_request_root_path_matching_configured_root_path_uses_cache():
    app = _openrpc_app(root_path='/proxy')

    schema = TestClient(app, root_path='/proxy').get('/openrpc.json').json()

    assert schema == app.openrpc_schema
