"""English/Polish string catalog for server-rendered artifacts.

The web UI ships its own catalogs; this one covers what the *server* renders
and sends out — notification and password-reset emails, webhook chat text,
operational alert titles, and the XLSX export. Emails and webhooks follow the
org-overridable ``email_language`` setting (resolved by the settings store);
the export endpoint takes an explicit ``lang`` from the UI instead, because a
download belongs to the person clicking, not to the organization.

Placeholders use plain ``str.replace`` substitution rather than ``str.format``
so a value containing braces (a brand name, a headline) can never reach
format-spec parsing.
"""

from __future__ import annotations

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "pl")
DEFAULT_LANGUAGE = "en"

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "badge.significant": "Significant change",
        "badge.change": "Change detected",
        "badge.action_needed": "Action needed",
        "badge.password_reset": "Password reset",
        "badge.account_invitation": "Account invitation",
        "headline.content_changed": "Content changed",
        "severity.significant": "significant",
        "severity.minor": "minor",
        "button.view_change": "View change",
        "footer.detected": "detected",
        "alert.subject_prefix": "Monitoring problem",
        "alert.selector_missing": "Monitored selector not found",
        "alert.blocked": "Page appears to be blocked",
        "alert.capture_failed": "Capture failed",
        "alert.generic": "Monitoring problem",
        "alert.site_down": "Site appears to be down",
        "alert.site_down_detail": (
            "The last {count} checks of this site failed in a row. Latest error: {detail}"
        ),
        "reset.subject": "Reset your {brand} password",
        "reset.headline": "Reset your password",
        "reset.summary": (
            "We received a request to reset your {brand} password. This link is "
            "valid for {minutes} minutes. If you did not request it, you can "
            "ignore this email — your password will not change."
        ),
        "reset.button": "Reset password",
        "reset.text_intro": "Reset your {brand} password (valid for {minutes} minutes):",
        "reset.ignore": "If you did not request this, ignore this email.",
        "invite.subject": "Set up your {brand} account",
        "invite.headline": "Your account is ready",
        "invite.summary": (
            "A workspace administrator invited you to {brand}. Use this single-use link to set "
            "your password within {hours} hours and activate your access."
        ),
        "invite.button": "Set password",
        "invite.text_intro": (
            "You were invited to {brand}. Use this single-use link within {hours} hours "
            "to set your password:"
        ),
        "invite.ignore": "If you were not expecting this invitation, ignore this email.",
        "export.sheet.changes": "Changes",
        "export.header.change": "Change",
        "export.header.site": "Site",
        "export.header.url": "URL",
        "export.header.detected_utc": "Detected (UTC)",
        "export.header.significant": "Significant",
        "export.header.headline": "Headline",
        "export.header.summary": "Summary",
        "export.header.notified": "Notified",
        "export.value.yes": "yes",
        "export.value.no": "no",
        "export.value.pending": "pending",
    },
    "pl": {
        "badge.significant": "Istotna zmiana",
        "badge.change": "Wykryto zmianę",
        "badge.action_needed": "Wymagana reakcja",
        "badge.password_reset": "Reset hasła",
        "badge.account_invitation": "Zaproszenie do konta",
        "headline.content_changed": "Treść się zmieniła",
        "severity.significant": "istotna",
        "severity.minor": "drobna",
        "button.view_change": "Zobacz zmianę",
        "footer.detected": "wykryto",
        "alert.subject_prefix": "Problem z monitorowaniem",
        "alert.selector_missing": "Nie znaleziono monitorowanego selektora",
        "alert.blocked": "Strona wygląda na zablokowaną",
        "alert.capture_failed": "Nie udało się pobrać strony",
        "alert.generic": "Problem z monitorowaniem",
        "alert.site_down": "Strona wygląda na niedostępną",
        "alert.site_down_detail": (
            "Ostatnie {count} sprawdzenia tej strony z rzędu nie powiodły się. "
            "Ostatni błąd: {detail}"
        ),
        "reset.subject": "Zresetuj hasło do {brand}",
        "reset.headline": "Zresetuj hasło",
        "reset.summary": (
            "Otrzymaliśmy prośbę o zresetowanie hasła do {brand}. Link jest ważny "
            "przez {minutes} minut. Jeśli to nie Ty, zignoruj tę wiadomość — "
            "hasło nie zostanie zmienione."
        ),
        "reset.button": "Zresetuj hasło",
        "reset.text_intro": "Zresetuj hasło do {brand} (link ważny przez {minutes} minut):",
        "reset.ignore": "Jeśli to nie Ty, zignoruj tę wiadomość.",
        "invite.subject": "Skonfiguruj konto w {brand}",
        "invite.headline": "Twoje konto jest gotowe",
        "invite.summary": (
            "Administrator przestrzeni roboczej zaprosił Cię do {brand}. Użyj tego "
            "jednorazowego linku, aby w ciągu {hours} godzin ustawić hasło i aktywować dostęp."
        ),
        "invite.button": "Ustaw hasło",
        "invite.text_intro": (
            "Otrzymujesz zaproszenie do {brand}. Użyj tego jednorazowego linku w ciągu "
            "{hours} godzin, aby ustawić hasło:"
        ),
        "invite.ignore": "Jeśli nie oczekujesz tego zaproszenia, zignoruj tę wiadomość.",
        "export.sheet.changes": "Zmiany",
        "export.header.change": "Zmiana",
        "export.header.site": "Strona",
        "export.header.url": "URL",
        "export.header.detected_utc": "Wykryto (UTC)",
        "export.header.significant": "Istotna",
        "export.header.headline": "Nagłówek",
        "export.header.summary": "Podsumowanie",
        "export.header.notified": "Powiadomiono",
        "export.value.yes": "tak",
        "export.value.no": "nie",
        "export.value.pending": "oczekuje",
    },
}


def normalize_language(value: str | None) -> str:
    """Collapse any stored or user-supplied value onto a supported language."""
    lowered = (value or "").strip().lower()
    return lowered if lowered in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def tr(language: str, key: str, **variables: str) -> str:
    """Look up ``key`` in ``language`` (falling back to English) and substitute
    ``{name}`` placeholders."""
    catalog = _STRINGS.get(language, _STRINGS[DEFAULT_LANGUAGE])
    text = catalog.get(key) or _STRINGS[DEFAULT_LANGUAGE][key]
    for name, value in variables.items():
        text = text.replace("{" + name + "}", value)
    return text
