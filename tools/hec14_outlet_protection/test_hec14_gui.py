"""Tests for the window front end.

The form helpers need no display and run everywhere. The window tests open
a real Tk window and skip when this Python has no Tk or no display (CI).
"""

from dataclasses import asdict
from pathlib import Path

import pytest

import hec14_gui as gui
import hec14_outlet_protection as h
import hy8_io

HY8 = Path(__file__).parent / "examples" / "HY8_Demo_Culverts.hy8"


# ---- form helpers ----------------------------------------------------------


@pytest.mark.parametrize("name", sorted(h.EXAMPLES))
def test_form_round_trip_matches_example(name):
    """Example -> form text -> Inputs gives the same record and report."""
    ex = h.EXAMPLES[name]
    back = gui.form_to_inputs(gui.inputs_to_form(ex))
    assert asdict(back) == asdict(ex)
    assert h.format_report(back, h.analyze(back)) == \
        h.format_report(ex, h.analyze(ex))


def test_every_input_field_is_on_the_form_or_a_constant():
    on_form = set(gui.FORM_KEYS) - set(gui.V_LB_KEYS) | {"V_LB"}
    constants = {"g", "gamma_w"}  # kept from the loaded file, not edited
    assert set(asdict(h.Inputs())) == on_form | constants


def test_blank_optional_fields_become_none():
    values = gui.inputs_to_form(h.EXAMPLES["culv1"])
    values["slope"] = " "
    values["HS_hy8"] = ""
    inp = gui.form_to_inputs(values)
    assert inp.slope is None and inp.HS_hy8 is None


def test_blank_required_field_names_the_label():
    values = gui.inputs_to_form(h.EXAMPLES["culv1"])
    values["Q"] = ""
    with pytest.raises(ValueError, match="Culvert discharge Q is blank"):
        gui.form_to_inputs(values)


def test_bad_number_names_the_label():
    values = gui.inputs_to_form(h.EXAMPLES["culv1"])
    values["barrels"] = "2.5"
    with pytest.raises(ValueError, match="Barrels must be a whole number"):
        gui.form_to_inputs(values)
    values = gui.inputs_to_form(h.EXAMPLES["culv1"])
    values["V_LB_3"] = "4,1"
    with pytest.raises(ValueError, match="Jet velocity at 3 LB"):
        gui.form_to_inputs(values)


def test_form_runs_input_validation():
    values = gui.inputs_to_form(h.EXAMPLES["culv1"])
    values["slope"] = "-0.01"
    with pytest.raises(ValueError, match="slope"):
        gui.form_to_inputs(values)


def test_constants_come_from_base():
    base = h.Inputs.from_dict({**asdict(h.EXAMPLES["culv1"]), "g": 32.174})
    inp = gui.form_to_inputs(gui.inputs_to_form(base), base=base)
    assert inp.g == 32.174


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_read_json_text_handles_powershell_encodings(tmp_path, encoding):
    f = tmp_path / "culv.json"
    f.write_text('{"Q": 639.56}', encoding=encoding)
    assert gui.read_json_text(f) == '{"Q": 639.56}'


def test_results_payload_matches_cli_json(tmp_path):
    out = tmp_path / "r.json"
    h.main(["--example", "culv1", "--out", str(tmp_path / "r.txt"),
            "--json-out", str(out)])
    import json
    inp = h.EXAMPLES["culv1"]
    payload = json.loads(json.dumps(gui.results_payload(inp, h.analyze(inp))))
    assert payload == json.loads(out.read_text(encoding="utf-8"))


def test_flow_choices_label_names_and_discharge():
    oak = hy8_io.read_hy8(HY8).crossing("Oak Creek Road")
    assert gui.flow_choices(oak) == [
        "2-yr (180 cfs)", "10-yr (320 cfs)", "25-yr (410 cfs)",
        "50-yr (490 cfs)", "100-yr (580 cfs)"]


# ---- window ---------------------------------------------------------------


@pytest.fixture
def app():
    if gui.tk is None:
        pytest.skip("no tkinter in this Python")
    try:
        root = gui.tk.Tk()
    except gui.tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    a = gui.App(root)
    yield a
    root.destroy()


def test_window_runs_example_report(app):
    app.example.set("culv4")
    app.load_example()
    app.run()
    shown = app.text.get("1.0", "end-1c")
    ex = h.EXAMPLES["culv4"]
    assert shown == h.format_report(ex, h.analyze(ex))
    assert "Protection length" in app.status.get()


def test_window_hy8_import_keeps_typed_values(app):
    app.load_example()  # culv1 typed Energy Dissipation values
    dlg = gui.Hy8Dialog(app, HY8)
    dlg.boxes["Flow"].current(3)  # 50-yr
    dlg._import()
    inp = app.read_form()
    want = hy8_io.inputs_from_hy8(HY8, 0, 0, 3,
                                  V_LB=h.EXAMPLES["culv1"].V_LB,
                                  HS_hy8=h.EXAMPLES["culv1"].HS_hy8)
    assert asdict(inp) == asdict(want)
    assert inp.design_storm == "50-yr"
