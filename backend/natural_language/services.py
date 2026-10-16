"""Inert query service; it never contacts a provider or broadband model."""

from dataclasses import dataclass

from natural_language.configuration import effective_enabled, get_configuration


@dataclass(frozen=True)
class QueryAnswer:
    question: str
    answer: str
    is_stub: bool = True


class QueryDisabledError(Exception):
    """The feature is not enabled with a complete saved configuration."""


class QueryCredentialsUnavailableError(Exception):
    """Saved credentials cannot currently be decrypted."""


def answer_question(question: str) -> QueryAnswer:
    config = get_configuration()
    if not (
        config.enabled
        and config.provider
        and config.model_name.strip()
        and config.api_key_ciphertext
    ):
        raise QueryDisabledError
    if not effective_enabled(config):
        raise QueryCredentialsUnavailableError
    return QueryAnswer(
        question=question,
        answer=(
            "This is a natural-language query stub. No broadband data was queried and "
            "no external provider was contacted."
        ),
    )
