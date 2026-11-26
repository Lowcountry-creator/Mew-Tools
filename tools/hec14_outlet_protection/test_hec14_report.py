"""Tests for the paged HTML/PDF report."""

from pathlib import Path

import pytest

import hec14_outlet_protection as h
import hec14_report
import hy8_io
from _report import export_pdf, find_pdf_browser

HERE = Path(__file__).parent / "examples"
HY8 = HERE / "HY8_Demo_Culverts.hy8"


def _items(keys=("culv1", "culv2", "culv4")):
    return [(h.EXAMPLES[k], h.analyze(h.EXAMPLES[k])) for k in keys]


def test_html_structure_and_logo():
    html = hec14_report.render_html(_items(), {"prepared_by": "JMW"})
    # Cover plus four pages per culvert.
    assert html.count("<section class='page") == 1 + 3 * 4
    assert "data:image/svg+xml;base64," in html
    assert "Culvert Outlet Protection Calculations" in html
    assert "Prepared by:</b> JMW" in html
    # Key numbers and strings from the workbook appear on the pages.
    assert "Class D 0 to 56 ft. Class C 56 to 108 ft." in html
    assert "Valid riprap basin for the trial stone" in html
    assert "Page 13 of 13" in html
    # Contents has one entry per culvert.
    assert html.count("<li><span>Culvert ") == 3


def test_custom_logo_and_presentation(tmp_path):
    png = tmp_path / "logo.png"
    png.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"))
    doc, meta = hec14_report.build_document(
        _items(("culv1",)), {"title": "Test Title", "project_number": "P-1"},
        str(png))
    assert meta["media_type"] == "image/png"
    assert meta["default"] is False
    html = doc.render()
    assert "data:image/png;base64," in html
    assert "<title>Test Title</title>" in html
    assert "P-1" in html
    with pytest.raises(ValueError):
        hec14_report.build_document(_items(("culv1",)), None,
                                    str(tmp_path / "missing.svg"))


def test_source_page_from_hy8():
    inp = hy8_io.inputs_from_hy8(HY8, "Oak Creek Road", "Twin 6x4 Box",
                                 "50-yr", V_LB=[10, 7, 5, 4])
    assert inp.hy8_summary["flow_index"] == 3
    assert inp.hy8_summary["columns"][3] == "50-yr"
    labels = [r["label"] for r in inp.hy8_summary["rows"]]
    assert "Outlet Velocity" in labels and "Flow Type" in labels
    html = hec14_report.render_html([(inp, h.analyze(inp))])
    # Five pages for this culvert: the source page is added.
    assert html.count("<section class='page") == 1 + 5
    assert "HY-8 source data" in html
    assert "Culvert Summary Table - Twin 6x4 Box" in html
    assert "class='src'" in html  # design column highlighted
    assert "1-S2n" in html  # text cells survive


def test_write_report_html_only(tmp_path):
    out = hec14_report.write_report(_items(("culv2",)), tmp_path / "r.html")
    assert Path(out["html"]).exists()
    assert out["pdf"] is None
    assert out["pages"] == 5


def _browser():
    try:
        return find_pdf_browser()
    except RuntimeError:
        return None


@pytest.mark.skipif(_browser() is None, reason="no Edge/Chrome for PDF")
def test_write_report_pdf(tmp_path):
    """Real print-to-PDF through the local browser.

    Skips, rather than fails, where the browser cannot print at all (for
    example a sandbox that blocks Chrome's start-up network calls so the
    headless process never exits). A code defect raises a different error.
    """
    html = tmp_path / "r.html"
    hec14_report.write_report(_items(("culv1",)), html)
    try:
        pdf = export_pdf(html, tmp_path / "r.pdf", timeout=45)
    except RuntimeError as exc:
        text = str(exc)
        if "timed out" in text or "Playwright is not installed" in text:
            pytest.skip(f"browser cannot print here: {text[:120]}")
        raise
    assert pdf.read_bytes()[:5] == b"%PDF-"
    assert pdf.stat().st_size > 10_000


def test_cli_batch_and_html(tmp_path, capsys):
    batch = tmp_path / "batch.json"
    rc = h.main(["--example", "all", "--inputs-out", str(batch), "--out",
                 str(tmp_path / "all.txt")])
    assert rc == 0
    html = tmp_path / "batch.html"
    rc = h.main(["--batch", str(batch), "--html", str(html),
                 "--prepared-by", "JMW", "--report-date", "2026-11-22"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "HTML report" in err and "13 pages" in err
    text = html.read_text(encoding="utf-8")
    assert "2026-11-22" in text
    assert text.count("<li><span>Culvert ") == 3


def test_cli_pdf_without_browser_reports_error(tmp_path, capsys):
    rc = h.main(["--example", "culv1", "--pdf", str(tmp_path / "r.pdf"),
                 "--browser", str(tmp_path / "no-browser")])
    assert rc == 2
    assert "ERROR" in capsys.readouterr().err
    assert (tmp_path / "r.html").exists()  # HTML still written
