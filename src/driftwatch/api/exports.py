"""Export detected changes to an XLSX workbook."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

from fastapi import APIRouter, Response
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import select
from sqlalchemy.orm import load_only

from driftwatch.api.deps import CurrentUser, SessionDep
from driftwatch.localization import normalize_language, tr
from driftwatch.models import ChangeEvent, Site

Row = tuple[object, ...]

router = APIRouter(prefix="/api/exports", tags=["exports"])

# A defensive ceiling so an export of a huge history can't materialize unbounded
# rows in memory; the rows are the most recent, matching the descending order.
_MAX_EXPORT_ROWS = 50_000

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_HEADER_KEYS = (
    "export.header.change",
    "export.header.site",
    "export.header.url",
    "export.header.detected_utc",
    "export.header.significant",
    "export.header.headline",
    "export.header.summary",
    "export.header.notified",
)


@router.get("/changes.xlsx")
async def export_changes(
    session: SessionDep,
    _: CurrentUser,
    site_id: int | None = None,
    project_id: int | None = None,
    lang: str = "en",
) -> Response:
    # The download belongs to the person clicking, so the UI passes its active
    # language; anything unsupported falls back to English.
    language = normalize_language(lang)
    query = (
        select(ChangeEvent, Site)
        .join(Site, Site.id == ChangeEvent.site_id)
        # The export never reads the diff body, so don't load the large
        # diff_text/diff_html columns just to throw them away.
        .options(
            load_only(
                ChangeEvent.id,
                ChangeEvent.created_at,
                ChangeEvent.significant,
                ChangeEvent.headline,
                ChangeEvent.summary,
                ChangeEvent.notified_at,
            )
        )
        .order_by(ChangeEvent.created_at.desc())
        .limit(_MAX_EXPORT_ROWS)
    )
    if site_id is not None:
        query = query.where(ChangeEvent.site_id == site_id)
    if project_id is not None:
        query = query.where(Site.project_id == project_id)
    rows = (await session.execute(query)).all()
    records = [
        (
            change.id,
            _safe_cell(site.name or site.url),
            _safe_cell(site.url),
            change.created_at.strftime("%Y-%m-%d %H:%M"),
            _significance(change.significant, language),
            _safe_cell(change.headline or ""),
            _safe_cell(change.summary or ""),
            tr(language, "export.value.yes" if change.notified_at else "export.value.no"),
        )
        for change, site in rows
    ]
    # Building the workbook is CPU/serialization work; keep it off the loop.
    content = await asyncio.to_thread(_build_workbook, records, language)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="driftwatch-changes.xlsx"'},
    )


def _build_workbook(records: Sequence[Row], language: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert isinstance(sheet, Worksheet)
    sheet.title = tr(language, "export.sheet.changes")
    sheet.append(tuple(tr(language, key) for key in _HEADER_KEYS))
    for record in records:
        sheet.append(record)
    _autosize(sheet)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _significance(significant: bool | None, language: str) -> str:
    if significant is None:
        return tr(language, "export.value.pending")
    return tr(language, "export.value.yes" if significant else "export.value.no")


def _safe_cell(value: str) -> str:
    """Neutralize spreadsheet formula injection: a cell that a spreadsheet would
    treat as a formula gets a leading apostrophe so it stays literal text."""
    return f"'{value}" if value[:1] in ("=", "+", "-", "@") else value


def _autosize(sheet: Worksheet) -> None:
    widths = [12, 28, 40, 18, 12, 40, 60, 10]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
