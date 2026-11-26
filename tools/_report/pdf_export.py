"""Create a PDF from a self-contained HTML report using a local browser.

Uses Microsoft Edge or Google Chrome (or Chromium) in headless mode, so no
Python PDF dependency is needed. Set ``REPORT_PDF_BROWSER`` to a browser
executable to override the search. Ported from HY-8_Exporter.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

BROWSER_ENV = "REPORT_PDF_BROWSER"


def browser_candidates():
    """Return likely Edge/Chrome executables without requiring installation."""
    candidates = []
    override = os.environ.get(BROWSER_ENV)
    if override:
        candidates.append(Path(override))
    for command in (
        "msedge",
        "msedge.exe",
        "chrome",
        "chrome.exe",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))

    suffixes = (
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Google/Chrome/Application/chrome.exe"),
    )
    for environment_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(environment_name)
        if not base:
            continue
        for suffix in suffixes:
            candidates.append(Path(base) / suffix)
    return list(dict.fromkeys(candidates))


def find_pdf_browser(candidates=None):
    """Find a local Chromium-family browser that supports print-to-PDF."""
    for candidate in candidates or browser_candidates():
        path = Path(candidate)
        if path.is_file():
            return path
    raise RuntimeError(
        "PDF export requires Microsoft Edge or Google Chrome. The HTML report "
        "was still created. Open it and use Print to PDF, or install "
        f"Edge/Chrome (or set {BROWSER_ENV}) and export again."
    )


def pdf_command(browser_path, html_path, pdf_path):
    """Build the non-interactive browser command for a local HTML report."""
    return [
        str(Path(browser_path)),
        "--headless",
        "--disable-gpu",
        "--disable-extensions",
        "--run-all-compositor-stages-before-draw",
        "--no-pdf-header-footer",
        f"--print-to-pdf={Path(pdf_path).resolve()}",
        Path(html_path).resolve().as_uri(),
    ]


def _export_with_browser(html_file, pdf_file, browser_path=None, timeout=90):
    """Headless Edge/Chrome ``--print-to-pdf``. No Python dependency."""
    browser = Path(browser_path) if browser_path else find_pdf_browser()
    try:
        with tempfile.TemporaryDirectory(prefix="mew_report_pdf_") as profile:
            command = pdf_command(browser, html_file, pdf_file)
            command.insert(1, f"--user-data-dir={profile}")
            command.insert(2, "--no-first-run")
            if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
                # Chromium refuses to run as root on Linux without this flag.
                command.insert(3, "--no-sandbox")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Browser PDF export failed: {exc}") from exc
    if result.returncode != 0 or not pdf_file.is_file() or pdf_file.stat().st_size == 0:
        detail = (result.stderr or result.stdout or "no browser detail").strip()
        raise RuntimeError(f"Browser PDF export failed: {detail}")


def _export_with_playwright(html_file, pdf_file):
    """Playwright-driven Chromium, used when the plain browser call fails.

    Only available where the ``playwright`` package and its browser are
    installed (developer machines, CI). Not a requirement for users.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed") from exc
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(html_file.as_uri())
            page.pdf(path=str(pdf_file), prefer_css_page_size=True,
                     print_background=True)
        finally:
            browser.close()


def export_pdf(html_path, pdf_path, browser_path=None, backend=None,
               timeout=90):
    """Print a self-contained HTML report to PDF and verify the output.

    backend: "browser" (headless Edge/Chrome), "playwright", or "auto"
    (browser first, then Playwright). Default from ``REPORT_PDF_BACKEND``,
    else "auto". ``timeout`` is the seconds allowed for the browser call.
    """
    html_file = Path(html_path).resolve()
    pdf_file = Path(pdf_path).resolve()
    if not html_file.is_file():
        raise ValueError(f"HTML report does not exist: {html_file}")
    if html_file == pdf_file:
        raise ValueError("HTML input and PDF output paths must differ")
    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    backend = backend or os.environ.get("REPORT_PDF_BACKEND", "auto")
    if backend not in ("auto", "browser", "playwright"):
        raise ValueError("backend must be auto, browser or playwright")

    errors = []
    if backend in ("auto", "browser"):
        try:
            _export_with_browser(html_file, pdf_file, browser_path, timeout)
        except RuntimeError as exc:
            errors.append(str(exc))
            if backend == "browser":
                raise
    if backend == "playwright" or (backend == "auto" and errors):
        try:
            _export_with_playwright(html_file, pdf_file)
        except RuntimeError as exc:
            errors.append(str(exc))
            raise RuntimeError("; ".join(errors)) from exc
    if not pdf_file.is_file() or pdf_file.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError("Browser created a file that is not a valid PDF")
    return pdf_file
