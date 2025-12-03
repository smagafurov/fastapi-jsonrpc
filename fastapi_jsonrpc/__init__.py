import asyncio
import contextvars  # noqa
import copy
import inspect
import logging
import typing
from collections import ChainMap, defaultdict
from collections.abc import Coroutine
from contextlib import AsyncExitStack, AbstractAsyncContextManager, asynccontextmanager, contextmanager
from functools import cached_property
from types import FunctionType
from typing import List, Tuple, Union, Any, Callable, Type, Optional, Dict, Sequence, Literal

import pydantic
from fastapi.dependencies.utils import _should_embed_body_fields  # noqa
from fastapi.openapi.constants import REF_PREFIX


from fastapi._compat import ModelField, Undefined  # noqa
from fastapi.dependencies.models import Dependant
from fastapi.encoders import jsonable_encoder
from fastapi.params import Depends
from fastapi import FastAPI, Body
from fastapi.dependencies.utils import solve_dependencies, get_dependant, get_flat_dependant, \
    get_parameterless_sub_dependant
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.routing import APIRoute, APIRouter, request_response, serialize_response
from pydantic import BaseModel, ValidationError, StrictStr, Field, create_model, ConfigDict
from starlette.background import BackgroundTasks
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Match, compile_path
import fastapi.params
import aiojobs
import warnings

logger = logging.getLogger(__name__)

try:
    import sentry_sdk
    import sentry_sdk.tracing
    from sentry_sdk.utils import transaction_from_function as sentry_transaction_from_function
except ImportError:
    sentry_sdk = None  # type: ignore
    sentry_transaction_from_function = None  # type: ignore

try:
    from fastapi._compat import _normalize_errors  # noqa
except ImportError:
    def _normalize_errors(errors: Sequence[Any]) -> Sequence[Any]:  # type: ignore
        return errors

if hasattr(sentry_sdk, 'new_scope'):
    # sentry_sdk 2.x
    sentry_new_scope = sentry_sdk.new_scope

    def get_sentry_integration():
        return sentry_sdk.get_client().get_integration(
            "FastApiJsonRPCIntegration"
        )
else:
    # sentry_sdk 1.x
    @contextmanager
    def sentry_new_scope():
        hub = sentry_sdk.Hub.current
        with sentry_sdk.Hub(hub) as hub:
            with hub.configure_scope() as scope:
                yield scope

    get_sentry_integration = lambda : None


class Params(fastapi.params.Body):
    def __init__(
        self,
        default: Any,
        *,
        media_type: str = 'application/json',
        title: Optional[str] = None,
        description: Optional[str] = None,
        gt: Optional[float] = None,
        ge: Optional[float] = None,
        lt: Optional[float] = None,
        le: Optional[float] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        regex: Optional[str] = None,
        example: Any = Undefined,
        examples: Optional[List[Any]] = None,
        **extra: Any,
    ):
        super().__init__(
            default,
            embed=False,
            media_type=media_type,
            alias='params',
            title=title,
            description=description,
            gt=gt,
            ge=ge,
            lt=lt,
            le=le,
            min_length=min_length,
            max_length=max_length,
            regex=regex,
            example=example,
            examples=examples,
            **extra,
        )


components: Dict[Tuple[str, str], Type[BaseModel]] = {}


def component_name(name: str, module: Optional[str] = None) -> Callable[[Type[BaseModel]], Type[BaseModel]]:
    """OpenAPI components must be unique by name"""
    def decorator(obj):
        assert issubclass(obj, BaseModel)
        opts: dict[str, Any] = {
            '__base__': tuple(obj.mro()[1:]),  # remove self from __base__
            '__module__': module or obj.__module__,
            **{
                field_name: (field.annotation, field)
                for field_name, field in obj.model_fields.items()
            },
        }
        if obj.model_config:
            opts.pop('__base__')
            opts['__config__'] = obj.model_config

        # re-create model to ensure given name will be applied to json schema
        # since Pydantic 2.0 model json schema generated at class creation process

        obj = create_model(name, **opts)

        if module is not None:
            obj.__module__ = module  # see: pydantic._internal._core_utils.get_type_ref
        key = (obj.__name__, obj.__module__)
        if key in components:
            lhs = components[key].model_json_schema()
            rhs = obj.model_json_schema()
            if lhs != rhs:
                raise RuntimeError(
                    f"Different models with the same name detected: {lhs!r} != {rhs}"
                )
            return components[key]
        components[key] = obj
        return obj

    return decorator


def is_scope_child(owner: Type[BaseModel], child: Type[BaseModel]) -> bool:
    return (
        (
            owner.__dict__.get(child.__name__) is child or
            owner.__dict__.get(child.__name__) is Optional[child]
        ) and
        child.__qualname__ == owner.__qualname__ + '.' + child.__name__ and
        child.__module__ == owner.__module__
    )


def rename_if_scope_child_component(owner: type, child, postfix: str):
    if is_scope_child(owner, child):
        child = component_name(f'{owner.__name__}.{postfix}', owner.__module__)(child)
    return child


class BaseError(Exception):
    CODE: Optional[int] = None
    MESSAGE: Optional[str] = None

    ErrorModel: Optional[Type[BaseModel]] = None
    DataModel: Optional[Type[BaseModel]] = None

    data_required: bool = False
    errors_required: bool = False

    error_model: Optional[Type[BaseModel]] = None
    data_model: Optional[Type[BaseModel]] = None
    resp_model: Optional[Type[BaseModel]] = None

    _component_name: Optional[str] = None

    def __init__(self, data=None):
        if data is None:
            data = {}

        raw_data = data
        data = self.validate_data(raw_data)

        Exception.__init__(self, self.CODE, self.MESSAGE)

        self.data = data
        self.raw_data = raw_data

    @classmethod
    def validate_data(cls, data):
        data_model = cls.get_data_model()
        if data_model:
            data = data_model.model_validate(data)
        return data

    def __str__(self):
        s = f"[{self.CODE}] {self.MESSAGE}"
        if self.data:
            s += f": {self.data!r}"
        return s

    def get_resp_data(self):
        return self.raw_data

    @classmethod
    def get_description(cls):
        s = cls.get_default_description()
        if cls.__doc__:
            s += "\n\n" + cls.__doc__
        return s

    @classmethod
    def get_default_description(cls):
        return f"[{cls.CODE}] {cls.MESSAGE}"

    def get_resp(self) -> dict:
        error = {
            'code': self.CODE,
            'message': self.MESSAGE,
        }

        resp_data = self.get_resp_data()
        if resp_data:
            error['data'] = resp_data

        resp = {
            'jsonrpc': '2.0',
            'error': error,
            'id': None,
        }

        return jsonable_encoder(resp)

    @classmethod
    def get_error_model(cls):
        if cls.__dict__.get('error_model') is not None:
            return cls.error_model
        cls.error_model = cls.build_error_model()
        return cls.error_model

    @classmethod
    def build_error_model(cls):
        if cls.ErrorModel is not None:
            return rename_if_scope_child_component(cls, cls.ErrorModel, 'Error')
        return None

    @classmethod
    def get_data_model(cls):
        if cls.__dict__.get('data_model') is not None:
            return cls.data_model
        cls.data_model = cls.build_data_model()
        return cls.data_model

    @classmethod
    def build_data_model(cls):
        if cls.DataModel is not None:
            return rename_if_scope_child_component(cls, cls.DataModel, 'Data')

        error_model = cls.get_error_model()
        if error_model is None:
            return None

        default_value = ...
        errors_annotation = List[error_model]
        if not cls.errors_required:
            errors_annotation = Optional[errors_annotation]
            default_value = None

        field_definitions = {
            'errors': (errors_annotation, default_value)
        }

        name = f'_ErrorData[{error_model.__name__}]'
        _ErrorData = create_model(
            name,
            __base__=(BaseModel,),
            __module__=error_model.__module__,
            **field_definitions,
        )
        _ErrorData = component_name(name, error_model.__module__)(_ErrorData)

        return _ErrorData

    @classmethod
    def get_resp_model(cls):
        if cls.__dict__.get('resp_model') is not None:
            return cls.resp_model
        cls.resp_model = cls.build_resp_model()
        return cls.resp_model

    @classmethod
    def build_resp_model(cls) -> Type[BaseModel]:
        fields_definition = {
            'code': (int, Field(cls.CODE, frozen=True, json_schema_extra={'example': cls.CODE})),
            'message': (str, Field(cls.MESSAGE, frozen=True, json_schema_extra={'example': cls.MESSAGE})),
        }

        data_model = cls.get_data_model()
        if data_model is not None:
            data_model_default_value = ...
            if not cls.data_required:
                data_model = Optional[data_model]
                data_model_default_value = None

            fields_definition['data'] = (data_model, data_model_default_value)

        name = cls._component_name or cls.__name__

        _JsonRpcErrorModel = create_model(
            name,
            __base__=(BaseModel,),
            __module__=cls.__module__,
            **fields_definition,
        )
        _JsonRpcErrorModel = component_name(name, cls.__module__)(_JsonRpcErrorModel)

        @component_name(f'_ErrorResponse[{name}]', cls.__module__)
        class _ErrorResponseModel(BaseModel):
            jsonrpc: Literal['2.0'] = Field('2.0', json_schema_extra={'example': '2.0'})
            id: Union[StrictStr, int] = Field(None, json_schema_extra={'example': 0})
            error: _JsonRpcErrorModel

            model_config = ConfigDict(extra='forbid')

        return _ErrorResponseModel


@component_name('_Error')
class ErrorModel(BaseModel):
    loc: List[Union[str, int]]
    msg: str
    type: str
    ctx: Optional[Dict[str, Any]] = None


class ParseError(BaseError):
    """Invalid JSON was received by the server"""
    CODE = -32700
    MESSAGE = "Parse error"


class InvalidRequest(BaseError):
    """The JSON sent is not a valid Request object"""
    CODE = -32600
    MESSAGE = "Invalid Request"
    error_model = ErrorModel


class MethodNotFound(BaseError):
    """The method does not exist / is not available"""
    CODE = -32601
    MESSAGE = "Method not found"


class InvalidParams(BaseError):
    """Invalid method parameter(s)"""
    CODE = -32602
    MESSAGE = "Invalid params"
    error_model = ErrorModel


class InternalError(BaseError):
    """Internal JSON-RPC error"""
    CODE = -32603
    MESSAGE = "Internal error"


class NoContent(Exception):
    pass


async def call_sync_async(call, *args, **kwargs):
    is_coroutine = asyncio.iscoroutinefunction(call)
    if is_coroutine:
        return await call(*args, **kwargs)
    else:
        return await run_in_threadpool(call, *args, **kwargs)


def errors_responses(errors: Optional[Sequence[Type[BaseError]]] = None)->Dict[Any, Any]:
    responses: Dict[Any, Any] = {'default': {}}

    if errors:
        # Swagger UI 5.0 and above allow use only int status_codes and in _valid range_
        # generate fake status codes for each error
        for fake_status_code, error_cls in enumerate(errors, start=210):
            responses[fake_status_code] = {
                'model': error_cls.get_resp_model(),
                'description': error_cls.get_description(),
            }

    return responses


@component_name(f'_Request')
class JsonRpcRequest(BaseModel):
    jsonrpc: Literal['2.0'] = Field('2.0', json_schema_extra={'example': '2.0'})
    id: Union[StrictStr, int] = Field(None, json_schema_extra={'example': 0})
    method: StrictStr
    params: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra='forbid')


@component_name(f'_Response')
class JsonRpcResponse(BaseModel):
    jsonrpc: Literal['2.0'] = Field('2.0', json_schema_extra={'example': '2.0'})
    id: Union[StrictStr, int] = Field(None, json_schema_extra={'example': 0})
    result: dict

    model_config = ConfigDict(extra='forbid', json_schema_serialization_defaults_required=True)


def invalid_request_from_validation_error(exc: ValidationError) -> InvalidRequest:
    return InvalidRequest(data={'errors': exc.errors(include_url=False)})


def invalid_params_from_validation_error(exc: typing.Union[ValidationError, RequestValidationError]) -> InvalidParams:
    errors = []

    for err in exc.errors():
        err.pop('url', None)

        if err['loc'][:1] == ('body',):
            err['loc'] = err['loc'][1:]
        else:
            assert err['loc']
            err['loc'] = (f"<{err['loc'][0]}>",) + err['loc'][1:]
        errors.append(err)

    return InvalidParams(data={'errors': errors})


def fix_query_dependencies(dependant: Dependant):
    dependant.body_params.extend(dependant.query_params)
    dependant.query_params = []

    for field in dependant.body_params:
        if not isinstance(field.field_info, Params):
            field.field_info.embed = True

    for sub_dependant in dependant.dependencies:
        fix_query_dependencies(sub_dependant)


def insert_dependencies(target: Dependant, dependencies: Optional[Sequence[Depends]] = None):
    assert target.path
    if not dependencies:
        return
    for depends in dependencies[::-1]:
        target.dependencies.insert(
            0,
            get_parameterless_sub_dependant(depends=depends, path=target.path),
        )


def make_request_model(name: str, module: str, body_params: List[ModelField]) -> Type[BaseModel]:
    whole_params_list = [p for p in body_params if isinstance(p.field_info, Params)]
    if len(whole_params_list):
        if len(whole_params_list) > 1:
            raise RuntimeError(
                f"Only one 'Params' allowed: "
                f"params={whole_params_list}"
            )
        body_params_list = [p for p in body_params if not isinstance(p.field_info, Params)]
        if body_params_list:
            raise RuntimeError(
                f"No other params allowed when 'Params' used: "
                f"params={whole_params_list}, other={body_params_list}"
            )

    if whole_params_list:
        assert whole_params_list[0].alias == 'params'
        params_field = whole_params_list[0]
        params_annotation, params_field_info = params_field.field_info.annotation, params_field.field_info
    else:
        fields = {
            param.name: (param.field_info.annotation, param.field_info)
            for param in body_params
        }
        _JsonRpcRequestParams = create_model(
            f'_Params[{name}]',
            __base__=(BaseModel,),
            __module__=module,
            **fields,
        )
        _JsonRpcRequestParams = component_name(f'_Params[{name}]', module)(_JsonRpcRequestParams)

        params_annotation = _JsonRpcRequestParams
        params_field_info = ...

    _Request = create_model(
        f'_Request[{name}]',
        __config__=ConfigDict(extra='forbid'),
        __module__=module,
        jsonrpc=(Literal['2.0'], Field('2.0', json_schema_extra={'example': '2.0'})),
        id=(Union[StrictStr, int], Field(None, json_schema_extra={'example': 0})),
        method=(StrictStr, Field(name, frozen=True, json_schema_extra={'example': name})),
        params=(params_annotation, params_field_info)
    )
    _Request = component_name(f'_Request[{name}]', module)(_Request)

    return _Request


def make_response_model(name: str, module: str, result_model: Type[BaseModel]) -> Type[BaseModel]:
    @component_name(f'_Response[{name}]', module)
    class _Response(BaseModel):
        jsonrpc: Literal['2.0'] = Field('2.0', json_schema_extra={'example': '2.0'})
        id: Union[StrictStr, int] = Field(None, json_schema_extra={'example': 0})
        result: result_model  # type: ignore[valid-type]

        model_config = ConfigDict(extra='forbid', json_schema_serialization_defaults_required=True)

    return _Response


class JsonRpcContext:
    def __init__(
        self,
        entrypoint: 'Entrypoint',
        raw_request: Any,
        http_request: Request,
        background_tasks: BackgroundTasks,
        http_response: Response,
        json_rpc_request_class: Type[JsonRpcRequest] = JsonRpcRequest,
        method_route: typing.Optional['MethodRoute'] = None,
    ):
        self.entrypoint: Entrypoint = entrypoint
        self.raw_request: Any = raw_request
        self.http_request: Request = http_request
        self.background_tasks: BackgroundTasks = background_tasks
        self.http_response: Response = http_response
        self.request_class: Type[JsonRpcRequest] = json_rpc_request_class
        self.method_route: typing.Optional[MethodRoute] = method_route
        self._raw_response: Optional[dict] = None
        self.exception: Optional[Exception] = None
        self.is_unhandled_exception: bool = False
        self.exit_stack: Optional[AsyncExitStack] = None
        self.jsonrpc_context_token: Optional[contextvars.Token] = None

    def on_raw_response(
        self,
        raw_response: Union[dict, Exception],
    ):
        exception = None
        is_unhandled_exception = False

        if isinstance(raw_response, Exception):
            exception = raw_response
            if isinstance(exception, BaseError):
                raw_response = exception.get_resp()
            elif isinstance(exception, HTTPException):
                raw_response = None
            else:
                raw_response = InternalError().get_resp()
                is_unhandled_exception = True

        if raw_response is not None:
            raw_response.pop('id', None)
            if isinstance(self.raw_request, dict) and 'id' in self.raw_request:
                raw_response['id'] = self.raw_request.get('id')
            elif 'error' in raw_response:
                raw_response['id'] = None

        self._raw_response = raw_response
        self.exception = exception
        self.is_unhandled_exception = is_unhandled_exception

    @property
    def raw_response(self) -> dict:
        return self._raw_response

    @raw_response.setter
    def raw_response(self, value: dict):
        self.on_raw_response(value)

    @cached_property
    def request(self) -> JsonRpcRequest:
        try:
            return self.request_class.model_validate(self.raw_request)
        except ValidationError as exc:
            raise invalid_request_from_validation_error(exc)

    async def __aenter__(self):
        assert self.exit_stack is None
        self.exit_stack = await AsyncExitStack().__aenter__()
        if (
            sentry_sdk is not None
            and get_sentry_integration() is None
        ):
            self.exit_stack.enter_context(self._enter_old_sentry_integration())

        await self.exit_stack.enter_async_context(self._handle_exception(reraise=False))
        self.jsonrpc_context_token = _jsonrpc_context.set(self)
        return self

    async def __aexit__(self, *exc_details):
        assert self.jsonrpc_context_token is not None
        _jsonrpc_context.reset(self.jsonrpc_context_token)
        return await self.exit_stack.__aexit__(*exc_details)

    @asynccontextmanager
    async def _handle_exception(self, reraise=True):
        try:
            yield
        except Exception as exception:
            if exception is not self.exception:
                try:
                    resp = await self.entrypoint.handle_exception(exception)
                except Exception as exc:
                    self.on_raw_response(exc)
                else:
                    self.on_raw_response(resp)
            if self.exception is not None and (reraise or isinstance(self.exception, HTTPException)):
                raise self.exception

        if self.exception is not None and self.is_unhandled_exception:
            logger.exception(str(self.exception), exc_info=self.exception)

    @contextmanager
    def _enter_old_sentry_integration(self):
        warnings.warn(
            "Implicit Sentry integration is deprecated and may be removed in a future major release. "
            "To ensure compatibility, use sentry-sdk 2.* and explicit integration:"
            "`from fastapi_jsonrpc.contrib.sentry import FastApiJsonRPCIntegration`. "
        )
        with sentry_new_scope() as scope:
            # Actually we can use set_transaction_name
            #             scope.set_transaction_name(
            #                 sentry_transaction_from_function(method_route.func),
            #                 source=sentry_sdk.tracing.TRANSACTION_SOURCE_CUSTOM,
            #             )
            # and we need `method_route` instance for that,
            # but method_route is optional and is harder to track it than adding event processor
            scope.clear_breadcrumbs()
            scope.add_event_processor(self._make_sentry_event_processor())
            yield scope

    def _make_sentry_event_processor(self):
        def event_processor(event, _):
            if self.method_route is not None:
                event['transaction'] = sentry_transaction_from_function(self.method_route.func)
                event['transaction_info']['source'] = sentry_sdk.tracing.TRANSACTION_SOURCE_CUSTOM
            return event

        return event_processor

    async def enter_middlewares(self, middlewares: Sequence['JsonRpcMiddleware']):
        for mw in middlewares:
            cm = mw(self)
            if not isinstance(cm, AbstractAsyncContextManager):
                raise RuntimeError("JsonRpcMiddleware(context) must return AsyncContextManager")
            await self.exit_stack.enter_async_context(cm)
            await self.exit_stack.enter_async_context(self._handle_exception())


JsonRpcMiddleware = Callable[[JsonRpcContext], AbstractAsyncContextManager]

_jsonrpc_context = contextvars.ContextVar('_fastapi_jsonrpc__jsonrpc_context')


def get_jsonrpc_context() -> JsonRpcContext:
    return _jsonrpc_context.get()


def get_jsonrpc_request_id() -> Optional[Union[str, int]]:
    return get_jsonrpc_context().raw_request.get('id')


def get_jsonrpc_method() -> Optional[str]:
    return get_jsonrpc_context().raw_request.get('method')


class MethodRoute(APIRoute):
    def __init__(
        self,
        entrypoint: 'Entrypoint',
        path: str,
        func: Union[FunctionType, Coroutine],
        *,
        result_model: Optional[Type[Any]] = None,
        name: Optional[str] = None,
        errors: Optional[List[Type[BaseError]]] = None,
        dependencies: Optional[Sequence[Depends]] = None,
        response_class: Type[Response] = JSONResponse,
        request_class: Type[JsonRpcRequest] = JsonRpcRequest,
        middlewares: Optional[Sequence[JsonRpcMiddleware]] = None,
        **kwargs,
    ):
        name = name or func.__name__
        result_model = result_model or func.__annotations__.get('return')

        _, path_format, _ = compile_path(path)
        func_dependant = get_dependant(path=path_format, call=func)
        insert_dependencies(func_dependant, dependencies)
        insert_dependencies(func_dependant, entrypoint.common_dependencies)
        fix_query_dependencies(func_dependant)
        flat_dependant = get_flat_dependant(func_dependant, skip_repeats=True)

        _Request = make_request_model(name, func.__module__, flat_dependant.body_params)
        _Response = make_response_model(name, func.__module__, result_model)

        # Only needed to generate OpenAPI
        async def endpoint(__request__: _Request):
            del __request__

        endpoint.__name__ = func.__name__
        endpoint.__doc__ = func.__doc__

        responses = errors_responses(errors)

        super().__init__(
            path,
            endpoint,
            methods=['POST'],
            name=name,
            response_class=response_class,
            response_model=_Response,
            responses=responses,
            **kwargs,
        )

        # Add dependencies and other parameters from func_dependant for correct OpenAPI generation
        self.dependant.path_params = func_dependant.path_params
        self.dependant.header_params = func_dependant.header_params
        self.dependant.cookie_params = func_dependant.cookie_params
        self.dependant.dependencies = func_dependant.dependencies
        self.dependant.security_requirements = func_dependant.security_requirements

        self.func = func
        self.flat_dependant = flat_dependant
        self.func_dependant = func_dependant
        self.entrypoint = entrypoint
        self.middlewares = middlewares or []
        self.app = request_response(self.handle_http_request)
        self.request_class = request_class
        self.result_model = result_model
        self.params_model = _Request.model_fields['params'].annotation
        self.errors = errors or []

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return (
            isinstance(other, MethodRoute)
            and self.path == other.path
            and self.func == other.func
        )

    async def parse_body(self, http_request) -> Any:
        try:
            req = await http_request.json()
        except ValueError:
            raise ParseError()
        return req

    async def handle_http_request(self, http_request: Request):
        background_tasks = BackgroundTasks()

        sub_response = Response()
        del sub_response.headers["content-length"]
        sub_response.status_code = None  # type: ignore

        try:
            body = await self.parse_body(http_request)
        except Exception as exc:
            resp = await self.entrypoint.handle_exception_to_resp(exc)
            response = self.response_class(content=resp, background=background_tasks)
        else:
            try:
                resp = await self.handle_body(http_request, background_tasks, sub_response, body)
            except NoContent:
                # no content for successful notifications
                response = Response(media_type='application/json', background=background_tasks)
            else:
                response = self.response_class(content=resp, background=background_tasks)

        response.headers.raw.extend(sub_response.headers.raw)
        if sub_response.status_code:
            response.status_code = sub_response.status_code

        return response

    async def handle_body(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        body: Any,
    ) -> dict:
        async with AsyncExitStack() as async_exit_stack:
            # Shared dependencies for all requests in one json-rpc batch request
            shared_dependencies_error = None
            try:
                dependency_cache = await self.entrypoint.solve_shared_dependencies(
                    http_request,
                    background_tasks,
                    sub_response,
                    async_exit_stack=async_exit_stack,
                )
            except BaseError as error:
                shared_dependencies_error = error
                dependency_cache = None

            resp = await self.handle_req_to_resp(
                http_request, background_tasks, sub_response, body,
                dependency_cache=dependency_cache,
                shared_dependencies_error=shared_dependencies_error,
            )

        # No response for successful notifications
        has_content = 'error' in resp or 'id' in resp
        if not has_content:
            raise NoContent

        return resp

    async def handle_req_to_resp(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        req: Any,
        dependency_cache: Optional[dict] = None,
        shared_dependencies_error: BaseError = None
    ) -> dict:
        async with JsonRpcContext(
            entrypoint=self.entrypoint,
            method_route=self,
            raw_request=req,
            http_request=http_request,
            background_tasks=background_tasks,
            http_response=sub_response,
            json_rpc_request_class=self.request_class,
        ) as ctx:
            await ctx.enter_middlewares(self.entrypoint.middlewares)

            if ctx.request.method != self.name:
                raise MethodNotFound

            resp = await self.handle_req(
                http_request, background_tasks, sub_response, ctx,
                dependency_cache=dependency_cache,
                shared_dependencies_error=shared_dependencies_error,
            )
            ctx.on_raw_response(resp)

        return ctx.raw_response

    async def handle_req(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        ctx: JsonRpcContext,
        dependency_cache: Optional[dict] = None,
        shared_dependencies_error: Optional[BaseError] = None
    ):
        await ctx.enter_middlewares(self.middlewares)

        if shared_dependencies_error:
            raise shared_dependencies_error

        # dependency_cache - there are shared dependencies, we pass them to each method, since
        # they are common to all methods in the batch.
        # But if the methods have their own dependencies, they are resolved separately.
        dependency_cache = copy.copy(dependency_cache)

        solved_dependency = await solve_dependencies(
            request=http_request,
            dependant=self.func_dependant,
            body=ctx.request.params,
            background_tasks=background_tasks,
            response=sub_response,
            dependency_overrides_provider=self.dependency_overrides_provider,
            dependency_cache=dependency_cache,
            async_exit_stack=ctx.exit_stack,
            embed_body_fields=_should_embed_body_fields(self.flat_dependant.body_params),
        )

        if solved_dependency.errors:
            raise invalid_params_from_validation_error(
                RequestValidationError(_normalize_errors(solved_dependency.errors))
            )

        # We MUST NOT return response for Notification
        # https://www.jsonrpc.org/specification#notification
        # Since we do not need response - run in scheduler
        if ctx.request.id is None:
            scheduler = await self.entrypoint.get_scheduler()
            await scheduler.spawn(call_sync_async(self.func, **solved_dependency.values))
            return {}

        # Для обычных запросов продолжаем как раньше
        result = await call_sync_async(self.func, **solved_dependency.values)

        response = {
            'jsonrpc': '2.0',
            'result': result,
        }

        # noinspection PyTypeChecker
        resp = await serialize_response(
            field=self.secure_cloned_response_field,
            response_content=response,
            include=self.response_model_include,
            exclude=self.response_model_exclude,
            by_alias=self.response_model_by_alias,
            exclude_unset=self.response_model_exclude_unset,
        )

        return resp


class RequestShadow(Request):
    def __init__(self, request: Request):
        super().__init__(scope=ChainMap({}, request.scope))
        self.request = request

    async def stream(self):
        async for body in self.request.stream():
            yield body

    async def body(self):
        return await self.request.body()

    async def json(self):
        return await self.request.json()

    async def form(self, **kw):
        return await self.request.form(**kw)

    async def close(self):
        raise NotImplementedError

    async def is_disconnected(self):
        return await self.request.is_disconnected()


class EntrypointRoute(APIRoute):
    def __init__(
        self,
        entrypoint: 'Entrypoint',
        path: str,
        *,
        name: Optional[str] = None,
        errors: Optional[List[Type[BaseError]]] = None,
        common_dependencies: Optional[Sequence[Depends]] = None,
        response_class: Type[Response] = JSONResponse,
        request_class: Type[JsonRpcRequest] = JsonRpcRequest,
        **kwargs,
    ):
        name = name or 'entrypoint'

        _, path_format, _ = compile_path(path)

        _Request = request_class

        common_dependant = Dependant(path=path_format)
        if common_dependencies:
            insert_dependencies(common_dependant, common_dependencies)
            fix_query_dependencies(common_dependant)
            common_dependant = get_flat_dependant(common_dependant, skip_repeats=True)

            if common_dependant.body_params:
                _Request = make_request_model(name, entrypoint.callee_module, common_dependant.body_params)

        # This is only necessary for generating OpenAPI
        def endpoint(__request__: _Request):
            del __request__

        responses = errors_responses(errors)

        super().__init__(
            path,
            endpoint,
            methods=['POST'],
            name=name,
            response_class=response_class,
            response_model=JsonRpcResponse,
            responses=responses,
            **kwargs,
        )

        flat_dependant = get_flat_dependant(self.dependant, skip_repeats=True)

        if len(flat_dependant.body_params) > 1:
            body_params = [p for p in flat_dependant.body_params if p.type_ is not _Request]
            raise RuntimeError(
                f"Entrypoint shared dependencies can't use 'Body' parameters: "
                f"params={body_params}"
            )

        if flat_dependant.query_params:
            raise RuntimeError(
                f"Entrypoint shared dependencies can't use 'Query' parameters: "
                f"params={flat_dependant.query_params}"
            )

        self.shared_dependant = copy.copy(self.dependant)

        # No shared 'Body' params, because each JSON-RPC request in batch has own body
        self.shared_dependant.body_params = []

        # Add dependencies and other parameters from common_dependant for correct OpenAPI generation
        self.dependant.path_params.extend(common_dependant.path_params)
        self.dependant.header_params.extend(common_dependant.header_params)
        self.dependant.cookie_params.extend(common_dependant.cookie_params)
        self.dependant.dependencies.extend(common_dependant.dependencies)
        self.dependant.security_requirements.extend(common_dependant.security_requirements)

        self.app = request_response(self.handle_http_request)
        self.entrypoint = entrypoint
        self.common_dependencies = common_dependencies
        self.request_class = request_class
        self.errors = errors or []

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return (
            isinstance(other, EntrypointRoute)
            and self.path == other.path
        )

    async def solve_shared_dependencies(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        async_exit_stack: AsyncExitStack,
    ) -> dict:
        # Must not be empty, otherwise FastAPI re-creates it
        dependency_cache = {(lambda: None, ('',)): 1}
        if self.dependencies:
            solved_dependency = await solve_dependencies(
                request=http_request,
                dependant=self.shared_dependant,
                body=None,
                background_tasks=background_tasks,
                response=sub_response,
                dependency_overrides_provider=self.dependency_overrides_provider,
                dependency_cache=dependency_cache,
                async_exit_stack=async_exit_stack,
                embed_body_fields=False,
            )
            if solved_dependency.errors:
                raise invalid_params_from_validation_error(
                    RequestValidationError(_normalize_errors(solved_dependency.errors))
                )
        return dependency_cache

    async def parse_body(self, http_request) -> Any:
        try:
            body = await http_request.json()
        except ValueError:
            raise ParseError()

        if isinstance(body, list) and not body:
            raise InvalidRequest(data={'errors': [
                {'loc': (), 'type': 'value_error.empty', 'msg': "rpc call with an empty array"}
            ]})

        return body

    async def handle_http_request(self, http_request: Request):
        background_tasks = BackgroundTasks()

        sub_response = Response()
        del sub_response.headers["content-length"]
        sub_response.status_code = None  # type: ignore

        try:
            body = await self.parse_body(http_request)
        except Exception as exc:
            resp = await self.entrypoint.handle_exception_to_resp(exc)
            response = self.response_class(content=resp, background=background_tasks)
        else:
            try:
                resp = await self.handle_body(http_request, background_tasks, sub_response, body)
            except NoContent:
                # no content for successful notifications
                response = Response(media_type='application/json', background=background_tasks)
            else:
                response = self.response_class(content=resp, background=background_tasks)

        response.headers.raw.extend(sub_response.headers.raw)
        if sub_response.status_code:
            response.status_code = sub_response.status_code

        return response

    async def handle_body(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        body: Any,
    ) -> dict:
        async with AsyncExitStack() as async_exit_stack:
            # Shared dependencies for all requests in one json-rpc batch request
            shared_dependencies_error = None
            try:
                dependency_cache = await self.solve_shared_dependencies(
                    http_request,
                    background_tasks,
                    sub_response,
                    async_exit_stack=async_exit_stack,
                )
            except BaseError as error:
                shared_dependencies_error = error
                dependency_cache = None

            scheduler = await self.entrypoint.get_scheduler()

            if isinstance(body, list):
                req_list = body
            else:
                req_list = [body]

            # Run concurrently through scheduler
            job_list = []
            for req in req_list:
                job = await scheduler.spawn(
                    self.handle_req_to_resp(
                        http_request, background_tasks, sub_response, req,
                        dependency_cache=dependency_cache,
                        shared_dependencies_error=shared_dependencies_error,
                    )
                )
                job_list.append(job.wait())

            resp_list = []

            for resp in await asyncio.gather(*job_list):
                # No response for successful notifications
                has_content = 'error' in resp or 'id' in resp
                if not has_content:
                    continue

                resp_list.append(resp)

        if not resp_list:
            raise NoContent

        if not isinstance(body, list):
            content = resp_list[0]
        else:
            content = resp_list

        return content

    async def handle_req_to_resp(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        req: Any,
        dependency_cache: Optional[dict] = None,
        shared_dependencies_error: BaseError = None
    ) -> dict:
        async with JsonRpcContext(
            entrypoint=self.entrypoint,
            raw_request=req,
            http_request=http_request,
            background_tasks=background_tasks,
            http_response=sub_response,
            json_rpc_request_class=self.request_class
        ) as ctx:
            await ctx.enter_middlewares(self.entrypoint.middlewares)

            resp = await self.handle_req(
                http_request, background_tasks, sub_response, ctx,
                dependency_cache=dependency_cache,
                shared_dependencies_error=shared_dependencies_error,
            )
            ctx.on_raw_response(resp)

        return ctx.raw_response

    async def handle_req(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        ctx: JsonRpcContext,
        dependency_cache: Optional[dict] = None,
        shared_dependencies_error: BaseError = None
    ):
        http_request_shadow = RequestShadow(http_request)
        http_request_shadow.scope['path'] = self.path + '/' + ctx.request.method

        for route in self.entrypoint.routes:  # type: MethodRoute
            match, child_scope = route.matches(http_request_shadow.scope)
            if match == Match.FULL:
                # http_request is a transport layer and it is common for all JSON-RPC requests in a batch
                ctx.method_route = route
                return await route.handle_req(
                    http_request_shadow, background_tasks, sub_response, ctx,
                    dependency_cache=dependency_cache,
                    shared_dependencies_error=shared_dependencies_error,
                )
        else:
            raise MethodNotFound()


class Entrypoint(APIRouter):
    method_route_class = MethodRoute
    entrypoint_route_class = EntrypointRoute

    default_errors: List[Type[BaseError]] = [
        InvalidParams, MethodNotFound, ParseError, InvalidRequest, InternalError,
    ]

    def __init__(
        self,
        path: str,
        *,
        name: Optional[str] = None,
        errors: Optional[List[Type[BaseError]]] = None,
        dependencies: Optional[Sequence[Depends]] = None,
        common_dependencies: Optional[Sequence[Depends]] = None,
        middlewares: Optional[Sequence[JsonRpcMiddleware]] = None,
        scheduler_factory: Callable[..., aiojobs.Scheduler] = aiojobs.Scheduler,
        scheduler_kwargs: Optional[dict] = None,
        request_class: Type[JsonRpcRequest] = JsonRpcRequest,
        **kwargs,
    ) -> None:
        super().__init__(redirect_slashes=False)
        if errors is None:
            errors = list(self.default_errors)
        self.middlewares = middlewares or []
        self.scheduler_factory = scheduler_factory
        self.scheduler_kwargs = scheduler_kwargs
        self.request_class = request_class
        self.scheduler = None
        self.callee_module = inspect.getmodule(inspect.stack()[1][0]).__name__
        self.entrypoint_route = self.entrypoint_route_class(
            self,
            path,
            name=name,
            errors=errors,
            dependencies=dependencies,
            common_dependencies=common_dependencies,
            request_class=request_class,
            **kwargs,
        )
        self.routes.append(self.entrypoint_route)

    def __hash__(self):
        return hash(self.entrypoint_route.path)

    def __eq__(self, other):
        return (
            isinstance(other, Entrypoint)
            and self.routes == other.routes
        )

    @property
    def common_dependencies(self):
        return self.entrypoint_route.common_dependencies

    async def shutdown(self):
        scheduler = self.scheduler
        self.scheduler = None
        if scheduler is not None:
            await scheduler.close()

    async def get_scheduler(self):
        if self.scheduler is not None:
            return self.scheduler
        self.scheduler = self.scheduler_factory(**(self.scheduler_kwargs or {}))
        return self.scheduler

    async def handle_exception(self, exc) -> dict:
        raise exc

    async def handle_exception_to_resp(self, exc) -> dict:
        try:
            resp = await self.handle_exception(exc)
        except BaseError as error:
            resp = error.get_resp()
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(str(exc), exc_info=exc)
            resp = InternalError().get_resp()
        return resp

    def bind_dependency_overrides_provider(self, value):
        for route in self.routes:
            route.dependency_overrides_provider = value

    async def solve_shared_dependencies(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        sub_response: Response,
        async_exit_stack: AsyncExitStack,
    ) -> dict:
        return await self.entrypoint_route.solve_shared_dependencies(
            http_request,
            background_tasks,
            sub_response,
            async_exit_stack=async_exit_stack,
        )

    def add_method_route(
        self,
        func: Union[FunctionType, Coroutine],
        *,
        name: Optional[str] = None,
        **kwargs,
    ) -> None:
        name = name or func.__name__
        tags = list(self.entrypoint_route.tags)
        tags.extend(kwargs.pop('tags', ()))
        route = self.method_route_class(
            self,
            self.entrypoint_route.path + '/' + name,
            func,
            name=name,
            request_class=self.request_class,
            tags=tags,
            **kwargs,
        )
        self.routes.append(route)

    def method(
        self,
        **kwargs,
    ) -> Callable:
        def decorator(func: Union[FunctionType, Coroutine]) -> Callable:
            self.add_method_route(
                func,
                **kwargs,
            )
            return func

        return decorator


class API(FastAPI):
    def __init__(
        self,
        *args,
        fastapi_jsonrpc_components_fine_names: bool = True,
        openrpc_url: Optional[str] = "/openrpc.json",
        **kwargs,
    ):
        self.fastapi_jsonrpc_components_fine_names = fastapi_jsonrpc_components_fine_names
        self.openrpc_schema = None
        self.openrpc_url = openrpc_url
        self.shutdown_functions: List = []
        super().__init__(*args, **kwargs)
        self.add_event_handler("shutdown", self.run_shutdown_functions)

    def _restore_json_schema_fine_component_names(self, data: dict):
        def update_refs(value):
            if not isinstance(value, (dict, list)):
                return

            if isinstance(value, list):
                for v in value:
                    update_refs(v)
                return

            if '$ref' not in value:
                for v in value.values():
                    update_refs(v)
                return

            ref = value['$ref']
            if ref.startswith(REF_PREFIX):
                *_, schema = ref.split(REF_PREFIX)
                new_schema = old2new_schema_name.get(schema, schema)
                if new_schema != schema:
                    ref = f'{REF_PREFIX}{new_schema}'
                    value['$ref'] = ref

        # restore components fine names
        old2new_schema_name = {}

        fine_schema = {}
        for key, schema in data['components']['schemas'].items():
            if 'title' in schema:
                fine_schema_name = key[:-len(schema['title'].replace('.', '__'))].replace('__', '.') + schema['title']
            else:
                fine_schema_name = key.replace('__', '.')
            old2new_schema_name[key] = fine_schema_name
            fine_schema[fine_schema_name] = schema
        data['components']['schemas'] = fine_schema

        update_refs(data)

    def openapi(self):
        result = super().openapi()

        if self.fastapi_jsonrpc_components_fine_names and 'components' in result:
            self._restore_json_schema_fine_component_names(result)

        for route in self.routes:
            if isinstance(route, (EntrypointRoute, MethodRoute,)):
                route: Union[EntrypointRoute, MethodRoute]
                for media_type in result['paths'][route.path]:
                    result['paths'][route.path][media_type]['responses'].pop('default', None)
        return result

    def get_openrpc(self):
        methods_spec = []
        schemas_spec = {}
        errors_by_code = defaultdict(set)
        ref_template = '#/components/schemas/{model}'

        for route in self.routes:
            if not isinstance(route, MethodRoute):
                continue

            params_schema = route.params_model.model_json_schema(ref_template=ref_template)

            if isinstance(route.result_model, BaseModel):
                result_schema = route.result_model.model_json_schema(ref_template=ref_template)
            else:
                result_model = create_model(f'{route.name}_Result', result=(route.result_model or Any, ...))
                result_schema = result_model.model_json_schema(ref_template=ref_template)

            for error in route.errors:
                errors_by_code[error.CODE].add(error)

            method_spec = {
                'name': route.name,
                'params': [
                    {
                        'name': param_name,
                        'schema': param_schema,
                        'required': param_name in params_schema.get('required', []),
                    }
                    for param_name, param_schema in params_schema['properties'].items()
                ],
                'result': {
                    'name': result_schema['title'],
                    'schema': result_schema['properties']['result'],
                },
                'tags': [
                    {
                        'name': tag,
                    }
                    for tag in route.tags
                ],
                'errors': [
                    {
                        '$ref': f'#/components/errors/{code}',
                    }
                    for code in sorted({error.CODE for error in route.errors})
                ],
            }
            if route.summary:
                method_spec['summary'] = route.summary

            methods_spec.append(method_spec)
            schemas_spec.update(params_schema.get('$defs', {}))
            schemas_spec.update(result_schema.get('$defs', {}))

        errors_spec = {}
        for code, errors in errors_by_code.items():
            assert errors
            first, *_ = errors
            spec = {
                'code': code,
                'message': first.MESSAGE,
            }

            error_models = []
            for error in errors:
                error_model = error.get_data_model()
                if error_model is not None:
                    error_models.append(error_model)

            if error_models:
                if len(error_models) == 1:
                    error_schema = error_models[0].model_json_schema(ref_template=ref_template)
                else:
                    # Data schemes of multiple error objects with same code
                    # are merged together in a single schema
                    error_models.sort(key=lambda m: m.__name__)
                    error_schema = pydantic.TypeAdapter(Union[tuple(error_models)]).json_schema(
                        ref_template=ref_template,
                    )
                    error_schema['title'] = f'ERROR_{code}'

                schemas_spec.update(error_schema.pop('$defs', {}))
                spec['data'] = error_schema

            errors_spec[str(code)] = spec

        return {
            'openrpc': '1.2.6',
            'info': {
                'version': self.version,
                'title': self.title,
            },
            'servers': self.servers,
            'methods': methods_spec,
            'components': {
                'schemas': schemas_spec,
                'errors': errors_spec,
            },
        }

    def openrpc(self):
        if self.openrpc_schema is None:
            self.openrpc_schema = self.get_openrpc()

        if self.fastapi_jsonrpc_components_fine_names and 'components' in self.openrpc_schema:
            self._restore_json_schema_fine_component_names(self.openrpc_schema)

        return self.openrpc_schema

    def setup(self) -> None:
        super().setup()

        if self.openrpc_url:
            assert self.title, "A title must be provided for OpenRPC, e.g.: 'My API'"
            assert self.version, "A version must be provided for OpenRPC, e.g.: '2.1.0'"

            async def openrpc(_: Request) -> JSONResponse:
                return JSONResponse(self.openrpc())

            self.add_route(self.openrpc_url, openrpc, include_in_schema=False)

    def bind_entrypoint(self, ep):
        ep.bind_dependency_overrides_provider(self)
        self.routes.extend(ep.routes)
        if hasattr(ep, 'shutdown') and callable(ep.shutdown):
            self.shutdown_functions.append(ep.shutdown)

    async def run_shutdown_functions(self):
        for shutdown_function in self.shutdown_functions:
            await shutdown_function()


if __name__ == '__main__':
    import uvicorn

    app = API()

    api_v1 = Entrypoint('/api/v1/jsonrpc')


    class MyError(BaseError):
        CODE = 5000
        MESSAGE = "My error"

        class DataModel(BaseModel):
            details: str


    @api_v1.method(errors=[MyError])
    def echo(
        data: str = Body(..., examples=['123']),
    ) -> str:
        if data == 'error':
            raise MyError(data={'details': 'error'})
        else:
            return data


    app.bind_entrypoint(api_v1)

    uvicorn.run(app, port=5000, debug=True, access_log=False)  # noqa
