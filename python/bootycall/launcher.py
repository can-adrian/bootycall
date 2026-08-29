"""
Tool launching.

BootyCall does not resolve rez itself -- the show's own bootstrap does that, and
duplicating it here would guarantee the two drift apart. We build the argv the
bootstrap expects and hand it to a detached subprocess, so closing the UI never
kills a running DCC.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from typing import Sequence

from . import config
from .discovery import Project


def build_command(tool: str) -> list[str]:
    """Return the argv used to start ``tool``."""
    return [part.format(tool=tool) for part in config.LAUNCH_COMMAND]


def build_terminal_command(packages: Sequence[str]) -> list[str]:
    """Return the argv used to open a shell in ``packages``.

    ``{packages}`` in the template expands to one argument per request rather
    than a single space-joined string, so the requests survive as separate argv
    entries.
    """
    argv: list[str] = []
    for part in config.TERMINAL_COMMAND:
        if "{packages}" in part:
            argv.extend(packages)
        else:
            argv.append(part.format(packages=""))
    return argv


def command_preview(project: Project, tool: str) -> str:
    """A copy-pasteable representation of what :func:`launch` will run."""
    return "cd %s && %s" % (
        shlex.quote(str(project.path)),
        " ".join(shlex.quote(part) for part in build_command(tool)),
    )


def terminal_preview(project: Project, packages: Sequence[str]) -> str:
    """A copy-pasteable representation of what :func:`open_terminal` will run."""
    return "cd %s && %s" % (
        shlex.quote(str(project.path)),
        " ".join(shlex.quote(part) for part in build_terminal_command(packages)),
    )


def open_terminal(
    project: Project, packages: Sequence[str], dry_run: bool = False
) -> subprocess.Popen | None:
    """Open a shell resolved against ``packages``, detached."""
    return _spawn(project, build_terminal_command(packages), dry_run)


def launch(project: Project, tool: str, dry_run: bool = False) -> subprocess.Popen | None:
    """Start ``tool`` for ``project`` in a detached process.

    Returns the :class:`subprocess.Popen`, or ``None`` when ``dry_run``.
    """
    return _spawn(project, build_command(tool), dry_run)


def _spawn(
    project: Project, argv: list[str], dry_run: bool
) -> subprocess.Popen | None:
    if dry_run:
        return None

    env = os.environ.copy()
    env["ILP_SHOW"] = project.name
    env["BOOTYCALL_SHOW"] = project.name

    kwargs: dict = {
        "cwd": str(project.path),
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(argv, **kwargs)  # noqa: S603
