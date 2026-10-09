"""Render the change-notification email.

Email clients are unforgiving, so the HTML is a single table with inline styles
rather than a modern stylesheet. A plain-text alternative is always produced so
the message degrades gracefully. All fixed copy comes from the localization
catalog, keyed by the caller's resolved email language.
"""

from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Environment, select_autoescape

from driftwatch.localization import DEFAULT_LANGUAGE, tr

_env = Environment(autoescape=select_autoescape(["html"]))

_PAGE_STYLE = "background:#0b1020;padding:32px 0;font-family:Segoe UI,Roboto,Arial,sans-serif"
_CARD_STYLE = "background:#11182e;border:1px solid #1e2a4a;border-radius:14px;overflow:hidden"
_BADGE_STYLE = "display:inline-block;font-size:12px;letter-spacing:.12em;text-transform:uppercase"
_BUTTON_STYLE = (
    "display:inline-block;color:#0b1020;text-decoration:none;font-weight:600;"
    "font-size:14px;padding:11px 20px;border-radius:9px"
)
_LINK_STYLE = "color:#7aa2ff;font-size:14px;word-break:break-all"

_HTML_TEMPLATE = _env.from_string(
    """\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{{ page_style }}">
  <tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="{{ card_style }}">
      <tr><td style="padding:24px 28px 8px">
        <span style="{{ badge_style }};color:{{ accent }}">{{ badge }}</span>
        <h1 style="margin:8px 0 0;color:#f1f5ff;font-size:20px;line-height:1.3">{{ headline }}</h1>
      </td></tr>
      <tr><td style="padding:12px 28px 0">
        <p style="margin:0;color:#aab4d4;font-size:15px;line-height:1.6">{{ summary }}</p>
      </td></tr>
      <tr><td style="padding:20px 28px">
        <a href="{{ site_url }}" style="{{ link_style }}">{{ site_url }}</a>
      </td></tr>
      <tr><td style="padding:0 28px 28px">
        <a href="{{ details_url }}" style="{{ button_style }}">{{ button_label }}</a>
      </td></tr>
      <tr><td style="padding:16px 28px;border-top:1px solid #1e2a4a">
        <span style="color:#5b678a;font-size:12px">{{ footer }}</span>
      </td></tr>
    </table>
  </td></tr>
</table>"""
)


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str


def render_change_email(
    *,
    site_label: str,
    site_url: str,
    headline: str,
    summary: str,
    significant: bool,
    details_url: str,
    detected_at: str,
    subject_template: str | None = None,
    intro: str | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> RenderedEmail:
    badge = tr(language, "badge.significant" if significant else "badge.change")
    accent = "#ffb454" if significant else "#7aa2ff"
    subject = _format_subject(subject_template, site_label, headline, significant, language)
    body = f"{intro}\n\n{summary}" if intro else summary
    return _render(
        subject=subject,
        badge=badge,
        accent=accent,
        headline=headline or tr(language, "headline.content_changed"),
        summary=body,
        site_url=site_url,
        site_label=site_label,
        details_url=details_url,
        detected_at=detected_at,
        language=language,
    )


def render_site_alert_email(
    *,
    site_label: str,
    site_url: str,
    title: str,
    detail: str,
    details_url: str,
    detected_at: str,
    language: str = DEFAULT_LANGUAGE,
) -> RenderedEmail:
    return _render(
        subject=f"{tr(language, 'alert.subject_prefix')} — {site_label}: {title}",
        badge=tr(language, "badge.action_needed"),
        accent="#ff6f91",
        headline=title,
        summary=detail,
        site_url=site_url,
        site_label=site_label,
        details_url=details_url,
        detected_at=detected_at,
        language=language,
    )


def render_password_reset_email(
    *,
    reset_url: str,
    valid_minutes: int,
    brand_name: str = "Driftwatch",
    language: str = DEFAULT_LANGUAGE,
) -> RenderedEmail:
    minutes = str(valid_minutes)
    html_body = _HTML_TEMPLATE.render(
        page_style=_PAGE_STYLE,
        card_style=_CARD_STYLE,
        badge_style=_BADGE_STYLE,
        button_style=f"{_BUTTON_STYLE};background:#7aa2ff",
        link_style=_LINK_STYLE,
        badge=tr(language, "badge.password_reset"),
        accent="#7aa2ff",
        headline=tr(language, "reset.headline"),
        summary=tr(language, "reset.summary", brand=brand_name, minutes=minutes),
        site_url=reset_url,
        details_url=reset_url,
        footer=brand_name,
        button_label=tr(language, "reset.button"),
    )
    text_body = (
        f"{tr(language, 'reset.text_intro', brand=brand_name, minutes=minutes)}\n{reset_url}\n\n"
        f"{tr(language, 'reset.ignore')}"
    )
    return RenderedEmail(
        subject=tr(language, "reset.subject", brand=brand_name),
        html_body=html_body,
        text_body=text_body,
    )


def render_account_invite_email(
    *,
    setup_url: str,
    valid_hours: int,
    brand_name: str = "Driftwatch",
    language: str = DEFAULT_LANGUAGE,
) -> RenderedEmail:
    hours = str(valid_hours)
    html_body = _HTML_TEMPLATE.render(
        page_style=_PAGE_STYLE,
        card_style=_CARD_STYLE,
        badge_style=_BADGE_STYLE,
        button_style=f"{_BUTTON_STYLE};background:#7aa2ff",
        link_style=_LINK_STYLE,
        badge=tr(language, "badge.account_invitation"),
        accent="#7aa2ff",
        headline=tr(language, "invite.headline"),
        summary=tr(language, "invite.summary", brand=brand_name, hours=hours),
        site_url=setup_url,
        details_url=setup_url,
        footer=brand_name,
        button_label=tr(language, "invite.button"),
    )
    text_body = (
        f"{tr(language, 'invite.text_intro', brand=brand_name, hours=hours)}\n{setup_url}\n\n"
        f"{tr(language, 'invite.ignore')}"
    )
    return RenderedEmail(
        subject=tr(language, "invite.subject", brand=brand_name),
        html_body=html_body,
        text_body=text_body,
    )


def _format_subject(
    template: str | None, site_label: str, headline: str, significant: bool, language: str
) -> str:
    if template and template.strip():
        # Plain placeholder replacement rather than str.format, which would let an
        # admin template reach object internals via "{site.__class__}" and friends.
        replacements = {
            "{site}": site_label,
            "{headline}": headline or tr(language, "headline.content_changed"),
            "{severity}": tr(language, "severity.significant" if significant else "severity.minor"),
        }
        rendered = template
        for token, value in replacements.items():
            rendered = rendered.replace(token, value)
        return rendered
    if headline:
        return f"{site_label}: {headline}"
    return f"{tr(language, 'badge.change')} — {site_label}"


def _render(
    *,
    subject: str,
    badge: str,
    accent: str,
    headline: str,
    summary: str,
    site_url: str,
    site_label: str,
    details_url: str,
    detected_at: str,
    language: str = DEFAULT_LANGUAGE,
) -> RenderedEmail:
    footer = f"{site_label} · {tr(language, 'footer.detected')} {detected_at}"
    html_body = _HTML_TEMPLATE.render(
        page_style=_PAGE_STYLE,
        card_style=_CARD_STYLE,
        badge_style=_BADGE_STYLE,
        button_style=f"{_BUTTON_STYLE};background:{accent}",
        link_style=_LINK_STYLE,
        badge=badge,
        accent=accent,
        headline=headline,
        summary=summary,
        site_url=site_url,
        details_url=details_url,
        footer=footer,
        button_label=tr(language, "button.view_change"),
    )
    text_body = (
        f"{badge}: {headline}\n\n{summary}\n\nPage: {site_url}\nDetails: {details_url}\n\n{footer}"
    )
    return RenderedEmail(subject=subject, html_body=html_body, text_body=text_body)
