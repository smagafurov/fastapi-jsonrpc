import asyncio
import inspect
import logging
from json import JSONDecodeError
from types import FunctionType, CoroutineType
from typing import List, Union, Any, Callable, Type, Optional, Dict, Sequence, Awaitable

# noinspection PyProtectedMember
from pydantic import DictError
from pydantic import StrictStr, ValidationError
from pydantic import BaseModel, BaseConfig
from pydantic.fields import ModelField, Field
# noinspection PyProtectedMember
from pydantic.main import ModelMetaclass
from fastapi.dependencies.models import Dependant
from fastapi.encoders import jsonable_encoder
from fastapi.params import Depends
from fastapi import FastAPI, Body
from fastapi.dependencies.utils import solve_dependencies, get_dependant, get_flat_dependant, \
    get_parameterless_sub_dependant
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute, APIRouter, serialize_response
from starlette.background import BackgroundTasks
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Match, request_response, compile_path
import fastapi.params
import aiojobs


logger = logging.getLogger(__name__)


class Params(fastapi.params.Body):
    def __init__(
        self,
        default: Any,
        *,
        media_type: str = 'application/json',
        title: str = None,
        description: str = None,
        gt: float = None,
        ge: float = None,
        lt: float = None,
        le: float = None,
        min_length: int = None,
        max_length: int = None,
        regex: str = None,
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
            **extra,
        )


components = {}


def component_name(name: str, module: str = None):
    """OpenAPI components must be unique by name"""
    def decorator(obj):
        obj.__name__ = name
        if module is not None:
            obj.__module__ = module  # see: pydantic.schema.get_long_model_name
        key = (obj.__name__, obj.__module__)
        if key in components:
            if components[key].schema() != obj.schema():
                raise RuntimeError(
                    f"Different models with the same name detected: {obj!r} != {components[key]}"
                )
            return components[key]
        components[key] = obj
        return obj
    return decorator


def is_scope_child(owner: type, child: type):
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
    CODE = None
    MESSAGE = None

    ErrorModel = None
    DataModel = None

    data_required = False
    errors_required = False

    error_model = None
    data_model = None
    resp_model = None

    _component_name = None

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
            data = data_model.validate(data)
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

    def get_resp(self):
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

        errors_annotation = List[error_model]
        if not cls.errors_required:
            errors_annotation = Optional[errors_annotation]

        ns = {
            '__annotations__': {
                'errors': errors_annotation,
            }
        }

        _ErrorData = ModelMetaclass.__new__(ModelMetaclass, '_ErrorData', (BaseModel,), ns)
        _ErrorData = component_name(f'_ErrorData[{error_model.__name__}]', error_model.__module__)(_ErrorData)

        return _ErrorData

    @classmethod
    def get_resp_model(cls):
        if cls.__dict__.get('resp_model') is not None:
            return cls.resp_model
        cls.resp_model = cls.build_resp_model()
        return cls.resp_model

    @classmethod
    def build_resp_model(cls):
        ns = {
            'code': Field(cls.CODE, const=True, example=cls.CODE),
            'message': Field(cls.MESSAGE, const=True, example=cls.MESSAGE),
            '__annotations__': {
                'code': int,
                'message': str,
            }
        }

        data_model = cls.get_data_model()
        if data_model is not None:
            if not cls.data_required:
                data_model = Optional[data_model]
            # noinspection PyTypeChecker
            ns['__annotations__']['data'] = data_model

        name = cls._component_name or cls.__name__

        _JsonRpcErrorModel = ModelMetaclass.__new__(ModelMetaclass, '_JsonRpcErrorModel', (BaseModel,), ns)
        _JsonRpcErrorModel = component_name(name, cls.__module__)(_JsonRpcErrorModel)

        @component_name(f'_ErrorResponse[{name}]', cls.__module__)
        class _ErrorResponseModel(BaseModel):
            jsonrpc: StrictStr = Field('2.0', const=True, example='2.0')
            id: Union[StrictStr, int] = Field(None, example=0)
            error: _JsonRpcErrorModel

            class Config:
                extra = 'forbid'

        return _ErrorResponseModel


@component_name('_Error')
class ErrorModel(BaseModel):
    loc: List[str]
    msg: str
    type: str
    ctx: Optional[Dict[str, Any]]


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


def errors_responses(errors: Sequence[Type[BaseError]] = None):
    responses = {'default': {}}

    if errors:
        cnt = 1
        for error_cls in errors:
            responses[f'200{" " * cnt}'] = {
                'model': error_cls.get_resp_model(),
                'description': error_cls.get_description(),
            }
            cnt += 1

    return responses


@component_name(f'_Request')
class JsonRpcRequest(BaseModel):
    jsonrpc: StrictStr = Field('2.0', const=True, example='2.0')
    id: Union[StrictStr, int] = Field(None, example=0)
    method: StrictStr
    params: dict

    class Config:
        extra = 'forbid'


@component_name(f'_Response')
class JsonRpcResponse(BaseModel):
    jsonrpc: StrictStr = Field('2.0', const=True, example='2.0')
    id: Union[StrictStr, int] = Field(None, example=0)
    result: dict

    class Config:
        extra = 'forbid'


def invalid_request_from_validation_error(exc: ValidationError) -> InvalidRequest:
    return InvalidRequest(data={'errors': exc.errors()})


def invalid_params_from_validation_error(exc: ValidationError) -> InvalidParams:
    errors = []

    for err in exc.errors():
        if err['loc'][:1] == ('body', ):
            err['loc'] = err['loc'][1:]
        else:
            assert err['loc']
            err['loc'] = (f"<{err['loc'][0]}>", ) + err['loc'][1:]
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


def clone_dependant(dependant: Dependant) -> Dependant:
    new_dependant = Dependant()
    new_dependant.path_params = dependant.path_params
    new_dependant.query_params = dependant.query_params
    new_dependant.header_params = dependant.header_params
    new_dependant.cookie_params = dependant.cookie_params
    new_dependant.body_params = dependant.body_params
    new_dependant.dependencies = dependant.dependencies
    new_dependant.security_requirements = dependant.security_requirements
    new_dependant.request_param_name = dependant.request_param_name
    new_dependant.websocket_param_name = dependant.websocket_param_name
    new_dependant.response_param_name = dependant.response_param_name
    new_dependant.background_tasks_param_name = dependant.background_tasks_param_name
    new_dependant.security_scopes = dependant.security_scopes
    new_dependant.security_scopes_param_name = dependant.security_scopes_param_name
    new_dependant.name = dependant.name
    new_dependant.call = dependant.call
    new_dependant.use_cache = dependant.use_cache
    new_dependant.path = dependant.path
    new_dependant.cache_key = dependant.cache_key
    return new_dependant


def insert_dependencies(target: Dependant, dependencies: Sequence[Depends] = None):
    assert target.path
    if not dependencies:
        return
    for depends in dependencies[::-1]:
        target.dependencies.insert(
            0,
            get_parameterless_sub_dependant(depends=depends, path=target.path),
        )


def make_request_model(name, module, body_params: List[ModelField]):
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
    else:
        _JsonRpcRequestParams = ModelMetaclass.__new__(ModelMetaclass, '_JsonRpcRequestParams', (BaseModel,), {})

        for f in body_params:
            _JsonRpcRequestParams.__fields__[f.name] = f

        _JsonRpcRequestParams = component_name(f'_Params[{name}]', module)(_JsonRpcRequestParams)

        params_field = ModelField(
            name='params',
            type_=_JsonRpcRequestParams,
            class_validators={},
            default=None,
            required=True,
            model_config=BaseConfig,
            field_info=Field(...),
        )

    class _Request(BaseModel):
        jsonrpc: StrictStr = Field('2.0', const=True, example='2.0')
        id: Union[StrictStr, int] = Field(None, example=0)
        method: StrictStr = Field(name, const=True, example=name)

        class Config:
            extra = 'forbid'

    _Request.__fields__[params_field.name] = params_field

    _Request = component_name(f'_Request[{name}]', module)(_Request)

    return _Request


class MethodRoute(APIRoute):
    def __init__(
        self,
        entrypoint: 'Entrypoint',
        path: str,
        func: Union[FunctionType, CoroutineType],
        *,
        result_model: Type[Any] = None,
        name: str = None,
        errors: Sequence[Type[BaseError]] = None,
        dependencies: Sequence[Depends] = None,
        response_class: Type[Response] = JSONResponse,
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

        @component_name(f'_Response[{name}]', func.__module__)
        class _Response(BaseModel):
            jsonrpc: StrictStr = Field('2.0', const=True, example='2.0')
            id: Union[StrictStr, int] = Field(None, example=0)
            result: result_model

            class Config:
                extra = 'forbid'

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
            response_model_exclude_unset=True,
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
        self.func_dependant = func_dependant
        self.entrypoint = entrypoint
        self.app = request_response(self.handle_http_request)

    async def parse_body(self, http_request) -> Any:
        try:
            req = await http_request.json()
        except JSONDecodeError:
            raise ParseError()
        return req

    async def handle_http_request(self, http_request: Request):
        background_tasks = BackgroundTasks()

        try:
            body = await self.parse_body(http_request)
        except Exception as exc:
            resp = await self.entrypoint.handle_exception_to_resp(exc)
        else:
            try:
                resp = await self.handle_body(http_request, background_tasks, body)
            except NoContent:
                # no content for successful notifications
                return Response(media_type='application/json', background=background_tasks)

        return self.response_class(content=resp, background=background_tasks)

    async def handle_body(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        body: Any,
    ) -> dict:
        # Shared dependencies for all requests in one json-rpc batch request
        shared_dependencies_error = None
        try:
            dependency_cache = await self.entrypoint.solve_shared_dependencies(http_request, background_tasks)
        except BaseError as error:
            shared_dependencies_error = error
            dependency_cache = None

        return await self.handle_req_to_resp(
            http_request, background_tasks, body,
            dependency_cache=dependency_cache,
            shared_dependencies_error=shared_dependencies_error,
        )

    async def handle_req_to_resp(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        req: Any,
        dependency_cache: dict = None,
        shared_dependencies_error: BaseError = None
    ) -> dict:
        handler_coro = self.handle_req(
            http_request, background_tasks, req,
            dependency_cache=dependency_cache,
            shared_dependencies_error=shared_dependencies_error,
        )
        return await self.entrypoint.handle_req_to_resp(handler_coro, req)

    async def handle_req(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        req: Any,
        dependency_cache: dict = None,
        shared_dependencies_error: BaseError = None
    ):
        try:
            JsonRpcRequest.validate(req)
        except DictError:
            raise InvalidRequest(data={'errors': [{
                'loc': (),
                'type': 'type_error.dict',
                'msg': "value is not a valid dict",
            }]})
        except ValidationError as exc:
            raise invalid_request_from_validation_error(exc)

        if req['method'] != self.name:
            raise MethodNotFound

        if shared_dependencies_error:
            raise shared_dependencies_error

        # dependency_cache - there are shared dependencies, we pass them to each method, since
        # they are common to all methods in the batch.
        # But if the methods have their own dependencies, they are resolved separately.
        dependency_cache = dependency_cache.copy()

        values, errors, background_tasks, sub_response, _ = await solve_dependencies(
            request=http_request,
            dependant=self.func_dependant,
            body=req['params'],
            background_tasks=background_tasks,
            dependency_overrides_provider=self.dependency_overrides_provider,
            dependency_cache=dependency_cache,
        )

        if errors:
            raise invalid_params_from_validation_error(RequestValidationError(errors))

        result = await call_sync_async(self.func, **values)

        response = {
            'jsonrpc': '2.0',
            'result': result,
            'id': req.get('id')
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


class EntrypointRoute(APIRoute):
    def __init__(
        self,
        entrypoint: 'Entrypoint',
        path: str,
        *,
        name: str = None,
        errors: Sequence[Type[BaseError]] = None,
        common_dependencies: Sequence[Depends] = None,
        response_class: Type[Response] = JSONResponse,
        **kwargs,
    ):
        name = name or 'entrypoint'

        _, path_format, _ = compile_path(path)

        _Request = JsonRpcRequest

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

        self.shared_dependant = clone_dependant(self.dependant)

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

    async def solve_shared_dependencies(self, http_request: Request, background_tasks: BackgroundTasks) -> dict:
        # Must not be empty, otherwise FastAPI re-creates it
        dependency_cache = {(lambda: None, ('', )): 1}
        if self.dependencies:
            _, errors, _, _, _ = await solve_dependencies(
                request=http_request,
                dependant=self.shared_dependant,
                body=None,
                background_tasks=background_tasks,
                dependency_overrides_provider=self.dependency_overrides_provider,
                dependency_cache=dependency_cache,
            )
            if errors:
                raise invalid_params_from_validation_error(RequestValidationError(errors))
        return dependency_cache

    async def parse_body(self, http_request) -> Any:
        try:
            body = await http_request.json()
        except JSONDecodeError:
            raise ParseError()

        if isinstance(body, list) and not body:
            raise InvalidRequest(data={'errors': [
                {'loc': (), 'type': 'value_error.empty', 'msg': "rpc call with an empty array"}
            ]})

        return body

    async def handle_http_request(self, http_request: Request):
        background_tasks = BackgroundTasks()

        try:
            body = await self.parse_body(http_request)
        except Exception as exc:
            resp = await self.entrypoint.handle_exception_to_resp(exc)
        else:
            try:
                resp = await self.handle_body(http_request, background_tasks, body)
            except NoContent:
                # no content for successful notifications
                return Response(media_type='application/json', background=background_tasks)

        return self.response_class(content=resp, background=background_tasks)

    async def handle_body(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        body: Any,
    ) -> dict:
        # Shared dependencies for all requests in one json-rpc batch request
        shared_dependencies_error = None
        try:
            dependency_cache = await self.solve_shared_dependencies(http_request, background_tasks)
        except BaseError as error:
            shared_dependencies_error = error
            dependency_cache = None

        scheduler = await self.entrypoint.get_scheduler()

        if isinstance(body, list):
            req_list = body
        else:
            req_list = [body]

        job_list = []
        if len(req_list) > 1:
            # Run concurrently through scheduler
            for req in req_list:
                job = await scheduler.spawn(
                    self.handle_req_to_resp(
                        http_request, background_tasks, req,
                        dependency_cache=dependency_cache,
                        shared_dependencies_error=shared_dependencies_error,
                    )
                )

                # TODO: https://github.com/aio-libs/aiojobs/issues/119
                job._explicit = True
                # noinspection PyProtectedMember
                coro = job._do_wait(timeout=None)

                job_list.append(coro)
        else:
            req = req_list[0]
            coro = self.handle_req_to_resp(
                http_request, background_tasks, req,
                dependency_cache=dependency_cache,
                shared_dependencies_error=shared_dependencies_error,
            )
            job_list.append(coro)

        resp_list = []

        for coro in job_list:
            try:
                resp = await coro
            except NoContent:
                # No response for successful notifications
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
        req: Any,
        dependency_cache: dict = None,
        shared_dependencies_error: BaseError = None
    ) -> dict:
        handler_coro = self.handle_req(
            http_request, background_tasks, req,
            dependency_cache=dependency_cache,
            shared_dependencies_error=shared_dependencies_error,
        )
        return await self.entrypoint.handle_req_to_resp(handler_coro, req)

    async def handle_req(
        self,
        http_request: Request,
        background_tasks: BackgroundTasks,
        req: Any,
        dependency_cache: dict = None,
        shared_dependencies_error: BaseError = None
    ):
        try:
            JsonRpcRequest.validate(req)
        except DictError:
            raise InvalidRequest(data={'errors': [
                {'loc': (), 'type': 'type_error.dict', 'msg': "value is not a valid dict"}
            ]})
        except ValidationError as exc:
            raise invalid_request_from_validation_error(exc)

        scope = http_request.scope.copy()
        scope['path'] = self.path + '/' + req['method']

        for route in self.entrypoint.routes:
            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                # http_request is a transport layer and it is common for all JSON-RPC requests in a batch
                return await route.handle_req(
                    http_request, background_tasks, req,
                    dependency_cache=dependency_cache,
                    shared_dependencies_error=shared_dependencies_error,
                )
        else:
            raise MethodNotFound()


class Entrypoint(APIRouter):
    method_route_class = MethodRoute
    entrypoint_route_class = EntrypointRoute

    default_errors: Sequence[Type[BaseError]] = [
        InvalidParams, MethodNotFound, ParseError, InvalidRequest, InternalError,
    ]

    def __init__(
        self,
        path: str,
        *,
        name: str = None,
        errors: Sequence[Type[BaseError]] = None,
        dependencies: Sequence[Depends] = None,
        common_dependencies: Sequence[Depends] = None,
        scheduler_factory: Callable[..., Awaitable[aiojobs.Scheduler]] = aiojobs.create_scheduler,
        scheduler_kwargs: dict = None,
        **kwargs,
    ) -> None:
        super().__init__(redirect_slashes=False)
        if errors is None:
            errors = self.default_errors
        self.scheduler_factory = scheduler_factory
        self.scheduler_kwargs = scheduler_kwargs
        self.scheduler = None
        self.callee_module = inspect.getmodule(inspect.stack()[1][0]).__name__
        self.entrypoint_route = self.entrypoint_route_class(
            self,
            path,
            name=name,
            errors=errors,
            dependencies=dependencies,
            common_dependencies=common_dependencies,
            **kwargs,
        )
        self.routes.append(self.entrypoint_route)

    @property
    def common_dependencies(self):
        return self.entrypoint_route.common_dependencies

    async def shutdown(self):
        if self.scheduler is not None:
            await self.scheduler.close()

    async def get_scheduler(self):
        if self.scheduler is not None:
            return self.scheduler
        self.scheduler = await self.scheduler_factory(**(self.scheduler_kwargs or {}))
        return self.scheduler

    async def handle_exception(self, exc):
        raise exc

    async def handle_exception_to_resp(self, exc) -> dict:
        try:
            resp = await self.handle_exception(exc)
        except BaseError as error:
            resp = error.get_resp()
        except Exception as exc:
            logger.exception(str(exc), exc_info=exc)
            resp = InternalError().get_resp()
        return resp

    async def handle_req_to_resp(self, handler_coro: Awaitable, req: Any) -> dict:
        try:
            resp = await handler_coro
        except Exception as exc:
            resp = await self.handle_exception_to_resp(exc)

        # empty response for successful notifications
        has_content = 'error' in resp or 'id' in req

        if not has_content:
            raise NoContent

        if isinstance(req, dict):
            resp['id'] = req.get('id')
        else:
            resp['id'] = None

        return resp

    def bind_dependency_overrides_provider(self, value):
        for route in self.routes:
            route.dependency_overrides_provider = value

    async def solve_shared_dependencies(self, http_request: Request, background_tasks: BackgroundTasks) -> dict:
        return await self.entrypoint_route.solve_shared_dependencies(http_request, background_tasks)

    def add_method_route(
        self,
        func: FunctionType,
        *,
        name: str = None,
        **kwargs,
    ) -> None:
        name = name or func.__name__
        route = self.method_route_class(
            self,
            self.entrypoint_route.path + '/' + name,
            func,
            name=name,
            **kwargs,
        )
        self.routes.append(route)

    def method(
        self,
        **kwargs,
    ) -> Callable:
        def decorator(func: Callable) -> Callable:
            self.add_method_route(
                func,
                **kwargs,
            )
            return func

        return decorator


class API(FastAPI):
    def openapi(self):
        result = super().openapi()
        for route in self.routes:
            if isinstance(route, (EntrypointRoute, MethodRoute, )):
                route: Union[EntrypointRoute, MethodRoute]
                for media_type in result['paths'][route.path]:
                    result['paths'][route.path][media_type]['responses'].pop('default', None)
        return result

    def bind_entrypoint(self, ep: Entrypoint):
        ep.bind_dependency_overrides_provider(self)
        self.routes.extend(ep.routes)
        self.on_event('shutdown')(ep.shutdown)


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
        data: str = Body(..., example='123'),
    ) -> str:
        if data == 'error':
            raise MyError(data={'details': 'error'})
        else:
            return data


    app.bind_entrypoint(api_v1)

    uvicorn.run(app, port=5000, debug=True, access_log=False)
