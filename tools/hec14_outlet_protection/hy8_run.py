"""Get current HY-8 results for a project, running HY-8 when needed.

A normal save in HY-8 8.x does not always leave a ``.rst`` results file
next to the project (8.0.1.2 does not). HY-8 does accept the command line
switch ``-OpenRunSave``, which opens a project, runs every crossing, saves
it, and writes ``.rst`` and ``.rsql`` next to it. This module runs that
switch on a COPY in a work folder, so the user's project is never touched,
and returns the ``.rst`` it wrote.

Same approach and executable search as HY-8_Exporter (hy8_runner.py and
hy8_package.py; MIT, same author). HY-8 runs on Windows only.

Results modes
    auto      use the .rst beside the project when it exists and is not
              older than the project, otherwise run HY-8 on a copy (an
              older .rst is used, with a note, when HY-8 is not found)
    existing  only use the .rst beside the project
    run       always run HY-8 on a copy
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Union

DEFAULT_LOCATIONS = (
    r"C:\Program Files\HY-8 8.00\HY864.exe",
    r"C:\Program Files\HY-8*\HY864.exe",
    r"C:\Program Files (x86)\HY-8*\HY864.exe",
    r"C:\Program Files\HY-8*\HY8*.exe",
)
RUN_TIMEOUT_SECONDS = 300
RESULT_MODES = ("auto", "existing", "run")
RUNS_FOLDER = "_hy8_runs"  # created beside the project
STALE_TOLERANCE_S = 2.0  # file time resolution on some shares

PathLike = Union[str, Path]


def find_hy8(configured: str = "") -> Optional[Path]:
    """HY-8 executable: the configured path, then HY8_EXE, then defaults."""
    for candidate in (configured, os.environ.get("HY8_EXE", "")):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    if os.name != "nt":
        return None
    for pattern in DEFAULT_LOCATIONS:
        for match in sorted(glob.glob(pattern), reverse=True):
            if Path(match).is_file():
                return Path(match)
    return None


def results_state(hy8_path: PathLike) -> str:
    """'current', 'stale' (older than the project) or 'missing'."""
    hy8_path = Path(hy8_path)
    rst = hy8_path.with_suffix(".rst")
    if not rst.is_file() or rst.stat().st_size == 0:
        return "missing"
    if rst.stat().st_mtime + STALE_TOLERANCE_S < hy8_path.stat().st_mtime:
        return "stale"
    return "current"


def run_hy8_copy(hy8_path: PathLike, work_dir: PathLike,
                 exe: Optional[PathLike]) -> Path:
    """Copy the project to work_dir, run HY-8 on the copy, return its .rst."""
    if exe is None:
        raise RuntimeError(
            "HY-8 was not found, so its results could not be generated. "
            "Point to HY864.exe (usually C:\\Program Files\\HY-8 8.00), or "
            "set the HY8_EXE environment variable.")
    source = Path(hy8_path)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    copy = work / source.name
    shutil.copy2(source, copy)
    for suffix in (".rst", ".rsql", ".plt"):
        old = copy.with_suffix(suffix)
        if old.exists():
            old.unlink()
    kwargs = {}
    if os.name == "nt":  # keep HY-8's window hidden
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startup
    try:
        done = subprocess.run(
            [str(exe), "-OpenRunSave", str(copy)], capture_output=True,
            text=True, timeout=RUN_TIMEOUT_SECONDS, check=False, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"HY-8 could not be run: {exc}") from exc
    rst = copy.with_suffix(".rst")
    if not rst.is_file() or rst.stat().st_size == 0:
        detail = (done.stderr or done.stdout or "").strip()
        raise RuntimeError(
            f"HY-8 finished (exit code {done.returncode}) but wrote no "
            f"results for {source.name}. {detail}".strip())
    return rst


def locate_results(hy8_path: PathLike, mode: str = "auto", exe: str = "",
                   work_dir: Optional[PathLike] = None) -> Tuple[Path, str]:
    """Return (.rst path, note on where it came from).

    Raises FileNotFoundError when mode is 'existing' and there is no .rst,
    and RuntimeError when HY-8 is needed but missing or fails.
    """
    if mode not in RESULT_MODES:
        raise ValueError(f"Unknown results mode {mode!r}; use one of "
                         f"{', '.join(RESULT_MODES)}")
    hy8_path = Path(hy8_path)
    state = results_state(hy8_path)
    beside = hy8_path.with_suffix(".rst")
    found = find_hy8(exe)
    if mode == "auto" and state == "stale" and found is None:
        mode = "existing"  # an older .rst beats no results; noted below
    if mode == "existing" or (mode == "auto" and state == "current"):
        if state == "missing":
            raise FileNotFoundError(
                f"{beside.name} not found beside {hy8_path.name}. Let this "
                "tool run HY-8 on a copy (results mode auto or run).")
        note = f"Results read from {beside.name} beside the project"
        if state == "stale":
            note += f" (older than {hy8_path.name}; inputs may have changed)"
        return beside, note
    work = Path(work_dir) if work_dir else hy8_path.parent / RUNS_FOLDER
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = work / f"{hy8_path.stem}_{stamp}"
    rst = run_hy8_copy(hy8_path, folder, found)
    return rst, (f"Results generated by HY-8 (-OpenRunSave) on a copy in "
                 f"{folder.name}; the project file was not changed")
