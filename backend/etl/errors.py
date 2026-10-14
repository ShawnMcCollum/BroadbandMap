"""Errors raised when a data load cannot be completed."""


class LoadError(Exception):
    """A source file is missing or malformed, or the load failed. Nothing was committed."""


class ReconciliationError(LoadError):
    """The database does not hold what the source files contain. The load was rolled back."""
