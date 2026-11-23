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


def fake_hy8(folder: Path, write=True) -> Path:
    exe = folder / "HY864.sh"
    body = f"cp '{RST}' \"${{2%.hy8}}.rst\"\n" if write else "exit 3\n"
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
    assert rst.name == "Demo.rst" and rst.stat().st_size > 0
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
