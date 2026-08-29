"""
Running the bootstrap probe, and reading what it says.

:mod:`bootycall.probe_main` is the script; this is the half that lives in the
UI's interpreter. It builds the command, reads the sentinel line back, and --
importantly -- turns every possible failure into a note rather than an error,
because the static reader is always there to fall back on.

Two entry points, because the caller has two situations:

* :func:`run` is synchronous, for tests and for scripts.
* :func:`command` plus :func:`parse_output` is the same thing taken apart, so
  the UI can drive it with ``QProcess`` and never block on a subprocess that
  has to import rez.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .probe_main import SENTINEL


@dataclass(frozen=True)
class ProbeResult:
    """What the bootstrap said, or why it did not say anything."""

    ok: bool = False
    #: tool name -> tuple of rez package requests, straight from the module
    packages: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: what ``_get_show_packages()`` appends to every resolve
    show_packages: tuple[str, ...] = ()
    class_name: str = ""
    #: Short, safe to put in a status bar. Empty when ``ok``.
    error: str = ""
    #: Long, for a details dialog or a log. May be empty.
    detail: str = ""

    def tools(self) -> tuple[str, ...]:
        return tuple(sorted(self.packages))


def script_path() -> Path:
    """The probe script's location, as an absolute path."""
    return Path(__file__).resolve().parent / "probe_main.py"


def command(bootstrap_path: str | Path) -> list[str]:
    """The argv that runs the probe against ``bootstrap_path``."""
    argv: list[str] = []
    for part in config.probe_command():
        argv.append(
            part.replace("{script}", str(script_path())).replace(
                "{bootstrap}", str(bootstrap_path)
            )
        )
    return argv


def parse_output(stdout: str, stderr: str = "") -> ProbeResult:
    """Read the probe's report out of its output.

    The sentinel line is searched for from the end: a bootstrap that prints on
    import puts its noise first, and nothing legitimately follows the report.
    """
    for line in reversed(stdout.splitlines()):
        if not line.startswith(SENTINEL):
            continue
        try:
            report = json.loads(line[len(SENTINEL) :])
        except ValueError as exc:
            return ProbeResult(error="unreadable probe output: %s" % exc)
        return _from_report(report)

    tail = (stderr or stdout).strip().splitlines()
    return ProbeResult(
        error=tail[-1][:200] if tail else "the probe produced no report",
        detail=stderr or stdout,
    )


def _from_report(report: dict) -> ProbeResult:
    if not report.get("ok"):
        return ProbeResult(
            error=str(report.get("error", "the bootstrap could not be read")),
            detail=str(report.get("traceback", "")),
        )

    packages = {
        str(key): tuple(str(item) for item in value)
        for key, value in (report.get("packages") or {}).items()
    }
    return ProbeResult(
        ok=True,
        packages=packages,
        show_packages=tuple(str(p) for p in (report.get("show_packages") or ())),
        class_name=str(report.get("class_name", "")),
        detail=str(report.get("show_packages_error", "")),
    )


def run(
    bootstrap_path: str | Path,
    cwd: str | Path | None = None,
    timeout: float | None = None,
) -> ProbeResult:
    """Probe ``bootstrap_path`` and wait for the answer.

    ``cwd`` should be the show folder: ``_get_show_packages`` walks up from the
    bootstrap's ``__file__``, but plenty of pipeline code is less careful and
    expects to start in the show.
    """
    argv = command(bootstrap_path)
    try:
        result = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout if timeout is not None else config.probe_timeout(),
            check=False,
            env=probe_env(),
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(
            error="the bootstrap took longer than %gs to load" % config.probe_timeout()
        )
    except OSError as exc:
        return ProbeResult(
            error="could not run the probe: %s" % exc,
            detail=" ".join(argv),
        )

    return parse_output(result.stdout, result.stderr)


def probe_env() -> dict[str, str]:
    """Environment for the probe process.

    ``PYTHONPATH`` keeps whatever the session has; what must go is anything
    that would make the probe's interpreter behave unlike a pipeline one.
    ``PYTHONDONTWRITEBYTECODE`` is set because the show tree is a network mount
    that nobody wants ``__pycache__`` scattered across.
    """
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["BOOTYCALL_PROBE"] = "1"
    return env


def merge(
    static_packages: dict[str, tuple[str, ...]], result: ProbeResult
) -> tuple[dict[str, tuple[str, ...]], str]:
    """Prefer the probe's answer, and say what changed.

    Returns ``(packages, note)``. The note is written for the status bar, and
    is empty when the two agree -- which is the normal case, and worth not
    commenting on.
    """
    if not result.ok:
        return dict(static_packages), ""

    added = sorted(set(result.packages) - set(static_packages))
    removed = sorted(set(static_packages) - set(result.packages))
    changed = sorted(
        key
        for key in set(result.packages) & set(static_packages)
        if result.packages[key] != static_packages[key]
    )

    parts = []
    if added:
        parts.append("%d only the bootstrap knows" % len(added))
    if removed:
        parts.append("%d read statically but not defined" % len(removed))
    if changed:
        parts.append("%d with different packages" % len(changed))

    note = ""
    if parts:
        note = "bootstrap differs from the static read: " + ", ".join(parts)
    return dict(result.packages), note
