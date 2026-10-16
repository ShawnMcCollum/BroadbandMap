"""OpenAPI helpers for consistent Problem Details responses."""

from typing import Any

from drf_spectacular.utils import OpenApiResponse, PolymorphicProxySerializer

from core.api.serializers import Problem, ValidationProblem


def problem_responses(
    *statuses: int,
) -> dict[int | tuple[int, str], OpenApiResponse]:
    responses: dict[int | tuple[int, str], OpenApiResponse] = {}
    for status in statuses:
        if status == 400:
            serializer: Any = PolymorphicProxySerializer(
                component_name="BadRequestProblem",
                serializers={"problem": Problem, "validation_problem": ValidationProblem},
                resource_type_field_name=None,
            )
        else:
            serializer = Problem
        responses[(status, "application/problem+json")] = OpenApiResponse(
            response=serializer,
            description="Problem Details response",
            examples=[],
        )
    return responses
