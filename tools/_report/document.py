"""Paged HTML report frame shared by Mew-Tools calculators.

One header (logo, title, meta), one title bar and one footer on every page,
a cover with a metadata table, contents and an optional results grid. The
output is a single self-contained HTML file: the logo is embedded as a data
URI and the stylesheet is inlined, so it prints the same from any browser
and converts to PDF with ``pdf_export.export_pdf``.

Ported from HY-8_Exporter ``document.py`` (MIT, same author) with the
HY-8-specific status and pairing fields made optional so any tool can use
the frame. US Letter landscape, 0.4 in margins; see ``assets/report.css``.

Presentation keys (all optional unless noted)
    title            report title (required)
    kind             short label under the app name on the cover
    project_name, project_number, scenario, prepared_by, checked_by,
    report_date      shown in the header and the cover meta table
    cover_rows       list of (label, value) to replace the default meta rows
    header_meta      list of (label, value) to replace the default header meta
    source_names     list of source file names for the cover
    notes            free text on the cover
    disclaimer       small print on the cover
    status           EXTRACTED / REVIEW / BLOCKED; draws the status card
    status_text      explanation under the status
    cover_results    {"title", "rows", "columns", "limit", "more"} results grid
    app_label        footer left text, e.g. "Mew-Tools HEC-14 v1.0"
    author           footer author text
"""

import base64
from datetime import datetime
import hashlib
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
DEFAULT_LOGO = ASSETS / "logo.svg"
STYLESHEET = ASSETS / "report.css"
LOGO_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}
MAX_LOGO_BYTES = 5 * 1024 * 1024


def esc(value):
    return html.escape("" if value is None else str(value))


def embedded_logo(logo_path=None):
    """Return (data URI, audit metadata) for the user logo or the default."""
    path = Path(logo_path).expanduser() if logo_path else DEFAULT_LOGO
    if not path.is_file():
        raise ValueError(f"Logo file does not exist: {path}")
    media_type = LOGO_TYPES.get(path.suffix.lower())
    if not media_type:
        raise ValueError("Logo must be a PNG, JPG, GIF, or SVG file")
    content = path.read_bytes()
    if len(content) > MAX_LOGO_BYTES:
        raise ValueError("Logo file must be 5 MB or smaller")
    encoded = base64.b64encode(content).decode("ascii")
    metadata = {
        "name": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "media_type": media_type,
        "default": not bool(logo_path),
    }
    return f"data:{media_type};base64,{encoded}", metadata


def fmt(value, decimals=2, suffix=""):
    """Display a value; missing values print as n/a."""
    if value is None or value == "":
        return "n/a"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:,.{decimals}f}{suffix}"
    if isinstance(value, int):
        return f"{value:,}{suffix}"
    return f"{value}{suffix}"


def kv_table(rows, css="kv"):
    """Two-column label/value table; rows are (label, value, decimals, suffix).

    Use css="kv text" for long text values (left aligned, wrapping).
    """
    body = "".join(
        f"<tr><th>{esc(label)}</th><td>{esc(fmt(value, decimals, suffix))}</td></tr>"
        for label, value, decimals, suffix in rows
    )
    return f"<table class='{css}'>{body}</table>"


def grid_table(rows, columns, css="grid", cell_class=None):
    """Table from dict rows; columns are (label, key, decimals-or-None).

    decimals=None renders text; an integer renders a right-aligned number.
    cell_class(row, key, value) may return extra CSS classes for a cell.
    """
    head = "".join(f"<th>{esc(label)}</th>" for label, _, _ in columns)
    body = []
    for row in rows:
        cells = []
        for _, key, decimals in columns:
            value = row.get(key)
            classes = []
            if decimals is not None and isinstance(value, (int, float)) \
                    and not isinstance(value, bool):
                classes.append("num")
                shown = fmt(value, decimals)
            else:
                shown = fmt(value) if value is not None else ""
            if cell_class:
                extra = cell_class(row, key, value)
                if extra:
                    classes.append(extra)
            attr = f" class='{' '.join(classes)}'" if classes else ""
            cells.append(f"<td{attr}>{esc(shown)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    if not rows:
        body.append(f"<tr><td colspan='{len(columns)}'>No records.</td></tr>")
    return (
        f"<table class='{css}'><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def chunks(rows, size):
    """Split rows into pages; always return at least one (possibly empty)."""
    return [rows[i:i + size] for i in range(0, len(rows), size)] or [[]]


def flag_cells(row, key, value):
    """Default cell_class: red for keys listed in the row's ``_flags``."""
    return "flag" if key in row.get("_flags", ()) else ""


class ReportDocument:
    """Collect pages, then render a numbered, self-contained HTML document."""

    def __init__(self, presentation, logo_uri):
        self.presentation = presentation
        self.logo_uri = logo_uri
        self.pages = []  # dicts: title, body, subtitle, css
        self.toc = []  # (section title, first page index)
        self.generated = datetime.now().strftime("%m/%d/%Y %H:%M")

    def section(self, title):
        """Start a contents entry at the next page."""
        self.toc.append((title, len(self.pages)))

    def add_page(self, title, body, subtitle="", css=""):
        self.pages.append(
            {"title": title, "body": body, "subtitle": subtitle, "css": css})

    def add_table_pages(self, title, rows, columns, rows_per_page=18,
                        before="", after="", cell_class=None, css="grid"):
        """Paginate a table, repeating the header on every page."""
        pages = chunks(rows, rows_per_page)
        for number, chunk in enumerate(pages, 1):
            subtitle = f"Page {number} of {len(pages)}" if len(pages) > 1 else ""
            body = (
                (before if number == 1 else "")
                + grid_table(chunk, columns, css, cell_class)
                + (after if number == len(pages) else "")
            )
            self.add_page(title, body, subtitle)

    # Rendering -----------------------------------------------------------
    def _header(self):
        p = self.presentation
        sub = " | ".join(
            v for v in (p.get("project_name"), p.get("project_number")) if v)
        meta_rows = p.get("header_meta") or [
            ("Scenario", p.get("scenario")),
            ("Prepared by", p.get("prepared_by")),
            ("Date", p.get("report_date")),
        ]
        meta = "".join(
            f"<div><b>{esc(label)}:</b> {esc(value)}</div>"
            for label, value in meta_rows if value)
        return (
            "<header class='page-head'><div class='logo' role='img' "
            "aria-label='Logo'></div>"
            f"<div><div class='head-title'>{esc(p.get('title'))}</div>"
            f"<div class='head-sub'>{esc(sub)}</div></div>"
            f"<div class='head-meta'>{meta}</div></header>"
        )

    def _footer(self, number, total):
        p = self.presentation
        left = " | ".join(v for v in (p.get("app_label"), p.get("author")) if v)
        if p.get("status"):
            left += f" | Status: {esc(p['status'])}"
        return (
            "<footer class='page-foot'>"
            f"<span>{left}</span>"
            f"<span>Generated {esc(self.generated)}</span>"
            f"<span>Page {number} of {total}</span></footer>"
        )

    def _cover(self, total):
        p = self.presentation
        rows = p.get("cover_rows") or [
            ("Project", p.get("project_name")),
            ("Project No.", p.get("project_number")),
            ("Scenario", p.get("scenario")),
            ("Prepared by", p.get("prepared_by")),
            ("Checked by", p.get("checked_by")),
            ("Report date", p.get("report_date")),
            ("Source files", ", ".join(p.get("source_names", []))),
        ]
        meta = "".join(
            f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>"
            for label, value in rows if value)
        status_html = ""
        if p.get("status"):
            status_html = (
                f"<div class='status-card {esc(p['status'])}'><strong>Status: "
                f"{esc(p['status'])}</strong><br>{esc(p.get('status_text', ''))}"
                "</div>")
        notes = p.get("notes", "")
        toc_items = "".join(
            f"<li><span>{esc(title)}</span><span>p. {first + 2}</span></li>"
            for title, first in self.toc)
        results = p.get("cover_results")
        results_html = ""
        many = len(self.toc) > 9
        toc_lines = (len(self.toc) + 1) // 2 if many else len(self.toc)
        if results and results.get("rows"):
            limit = results.get("limit", 10) - max(0, toc_lines - 5)
            rows_shown = results["rows"][: max(3, limit)]
            more = ""
            if len(results["rows"]) > len(rows_shown):
                more = (f"<p class='note'>{len(rows_shown)} of "
                        f"{len(results['rows'])} items shown; all are in the "
                        f"{esc(results.get('more', 'report'))}.</p>")
            results_html = (
                f"<div class='cover-results'><h2>{esc(results.get('title', 'Results'))}</h2>"
                + grid_table(rows_shown, results["columns"], "grid compact",
                             flag_cells) + more + "</div>")
        disclaimer = p.get("disclaimer", "")
        return (
            f"<section class='page cover{' many' if many else ''}'>"
            "<div class='cover-top'><div class='cover-logo' role='img' "
            "aria-label='Logo'></div>"
            f"<div class='cover-kind'>{esc(p.get('app_label', ''))}<br>"
            f"{esc(p.get('kind', ''))}</div></div>"
            f"<h1>{esc(p.get('title'))}</h1>"
            f"<div class='cover-sub'>{esc(p.get('project_name') or p.get('kind'))}</div>"
            "<div class='cover-grid'><div>"
            f"<table class='meta-table'>{meta}</table>"
            + status_html
            + (f"<div class='notes'><b>Notes:</b> {esc(notes)}</div>" if notes else "")
            + "</div><div class='toc'><h2>Contents</h2>"
            f"<ol class='{'two-col' if many else ''}'>{toc_items}</ol>"
            + (f"<p class='disclaimer'>{esc(disclaimer)}</p>" if disclaimer else "")
            + "</div></div>"
            + results_html
            + self._footer(1, total)
            + "</section>"
        )

    def render(self, stylesheet=None, extra_css=""):
        css = stylesheet if stylesheet is not None else STYLESHEET.read_text(
            encoding="utf-8")
        total = len(self.pages) + 1
        parts = [
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width,initial-scale=1'>",
            f"<meta name='generator' content='{esc(self.presentation.get('app_label', 'Mew-Tools'))}'>",
            f"<title>{esc(self.presentation.get('title'))}</title>",
            f"<style>:root{{--logo:url('{self.logo_uri}')}}\n{css}\n{extra_css}</style>",
            "</head><body>",
            self._cover(total),
        ]
        header = self._header()
        for number, page in enumerate(self.pages, 2):
            subtitle = (f"<small>{esc(page['subtitle'])}</small>"
                        if page["subtitle"] else "")
            parts.append(
                f"<section class='page {page['css']}'>{header}"
                f"<div class='title-bar'><span>{esc(page['title'])}</span>"
                f"{subtitle}</div>"
                f"<div class='page-body'>{page['body']}</div>"
                f"{self._footer(number, total)}</section>"
            )
        parts.append("</body></html>")
        return "\n".join(parts)
