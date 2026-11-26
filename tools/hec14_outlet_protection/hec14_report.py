"""HTML and PDF report for the HEC-14 outlet protection calculator.

Lays the ten workbook blocks, and the HY-8 Culvert Summary Table the inputs
came from, onto US Letter landscape pages in the shared Mew-Tools frame
(``tools/_report``), the same frame HY-8_Exporter uses: logo, title bar,
footer with page numbers, cover with contents and a results grid.

One culvert gives five pages (six with HY-8 source data): a figures page
in the HY-8_Exporter style (profile sketch, velocity decay chart, basin
plan or stone check chart), then the calculation blocks. A batch gives
one document with a section per culvert.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# The shared report frame lives one folder up, in tools/_report.
_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from _report import (ReportDocument, embedded_logo, esc, export_pdf,  # noqa: E402
                     grid_table, kv_table)
import hec14_figures as fig  # noqa: E402
from hec14_outlet_protection import (GIVES_BASIN, Inputs, Results,  # noqa: E402
                                     __version__)

APP_LABEL = f"Mew-Tools HEC-14 Outlet Protection v{__version__}"
DEFAULT_TITLE = "Culvert Outlet Protection Calculations"
DEFAULT_KIND = "FHWA HEC-14 (3rd ed.) Chapter 10 with HY-8"
DISCLAIMER = (
    "Calculations follow FHWA HEC-14 (3rd ed.) Chapter 10 using outlet "
    "hydraulics from HY-8, typed or read from HY-8 files. Energy Dissipation "
    "values (jet velocities, pool depth HS) are transcribed from the HY-8 "
    "report. This document supports, and does not replace, the Engineer's "
    "review."
)

Item = Tuple[Inputs, Results]


def _h3(text: str) -> str:
    return f"<h3 class='rule'>{esc(text)}</h3>"


def _note(text: str) -> str:
    return f"<p class='note'>{esc(text)}</p>"


def _eq(text: str) -> str:
    return f"<p class='eq'>{esc(text)}</p>"


def _cols(left: str, right: str, css: str = "cols-2") -> str:
    return f"<div class='{css}'><div>{left}</div><div>{right}</div></div>"


def _name(inp: Inputs, index: int) -> str:
    return inp.culvert or f"Culvert {index}"


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


def _page_inputs(inp: Inputs, r: Results) -> str:
    lb_note = ("Ls + La (valid basin)" if r.trial_gives == GIVES_BASIN
               else "4 Wo (no basin)")
    inputs = [
        ("Design discharge, Q", inp.Q, 2, " cfs"),
        ("Outlet shape", inp.shape, 0, ""),
        ("Barrels", inp.barrels, 0, ""),
        ("Culvert width, Wo (all barrels)", inp.Wo, 2, " ft"),
        ("Culvert rise" + (" (diameter)" if inp.shape == "circular" else ""),
         inp.rise, 2, " ft"),
        ("Embedment", inp.embedment, 2, " ft"),
        ("Brink (outlet) depth, yo", inp.yo, 2, " ft"),
        ("Brink velocity, Vo", inp.Vo, 2, " fps"),
        ("Tailwater depth, TW", inp.TW, 2, " ft"),
        ("Channel velocity at design storm", inp.V_channel, 2, " fps"),
        ("Channel slope", inp.slope, 4, " ft/ft"),
        ("Permissible velocity, vegetated channel", inp.V_perm, 2, " fps"),
        ("Permissible shear, vegetated channel", inp.tau_perm, 2, " psf"),
        ("Riprap specific gravity, Ss", inp.Ss, 2, ""),
        ("Trial D50", inp.D50_trial, 2, " ft"),
        ("Minimum riprap class to specify", inp.min_class, 0, ""),
        ("HY-8 jet velocity at 1 LB", inp.V_LB[0], 3, " fps"),
        ("HY-8 jet velocity at 2 LB", inp.V_LB[1], 3, " fps"),
        ("HY-8 jet velocity at 3 LB", inp.V_LB[2], 3, " fps"),
        ("HY-8 jet velocity at 4 LB", inp.V_LB[3], 3, " fps"),
        ("HY-8 Pool Depth (HS), Envelope Curve", inp.HS_hy8, 3, " ft"),
        (f"Basin length LB, calculated: {lb_note}", r.LB, 2, " ft"),
    ]
    hydraulics = [
        ("Hydraulic rise, D = rise - embedment", r.D, 2, " ft"),
        ("Flow area at brink, A", r.A, 2, " ft2"),
        ("Critical depth, yc", r.yc, 3, " ft"),
        ("Outlet regime", r.regime, 0, ""),
        ("Check Vo = Q / A", r.Vo_check, 2, " fps"),
        ("Vo check", r.Vo_check_result, 0, ""),
        ("Equivalent depth, ye" + (" = yo" if inp.shape == "box"
                                   else " = (A/2)^0.5"), r.ye, 3, " ft"),
        ("Froude number, Fr = Vo / (g ye)^0.5", r.Fr, 3, ""),
        ("TW / ye", r.TW_ye, 3, ""),
        ("Tailwater case", r.tailwater_case, 0, ""),
    ]
    screen = [
        ("Riprap apron, Sec 10.2", r.apron_applicable, 0, ""),
        ("Riprap basin, Sec 10.1", r.basin_applicable, 0, ""),
        ("Hydraulic jump basins, Ch. 8", r.jump_basin, 0, ""),
    ]
    left = _h3("1. Inputs") + kv_table(inputs, "kv tight")
    if inp.description:
        left = _note(inp.description) + left
    right = (_h3("2. Outlet hydraulics") + kv_table(hydraulics, "kv text")
             + _h3("3. Applicability screen, HEC-14 Table 1.1")
             + kv_table(screen, "kv text")
             + _note("Fr is cited from this sheet. The Froude number on the "
                     "HY-8 dissipator screen may differ. TW/ye above 0.75 is "
                     "high tailwater (HEC-14 Sec 10.1.3)."))
    return _cols(left, right, "cols-2-wide")


def _figure(title: str, svg: str, legend: str, css: str) -> str:
    return (f"<div class='fig-block'>{_h3(title)}"
            f"<div class='figure {css}'>{svg}</div>{legend}</div>")


def _page_figures(inp: Inputs, r: Results) -> str:
    """Overview page: profile, velocity decay, basin plan or stone check."""
    length = (f"{r.L_adopted:g} ft" if isinstance(r.L_adopted, (int, float))
              else str(r.L_adopted))
    key = [
        ("Froude number, Fr", r.Fr, 2, ""),
        ("TW / ye, tailwater case", f"{r.TW_ye:.2f}, {r.tailwater_case}", 0,
         ""),
        ("Trial stone gives", r.trial_gives, 0, ""),
        ("Outlet protection length", length, 0, ""),
        ("Option 1, lined channel at bed grade", r.option_1, 0, ""),
        ("Option 2, riprap basin", r.option_2, 0, ""),
    ]
    top = _cols(
        _figure("Outlet protection profile (schematic)", fig.profile_svg(inp, r),
                fig.profile_legend(r), "sketch"),
        _figure("Jet velocity decay, HEC-14 Sec 10.1.3",
                fig.velocity_decay_svg(inp, r), fig.velocity_legend(),
                "sketch"))
    title, svg, legend = fig.lower_figure(inp, r)
    bottom = _cols(_figure(title, svg, legend, "lower"),
                   _h3("Key results") + kv_table(key, "kv text tight"))
    note = _note("Profile: horizontal to scale, vertical exaggerated, rock "
                 "thickness not to scale. Datum is the outlet invert. Values "
                 "are from the blocks on the following pages.")
    return top + bottom + note


def _page_source(inp: Inputs) -> Optional[str]:
    """HY-8 Culvert Summary Table the inputs were read from, if any."""
    src = inp.hy8_summary
    if not src:
        return None
    cols = src.get("columns", [])
    i = src.get("flow_index", -1)
    keys = [f"c{j}" for j in range(len(cols))]
    columns = [("Parameter", "label", None), ("Unit", "unit", None)]
    columns += [(c, k, None) for c, k in zip(cols, keys)]
    rows = []
    for row in src.get("rows", []):
        d: Dict = {"label": row["label"], "unit": row.get("unit", "")}
        texts = row.get("text") or [("" if v is None else f"{v:g}")
                                    for v in row.get("values", [])]
        for k, t in zip(keys, texts):
            d[k] = t
        if 0 <= i < len(keys):
            d["_src"] = keys[i]
        rows.append(d)

    def mark(row, key, value):
        return "src" if key == row.get("_src") else ""

    used = (f"Design storm column: {cols[i]}" if 0 <= i < len(cols)
            else "Design storm column not recorded")
    if src.get("results_note"):
        used += f". {src['results_note']}"
    mapping = [
        ("Q", "Culvert Discharge (this culvert, all barrels)", 0, ""),
        ("yo", "Outlet Depth", 0, ""),
        ("Vo", "Outlet Velocity", 0, ""),
        ("TW", "Tailwater Depth", 0, ""),
        ("Channel velocity", "Tailwater Velocity", 0, ""),
        ("Wo, rise, barrels, embedment, slope",
         f"{inp.hy8_file or 'HY-8 project file'} (.hy8)", 0, ""),
        ("Jet velocities, HS", "HY-8 Energy Dissipation screen, typed", 0, ""),
    ]
    return (_note(f"{src.get('table', 'Culvert Summary Table')}. {used}, "
                  "highlighted.")
            + grid_table(rows, columns, "grid compact", mark)
            + _h3("Block 1 fields taken from HY-8")
            + kv_table(mapping, "kv text tight"))


def _page_basin(inp: Inputs, r: Results) -> str:
    stones = []
    for s in [r.trial] + r.classes:
        stones.append({
            "stone": s.label, "d50": s.D50, "ratio": s.D50_ye,
            "hs": s.hs_envelope, "hsd50": s.hs_D50, "hsbf": s.hs_best_fit,
            "result": s.result,
        })
    columns = [
        ("Stone", "stone", None), ("D50 (ft)", "d50", 2),
        ("D50/ye", "ratio", 3), ("hs, envelope (ft)", "hs", 3),
        ("hs/D50", "hsd50", 2), ("hs, best fit (ft)", "hsbf", 3),
        ("Result (envelope)", "result", None),
    ]

    def color(row, key, value):
        if key != "result":
            return ""
        return {"Valid basin": "ok", "No pool": "",
                "hs/D50 below 2": "warn",
                "D50/ye out of range": "warn"}.get(value, "")

    c0 = [
        ("C0, Envelope Curve (Eq. 10.2), design", r.C0_envelope, 2, ""),
        ("C0, Best Fit Curve (Eq. 10.3), comparison", r.C0_best_fit, 2, ""),
    ]
    findings = [
        ("Result for trial D50", r.trial_result, 0, ""),
        ("Largest class giving a valid basin", r.largest_valid_class, 0, ""),
        ("Smallest class with no scour pool", r.smallest_no_pool_class, 0, ""),
        ("Tie to HY-8 Pool Depth (HS)", r.tie_to_hy8, 0, ""),
        ("Trial stone gives", r.trial_gives, 0, ""),
    ]
    left = (_h3("4. Riprap basin check, HEC-14 Eq. 10.1 (Sec 10.1)")
            + _eq("hs/ye = 0.86 (D50/ye)^-0.55 Fr - C0")
            + kv_table(c0)
            + grid_table(stones, columns, "grid compact", color)
            + _note("Valid basin needs 0.1 <= D50/ye <= 0.7, hs > 0 and "
                    "hs/D50 >= 2 (HEC-14 Sec 10.1.5 Step 2). Envelope Curve "
                    "is the design basis; Best Fit predicts a shallower pool "
                    "and is shown for comparison.")
            + kv_table(findings, "kv text"))
    if r.basin_applies == "Yes":
        geom = [
            ("Pool depth, hs", r.hs, 2, " ft"),
            ("Pool length, Ls = max(10 hs, 3 Wo)", r.Ls, 2, " ft"),
            ("Apron length, La = max(5 hs, Wo)", r.La, 2, " ft"),
            ("Basin length, Ls + La", r.Lb, 2, " ft"),
            ("Basin width at downstream end, Wo + 2/3 (Ls + La)", r.Wb, 2, " ft"),
            ("Riprap thickness, approach slope, 3 D50", r.t_approach, 2, " ft"),
            ("Riprap thickness, pool and apron, 2 D50", r.t_pool, 2, " ft"),
        ]
        right = (_h3("5. Riprap basin geometry, HEC-14 Sec 10.1")
                 + kv_table(geom)
                 + _note("Compare each to the HY-8 Riprap Basin screen. 1:3 "
                         "flare each side. Side slopes 2H:1V. Pool floor is "
                         "hs below the outlet bed. Final thickness per SCDOT "
                         "standard drawing."))
    else:
        right = (_h3("5. Riprap basin geometry, HEC-14 Sec 10.1")
                 + kv_table([("Basin applies?", "No", 0, "")], "kv text")
                 + _note("The trial stone does not give a valid basin. HY-8 "
                         "basin dimensions on screen are default minimums, "
                         "not a design. See block 10, Option 1."))
    return _cols(left, right, "cols-2-wide")


def _page_length(inp: Inputs, r: Results) -> str:
    decay = [{"station": f"{i} LB", "L": L, "V": V, "ratio": ratio}
             for i, (L, V, ratio) in enumerate(
                 zip(r.decay_L, r.decay_V, r.decay_ratio), 1)]
    decay.insert(0, {"station": "Outlet", "L": 0.0, "V": inp.Vo, "ratio": 1.0})
    dcols = [("Station", "station", None), ("L (ft)", "L", 1),
             ("Jet velocity (fps)", "V", 3), ("VL/Vo", "ratio", 3)]
    length = [
        ("High tailwater procedure applies?", r.high_tw_procedure, 0, ""),
        ("Channel velocity against permissible", r.channel_vs_perm, 0, ""),
        ("Target velocity", r.V_target, 2, " fps"),
        ("Length where jet velocity = target", r.L_target, 1, " ft"),
        ("Minimum length, 1 LB", r.L_min, 1, " ft"),
        ("Outlet protection length adopted (up to 6 ft)", r.L_adopted, 0, " ft"),
        ("Reference: length where jet = permissible velocity", r.L_perm, 1, " ft"),
    ]
    reaches = [{"reach": x.label, "from": x.from_ft, "to": x.to_ft, "V": x.V,
                "d50": x.D50_required, "cls": x.scdot_class,
                "within": x.within_protection} for x in r.reaches]
    rcols = [("Reach", "reach", None), ("From (ft)", "from", 0),
             ("To (ft)", "to", 0), ("V (fps)", "V", 3),
             ("Required D50 (ft)", "d50", 3), ("SCDOT class (d50 ft)", "cls", None),
             ("Within length?", "within", None)]

    def within(row, key, value):
        if key == "within":
            return "ok" if value == "Yes" else ""
        return ""

    left = (_h3("6. Downstream velocity decay, HEC-14 Sec 10.1.3 and Fig. 10.3")
            + grid_table(decay, dcols, "grid compact")
            + _note("Jet centerline velocities from the HY-8 report "
                    "(Downstream Riprap for High TW). LB is a reporting "
                    "interval, not a required length.")
            + _h3("7. Protection length")
            + kv_table(length, "kv text")
            + _note("Target is the larger of the permissible velocity and the "
                    "channel velocity (HEC-14 Sec 10.1.5 Step 4). Linear "
                    "interpolation between the HY-8 points at 0 to 4 LB."))
    right = (_h3("8. Riprap sizing, HEC-14 Eq. 10.6 (Sec 10.3)")
             + _eq("D50 = 0.692 V^2 / (2 g (Ss - 1))")
             + grid_table(reaches, rcols, "grid compact", within)
             + kv_table([("Headwall class for a lined channel with no pool",
                          r.headwall_class_lined, 0, "")], "kv text")
             + _note("Velocity at the upstream end of each reach governs. "
                     "Class is the smallest SCDOT class whose d50 meets the "
                     "requirement, not less than the minimum class in block "
                     "1. Headwall class also takes the smallest class with "
                     "no scour pool (block 4)."))
    return _cols(left, right)


def _page_summary(inp: Inputs, r: Results) -> str:
    channel = [
        ("Channel velocity against permissible", r.channel_vs_perm, 0, ""),
        ("Bed shear, tau = gamma x TW x S", r.tau, 3, " psf"),
        ("Shear against permissible shear", r.shear_result, 0, ""),
        ("Required riprap D50 for channel bed, tau / (0.047 (Ss - 1) gamma)",
         r.D50_channel, 3, " ft"),
        ("Channel riprap class, bed", r.channel_class, 0, ""),
        ("Receiving channel finding", r.channel_finding, 0, ""),
    ]
    summary = [
        ("Option 1, lined channel at bed grade (no pool)", r.option_1, 0, ""),
        ("Option 2, riprap basin (Sec 10.1)", r.option_2, 0, ""),
        ("Outlet protection length", r.L_adopted, 0, " ft"),
        ("Vertical limits", r.vertical_limits, 0, ""),
        ("Banks", r.banks, 0, ""),
        ("Basis", r.basis, 0, ""),
    ]
    left = (_h3("9. Receiving channel check at the design storm, HEC-15 "
                "(shear basis)")
            + kv_table(channel, "kv text")
            + _note("Depth used in place of hydraulic radius; conservative. "
                    "HEC-15 Shields form, bed only. Side slopes need larger "
                    "stone or flatter slopes."))
    right = _h3("10. Design summary") + kv_table(summary, "kv text")
    return _cols(left, right)


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------


def _cover_results(items: Sequence[Item]) -> Dict:
    rows = []
    for k, (inp, r) in enumerate(items, 1):
        row = {
            "culvert": _name(inp, k), "Q": inp.Q, "Fr": r.Fr, "tw": r.TW_ye,
            "vo": r.Vo_check_result, "gives": r.trial_gives,
            "L": r.L_adopted, "opt1": r.option_1, "_flags": [],
        }
        if r.Vo_check_result != "OK":
            row["_flags"].append("vo")
        rows.append(row)
    columns = [
        ("Culvert", "culvert", None), ("Q (cfs)", "Q", 1), ("Fr", "Fr", 2),
        ("TW/ye", "tw", 2), ("Vo check", "vo", None),
        ("Trial stone gives", "gives", None), ("Length (ft)", "L", 0),
        ("Option 1", "opt1", None),
    ]
    return {"title": "Results", "rows": rows, "columns": columns,
            "limit": 8, "more": "culvert sections"}


def build_document(items: Sequence[Item], presentation: Optional[Dict] = None,
                   logo_path: Optional[str] = None) -> Tuple[ReportDocument, Dict]:
    """Assemble the paged document. Returns (document, logo metadata)."""
    if not items:
        raise ValueError("No culverts to report")
    first = items[0][0]
    p = {
        "title": DEFAULT_TITLE,
        "kind": DEFAULT_KIND,
        "project_name": first.project,
        "scenario": first.design_storm,
        "app_label": APP_LABEL,
        "disclaimer": DISCLAIMER,
        "source_names": sorted({inp.hy8_file for inp, _ in items if inp.hy8_file}),
    }
    p.update({k: v for k, v in (presentation or {}).items() if v is not None})
    p.setdefault("cover_results", _cover_results(items))
    logo_uri, meta = embedded_logo(logo_path)
    doc = ReportDocument(p, logo_uri)
    for k, (inp, r) in enumerate(items, 1):
        name = _name(inp, k)
        doc.section(name)
        doc.add_page(f"{name}: outlet protection figures",
                     _page_figures(inp, r), inp.design_storm)
        doc.add_page(f"{name}: inputs and outlet hydraulics",
                     _page_inputs(inp, r), inp.design_storm)
        source = _page_source(inp)
        if source:
            doc.add_page(f"{name}: HY-8 source data", source, inp.hy8_file)
        doc.add_page(f"{name}: riprap basin check and geometry",
                     _page_basin(inp, r), inp.design_storm)
        doc.add_page(f"{name}: velocity decay, protection length, riprap sizing",
                     _page_length(inp, r), inp.design_storm)
        doc.add_page(f"{name}: receiving channel and design summary",
                     _page_summary(inp, r), inp.design_storm)
    return doc, meta


def render_html(items: Sequence[Item], presentation: Optional[Dict] = None,
                logo_path: Optional[str] = None) -> str:
    doc, _ = build_document(items, presentation, logo_path)
    return doc.render()


def write_report(items: Sequence[Item], html_path: str,
                 pdf_path: Optional[str] = None,
                 presentation: Optional[Dict] = None,
                 logo_path: Optional[str] = None,
                 browser: Optional[str] = None) -> Dict:
    """Write the HTML report and, if asked, print it to PDF.

    Returns {"html": path, "pdf": path or None, "logo": metadata}.
    """
    doc, meta = build_document(items, presentation, logo_path)
    html_file = Path(html_path)
    html_file.parent.mkdir(parents=True, exist_ok=True)
    html_file.write_text(doc.render(), encoding="utf-8")
    out = {"html": str(html_file), "pdf": None, "logo": meta,
           "pages": len(doc.pages) + 1}
    if pdf_path:
        out["pdf"] = str(export_pdf(html_file, pdf_path, browser))
    return out
