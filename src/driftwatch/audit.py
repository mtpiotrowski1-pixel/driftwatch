"""Safe, transaction-local recording of privileged application actions."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.models import AuditEvent, User

_REDACTED = "[redacted]"
_SENSITIVE_FRAGMENTS = ("password", "secret", "token", "api_key", "credential")
_MAX_TEXT_LENGTH = 500


def record_audit_event(
    session: AsyncSession,
    request: Request,
    actor: User,
    *,
    action: str,
    target_type: str,
    organization_id: int | None,
    target_id: int | str | None = None,
    target_label: str | None = None,
    details: Mapping[str, object] | None = None,
) -> AuditEvent:
    """Append an event to the caller's transaction.

    Only explicit, bounded metadata belongs here. A defensive scrub prevents a
    future caller from accidentally persisting common secret-bearing fields.
    The event commits or rolls back with the administrative mutation it records.
    """
    client = request.client.host if request.client else None
    event = AuditEvent(
        actor_user_id=actor.id,
        actor_email=actor.email,
        actor_is_superadmin=actor.is_superadmin,
        organization_id=organization_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        target_label=_bounded(target_label),
        source_ip=_bounded(client, limit=64),
        details=_sanitize_mapping(details or {}),
    )
    session.add(event)
    return event


def _sanitize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for raw_key, item in value.items():
        key = str(raw_key)[:100]
        if any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS):
            sanitized[key] = _REDACTED
        else:
            sanitized[key] = _sanitize_value(item)
    return sanitized


def _sanitize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize_value(item) for item in list(value)[:100]]
    if isinstance(value, str):
        return _bounded(value) or ""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _bounded(str(value)) or ""


def _bounded(value: str | None, *, limit: int = _MAX_TEXT_LENGTH) -> str | None:
    if value is None:
        return None
    return value[:limit]
