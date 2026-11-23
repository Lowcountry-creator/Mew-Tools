"""Tests for finding or generating HY-8 results (hy8_run).

HY-8 itself runs on Windows only, so these use a stand-in executable that
behaves like ``HY864.exe -OpenRunSave project.hy8``: it writes project.rst
next to the copy it was given. The real switch has to be checked on a
machine with HY-8 installed.
"""

import os
import shutil
from pathlib import Path

import pytest

import hec14_outlet_protection as h
import hy8_run

HY8 = Path(__file__).parent / "examples" / "HY8_Demo_Culverts.hy8"
RST = HY8.with_suffix(".rst")
POSIX = pytest.mark.skipif(os.name == "nt", reason="stand-in is a sh script")


def fake_hy8(folder: Path, write=True, code=3) -> Path:
    exe = folder / "HY864.sh"
    body = (f"cp '{RST}' \"${{2%.hy8}}.rst\"\n" if write
            else f"echo 'called with OpenRunSave'\nexit {code}\n")
    exe.write_text("#!/bin/sh\n" + body)
    exe.chmod(0o755)
    return exe


def project(tmp_path, with_rst=False, rst_age_s=0.0) -> Path:
    p = tmp_path / "proj" / "Demo.hy8"
    p.parent.mkdir(parents=True)
    shutil.copy(HY8, p)
    if with_rst:
        rst = p.with_suffix(".rst")
        shutil.copy(RST, rst)
        t = p.stat().st_mtime
        os.utime(rst, (t - rst_age_s, t - rst_age_s))
    return p


def test_results_state(tmp_path):
    assert hy8_run.results_state(project(tmp_path)) == "missing"
    assert hy8_run.results_state(project(tmp_path / "a", True)) == "current"
    assert hy8_run.results_state(project(tmp_path / "b", True, 60)) == "stale"


def test_find_hy8_prefers_configured_then_env(tmp_path, monkeypatch):
    exe = tmp_path / "HY864.exe"
    exe.write_text("")
    monkeypatch.delenv("HY8_EXE", raising=False)
    assert hy8_run.find_hy8(str(exe)) == exe
    monkeypatch.setenv("HY8_EXE", str(exe))
    assert hy8_run.find_hy8("") == exe
    assert hy8_run.find_hy8(str(tmp_path / "missing.exe")) == exe


def test_current_rst_is_used_without_running(tmp_path):
    p = project(tmp_path, with_rst=True)
    rst, note = hy8_run.locate_results(p, "auto", "")
    assert rst == p.with_suffix(".rst")
    assert note.startswith("Results read from Demo.rst")


def test_existing_mode_without_rst_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match="Demo.rst not found"):
        hy8_run.locate_results(project(tmp_path), "existing")


def test_missing_rst_and_no_hy8_explains(tmp_path, monkeypatch):
    monkeypatch.delenv("HY8_EXE", raising=False)
    with pytest.raises(RuntimeError, match="HY-8 was not found"):
        hy8_run.locate_results(project(tmp_path), "auto",
                               str(tmp_path / "nope.exe"))


def test_stale_rst_without_hy8_falls_back_with_a_note(tmp_path, monkeypatch):
    monkeypatch.delenv("HY8_EXE", raising=False)
    p = project(tmp_path, with_rst=True, rst_age_s=60)
    rst, note = hy8_run.locate_results(p, "auto", "")
    assert rst == p.with_suffix(".rst")
    assert "older than Demo.hy8" in note


def test_bad_mode():
    with pytest.raises(ValueError, match="Unknown results mode"):
        hy8_run.locate_results(HY8, "sometimes")


@POSIX
def test_runs_hy8_on_a_copy(tmp_path):
    p = project(tmp_path)
    before = p.read_bytes()
    rst, note = hy8_run.locate_results(p, "auto", str(fake_hy8(tmp_path)))
    assert rst.parent.parent == p.parent / hy8_run.RUNS_FOLDER
    assert rst.suffix == ".rst" and rst.stat().st_size > 0
    assert "-OpenRunSave" in note
    assert p.read_bytes() == before
    assert not p.with_suffix(".rst").exists()


@POSIX
def test_run_mode_runs_even_with_a_current_rst(tmp_path):
    p = project(tmp_path, with_rst=True)
    rst, _ = hy8_run.locate_results(p, "run", str(fake_hy8(tmp_path)))
    assert hy8_run.RUNS_FOLDER in rst.parts


@POSIX
def test_hy8_that_writes_nothing_is_reported(tmp_path):
    exe = fake_hy8(tmp_path, write=False)
    with pytest.raises(RuntimeError, match="exit code 3"):
        hy8_run.locate_results(project(tmp_path), "auto", str(exe))


@POSIX
def test_hy8_runs_from_the_work_folder_and_logs(tmp_path):
    exe = tmp_path / "HY864.sh"
    exe.write_text("#!/bin/sh\npwd\n"
                   f"cp '{RST}' \"${{2%.hy8}}.rst\"\n")
    exe.chmod(0o755)
    rst, _ = hy8_run.locate_results(project(tmp_path), "run", str(exe))
    log = (rst.parent / hy8_run.RUN_LOG).read_text()
    assert log.startswith("Source project: ")
    assert f"\n{rst.parent}\n" in log  # pwd printed by every run


@POSIX
def test_long_run_paths_use_a_short_copy_name(tmp_path, monkeypatch):
    exe = fake_hy8(tmp_path)
    monkeypatch.setattr(hy8_run, "MAX_RUN_PATH", 10_000)
    rst, _ = hy8_run.locate_results(project(tmp_path / "a"), "run", str(exe))
    assert rst.name == "Demo.rst"
    monkeypatch.setattr(hy8_run, "MAX_RUN_PATH", 20)
    rst, _ = hy8_run.locate_results(project(tmp_path / "b"), "run", str(exe))
    assert rst.name == "run.rst" and rst.stat().st_size > 0


def test_runs_root_does_not_nest(tmp_path):
    runs = tmp_path / hy8_run.RUNS_FOLDER
    inner = runs / "20261123_173409" / "Demo.hy8"
    assert hy8_run.runs_root(inner) == runs
    assert hy8_run.runs_root(tmp_path / "Demo.hy8") == runs


def test_crash_code_is_explained(tmp_path):
    cmd = ["C:/HY-8/HY864.exe", "-OpenRunSave", "C:/runs/Demo.hy8"]
    msg = hy8_run._no_results_message(Path("Demo.hy8"), 3221225477, cmd)
    assert "HY-8 crashed" in msg and "access violation" in msg
    assert "0xC0000005" in msg
    assert '"C:/HY-8/HY864.exe" -OpenRunSave "C:/runs/Demo.hy8"' in msg


@POSIX
def test_hy8_output_is_shown_when_it_writes_nothing(tmp_path):
    exe = fake_hy8(tmp_path, write=False)
    with pytest.raises(RuntimeError, match="HY-8 said: called with"):
        hy8_run.locate_results(project(tmp_path), "auto", str(exe))


@POSIX
def test_cli_runs_hy8_when_no_rst(tmp_path, capsys):
    p = project(tmp_path)
    out = tmp_path / "r.json"
    rc = h.main(["--hy8", str(p), "--flow", "50-yr", "--hy8-exe",
                 str(fake_hy8(tmp_path)), "--v-lb", "10", "7", "5", "4",
                 "--out", str(tmp_path / "r.txt"), "--inputs-out", str(out)])
    assert rc == 0
    assert "-OpenRunSave" in capsys.readouterr().err
    assert "-OpenRunSave" in out.read_text(encoding="utf-8")


def test_cli_without_hy8_or_rst_exits_with_message(tmp_path, monkeypatch):
    monkeypatch.delenv("HY8_EXE", raising=False)
    with pytest.raises(SystemExit, match="HY-8 was not found"):
        h.main(["--hy8", str(project(tmp_path)), "--hy8-exe",
                str(tmp_path / "nope.exe")])


def per_crossing_hy8(folder: Path, fail: str = "") -> Path:
    """Stand-in that writes a one-crossing .rst named for the file's
    crossing, and exits 5 with no results for the crossing named fail."""
    exe = folder / "HY864_split.sh"
    exe.write_text(
        "#!/bin/sh\n"
        "name=$(sed -n 's/^STARTCROSSING *\"\\(.*\\)\".*/\\1/p' \"$2\" "
        "| head -1)\n"
        f"[ \"$name\" = \"{fail}\" ] && exit 5\n"
        "printf 'CrossingGUID: g\\n\\nDialog: Summary of Flows at Crossing"
        " - %s\\nTotal Discharge (cfs), 1.00\\n\\nEndCrossing\\n' "
        "\"$name\" > \"${2%.hy8}.rst\"\n")
    exe.chmod(0o755)
    return exe


def test_split_crossings_one_per_file():
    import hy8_io
    names = [c.name for c in hy8_io.read_hy8(HY8).crossings]
    parts = hy8_run.split_crossings(HY8.read_text())
    assert [n for n, _ in parts] == names and len(names) > 1
    for name, body in parts:
        assert "NUMCROSSINGS         1" in body
        assert body.count("STARTCROSSING") == 1
        assert body.rstrip().endswith("ENDPROJECTFILE")


def test_split_keeps_crlf_line_endings():
    text = HY8.read_text().replace("\n", "\r\n")
    for _, body in hy8_run.split_crossings(text):
        assert "\r\n" in body and "\n" not in body.replace("\r\n", "")


@POSIX
def test_multi_crossing_project_runs_one_crossing_at_a_time(tmp_path):
    import hy8_io
    p = project(tmp_path)
    rst, note = hy8_run.locate_results(p, "run",
                                       str(per_crossing_hy8(tmp_path)))
    want = [c.name for c in hy8_io.read_hy8(p).crossings]
    assert [r.name for r in hy8_io.read_rst(rst)] == want
    assert "one at a time" in note and "no results" not in note
    log = (rst.parent / hy8_run.RUN_LOG).read_text()
    assert log.count("-OpenRunSave") == len(want)


@POSIX
def test_crossing_without_results_is_named(tmp_path):
    import hy8_io
    p = project(tmp_path)
    bad = hy8_io.read_hy8(p).crossings[1].name
    rst, note = hy8_run.locate_results(
        p, "run", str(per_crossing_hy8(tmp_path, fail=bad)))
    assert bad not in [r.name for r in hy8_io.read_rst(rst)]
    assert f"no results for {bad!r}" in note
