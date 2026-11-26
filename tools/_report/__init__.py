"""Shared paged HTML/PDF report frame for Mew-Tools calculators."""

from .document import (ASSETS, DEFAULT_LOGO, STYLESHEET, ReportDocument,  # noqa: F401
                       embedded_logo, esc, flag_cells, fmt, grid_table,
                       kv_table)
from .pdf_export import export_pdf, find_pdf_browser  # noqa: F401
from . import svgplot  # noqa: F401,E402
