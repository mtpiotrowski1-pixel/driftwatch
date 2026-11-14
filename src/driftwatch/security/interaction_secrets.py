"""Encrypted vault for values used by browser ``fill`` interaction steps.

Only opaque references are stored with a site. Plaintext is accepted at the
write boundary, encrypted immediately, and reconstructed in memory immediately
before capture. The encrypted envelope binds a value to its tenant, site, and
reference and approved origin so copying ciphertext or changing the destination
fails closed. Legacy envelopes require the user to enter the value again.
"""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING
from urllib.parse import quote
from uuid import uuid4

from bs4 import BeautifulSoup
from bs4.element import AttributeValueList
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.exceptions import InvalidRequest
from driftwatch.models import InteractionSecret, Site
from driftwatch.security.crypto import SecretBox
from driftwatch.security.origins import http_origin

if TYPE_CHECKING:
    from driftwatch.schemas import InteractionStepIn

_ENVELOPE_VERSION = 2
# Shorter fill values (an age, a country code, a PIN) also occur inside
# unrelated page content, such as a year or a price. In captured markup they are
# redacted only where they are a whole text node or attribute value.
_INLINE_REDACTION_MIN_LENGTH = 8


class InteractionSecretUnavailable(RuntimeError):
    """A stored reference cannot be safely resolved for capture."""


async def replace_site_interaction_steps(
    session: AsyncSession,
    box: SecretBox,
    site: Site,
    steps: Sequence[InteractionStepIn],
) -> None:
    """Replace a site's script and remove encrypted values it no longer uses.

    Existing references may be retained only by the site that owns them. New
    plaintext values are encrypted before the resulting step JSON is assigned.
    The surrounding request transaction makes the script and vault rotation
    atomic.
    """

    stored_steps: list[dict[str, object]] = []
    retained_refs: set[str] = set()

    for step in steps:
        stored: dict[str, object] = {
            "action": step.action,
            "selector": step.selector,
            "timeout_ms": step.timeout_ms,
        }
        if step.action == "fill":
            if step.secret_value is not None:
                reference = str(uuid4())
                plaintext = step.secret_value.get_secret_value()
                session.add(
                    InteractionSecret(
                        id=reference,
                        organization_id=site.organization_id,
                        site_id=site.id,
                        ciphertext=box.encrypt(
                            _encode_envelope(
                                reference=reference,
                                organization_id=site.organization_id,
                                site_id=site.id,
                                origin=http_origin(site.url),
                                value=plaintext,
                            )
                        ),
                        version=_ENVELOPE_VERSION,
                    )
                )
            else:
                assert step.secret_ref is not None  # enforced by the request schema
                reference = str(step.secret_ref)
                existing = await session.scalar(
                    select(InteractionSecret).where(
                        InteractionSecret.id == reference,
                        InteractionSecret.site_id == site.id,
                        InteractionSecret.organization_id == site.organization_id,
                    )
                )
                if existing is None:
                    raise InvalidRequest("The interaction secret reference is invalid.")
                try:
                    _decode_envelope(
                        box.decrypt(existing.ciphertext),
                        reference=reference,
                        organization_id=site.organization_id,
                        site_id=site.id,
                        origin=http_origin(site.url),
                    )
                except InteractionSecretUnavailable as exc:
                    raise InvalidRequest(
                        "The fill secret does not belong to this origin. Enter the value again."
                    ) from exc
            stored["secret_ref"] = reference
            retained_refs.add(reference)
        stored_steps.append(stored)

    stale = delete(InteractionSecret).where(
        InteractionSecret.site_id == site.id,
        InteractionSecret.organization_id == site.organization_id,
    )
    if retained_refs:
        stale = stale.where(InteractionSecret.id.not_in(retained_refs))
    await session.execute(stale)
    site.interaction_steps = stored_steps


async def resolve_site_interaction_steps(
    session: AsyncSession, box: SecretBox | None, site: Site
) -> list[dict[str, object]]:
    """Resolve stored references into an ephemeral capture-only script."""

    raw_steps = site.interaction_steps or []
    references = {
        str(step.get("secret_ref"))
        for step in raw_steps
        if isinstance(step, dict)
        and step.get("action") == "fill"
        and step.get("secret_ref") is not None
    }
    secrets: dict[str, InteractionSecret] = {}
    if references:
        rows = (
            await session.execute(
                select(InteractionSecret).where(
                    InteractionSecret.id.in_(references),
                    InteractionSecret.site_id == site.id,
                    InteractionSecret.organization_id == site.organization_id,
                )
            )
        ).scalars()
        secrets = {row.id: row for row in rows}

    resolved: list[dict[str, object]] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            raise InteractionSecretUnavailable("Interaction configuration is invalid.")
        action = str(raw.get("action", ""))
        step: dict[str, object] = {
            "action": action,
            "selector": raw.get("selector"),
            "timeout_ms": raw.get("timeout_ms", 10_000),
        }
        if action == "fill":
            reference = raw.get("secret_ref")
            if not isinstance(reference, str):
                raise InteractionSecretUnavailable(
                    "A fill interaction is missing its encrypted secret. Update the step."
                )
            row = secrets.get(reference)
            if row is None or row.version != _ENVELOPE_VERSION or box is None:
                raise InteractionSecretUnavailable(
                    "An interaction secret is unavailable. Update the fill step."
                )
            plaintext = box.decrypt(row.ciphertext)
            rotated = box.rotate(row.ciphertext)
            if plaintext is not None and rotated is not None and rotated != row.ciphertext:
                row.ciphertext = rotated
            value = _decode_envelope(
                plaintext,
                reference=reference,
                organization_id=site.organization_id,
                site_id=site.id,
                origin=http_origin(site.url),
            )
            step["value"] = value
            step["allowed_origin"] = http_origin(site.url)
        resolved.append(step)
    return resolved


def redact_resolved_step_values(message: str, steps: Sequence[dict[str, object]]) -> str:
    """Remove every resolved value and its common encodings from an error message.

    A browser or capture adapter can repeat its arguments in an exception.
    Diagnostics lose nothing important when a short value is also replaced
    inside other words, so every value is removed wherever it occurs.
    """
    return _replace_variants(message, _fill_values(steps))


def redact_raw_markup(markup: str, steps: Sequence[dict[str, object]]) -> str:
    """Remove long resolved values from markup before it is parsed.

    Short values are left to :func:`redact_captured_html`: replacing them in raw
    markup could also rewrite tag names and attribute values.
    """
    return _replace_variants(markup, _inline_values(_fill_values(steps)))


def redact_captured_html(markup: str, steps: Sequence[dict[str, object]]) -> str:
    """Redact decoded text and attributes, including alternative HTML entities.

    Raw string replacement cannot cover every browser-valid entity spelling.
    Parsing first lets us compare the values that extraction would actually
    persist. A monitored page can echo an entered password or token into its
    DOM, and persisting that reflection would bypass the encrypted vault. This
    covers reflected plaintext and common encodings; it cannot stop a page that
    already received a value from intentionally transforming it.
    """
    values = _fill_values(steps)
    if not values:
        return markup
    inline = _inline_values(values)
    whole = {variant for value in values for variant in _variants(value)}

    def redact(text: str) -> str:
        stripped = text.strip()
        if stripped in whole:
            return text.replace(stripped, "[REDACTED]")
        return _replace_variants(text, inline)

    soup = BeautifulSoup(markup, "html.parser")
    for node in soup.find_all(string=True):
        original = str(node)
        redacted = redact(original)
        if redacted != original:
            node.replace_with(redacted)
    for tag in soup.find_all():
        for key, attribute in list(tag.attrs.items()):
            if isinstance(attribute, str):
                tag.attrs[key] = redact(attribute)
            elif isinstance(attribute, list):
                tag.attrs[key] = AttributeValueList([redact(str(item)) for item in attribute])
    return str(soup)


def _fill_values(steps: Sequence[dict[str, object]]) -> set[str]:
    return {
        value
        for step in steps
        if step.get("action") == "fill" and isinstance((value := step.get("value")), str) and value
    }


def _inline_values(values: set[str]) -> set[str]:
    return {value for value in values if len(value) >= _INLINE_REDACTION_MIN_LENGTH}


def _variants(value: str) -> set[str]:
    encodings = (
        value,
        html.escape(value, quote=True),
        html.escape(value, quote=False),
        quote(value, safe=""),
    )
    return {variant for variant in encodings if variant}


def _replace_variants(text: str, values: set[str]) -> str:
    variants = {variant for value in values for variant in _variants(value)}
    for variant in sorted(variants, key=len, reverse=True):
        text = text.replace(variant, "[REDACTED]")
    return text


def _encode_envelope(
    *, reference: str, organization_id: int, site_id: int, origin: str, value: str
) -> str:
    return json.dumps(
        {
            "version": _ENVELOPE_VERSION,
            "reference": reference,
            "organization_id": organization_id,
            "site_id": site_id,
            "origin": origin,
            "value": value,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_envelope(
    plaintext: str | None, *, reference: str, organization_id: int, site_id: int, origin: str
) -> str:
    try:
        payload = json.loads(plaintext) if plaintext is not None else None
    except (TypeError, json.JSONDecodeError) as exc:
        raise InteractionSecretUnavailable(
            "An interaction secret cannot be decrypted. Update the fill step."
        ) from exc
    if not isinstance(payload, dict) or (
        payload.get("version") != _ENVELOPE_VERSION
        or payload.get("reference") != reference
        or payload.get("organization_id") != organization_id
        or payload.get("site_id") != site_id
        or payload.get("origin") != origin
        or not isinstance(payload.get("value"), str)
    ):
        raise InteractionSecretUnavailable(
            "An interaction secret cannot be decrypted. Update the fill step."
        )
    value = payload["value"]
    assert isinstance(value, str)
    return value
