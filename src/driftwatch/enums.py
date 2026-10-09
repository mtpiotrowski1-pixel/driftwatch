"""Domain enumerations shared by the ORM models and the API schemas."""

from __future__ import annotations

from enum import StrEnum


class AnalysisMode(StrEnum):
    AI = "ai"
    DISABLED = "disabled"


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    DISABLED = "disabled"
    NOT_REQUESTED = "not_requested"
    SKIPPED_NO_DELIVERY = "skipped_no_delivery"
    ERROR = "error"
    QUOTA_BLOCKED = "quota_blocked"


class NotificationMode(StrEnum):
    """When a site should generate an email after a detected change."""

    ONLY_SIGNIFICANT = "only_significant"
    ALWAYS = "always"


class NotificationStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationDeliveryStatus(StrEnum):
    """Durable state of one required outbox destination."""

    PENDING = "pending"
    FAILED = "failed"
    SENT = "sent"


class AccountEmailKind(StrEnum):
    PASSWORD_RESET = "password_reset"
    ACCOUNT_INVITATION = "account_invitation"


class AccountEmailStatus(StrEnum):
    """Durable state of a security-sensitive account email request."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CheckJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEAD = "dead"
    CANCELLED = "cancelled"


class CheckJobKind(StrEnum):
    CHECK = "check"
    SNAPSHOT = "snapshot"


class CheckJobSource(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    REDRIVE = "redrive"


class EmailChannelName(StrEnum):
    SMTP = "smtp"
    BREVO = "brevo"
    LOG = "log"


class RetryStatus(StrEnum):
    """Delivery/analysis retry state for a change event."""

    REQUIRES_ACTION = "requires_action"


class AlertCode(StrEnum):
    """Operational problems detected while capturing a site."""

    SELECTOR_MISSING = "selector_missing"
    BLOCKED = "blocked"
    CAPTURE_FAILED = "capture_failed"
