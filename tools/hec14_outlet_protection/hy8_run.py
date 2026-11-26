"""Get current HY-8 results for a project, running HY-8 when needed.

A normal save in HY-8 8.x does not always leave a ``.rst`` results file
next to the project (8.0.1.2 does not). HY-8 does accept the command line
switch ``-OpenRunSave``, which opens a project, runs every crossing, saves
it, and writes ``.rst`` and ``.rsql`` next to it. This module runs that
switch on a COPY in a work folder, so the user's project is never touched,
and returns the ``.rst`` it wrote. HY-8's console output goes to
``hy8_run_log.txt`` in the same folder.

HY-8 8.0.1.2 crashes under -OpenRunSave on a project with more than one
crossing, though each crossing runs on its own (found on a real 3-crossing
project, Nov 2026). So a multi-crossing project is split into one file per
crossing, each is run in turn, and the .rst files are joined.

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
from typing import List, Optional, Tuple, Union

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


def split_crossings(text: str) -> List[Tuple[str, str]]:
    """Split HY-8 project text into one project per crossing.

    Returns (crossing name, project text) pairs. Each keeps the project
    header with NUMCROSSINGS set to 1, its own crossing block, and the end
    card. Line endings are kept as they are in the file.
    """
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    starts = [i for i, ln in enumerate(lines)
              if ln.startswith("STARTCROSSING")]
    if not starts:
        return []
    head = [("NUMCROSSINGS         1" if ln.startswith("NUMCROSSINGS")
             else ln) for ln in lines[:starts[0]]]
    tail_at = next((i for i, ln in enumerate(lines)
                    if ln.strip() == "ENDPROJECTFILE"), len(lines))
    out = []
    for i in starts:
        name = lines[i].split(None, 1)[1].strip().strip('"') \
            if len(lines[i].split(None, 1)) > 1 else ""
        end = next((j for j in range(i + 1, tail_at)
                    if lines[j].startswith("ENDCROSSING")), tail_at - 1)
        out.append((name, nl.join(head + lines[i:end + 1] + lines[tail_at:])))
    return out


def _run_once(exe: PathLike, copy: Path, work: Path,
              log) -> Tuple[int, str]:
    """Run HY-8 -OpenRunSave on one file. Returns (exit code, its output);
    both also go to the open run log."""
    command = [str(exe), "-OpenRunSave", str(copy)]
    capture = copy.with_suffix(".out.txt")
    # Same call as Aquaveo's hy8runner: a normal window, no hidden-start
    # flags. Run from the work folder, which is writable and holds the copy.
    with open(capture, "w", encoding="utf-8", errors="replace") as out:
        done = subprocess.run(
            command, cwd=str(work), stdin=subprocess.DEVNULL, stdout=out,
            stderr=subprocess.STDOUT, timeout=RUN_TIMEOUT_SECONDS,
            check=False)
    said = capture.read_text(encoding="utf-8", errors="replace").strip()
    capture.unlink()
    log.write(f"Command: {' '.join(command)}\n{said}\n"
              f"Exit code: {done.returncode}\n\n")
    log.flush()
    return done.returncode, said


def _has_results(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def run_hy8_copy(hy8_path: PathLike, work_dir: PathLike,
                 exe: Optional[PathLike]) -> Tuple[Path, List[str]]:
    """Copy the project to work_dir, run HY-8 on it, return its .rst.

    HY-8 8.0.1.2 crashes (0xC0000005) under -OpenRunSave on projects with
    more than one crossing, while the same crossings run one per file. So
    a multi-crossing project is split into one file per crossing, each is
    run in turn, and their .rst files are joined into one. Returns the .rst
    and the names of any crossings that got no results.
    """
    if exe is None:
        raise RuntimeError(
            "HY-8 was not found, so its results could not be generated. "
            "Point to HY864.exe (usually C:\\Program Files\\HY-8 8.00), or "
            "set the HY8_EXE environment variable.")
    source = Path(hy8_path)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    copy = work / source.name
    # Keep the full path short; HY-8 is old code and paths are cheap to trim.
    if len(str(copy.with_suffix(".rsql"))) > MAX_RUN_PATH:
        copy = work / ("run" + source.suffix)
    shutil.copy2(source, copy)
    for suffix in (".rst", ".rsql", ".plt"):
        old = copy.with_suffix(suffix)
        if old.exists():
            old.unlink()
    text = source.read_bytes().decode("utf-8", errors="replace")
    parts = split_crossings(text)
    log = work / RUN_LOG
    rst = copy.with_suffix(".rst")
    try:
        with open(log, "w", encoding="utf-8", errors="replace") as out:
            out.write(f"Source project: {source}\n\n")
            if len(parts) <= 1:
                runs = [("", copy, *_run_once(exe, copy, work, out))]
            else:
                runs = []
                for i, (name, body) in enumerate(parts, 1):
                    one = work / f"c{i}{source.suffix}"
                    one.write_bytes(body.encode("utf-8"))
                    out.write(f"Crossing {name!r} -> {one.name}\n")
                    code, said = _run_once(exe, one, work, out)
                    runs.append((name, one, code, said))
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"HY-8 could not be run: {exc}") from exc

    ok = [r for r in runs if _has_results(r[1].with_suffix(".rst"))]
    if not ok:
        name, failed, code, said = runs[0]
        command = [str(exe), "-OpenRunSave", str(failed)]
        raise RuntimeError(_no_results_message(source, code, command, said))
    if len(parts) > 1:  # join the per-crossing results into one .rst
        joined = [r[1].with_suffix(".rst").read_text(
            encoding="utf-8", errors="replace").strip() for r in ok]
        rst.write_text("\n\n".join(joined) + "\n", encoding="utf-8")
    missing = [r[0] for r in runs if r not in ok]
    return rst, missing


def _quote(path: PathLike) -> str:
    return f'"{path}"'


def _no_results_message(source: Path, code: int, command,
                        detail: str = "") -> str:
    """Plain explanation when HY-8 wrote no .rst, with a command to retry."""
    code_u = code & 0xFFFFFFFF  # Windows reports crashes as large unsigned
    if code_u in CRASH_CODES:
        what = (f"HY-8 crashed while running {source.name} "
                f"({CRASH_CODES[code_u]}, exit code 0x{code_u:08X}) and "
                "wrote no results.")
    else:
        what = (f"HY-8 finished (exit code {code}) but wrote no results "
                f"for {source.name}.")
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
    rst, missing = run_hy8_copy(hy8_path, folder, found)
    note = (f"Results generated by HY-8 (-OpenRunSave) on a copy in "
            f"{folder.name}; the project file was not changed")
    if len(split_crossings(hy8_path.read_bytes().decode(
            "utf-8", errors="replace"))) > 1:
        note += "; crossings were run one at a time"
    if missing:
        note += ("; HY-8 gave no results for "
                 + ", ".join(repr(m) for m in missing))
    return rst, note
