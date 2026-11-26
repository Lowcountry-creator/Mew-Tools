"""Dependency-free SVG chart primitives shared by every report figure.

Copied from HY-8_Exporter (hy8_exporter/svgplot.py; MIT, same author) so
Mew-Tools figures use the same palette, tick logic, fonts and axis
treatment as the HY-8 Exporter report.
"""

import html
import math

# One palette for every figure. Report CSS mirrors these values.
COLORS = {
    "ink": "#0F172A",
    "text": "#1E293B",
    "muted": "#64748B",
    "grid": "#E2E8F0",
    "grid_major": "#CBD5E1",
    "frame": "#334155",
    "ground": "#7C5A3A",
    "ground_fill": "#EADBC4",
    "pipe": "#334155",
    "pipe_fill": "#F1F5F9",
    "structure_fill": "#FFFFFF",
    "water": "#1D4ED8",
    "water_fill": "#93C5FD",
    "hgl": "#1D4ED8",
    "bank": "#0F766E",
    "warning": "#B91C1C",
    "caution": "#B45309",
    "accent": "#0C4A6E",
}

FONT = "Segoe UI, Arial, Helvetica, sans-serif"
_ID_COUNTER = [0]


def unique_id(prefix):
    """Document-unique SVG element ID (clip paths must not collide)."""
    _ID_COUNTER[0] += 1
    return f"{prefix}{_ID_COUNTER[0]}"


def esc(value):
    """Escape text for SVG/HTML output."""
    return html.escape(str(value))


def nice_step(span, target=6):
    """Return a 1-2-2.5-5 x 10^n step giving about `target` intervals."""
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / target
    magnitude = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * magnitude
        if step >= raw:
            return step
    return 10 * magnitude


def nice_range(low, high, target=6, pad_fraction=0.0):
    """Expand [low, high] to whole tick multiples; return (lo, hi, step)."""
    if low > high:
        low, high = high, low
    span = high - low
    if span == 0:
        span = abs(low) * 0.1 or 1.0
        low, high = low - span / 2, high + span / 2
    pad = span * pad_fraction
    low, high = low - pad, high + pad
    step = nice_step(high - low, target)
    lo = math.floor(low / step + 1e-9) * step
    hi = math.ceil(high / step - 1e-9) * step
    if hi <= lo:
        hi = lo + step
    return lo, hi, step


def tick_values(lo, hi, step):
    """Tick multiples of `step` inside [lo, hi], without floating drift."""
    first = math.ceil(lo / step - 1e-9)
    last = math.floor(hi / step + 1e-9)
    return [index * step for index in range(first, last + 1)]


def decimals_for(step):
    """Decimal places needed to print ticks of this step cleanly."""
    for places in range(5):
        if abs(round(step, places) - step) < 1e-9:
            return places
    return 4


def station_label(value, decimals=0):
    """Format a station in feet as engineering stationing, e.g. 12+50."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    hundreds = int(value // 100)
    remainder = value - hundreds * 100
    if decimals:
        text = f"{remainder:0{3 + decimals}.{decimals}f}"
        if text.startswith("100"):
            hundreds += 1
            text = f"{0:0{3 + decimals}.{decimals}f}"
    else:
        rounded = int(round(remainder))
        if rounded == 100:
            hundreds, rounded = hundreds + 1, 0
        text = f"{rounded:02d}"
    return f"{sign}{hundreds}+{text}"


class Chart:
    """Linear x/y chart frame with nice ticks and a shared visual style."""

    def __init__(
        self,
        x_values,
        y_values,
        width=1000,
        height=420,
        margins=(70, 24, 26, 56),
        x_target=8,
        y_target=6,
        x_pad=0.0,
        y_pad=0.06,
        y_floor=None,
        snap_x=True,
    ):
        self.width = width
        self.height = height
        self.left, self.right, self.top, self.bottom = margins
        if snap_x:
            self.x_lo, self.x_hi, self.x_step = nice_range(
                min(x_values), max(x_values), x_target, x_pad
            )
        else:
            # Data-tight horizontal range; ticks fall inside it.
            low, high = min(x_values), max(x_values)
            span = (high - low) or 1.0
            self.x_lo, self.x_hi = low - span * x_pad, high + span * x_pad
            self.x_step = nice_step(self.x_hi - self.x_lo, x_target)
        y_low = min(y_values)
        if y_floor is not None:
            y_low = max(min(y_low, y_floor), y_floor)
        self.y_lo, self.y_hi, self.y_step = nice_range(
            y_low, max(y_values), y_target, y_pad
        )
        if y_floor is not None and self.y_lo < y_floor:
            self.y_lo = y_floor
        self.plot_w = width - self.left - self.right
        self.plot_h = height - self.top - self.bottom

    def x(self, value):
        return self.left + (value - self.x_lo) / (self.x_hi - self.x_lo) * self.plot_w

    def y(self, value):
        return self.top + (self.y_hi - value) / (self.y_hi - self.y_lo) * self.plot_h

    def xy(self, x_value, y_value):
        return self.x(x_value), self.y(y_value)

    @property
    def baseline(self):
        return self.top + self.plot_h

    def vertical_exaggeration(self):
        """Ratio of vertical to horizontal drawing scale."""
        x_scale = self.plot_w / (self.x_hi - self.x_lo)
        y_scale = self.plot_h / (self.y_hi - self.y_lo)
        return y_scale / x_scale

    def open_svg(self, label, css_class="chart"):
        return (
            f"<svg class='{css_class}' viewBox='0 0 {self.width} {self.height}' "
            f"preserveAspectRatio='xMidYMid meet' role='img' "
            f"aria-label='{esc(label)}' font-family='{FONT}'>"
            f"<rect width='{self.width}' height='{self.height}' fill='#FFFFFF'/>"
        )

    def clip_def(self, clip_id):
        return (
            f"<defs><clipPath id='{clip_id}'><rect x='{self.left}' "
            f"y='{self.top}' width='{self.plot_w}' height='{self.plot_h}'/>"
            "</clipPath></defs>"
        )

    def grid(self):
        """Light grid at every tick; drawn under the data."""
        out = []
        for value in tick_values(self.x_lo, self.x_hi, self.x_step):
            sx = self.x(value)
            out.append(
                f"<line x1='{sx:.1f}' y1='{self.top}' x2='{sx:.1f}' "
                f"y2='{self.baseline:.1f}' stroke='{COLORS['grid']}' "
                "stroke-width='1'/>"
            )
        for value in tick_values(self.y_lo, self.y_hi, self.y_step):
            sy = self.y(value)
            out.append(
                f"<line x1='{self.left}' y1='{sy:.1f}' "
                f"x2='{self.left + self.plot_w}' y2='{sy:.1f}' "
                f"stroke='{COLORS['grid']}' stroke-width='1'/>"
            )
        return "".join(out)

    def axes(self, x_title, y_title, x_format=None, y_format=None):
        """Frame, ticks, tick labels, and axis titles; drawn over the data."""
        x_dec = decimals_for(self.x_step)
        y_dec = decimals_for(self.y_step)
        x_format = x_format or (lambda value: f"{value:,.{x_dec}f}")
        y_format = y_format or (lambda value: f"{value:,.{y_dec}f}")
        out = [
            f"<rect x='{self.left}' y='{self.top}' width='{self.plot_w}' "
            f"height='{self.plot_h}' fill='none' stroke='{COLORS['frame']}' "
            "stroke-width='1.2'/>"
        ]
        for value in tick_values(self.x_lo, self.x_hi, self.x_step):
            sx = self.x(value)
            out.append(
                f"<line x1='{sx:.1f}' y1='{self.baseline:.1f}' x2='{sx:.1f}' "
                f"y2='{self.baseline + 5:.1f}' stroke='{COLORS['frame']}'/>"
                f"<text x='{sx:.1f}' y='{self.baseline + 18:.1f}' "
                f"text-anchor='middle' font-size='11' fill='{COLORS['text']}'>"
                f"{esc(x_format(value))}</text>"
            )
        for value in tick_values(self.y_lo, self.y_hi, self.y_step):
            sy = self.y(value)
            out.append(
                f"<line x1='{self.left - 5}' y1='{sy:.1f}' x2='{self.left}' "
                f"y2='{sy:.1f}' stroke='{COLORS['frame']}'/>"
                f"<text x='{self.left - 8}' y='{sy + 4:.1f}' text-anchor='end' "
                f"font-size='11' fill='{COLORS['text']}'>"
                f"{esc(y_format(value))}</text>"
            )
        out.append(
            f"<text x='{self.left + self.plot_w / 2:.1f}' "
            f"y='{self.height - 10}' text-anchor='middle' font-size='12' "
            f"font-weight='600' fill='{COLORS['ink']}'>{esc(x_title)}</text>"
            f"<text transform='translate(16 {self.top + self.plot_h / 2:.1f}) "
            "rotate(-90)' text-anchor='middle' font-size='12' font-weight='600' "
            f"fill='{COLORS['ink']}'>{esc(y_title)}</text>"
        )
        return "".join(out)


def points_attr(points):
    """SVG points attribute from screen coordinates."""
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def polyline(chart, points, color, width=2.0, dash="", extra=""):
    """Draw a data polyline, splitting it where values are missing."""
    dash_attr = f" stroke-dasharray='{dash}'" if dash else ""
    segments, current = [], []
    for x_value, y_value in points:
        if x_value is None or y_value is None:
            if len(current) >= 2:
                segments.append(current)
            current = []
        else:
            current.append(chart.xy(x_value, y_value))
    if len(current) >= 2:
        segments.append(current)
    return "".join(
        f"<polyline points='{points_attr(segment)}' fill='none' "
        f"stroke='{color}' stroke-width='{width}' stroke-linejoin='round' "
        f"stroke-linecap='round'{dash_attr}{extra}/>"
        for segment in segments
    )


def text(x, y, value, size=11, anchor="start", weight="normal", color=None,
         halo=True, rotate=None, italic=False):
    """Text with an optional white backing box so labels stay legible over lines.

    The box replaces an SVG stroke halo, which some PDF viewers render as
    smeared blobs on bold colored text.
    """
    color = color or COLORS["text"]
    transform = f" transform='rotate({rotate} {x:.1f} {y:.1f})'" if rotate else ""
    style = " font-style='italic'" if italic else ""
    backing = ""
    if halo:
        # Approximate text width from character count (sans-serif average).
        per_char = size * (0.62 if weight in ("bold", "700", "600") else 0.56)
        width = len(str(value)) * per_char + 6
        height = size * 1.25
        left = {"start": x - 3, "middle": x - width / 2, "end": x - width + 3}[anchor]
        backing = (
            f"<rect x='{left:.1f}' y='{y - size * 0.95:.1f}' width='{width:.1f}' "
            f"height='{height:.1f}' rx='2' fill='#FFFFFF' fill-opacity='0.85'"
            f"{transform}/>"
        )
    return (
        backing
        + f"<text x='{x:.1f}' y='{y:.1f}' text-anchor='{anchor}' "
        f"font-size='{size}' font-weight='{weight}' fill='{color}'"
        f"{style}{transform}>{esc(value)}</text>"
    )


def wetted_spans(points, water_elevation):
    """Station ranges where the ground is below a level water surface."""
    spans = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        below1, below2 = y1 < water_elevation, y2 < water_elevation
        if below1 and below2:
            spans.append([x1, x2])
        elif below1 != below2 and y2 != y1:
            crossing = x1 + (water_elevation - y1) / (y2 - y1) * (x2 - x1)
            spans.append([x1, crossing] if below1 else [crossing, x2])
    merged = []
    for start, end in spans:
        if merged and abs(start - merged[-1][1]) < 1e-9:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


def water_polygons(points, water_elevation):
    """Closed polygons (data units) between the ground and a water level."""
    polygons = []
    for start, end in wetted_spans(points, water_elevation):
        shape = [(start, water_elevation)]
        for x_value, y_value in points:
            if start < x_value < end:
                shape.append((x_value, y_value))
        # Ground elevation at the span ends equals the water level by
        # construction (or the span starts at an end point below water).
        start_ground = _ground_at(points, start)
        end_ground = _ground_at(points, end)
        shape.insert(1, (start, start_ground))
        shape.append((end, end_ground))
        shape.append((end, water_elevation))
        polygons.append(shape)
    return polygons


def _ground_at(points, station):
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 <= station <= x2:
            if x2 == x1:
                return min(y1, y2)
            return y1 + (station - x1) / (x2 - x1) * (y2 - y1)
    return points[0][1] if station <= points[0][0] else points[-1][1]


def legend(items):
    """HTML legend row; items are (css swatch class, label)."""
    spans = "".join(
        f"<span><i class='sw {css}'></i>{esc(label)}</span>" for css, label in items
    )
    return f"<div class='legend'>{spans}</div>"
