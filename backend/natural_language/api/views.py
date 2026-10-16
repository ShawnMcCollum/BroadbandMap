# ruff: noqa: RUF012 -- DRF view configuration uses class-level lists.
"""Status, administrator configuration, and query stub endpoints."""

from typing import Any, cast

from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.permissions import IsAdministratorWithOperationPermission
from core.api.problems import AICredentialsUnavailable, NaturalLanguageDisabled
from core.api.schema import problem_responses
from natural_language.api.serializers import (
    ConfigurationPatch,
    ConfigurationResponse,
    EmptyQuery,
    QueryRequest,
    QueryResponse,
    StatusResponse,
)
from natural_language.configuration import (
    configuration_payload,
    effective_enabled,
    get_configuration,
    update_configuration,
)
from natural_language.credentials import CredentialStorageUnavailable
from natural_language.services import (
    QueryCredentialsUnavailableError,
    QueryDisabledError,
    answer_question,
)

DISABLED_MESSAGE = "Ask an application administrator to enable AI in the application settings."
ENABLED_MESSAGE = "AI is configured as a stub. No provider or broadband queries are performed."


class NaturalLanguageConfiguration(APIView):
    permission_classes = [IsAdministratorWithOperationPermission]
    required_operation_permissions = ("natural_language.manage_ai_configuration",)
    http_method_names = ["get", "head", "options", "patch"]

    @extend_schema(
        operation_id="natural_language_configuration_read",
        description="Administrator-only installation settings. Credentials are never returned. "
        "Sets the CSRF cookie for a subsequent session-authenticated PATCH.",
        responses={200: ConfigurationResponse, **problem_responses(400, 403, 405, 406, 415, 500)},
    )
    def get(self, request: Request) -> Response:
        query = EmptyQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        get_token(cast(Any, request)._request)
        return Response(
            configuration_payload(get_configuration()), headers={"Cache-Control": "no-store"}
        )

    @extend_schema(
        operation_id="natural_language_configuration_update",
        description="Atomically update persistent AI settings. Omit api_key to preserve it; "
        "clear_api_key removes it and disables AI. Provider/model identifiers remain unverified. "
        "Requires an active staff session, manage_ai_configuration permission, and CSRF token.",
        request=ConfigurationPatch,
        responses={
            200: ConfigurationResponse,
            **problem_responses(400, 403, 405, 406, 415, 500, 503),
        },
    )
    def patch(self, request: Request) -> Response:
        query = EmptyQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        serializer = ConfigurationPatch(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            config = update_configuration(serializer.validated_data, cast(Any, request.user))
        except CredentialStorageUnavailable:
            raise AICredentialsUnavailable from None
        return Response(configuration_payload(config), headers={"Cache-Control": "no-store"})


class NaturalLanguageStatus(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        operation_id="natural_language_status",
        description="Public availability of the inert stub. No provider or broadband queries "
        "are performed; detailed configuration is restricted to application administrators.",
        responses={200: StatusResponse, **problem_responses(400, 405, 406, 500)},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        query = EmptyQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        enabled = effective_enabled(get_configuration())
        message = ENABLED_MESSAGE if enabled else DISABLED_MESSAGE
        return Response(
            {"enabled": enabled, "is_stub": True, "message": message},
            headers={"Cache-Control": "no-store"},
        )


class NaturalLanguageQuery(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    @extend_schema(
        operation_id="natural_language_query",
        description="Pass a question through the configured, read-only stub. Returns a fixed "
        "explanatory answer without provider calls or broadband data queries.",
        request=QueryRequest,
        responses={200: QueryResponse, **problem_responses(400, 405, 406, 415, 500, 503)},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        query = EmptyQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        serializer = QueryRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            answer = answer_question(cast(str, serializer.validated_data["question"]))
        except QueryDisabledError:
            raise NaturalLanguageDisabled from None
        except QueryCredentialsUnavailableError:
            raise AICredentialsUnavailable from None
        return Response(
            {"question": answer.question, "answer": answer.answer, "is_stub": answer.is_stub},
            headers={"Cache-Control": "no-store"},
        )
