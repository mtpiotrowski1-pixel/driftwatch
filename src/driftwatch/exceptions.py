"""Domain exceptions, mapped to HTTP status codes by the API layer."""

from __future__ import annotations


class DriftwatchError(Exception):
    """Base class for expected, client-facing failures."""


class NotFoundError(DriftwatchError):
    """A requested entity does not exist."""


class ConflictError(DriftwatchError):
    """The request conflicts with current state (e.g. a duplicate email)."""


class AccessDenied(DriftwatchError):
    """The authenticated user may not perform this action."""


class InvalidRequest(DriftwatchError):
    """The request is well-formed but semantically invalid (maps to 400)."""


class PlanLimitReached(DriftwatchError):
    """The organization is at a limit set by its billing plan (maps to 403)."""
