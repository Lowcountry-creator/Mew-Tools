"""Get current HY-8 results for a project, running HY-8 when needed.

A normal save in HY-8 8.x does not always leave a ``.rst`` results file
next to the project (8.0.1.2 does not). HY-8 does accept the command line
switch ``-OpenRunSave``, which opens a project, runs every crossing, saves
it, and writes ``.rst`` and ``.rsql`` next to it. This module runs that
switch on a COPY in a work folder, so the user's project is never touched,
and returns the ``.rst`` it wrote. HY-8's console output goes to
``hy8_run_log.txt`` in the same folder.

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
MAX_RUN_PATH = 80  # characters; see run_hy8_copy
RUN_LOG = "hy8_run_log.txt"  # HY-8 console output, kept in the run folder
# Windows exit codes that mean the program crashed rather than finished.
CRASH_CODES = {
    0xC0000005: "access violation",
    0xC0000409: "stack buffer overrun",
    0xC0000374: "heap corruption",
}

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


def runs_root(hy8_path: PathLike) -> Path:
    """The _hy8_runs folder for a project. A project picked from inside an
    earlier run folder reuses that _hy8_runs instead of nesting a new one."""
    hy8_path = Path(hy8_path)
    for parent in hy8_path.parents:
        if parent.name == RUNS_FOLDER:
            return parent
    return hy8_path.parent / RUNS_FOLDER


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
    # HY-8 created empty result files and then crashed on runs whose paths
    # were 112+ characters, but not on its usual short paths. A fixed-size
    # path buffer is a likely cause, so keep the full path short.
    if len(str(copy.with_suffix(".rsql"))) > MAX_RUN_PATH:
        copy = work / ("run" + source.suffix)
    shutil.copy2(source, copy)
    for suffix in (".rst", ".rsql", ".plt"):
        old = copy.with_suffix(suffix)
        if old.exists():
            old.unlink()
    log = work / RUN_LOG
    command = [str(exe), "-OpenRunSave", str(copy)]
    try:
        # Same call as Aquaveo's hy8runner: a normal window, no hidden-start
        # flags. Run from the work folder, which is writable and holds the
        # copy, not from wherever the calling app was started.
        with open(log, "w", encoding="utf-8", errors="replace") as out:
            out.write(f"Source project: {source}\nCommand: "
                      f"{' '.join(command)}\n\n")
            out.flush()
            done = subprocess.run(
                command, cwd=str(work), stdin=subprocess.DEVNULL, stdout=out,
                stderr=subprocess.STDOUT, timeout=RUN_TIMEOUT_SECONDS,
                check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"HY-8 could not be run: {exc}") from exc
    rst = copy.with_suffix(".rst")
    if not rst.is_file() or rst.stat().st_size == 0:
        raise RuntimeError(_no_results_message(source, done.returncode,
                                               command, log))
    return rst


def _quote(path: PathLike) -> str:
    return f'"{path}"'


def _no_results_message(source: Path, code: int, command, log: Path) -> str:
    """Plain explanation when HY-8 wrote no .rst, with a command to retry."""
    code_u = code & 0xFFFFFFFF  # Windows reports crashes as large unsigned
    if code_u in CRASH_CODES:
        what = (f"HY-8 crashed while running {source.name} "
                f"({CRASH_CODES[code_u]}, exit code 0x{code_u:08X}) and "
                "wrote no results.")
    else:
        what = (f"HY-8 finished (exit code {code}) but wrote no results "
                f"for {source.name}.")
    detail = ""
    if log.is_file():
        text = log.read_text(encoding="utf-8", errors="replace")
        detail = text.split("\n\n", 1)[-1].strip()  # HY-8's own output
    manual = " ".join([_quote(command[0]), command[1], _quote(command[2])])
    parts = [what]
    if detail:
        parts.append(f"HY-8 said: {detail[:400]}")
    parts.append("To see whether HY-8 can run this file outside this tool, "
                 f"paste into Command Prompt: {manual}")
    return "\n\n".join(parts)


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
    work = Path(work_dir) if work_dir else runs_root(hy8_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = work / stamp  # short; the run log names the source project
    rst = run_hy8_copy(hy8_path, folder, found)
    return rst, (f"Results generated by HY-8 (-OpenRunSave) on a copy in "
                 f"{folder.name}; the project file was not changed")
