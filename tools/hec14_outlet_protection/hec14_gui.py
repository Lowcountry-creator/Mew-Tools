"""Window front end for the HEC-14 culvert outlet protection calculator.

A thin tkinter form over ``hec14_outlet_protection``. All engineering stays
in that module: this file only moves values between the form and an
``Inputs`` record, calls ``analyze`` and ``format_report``, and shows the
same text report the command line writes.

What it does
    - Block 1 inputs as a form, grouped the way the workbook groups them.
    - Load a built-in US176 example, or open and save an inputs JSON.
    - Import block 1 from an HY-8 project (.hy8) and its results (.rst),
      picking the crossing, culvert and flow from lists.
    - Run, read the report, save it as text, save full results as JSON.

Launch (Windows, from this folder)
    py hec14_gui.py          (console window stays open behind the app)
    pyw hec14_gui.py         (no console window)

Standard library only (tkinter ships with the python.org installer).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import hec14_outlet_protection as h

try:  # Tk is optional so the form helpers below import on headless Pythons.
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - depends on the Python build
    tk = None

APP_TITLE = "HEC-14 Culvert Outlet Protection"

# --------------------------------------------------------------------------
# Form layout. (key, label, unit). Keys V_LB_1..4 map to Inputs.V_LB.
# --------------------------------------------------------------------------

GROUPS: List[Tuple[str, List[Tuple[str, str, str]]]] = [
    ("Project", [
        ("project", "Project", ""),
        ("culvert", "Culvert", ""),
        ("description", "Description", ""),
        ("design_storm", "Design storm", ""),
        ("hy8_file", "HY-8 file", ""),
    ]),
    ("HY-8 Culvert Summary, design storm row", [
        ("Q", "Culvert discharge Q", "cfs"),
        ("yo", "Outlet depth yo", "ft"),
        ("Vo", "Outlet velocity Vo", "fps"),
        ("TW", "Tailwater depth TW", "ft"),
        ("V_channel", "Tailwater velocity", "fps"),
    ]),
    ("Culvert and channel", [
        ("shape", "Shape", ""),
        ("barrels", "Barrels", ""),
        ("Wo", "Total clear width Wo", "ft"),
        ("rise", "Rise (diameter if circular)", "ft"),
        ("embedment", "Embedment", "ft"),
        ("slope", "Channel slope (blank skips block 9)", "ft/ft"),
    ]),
    ("Limits and trial stone", [
        ("V_perm", "Permissible velocity", "fps"),
        ("tau_perm", "Permissible shear", "psf"),
        ("Ss", "Riprap specific gravity", ""),
        ("D50_trial", "Trial D50", "ft"),
        ("min_class", "Minimum SCDOT class", ""),
    ]),
    ("HY-8 Energy Dissipation screen (typed)", [
        ("V_LB_1", "Jet velocity at 1 LB", "fps"),
        ("V_LB_2", "Jet velocity at 2 LB", "fps"),
        ("V_LB_3", "Jet velocity at 3 LB", "fps"),
        ("V_LB_4", "Jet velocity at 4 LB", "fps"),
        ("HS_hy8", "Pool depth HS (blank if none)", "ft"),
    ]),
]

FORM_KEYS = [key for _, rows in GROUPS for key, _, _ in rows]
LABELS = {key: label for _, rows in GROUPS for key, label, _ in rows}
V_LB_KEYS = ["V_LB_1", "V_LB_2", "V_LB_3", "V_LB_4"]

STR_FIELDS = {"project", "culvert", "description", "design_storm",
              "hy8_file", "shape", "min_class"}
INT_FIELDS = {"barrels"}
OPTIONAL_FIELDS = {"slope", "HS_hy8"}  # blank means None
CHOICES = {"shape": sorted(h.SHAPES), "min_class": list(h.CLASS_NAMES)}

# Values HY-8 does not write to a file. Kept from the form on an HY-8 import.
TYPED_ONLY = ("V_LB", "HS_hy8", "D50_trial", "min_class", "V_perm",
              "tau_perm")


# --------------------------------------------------------------------------
# Form <-> Inputs. No Tk here, so these are unit tested on any Python.
# --------------------------------------------------------------------------


def _num_text(x) -> str:
    """Number as typed text: 10 significant figures, no trailing zeros."""
    if x is None:
        return ""
    if isinstance(x, int) and not isinstance(x, bool):
        return str(x)
    return format(float(x), ".10g")


def _parse_number(text: str):
    """Typed text -> int when it is a plain whole number, else float."""
    try:
        return int(text)
    except ValueError:
        return float(text)


def inputs_to_form(inp: "h.Inputs") -> Dict[str, str]:
    """Inputs record -> {form key: text}."""
    out: Dict[str, str] = {}
    for key in FORM_KEYS:
        if key in V_LB_KEYS:
            i = V_LB_KEYS.index(key)
            out[key] = _num_text(inp.V_LB[i]) if i < len(inp.V_LB) else ""
        elif key in STR_FIELDS:
            out[key] = str(getattr(inp, key) or "")
        else:
            out[key] = _num_text(getattr(inp, key))
    return out


def form_to_inputs(values: Dict[str, str],
                   base: Optional["h.Inputs"] = None) -> "h.Inputs":
    """{form key: text} -> validated Inputs.

    Fields not on the form (g, gamma_w) come from ``base``. Raises
    ValueError naming the form label of the first bad entry.
    """
    data = asdict(base) if base is not None else asdict(h.Inputs())
    v_lb: List[float] = []
    for key in FORM_KEYS:
        text = str(values.get(key, "")).strip()
        label = LABELS[key]
        if key in STR_FIELDS:
            data[key] = text
            continue
        if text == "":
            if key in OPTIONAL_FIELDS:
                data[key] = None
                continue
            raise ValueError(f"{label} is blank.")
        try:
            # A whole number stays an int, the way json.load reads "14", so
            # the report prints "14 ft" for a typed 14 the same as the CLI.
            num = int(text) if key in INT_FIELDS else _parse_number(text)
        except ValueError:
            kind = "a whole number" if key in INT_FIELDS else "a number"
            raise ValueError(
                f"{label} must be {kind}, not {text!r}.") from None
        if key in V_LB_KEYS:
            v_lb.append(num)
        else:
            data[key] = num
    data["V_LB"] = v_lb
    inp = h.Inputs.from_dict(data)
    inp.validate()  # same checks analyze runs, so errors show before Run
    return inp


def read_json_text(path) -> str:
    """File text as UTF-8, or UTF-16 when it has that byte order mark.

    Windows PowerShell 5.1 writes ``--template > culv.json`` as UTF-16, which
    the CLI cannot read. The window accepts it.
    """
    raw = Path(path).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def results_payload(inp: "h.Inputs", r: "h.Results") -> Dict:
    """Same JSON layout as the command line --json-out."""
    return {"inputs": asdict(inp), "results": asdict(r)}


def flow_choices(crossing) -> List[str]:
    """Readable flow list for an HY-8 crossing, in column order."""
    names = crossing.flow_names
    return [f"{n} ({q:g} cfs)" if n else f"{q:g} cfs"
            for n, q in zip(names, crossing.flows_cfs)]


# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------


class App:
    """Main window: toolbar, form on the left, report on the right."""

    def __init__(self, root: "tk.Tk") -> None:
        self.root = root
        self.base = h.Inputs()  # keeps g and gamma_w from loaded files
        self.inp: Optional[h.Inputs] = None
        self.results: Optional[h.Results] = None
        self.vars: Dict[str, tk.StringVar] = {}

        root.title(APP_TITLE)
        root.minsize(900, 560)
        self._build_toolbar()
        panes = ttk.PanedWindow(root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        panes.add(self._build_form(panes), weight=0)
        panes.add(self._build_report(panes), weight=1)
        self.status = tk.StringVar(value="Load an example, open an inputs "
                                         "file or import HY-8, then Run.")
        ttk.Label(root, textvariable=self.status, anchor="w",
                  relief="sunken", padding=(6, 2)).pack(fill="x")
        root.bind("<F5>", lambda _e: self.run())
        root.bind("<Control-r>", lambda _e: self.run())
        self.set_inputs(h.Inputs())

    # ---- layout ---------------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(6, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="Example:").pack(side="left")
        self.example = ttk.Combobox(bar, width=7, state="readonly",
                                    values=sorted(h.EXAMPLES))
        self.example.set(sorted(h.EXAMPLES)[0])
        self.example.pack(side="left", padx=(2, 2))
        ttk.Button(bar, text="Load", command=self.load_example).pack(
            side="left", padx=(0, 12))
        for text, cmd in (("Open inputs...", self.open_inputs),
                          ("Save inputs...", self.save_inputs),
                          ("Import HY-8...", self.import_hy8)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
        ttk.Button(bar, text="Save results JSON...",
                   command=self.save_results).pack(side="right", padx=2)
        ttk.Button(bar, text="Save report...",
                   command=self.save_report).pack(side="right", padx=2)
        ttk.Button(bar, text="Run (F5)", command=self.run).pack(
            side="right", padx=(2, 12))

    def _build_form(self, parent) -> "ttk.Frame":
        form = ttk.Frame(parent, padding=(0, 0, 6, 0))
        cols = [ttk.Frame(form), ttk.Frame(form)]
        cols[0].grid(row=0, column=0, sticky="n")
        cols[1].grid(row=0, column=1, sticky="n", padx=(6, 0))
        # Project, HY-8 row, geometry on the left; limits and HY-8 energy
        # dissipation on the right.
        for gi, (title, rows) in enumerate(GROUPS):
            box = ttk.LabelFrame(cols[0 if gi < 3 else 1], text=title,
                                 padding=(6, 4))
            box.pack(fill="x", pady=(0, 6))
            for r, (key, label, unit) in enumerate(rows):
                ttk.Label(box, text=label).grid(row=r, column=0, sticky="w",
                                                pady=1)
                var = tk.StringVar()
                self.vars[key] = var
                if key in CHOICES:
                    w = ttk.Combobox(box, textvariable=var, width=10,
                                     state="readonly", values=CHOICES[key])
                else:
                    width = 30 if key in STR_FIELDS else 12
                    w = ttk.Entry(box, textvariable=var, width=width)
                w.grid(row=r, column=1, sticky="w", padx=4, pady=1)
                ttk.Label(box, text=unit, foreground="gray40").grid(
                    row=r, column=2, sticky="w")
        note = ("Energy Dissipation values are not in the HY-8 files. Type "
                "them from the HY-8 Riprap Basin screen.")
        ttk.Label(cols[1], text=note, wraplength=300,
                  foreground="gray30").pack(fill="x", pady=(2, 0))
        return form

    def _build_report(self, parent) -> "ttk.Frame":
        frame = ttk.Frame(parent)
        self.text = tk.Text(frame, wrap="none", font="TkFixedFont",
                            width=96, height=36, state="disabled")
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        xs = ttk.Scrollbar(frame, orient="horizontal",
                           command=self.text.xview)
        self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return frame

    # ---- form state -----------------------------------------------------

    def set_inputs(self, inp: "h.Inputs") -> None:
        self.base = inp
        for key, text in inputs_to_form(inp).items():
            self.vars[key].set(text)
        self.results = None
        self._show("")

    def read_form(self) -> "h.Inputs":
        return form_to_inputs({k: v.get() for k, v in self.vars.items()},
                              base=self.base)

    def _show(self, report: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", report)
        self.text.configure(state="disabled")

    def _error(self, title: str, err: Exception) -> None:
        messagebox.showerror(title, str(err), parent=self.root)

    # ---- actions --------------------------------------------------------

    def load_example(self) -> None:
        name = self.example.get()
        self.set_inputs(h.Inputs.from_dict(asdict(h.EXAMPLES[name])))
        self.status.set(f"Loaded example {name}. Press Run.")

    def open_inputs(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="Open inputs JSON",
            filetypes=[("Inputs JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = json.loads(read_json_text(path))
            if "inputs" in data and "results" in data:
                data = data["inputs"]  # a results file also works
            self.set_inputs(h.Inputs.from_dict(data))
        except (OSError, ValueError, TypeError) as err:
            self._error("Could not open inputs", err)
            return
        self.status.set(f"Opened {Path(path).name}. Press Run.")

    def save_inputs(self) -> None:
        try:
            inp = self.read_form()
        except (ValueError, TypeError) as err:
            self._error("Check inputs", err)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save inputs JSON",
            defaultextension=".json", filetypes=[("Inputs JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(inp), fh, indent=2)
        self.status.set(f"Saved inputs to {Path(path).name}.")

    def run(self) -> None:
        try:
            inp = self.read_form()
            r = h.analyze(inp)
            report = h.format_report(inp, r)
        except (ValueError, TypeError, ZeroDivisionError) as err:
            self._error("Check inputs", err)
            return
        self.inp, self.results = inp, r
        self._show(report)
        msg = f"Trial stone gives: {r.trial_gives}.   Protection length: "
        msg += (f"{r.L_adopted:g} ft" if isinstance(r.L_adopted, (int, float))
                else str(r.L_adopted))
        if not any(inp.V_LB):
            msg += ("   Jet velocities are 0, so blocks 6 to 8 and 10 are "
                    "placeholders.")
        self.status.set(msg)

    def _need_results(self) -> bool:
        if self.results is None:
            messagebox.showinfo(APP_TITLE, "Run the calculation first.",
                                parent=self.root)
            return False
        return True

    def save_report(self) -> None:
        if not self._need_results():
            return
        stem = (self.inp.culvert or "outlet_protection").replace(" ", "_")
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save report", initialfile=f"{stem}.txt",
            defaultextension=".txt", filetypes=[("Text report", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(h.format_report(self.inp, self.results) + "\n")
        self.status.set(f"Saved report to {Path(path).name}.")

    def save_results(self) -> None:
        if not self._need_results():
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save results JSON",
            defaultextension=".json", filetypes=[("Results JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(results_payload(self.inp, self.results), fh, indent=2)
        self.status.set(f"Saved results to {Path(path).name}.")

    def import_hy8(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="Open HY-8 project",
            filetypes=[("HY-8 project", "*.hy8"), ("All files", "*.*")])
        if path:
            Hy8Dialog(self, Path(path))


class Hy8Dialog:
    """Pick crossing, culvert and flow from an HY-8 project, then import."""

    def __init__(self, app: App, path: Path) -> None:
        import hy8_io  # local module, same folder

        self.app, self.path, self.hy8_io = app, path, hy8_io
        try:
            self.project = hy8_io.read_hy8(path)
        except (OSError, ValueError) as err:
            app._error("Could not read HY-8 project", err)
            return
        if not self.project.crossings:
            messagebox.showerror(APP_TITLE, "No crossings in that file.",
                                 parent=app.root)
            return

        win = self.win = tk.Toplevel(app.root)
        win.title(f"Import from {path.name}")
        win.transient(app.root)
        win.resizable(False, False)
        body = ttk.Frame(win, padding=10)
        body.pack(fill="both")

        self.boxes = {}
        for r, name in enumerate(("Crossing", "Culvert", "Flow")):
            ttk.Label(body, text=name).grid(row=r, column=0, sticky="w",
                                            pady=3)
            cb = ttk.Combobox(body, state="readonly", width=40)
            cb.grid(row=r, column=1, sticky="w", padx=6, pady=3)
            self.boxes[name] = cb
        self.boxes["Crossing"]["values"] = [c.name for c in
                                            self.project.crossings]
        self.boxes["Crossing"].current(0)
        self.boxes["Crossing"].bind("<<ComboboxSelected>>",
                                    lambda _e: self._fill())
        note = ("Reads the matching .rst results file. Your typed Energy "
                "Dissipation values, trial stone and limits are kept.")
        ttk.Label(body, text=note, wraplength=380,
                  foreground="gray30").grid(row=3, column=0, columnspan=2,
                                            sticky="w", pady=(6, 8))
        btns = ttk.Frame(body)
        btns.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Import", command=self._import).pack(
            side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left")
        self._fill()
        win.grab_set()

    def _fill(self) -> None:
        xing = self.project.crossings[self.boxes["Crossing"].current()]
        self.boxes["Culvert"]["values"] = [c.name for c in xing.culverts]
        if xing.culverts:
            self.boxes["Culvert"].current(0)
        flows = flow_choices(xing)
        self.boxes["Flow"]["values"] = flows
        if flows:
            self.boxes["Flow"].current(len(flows) - 1)  # CLI default: last

    def _import(self) -> None:
        app = self.app
        # Keep what HY-8 does not write; fall back to defaults if the form
        # does not parse yet.
        try:
            current = app.read_form()
            overrides = {k: getattr(current, k) for k in TYPED_ONLY}
        except (ValueError, TypeError):
            overrides = {}
        try:
            inp = self.hy8_io.inputs_from_hy8(
                self.path, self.boxes["Crossing"].current(),
                self.boxes["Culvert"].current(),
                self.boxes["Flow"].current(), **overrides)
        except (OSError, ValueError, KeyError, IndexError) as err:
            app._error("HY-8 import failed", err)
            return
        self.win.destroy()
        app.set_inputs(inp)
        app.status.set(f"Imported {inp.culvert}, {inp.design_storm}. Check "
                       "the Energy Dissipation values, then Run.")


def main() -> int:
    if tk is None:
        print("This Python has no tkinter. Install Python from python.org "
              "(tkinter is included) or use the command line tool.",
              file=sys.stderr)
        return 1
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
