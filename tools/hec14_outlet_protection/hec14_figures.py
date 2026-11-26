"""Report figures for the HEC-14 outlet protection calc package.

SVG only, drawn with the HY-8_Exporter chart primitives in
``tools/_report/svgplot.py`` so the figures match that report's look.

Every value plotted comes from ``Inputs`` or ``Results``. Nothing is
computed here except positions on the page. Sketches are schematic: the
horizontal scale is true, the vertical scale is exaggerated, and riprap
thickness is drawn to a fixed size, not to the design thickness.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from _report.svgplot import (COLORS, FONT, Chart, legend,  # noqa: E402
                             polyline, text, unique_id)
from hec14_outlet_protection import (GIVES_BASIN, Inputs,  # noqa: E402
                                     Results)

# Riprap class fills, light to dark. Report CSS (.sw.cls-*) mirrors these.
CLASS_FILL = {"A": "#E7E5E4", "B": "#C8C2BC", "C": "#A39A92",
              "D": "#78706A"}
CLASS_OTHER = "#FCA5A5"  # larger than D or none of A to D: needs a look
PERM = "#047857"
CHANNEL = "#64748B"
LENGTH = "#0C4A6E"
BASIN = "#B45309"
RESULT_COLOR = {"Valid basin": "#047857", "No pool": "#64748B"}
# Drawing size in SVG units. Figures print about 5 in wide, so a narrower
# viewBox keeps the 10 to 11 unit labels readable.
FIG_W, FIG_H = 760, 400
MARGINS = (62, 18, 20, 50)


def _num(value) -> Optional[float]:
    """Float for a numeric result, None for a text result ('See block 7')."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def class_letter(label: str) -> str:
    """'D (1.80)' -> 'D'. Text labels ('Larger than D') come back as is."""
    head = str(label).split(" ")[0]
    return head if head in CLASS_FILL else str(label)


def class_fill(label: str) -> str:
    return CLASS_FILL.get(class_letter(label), CLASS_OTHER)


def lined_reaches(r: Results) -> List[Tuple[float, float, str]]:
    """(from ft, to ft, class label) for the reaches inside the length.

    Same rule as block 10 Option 1: each block 8 reach that starts inside
    the adopted length, cut off at that length.
    """
    length = _num(r.L_adopted)
    if length is None:
        return []
    out = []
    for x in r.reaches:
        if x.from_ft < length:
            out.append((float(x.from_ft), min(float(x.to_ft), length),
                        x.scdot_class))
    return out


def has_jet_velocities(inp: Inputs) -> bool:
    return any(v for v in inp.V_LB)


# --------------------------------------------------------------------------
# Velocity decay
# --------------------------------------------------------------------------


def velocity_decay_svg(inp: Inputs, r: Results) -> str:
    """Jet velocity against distance, with the limits and the length."""
    if not has_jet_velocities(inp):
        return ("<p class='callout'>Jet velocities at 1 to 4 LB are not "
                "entered, so there is no velocity decay to plot.</p>")
    pts = [(0.0, float(inp.Vo))] + [(float(L), float(V))
                                    for L, V in zip(r.decay_L, r.decay_V)]
    length = _num(r.L_adopted)
    L_target = _num(r.L_target)
    xs = [p[0] for p in pts] + [v for v in (length, L_target) if v]
    ys = [p[1] for p in pts] + [0.0, float(inp.V_perm),
                                float(inp.V_channel)]
    c = Chart(xs, ys, FIG_W, FIG_H, margins=MARGINS, y_floor=0.0,
              y_pad=0.08)
    clip = unique_id("vd")
    out = [c.open_svg("Jet velocity decay downstream of the outlet"),
           c.clip_def(clip), c.grid(), f"<g clip-path='url(#{clip})'>"]

    # Riprap reaches as a band along the bottom of the plot.
    band = 16
    for a, b, label in lined_reaches(r):
        x1, x2 = c.x(a), c.x(b)
        out.append(f"<rect x='{x1:.1f}' y='{c.baseline - band:.1f}' "
                   f"width='{x2 - x1:.1f}' height='{band}' "
                   f"fill='{class_fill(label)}' stroke='#FFFFFF'/>")
        if x2 - x1 > 60:
            out.append(text((x1 + x2) / 2, c.baseline - 4, f"Class "
                            f"{class_letter(label)}", 10, "middle", "600",
                            COLORS["ink"], halo=False))

    for y, name, color in ((float(inp.V_perm), "Permissible", PERM),
                           (float(inp.V_channel), "Channel (HY-8 TW)",
                            CHANNEL)):
        sy = c.y(y)
        out.append(f"<line x1='{c.left}' y1='{sy:.1f}' "
                   f"x2='{c.left + c.plot_w}' y2='{sy:.1f}' stroke='{color}' "
                   "stroke-width='1.6' stroke-dasharray='8 5'/>")
        out.append(text(c.left + c.plot_w - 8, sy - 5,
                        f"{name} {y:.2f} fps", 10.5, "end", "600", color))

    if length is not None:
        sx = c.x(length)
        out.append(f"<line x1='{sx:.1f}' y1='{c.top}' x2='{sx:.1f}' "
                   f"y2='{c.baseline:.1f}' stroke='{LENGTH}' "
                   "stroke-width='2'/>")
        out.append(text(sx - 6, c.top + 16, f"Protection length "
                        f"{length:g} ft", 10.5, "end", "700", LENGTH))

    out.append(polyline(c, pts, COLORS["water"], 2.6))
    for x, y in pts:
        sx, sy = c.xy(x, y)
        out.append(f"<circle cx='{sx:.1f}' cy='{sy:.1f}' r='3.2' "
                   f"fill='#FFFFFF' stroke='{COLORS['water']}' "
                   "stroke-width='1.8'/>")
    sx, sy = c.xy(0.0, float(inp.Vo))
    out.append(text(sx + 10, sy + 4, f"Vo {inp.Vo:.2f} fps", 10.5, "start",
                    "600", COLORS["water"]))
    if L_target is not None:
        sx, sy = c.xy(L_target, float(r.V_target))
        out.append(f"<circle cx='{sx:.1f}' cy='{sy:.1f}' r='6' "
                   f"fill='{COLORS['warning']}' stroke='#FFFFFF' "
                   "stroke-width='2'/>")
        out.append(text(sx + 10, sy - 10, f"Target {r.V_target:.2f} fps at "
                        f"{L_target:.1f} ft", 10.5, "start", "700",
                        COLORS["warning"]))
    out.append("</g>")
    out.append(c.axes("Distance downstream of the culvert outlet (ft)",
                      "Jet velocity (fps)"))
    out.append("</svg>")
    return "".join(out)


def velocity_legend() -> str:
    return legend([("jet", "HY-8 jet velocity"),
                   ("perm", "Permissible"),
                   ("chan", "Channel (tailwater)"),
                   ("len", "Protection length")])


# --------------------------------------------------------------------------
# Profile along the outlet centerline
# --------------------------------------------------------------------------


def profile_svg(inp: Inputs, r: Results) -> str:
    """Schematic profile: barrel end, brink depth, tailwater, riprap.

    Shows Option 1 (lined channel at bed grade) as built rock along the
    adopted length, and the Option 2 pool outline dashed when a basin
    applies. Datum is the outlet invert (bed at the brink).
    """
    length = _num(r.L_adopted) or 0.0
    basin = r.basin_applies == "Yes" and r.Lb
    far = max(length, float(r.Lb) if basin else 0.0, 4 * float(inp.Wo))
    x_end = far * 1.08
    x_barrel = -0.14 * x_end
    rise = float(r.D)
    top = max(rise, float(inp.TW), float(inp.yo)) * 1.18 + 0.5
    hs = float(r.hs) if basin else 0.0
    rock = max(0.06 * (top + hs), 0.35)  # drawn thickness, not to scale
    bottom = -(hs + rock) - 0.12 * top
    c = Chart([x_barrel, x_end], [bottom, top], FIG_W, FIG_H,
              margins=MARGINS, x_pad=0.0, y_pad=0.0, snap_x=False)
    clip = unique_id("pf")
    out = [c.open_svg("Outlet protection profile, schematic"),
           c.clip_def(clip), c.grid(), f"<g clip-path='url(#{clip})'>"]

    def rect(x1, y1, x2, y2, fill, stroke="none", extra=""):
        a, b = c.xy(x1, y2)
        w = c.x(x2) - c.x(x1)
        h = c.y(y1) - c.y(y2)
        return (f"<rect x='{a:.1f}' y='{b:.1f}' width='{w:.1f}' "
                f"height='{h:.1f}' fill='{fill}' stroke='{stroke}'{extra}/>")

    # Ground below the bed, and the fill around the barrel upstream.
    out.append(rect(c.x_lo, c.y_lo, c.x_hi, 0.0, COLORS["ground_fill"]))
    out.append(rect(c.x_lo, 0.0, 0.0, c.y_hi, COLORS["ground_fill"]))
    # Tailwater over the channel, brink water in the barrel.
    if inp.TW > 0:
        out.append(rect(0.0, 0.0, c.x_hi, float(inp.TW),
                        COLORS["water_fill"], extra=" fill-opacity='0.55'"))
    out.append(rect(c.x_lo, 0.0, 0.0, rise, COLORS["pipe_fill"],
                    COLORS["pipe"], " stroke-width='1.6'"))
    out.append(rect(c.x_lo, 0.0, 0.0, min(float(inp.yo), rise),
                    COLORS["water_fill"]))
    # Riprap along the adopted length, one block per reach and class.
    for a, b, label in lined_reaches(r):
        out.append(rect(a, -rock, b, 0.0, class_fill(label), "#FFFFFF"))
        sx = (c.x(a) + c.x(b)) / 2
        if c.x(b) - c.x(a) > 70:
            out.append(text(sx, c.y(-rock / 2) + 4,
                            f"Class {class_letter(label)}", 10, "middle",
                            "700", COLORS["ink"], halo=False))
    # Bed line.
    out.append(f"<line x1='{c.x(c.x_lo):.1f}' y1='{c.y(0):.1f}' "
               f"x2='{c.x(c.x_hi):.1f}' y2='{c.y(0):.1f}' "
               f"stroke='{COLORS['ground']}' stroke-width='1.8'/>")
    # Option 2 pool outline, schematic shape with the computed hs, Ls, Lb.
    if basin:
        Ls, Lb = float(r.Ls), float(r.Lb)
        pool = [(0.0, 0.0), (0.12 * Ls, -hs), (0.7 * Ls, -hs), (Ls, 0.0),
                (Lb, 0.0)]
        out.append(polyline(c, pool, BASIN, 2.2, dash="7 4"))
        out.append(text(c.x(0.4 * Ls), c.y(-hs) + 16,
                        f"Option 2 pool: hs {hs:.2f} ft, Ls {Ls:g} ft, "
                        f"La {float(r.La):g} ft", 10, "middle", "600",
                        BASIN))
    out.append(polyline(c, [(0.0, float(inp.TW)), (c.x_hi, float(inp.TW))],
                        COLORS["water"], 2.0))
    out.append("</g>")

    # Labels drawn over the frame-clipped art.
    out.append(text(c.x(c.x_lo) + 6, c.y(rise) - 6, f"Barrel D {rise:g} ft",
                    10.5, "start", "600", COLORS["pipe"]))
    out.append(text(c.x(c.x_lo) + 6, c.y(min(float(inp.yo), rise) / 2) + 4,
                    f"yo {inp.yo:.2f} ft", 10.5, "start", "700",
                    COLORS["water"]))
    out.append(text(c.x(c.x_hi) - 8, c.y(float(inp.TW)) - 6,
                    f"TW {inp.TW:.2f} ft", 10.5, "end", "700",
                    COLORS["water"]))
    if length:
        y_dim = c.top + 12
        x1, x2 = c.x(0.0), c.x(length)
        out.append(f"<line x1='{x1:.1f}' y1='{y_dim:.1f}' x2='{x2:.1f}' "
                   f"y2='{y_dim:.1f}' stroke='{LENGTH}' stroke-width='1.4'/>"
                   f"<line x1='{x1:.1f}' y1='{y_dim - 5:.1f}' x2='{x1:.1f}' "
                   f"y2='{y_dim + 5:.1f}' stroke='{LENGTH}'/>"
                   f"<line x1='{x2:.1f}' y1='{y_dim - 5:.1f}' x2='{x2:.1f}' "
                   f"y2='{y_dim + 5:.1f}' stroke='{LENGTH}'/>")
        out.append(text((x1 + x2) / 2, y_dim + 16, f"Protection length "
                        f"{length:g} ft (Option 1)", 10.5, "middle", "700",
                        LENGTH))
    out.append(c.axes("Distance downstream of the culvert outlet (ft)",
                      "Height above outlet invert (ft)"))
    out.append("</svg>")
    return "".join(out)


def profile_legend(r: Results) -> str:
    items = [("water", "Brink depth, tailwater"), ("pipe", "Barrel")]
    seen = []
    for _, _, label in lined_reaches(r):
        letter = class_letter(label)
        if letter not in seen:
            seen.append(letter)
            css = f"cls-{letter}" if letter in CLASS_FILL else "cls-x"
            items.append((css, f"Riprap Class {letter}"
                          if letter in CLASS_FILL else letter))
    if r.basin_applies == "Yes":
        items.append(("basin", "Option 2 pool"))
    return legend(items)


# --------------------------------------------------------------------------
# Riprap basin plan (Option 2) or stone check chart
# --------------------------------------------------------------------------


def basin_plan_svg(inp: Inputs, r: Results) -> str:
    """Plan of the Sec 10.1 basin at true scale: flare, pool, apron."""
    Wo, Ls, La = float(inp.Wo), float(r.Ls), float(r.La)
    Lb, Wb = float(r.Lb), float(r.Wb)
    width, height = FIG_W, 350
    left, right, top, bottom = 120, 120, 34, 56
    x_lo, x_hi = -0.15 * Lb, Lb
    scale = min((width - left - right) / (x_hi - x_lo),
                (height - top - bottom) / Wb)
    cx = left + ((width - left - right) - (x_hi - x_lo) * scale) / 2
    cy = top + (height - top - bottom) / 2

    def p(x, y):
        return cx + (x - x_lo) * scale, cy - y * scale

    def poly(pts, fill, stroke=COLORS["frame"]):
        pts_attr = " ".join("%.1f,%.1f" % p(x, y) for x, y in pts)
        return (f"<polygon points='{pts_attr}' fill='{fill}' "
                f"stroke='{stroke}' stroke-width='1.4'/>")

    def half_w(x):  # 1:3 flare each side, so Wb = Wo + 2/3 (Ls + La)
        return (Wo + 2.0 / 3.0 * x) / 2

    def dim(x1, y1, x2, y2, label, anchor):
        a, b = p(x1, y1)
        d, e = p(x2, y2)
        vertical = abs(a - d) < 1
        out = (f"<line x1='{a:.1f}' y1='{b:.1f}' x2='{d:.1f}' y2='{e:.1f}' "
               f"stroke='{LENGTH}' stroke-width='1.3'/>")
        for u, v in ((a, b), (d, e)):
            if vertical:
                out += (f"<line x1='{u - 5:.1f}' y1='{v:.1f}' "
                        f"x2='{u + 5:.1f}' y2='{v:.1f}' stroke='{LENGTH}'/>")
            else:
                out += (f"<line x1='{u:.1f}' y1='{v - 5:.1f}' "
                        f"x2='{u:.1f}' y2='{v + 5:.1f}' stroke='{LENGTH}'/>")
        if vertical:
            dx = 8 if anchor == "start" else -8
            return out + text(a + dx, (b + e) / 2 + 4, label, 10.5, anchor,
                              "700", LENGTH)
        return out + text((a + d) / 2, b + 16, label, 10.5, "middle", "700",
                          LENGTH)

    out = [f"<svg class='chart' viewBox='0 0 {width} {height}' "
           "preserveAspectRatio='xMidYMid meet' role='img' "
           f"aria-label='Riprap basin plan' font-family='{FONT}'>"
           f"<rect width='{width}' height='{height}' fill='#FFFFFF'/>"]
    out.append(poly([(x_lo, -Wo / 2), (0, -Wo / 2), (0, Wo / 2),
                     (x_lo, Wo / 2)], COLORS["pipe_fill"]))
    out.append(poly([(0, -Wo / 2), (Ls, -half_w(Ls)), (Ls, half_w(Ls)),
                     (0, Wo / 2)], CLASS_FILL["B"]))
    out.append(poly([(Ls, -half_w(Ls)), (Lb, -Wb / 2), (Lb, Wb / 2),
                     (Ls, half_w(Ls))], CLASS_FILL["A"]))
    # Labels outside the outline so narrow basins stay readable.
    x0, y0 = p(Ls / 2, half_w(Ls / 2))
    out.append(text(x0, y0 - 8, f"Pool: Ls {Ls:g} ft, hs {r.hs:.2f} ft",
                    10.5, "middle", "700", COLORS["ink"]))
    x0, y0 = p(Ls + La / 2, -half_w(Ls + La / 2))
    out.append(text(x0, y0 + 16, f"Apron: La {La:g} ft", 10.5, "middle",
                    "700", COLORS["ink"]))
    x0, y0 = p(x_lo / 2, Wo / 2)
    out.append(text(x0, y0 - 8, "Culvert", 10.5, "middle", "600",
                    COLORS["pipe"]))
    out.append(dim(x_lo - 14 / scale, -Wo / 2, x_lo - 14 / scale, Wo / 2,
                   f"Wo {Wo:g} ft", "end"))
    out.append(dim(Lb + 14 / scale, -Wb / 2, Lb + 14 / scale, Wb / 2,
                   f"Wb {Wb:.1f} ft", "start"))
    y_dim = -Wb / 2 - 30 / scale
    out.append(dim(0, y_dim, Lb, y_dim, f"Ls + La = {Lb:g} ft", "middle"))
    out.append("</svg>")
    return "".join(out)


def stone_check_svg(inp: Inputs, r: Results) -> str:
    """Block 4: envelope pool depth for the trial stone and each class."""
    stones = [s for s in [r.trial] + list(r.classes) if s is not None]
    if not stones:
        return "<p class='callout'>No stone checks to plot.</p>"
    ye = float(r.ye)
    xs = [s.D50 for s in stones] + [0.0, 0.7 * ye]
    ys = [s.hs_envelope for s in stones] + [0.0]
    ys += [2 * max(s.D50 for s in stones)]
    c = Chart(xs, ys, FIG_W, 330, margins=MARGINS, y_pad=0.08)
    clip = unique_id("sc")
    out = [c.open_svg("Scour pool depth by stone size"), c.clip_def(clip),
           c.grid(), f"<g clip-path='url(#{clip})'>"]
    # D50/ye range where Eq. 10.1 applies.
    a, b = c.x(0.1 * ye), c.x(0.7 * ye)
    out.append(f"<rect x='{a:.1f}' y='{c.top}' width='{b - a:.1f}' "
               f"height='{c.plot_h}' fill='#ECFDF5'/>")
    out.append(text(a + 6, c.top + 15, "0.1 <= D50/ye <= 0.7", 10, "start",
                    "600", PERM))
    zero = c.y(0.0)
    out.append(f"<line x1='{c.left}' y1='{zero:.1f}' "
               f"x2='{c.left + c.plot_w}' y2='{zero:.1f}' "
               f"stroke='{COLORS['ground']}' stroke-width='1.6'/>")
    out.append(polyline(c, [(c.x_lo, 2 * c.x_lo), (c.x_hi, 2 * c.x_hi)],
                        BASIN, 1.6, dash="8 5"))
    out.append(text(c.x(c.x_hi) - 8, c.y(2 * c.x_hi) + 16, "hs = 2 D50",
                    10.5, "end", "600", BASIN))
    out.append("</g>")
    groups = {}  # the trial stone often equals a class: one point, one label
    for s in stones:
        groups.setdefault(round(s.D50, 6), []).append(s)
    for same in groups.values():
        s = same[0]
        sx, sy = c.xy(s.D50, s.hs_envelope)
        color = RESULT_COLOR.get(s.result, BASIN)
        name = ", ".join(x.label for x in same)
        out.append(f"<circle cx='{sx:.1f}' cy='{sy:.1f}' r='5.5' "
                   f"fill='{color}' stroke='#FFFFFF' stroke-width='1.6'/>")
        out.append(text(sx + 8, sy - 7, name, 10.5, "start", "700", color))
    out.append(c.axes("Stone size D50 (ft)",
                      "Envelope pool depth hs (ft)"))
    out.append("</svg>")
    return "".join(out)


def stone_legend() -> str:
    return legend([("valid", "Valid basin"), ("nopool", "No pool, hs <= 0"),
                   ("warnpt", "Outside Eq. 10.1 limits"),
                   ("basin", "hs = 2 D50")])


def lower_figure(inp: Inputs, r: Results) -> Tuple[str, str, str]:
    """(title, svg, legend) for the lower figure on the figures page."""
    if r.basin_applies == "Yes" and r.trial_gives == GIVES_BASIN and r.Lb:
        return ("Option 2 riprap basin, plan at true scale, 1:3 flare",
                basin_plan_svg(inp, r),
                legend([("cls-B", "Pool"), ("cls-A", "Apron"),
                        ("pipe", "Culvert barrels")]))
    return ("Riprap basin check, HEC-14 Eq. 10.1 (Envelope Curve)",
            stone_check_svg(inp, r), stone_legend())
