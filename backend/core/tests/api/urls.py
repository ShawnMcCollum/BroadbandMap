"""Test-only API resources; never included by production URL configuration."""

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    ParseError,
    Throttled,
)
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from config.urls import PublicSchemaView
from core.api.permissions import IsAdministratorWithOperationPermission
from core.api.problems import ServiceUnavailable
from core.api.schema import problem_responses
from core.api.validation import StrictQuerySerializer
from core.views import health


class LimitQuery(StrictQuerySerializer):
    limit = serializers.IntegerField(default=7, min_value=1, max_value=10)


class PairQuery(StrictQuerySerializer):
    start = serializers.IntegerField(required=False)
    end = serializers.IntegerField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if ("start" in attrs) != ("end" in attrs):
            raise serializers.ValidationError("Both start and end are required together.")
        return attrs


class NestedQuery(StrictQuerySerializer):
    values = serializers.ListField(child=serializers.IntegerField())


class SlashQuery(StrictQuerySerializer):
    class Meta:
        fields = ("a~/b",)

    def get_fields(self) -> dict[str, Any]:
        return {"a~/b": serializers.IntegerField()}


class MultipleMessageField(serializers.IntegerField):
    def run_validators(self, value: Any) -> None:
        raise serializers.ValidationError(["First message.", "Second message."])


class MultipleMessageQuery(StrictQuerySerializer):
    value = MultipleMessageField()


class PublicPayload(serializers.Serializer[Any]):
    id = serializers.CharField()
    count = serializers.IntegerField()
    enabled = serializers.BooleanField()


class LimitResult(serializers.Serializer[Any]):
    limit = serializers.IntegerField()


class OperationResult(serializers.Serializer[Any]):
    allowed = serializers.BooleanField()


class OperationWriteResult(serializers.Serializer[Any]):
    saved = serializers.BooleanField()


class PublicRead(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    http_method_names = ["get", "head", "options"]

    @classmethod
    def get_view_name(cls: "type[PublicRead]") -> str:
        return "Public test read"

    @extend_schema(operation_id="test_public_read", responses=PublicPayload, auth=[])
    def get(self, request: Request) -> Response:
        return Response({"id": "00123", "count": 4, "enabled": True})


class UnmarkedRead(APIView):
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        return Response({"unreachable": True})


class OperationView(APIView):
    permission_classes = [IsAdministratorWithOperationPermission]
    required_operation_permissions = ("bdc.view_release",)
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(
        operation_id="test_operation_read",
        request=None,
        responses={200: OperationResult, **problem_responses(403)},
    )
    def get(self, request: Request) -> Response:
        return Response({"allowed": True})

    @extend_schema(
        operation_id="test_operation_write",
        request=None,
        responses={200: OperationWriteResult, **problem_responses(403)},
    )
    def post(self, request: Request) -> Response:
        return Response({"saved": True})


class MissingOperationPermission(APIView):
    permission_classes = [IsAdministratorWithOperationPermission]

    def get(self, request: Request) -> Response:
        return Response({"unreachable": True})


class EmptyOperationPermission(MissingOperationPermission):
    required_operation_permissions: tuple[str, ...] = ()


class CsrfTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    def get(self, request: Request) -> Response:
        return Response({"token": get_token(request._request)})


class LimitView(PublicRead):
    @extend_schema(
        operation_id="test_limit_read",
        parameters=[LimitQuery],
        responses={200: LimitResult, **problem_responses(400)},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        serializer = LimitQuery(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response({"limit": serializer.validated_data["limit"]})


class PairView(PublicRead):
    def get(self, request: Request) -> Response:
        serializer = PairQuery(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class NestedView(PublicRead):
    def get(self, request: Request) -> Response:
        serializer = NestedQuery(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class MultipleMessageView(PublicRead):
    def get(self, request: Request) -> Response:
        serializer = MultipleMessageQuery(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class SlashView(PublicRead):
    def get(self, request: Request) -> Response:
        serializer = SlashQuery(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class ParseView(PublicRead):
    http_method_names = ["post", "options"]

    def post(self, request: Request) -> Response:
        return Response(request.data)


class ErrorView(PublicRead):
    def get(self, request: Request) -> Response:
        error = request.query_params.get("kind")
        if error == "not_found":
            raise Http404
        if error == "permission":
            raise PermissionDenied
        if error == "bad_request":
            raise BadRequest
        if error == "suspicious":
            raise SuspiciousOperation("malformed request")
        if error == "parse":
            raise ParseError
        if error == "not_authenticated":
            raise NotAuthenticated
        if error == "authentication_failed":
            raise AuthenticationFailed
        if error == "throttle":
            raise Throttled(wait=3)
        if error == "unavailable":
            raise ServiceUnavailable
        if error == "unexpected":
            raise RuntimeError("select * from secrets at C:\\private\\db.sqlite")
        return Response({"ok": True})


class RejectingRenderer(JSONRenderer):
    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> bytes:
        del data, accepted_media_type, renderer_context
        raise RuntimeError("renderer leaked secret SQL")


class RenderingFailure(PublicRead):
    renderer_classes: list[type[BaseRenderer]] = [RejectingRenderer]


api_patterns: list[URLPattern] = [
    path("public/", PublicRead.as_view(), name="test-public"),
    path("unmarked/", UnmarkedRead.as_view(), name="test-unmarked"),
    path("operation/", OperationView.as_view(), name="test-operation"),
    path("operation-missing/", MissingOperationPermission.as_view()),
    path("operation-empty/", EmptyOperationPermission.as_view()),
    path("csrf-token/", CsrfTokenView.as_view()),
    path("limit/", LimitView.as_view(), name="test-limit"),
    path("pair/", PairView.as_view()),
    path("nested/", NestedView.as_view()),
    path("multiple/", MultipleMessageView.as_view()),
    path("slash/", SlashView.as_view()),
    path("parse/", ParseView.as_view()),
    path("error/", ErrorView.as_view()),
    path("render-failure/", RenderingFailure.as_view()),
    path("middleware-failure/", PublicRead.as_view()),
    path("schema/", PublicSchemaView.as_view(), name="test-schema"),
]


def django_error(request: HttpRequest, kind: str) -> HttpResponse:
    del request
    if kind == "not_found":
        raise Http404
    if kind == "permission":
        raise PermissionDenied
    if kind == "bad_request":
        raise BadRequest
    if kind == "suspicious":
        raise SuspiciousOperation("malformed request")
    return HttpResponse("ok")


def plain_returned_error(request: HttpRequest) -> HttpResponse:
    del request
    response = HttpResponse("unsafe detail", status=400)
    response["Allow"] = "GET"
    response["Retry-After"] = "3"
    response["WWW-Authenticate"] = "Session"
    response["Vary"] = "Cookie"
    response["Content-Length"] = "999"
    response["Content-Encoding"] = "gzip"
    response["ETag"] = '"old"'
    response.set_cookie("sessionid", "session-value")
    return response


def outside_not_found(request: HttpRequest) -> HttpResponse:
    del request
    return HttpResponse("outside", status=404)


urlpatterns: list[URLPattern | URLResolver] = [
    path("api/v1/", include((api_patterns, "test_api"), namespace="test_api")),
    path("api/schema/", PublicSchemaView.as_view(), name="api-schema"),
    path("api/health/", health, name="health"),
    path("api/plain-error/<str:kind>/", django_error, name="plain-error"),
    path("api/plain-returned/", plain_returned_error, name="plain-returned"),
    path("outside/", outside_not_found),
]
