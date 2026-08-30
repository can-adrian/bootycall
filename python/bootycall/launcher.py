"""
Launching.

Both a DCC and a plain shell are the same shape: resolve the context with rez,
open a terminal, and either run an application in it or leave a prompt. So both
go through one argv expander over a template, and differ only in whether a
``{command}`` is supplied.

Everything is started detached, so closing BootyCall never takes a running DCC
with it.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Sequence

from . import config
from .discovery import Project

#: Cached answer from :func:`packages_path`. Asking rez costs a subprocess, and
#: the value does not change while BootyCall is open.
_PACKAGES_PATH: list[str] | None = None


def packages_path() -> list[str]:
    """The rez packages path, as rez itself would see it.

    ``REZ_PACKAGES_PATH`` when it is set, otherwise whatever ``rez-config``
    reports. Empty when neither is available -- which is a real answer, not a
    failure, and callers must treat it as "cannot filter" rather than "the path
    is empty".
    """
    global _PACKAGES_PATH
    if _PACKAGES_PATH is not None:
        return list(_PACKAGES_PATH)

    from_env = os.environ.get("REZ_PACKAGES_PATH", "")
    if from_env:
        _PACKAGES_PATH = [p for p in from_env.split(os.pathsep) if p]
        return list(_PACKAGES_PATH)

    _PACKAGES_PATH = _ask_rez_for_packages_path()
    return list(_PACKAGES_PATH)


def _ask_rez_for_packages_path() -> list[str]:
    """``rez-config packages_path``, parsed leniently.

    The output is a YAML list whose exact punctuation has varied across rez
    versions, so this strips list markers and quotes rather than parsing YAML,
    and keeps only lines that look like absolute paths.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["rez-config", "packages_path"],
            capture_output=True,
            text=True,
            # Short: this runs on the UI thread the first time a section is
            # switched off, and the answer is cached from then on.
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    paths = []
    for line in result.stdout.splitlines():
        entry = line.strip().lstrip("-").strip().strip("'\"")
        if entry.startswith("/") or (len(entry) > 2 and entry[1] == ":"):
            paths.append(entry)
    return paths


def filtered_packages_path(
    exclude: Sequence[str] = (), include: Sequence[str] = ()
) -> tuple[list[str], str]:
    """The packages path with ``exclude`` removed and ``include`` prepended.

    Returns ``(paths, note)``. ``note`` is non-empty when the change could not
    be applied, so the caller can say so rather than launching an environment
    that quietly still contains what was switched off -- or one that is missing
    a root a request depends on.

    ``include`` is prepended because that is where a more specific package root
    belongs: a show's own copy of a package should win over the studio one, and
    the user's own copy over both.
    """
    if not exclude and not include:
        return [], ""

    current = packages_path()
    if not current:
        # Replacing the whole variable from nothing would drop the site's
        # defaults, which is far worse than not applying the change.
        return [], (
            "could not read the rez packages path, so it was left alone - "
            "set REZ_PACKAGES_PATH or make rez-config available"
        )

    unwanted = {os.path.normpath(p) for p in exclude}
    kept = [p for p in current if os.path.normpath(p) not in unwanted]

    known = {os.path.normpath(p) for p in kept}
    extra = [
        p for p in include if os.path.normpath(p) not in known and os.path.isdir(p)
    ]
    paths = extra + kept

    # The only exclusion worth complaining about is one that did not take. A
    # root that was never on the path in the first place needs no removing --
    # the result is exactly what was asked for, and warning about it was noise
    # that fired every time a package section was switched off at a site whose
    # rez config does not list these roots. Which is most of them.
    still_there = [p for p in paths if os.path.normpath(p) in unwanted]
    if still_there:
        return paths, "could not take %s off the packages path" % ", ".join(
            still_there
        )
    return paths, ""


@dataclass(frozen=True)
class ResolveProbe:
    """What rez actually resolved, as opposed to what we predicted."""

    ok: bool = False
    #: package name -> (version, root it came from)
    resolved: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: rez's own words when the resolve failed.
    error: str = ""
    #: The command that was run, for the report.
    command: str = ""

    def version_of(self, name: str) -> tuple[str, str]:
        return self.resolved.get(name, ("", ""))


def _rez_env_key(name: str) -> str:
    """rez's environment-variable spelling of a package name."""
    cleaned = "".join(c if c.isalnum() else "_" for c in name)
    return cleaned.upper()


def resolve_probe(
    project: Project,
    packages: Sequence[str],
    exclude_roots: Sequence[str] = (),
    include_roots: Sequence[str] = (),
    timeout: float = 300.0,
) -> ResolveProbe:
    """Run the real resolve and report what rez chose.

    Everything else BootyCall says about which package wins is a prediction
    from a directory scan. A scan can compare version numbers; it cannot
    evaluate the ``requires`` of every package in the resolve, and a single
    ``requires = ["rig_utils-1.7"]`` somewhere in the graph will pin a version
    the scan says should have lost. That is not a gap worth closing by
    reimplementing a solver -- there is already one, and this asks it.

    ``rez-env ... -- printenv`` rather than parsing ``rez-context`` output:
    rez sets ``REZ_<NAME>_VERSION`` and ``REZ_<NAME>_ROOT`` for every resolved
    package, which is a documented contract rather than a human-readable table
    whose columns move between versions.
    """
    argv = ["rez-env", *packages, "--", "printenv"]
    overrides = {"ILP_SHOW": project.name, "BOOTYCALL_SHOW": project.name}
    paths, _note = filtered_packages_path(exclude_roots, include_roots)
    if paths:
        overrides["REZ_PACKAGES_PATH"] = os.pathsep.join(paths)

    env = os.environ.copy()
    env.update(overrides)
    shown = " ".join(shlex.quote(part) for part in argv)

    try:
        result = subprocess.run(  # noqa: S603
            argv,
            cwd=str(project.path),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ResolveProbe(
            error="the resolve was still going after %gs" % timeout, command=shown
        )
    except OSError as exc:
        return ResolveProbe(error="could not run rez-env: %s" % exc, command=shown)

    if result.returncode != 0:
        return ResolveProbe(
            error=(result.stderr or result.stdout or "").strip()
            or "rez-env exited %d" % result.returncode,
            command=shown,
        )

    versions: dict[str, str] = {}
    roots: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if not sep or not key.startswith("REZ_"):
            continue
        if key.endswith("_VERSION"):
            versions[key[4:-8]] = value.strip()
        elif key.endswith("_ROOT"):
            roots[key[4:-5]] = value.strip()

    resolved = {
        key: (version, roots.get(key, "")) for key, version in versions.items()
    }
    return ResolveProbe(ok=True, resolved=resolved, command=shown)


def resolved_for(probe: ResolveProbe, name: str) -> tuple[str, str]:
    """``(version, root)`` rez chose for ``name``, or ``("", "")``."""
    return probe.version_of(_rez_env_key(name))


def mine_summary(roots: Sequence[tuple[str, str]]) -> str:
    """Shell that lists which resolved packages came out of the user's roots.

    rez already marks packages from its *configured* local packages path green
    and ``(local)`` in the context table. A dev root BootyCall adds to the path
    gets no such mark -- rez has no reason to think it is special -- so a dev
    build sits in that table looking exactly like the other forty entries and
    is trivially missed. This says which ones are yours, in BootyCall's own
    words, right under rez's table.

    Read from ``REZ_<NAME>_ROOT`` in the resolved environment rather than from
    anything BootyCall predicted: this line has to be true, and the environment
    is the only place that knows.

    The line printed when *nothing* matched is the one that matters most. "None
    of your packages are in this environment" is the answer to the question
    that otherwise costs an afternoon.
    """
    if not roots:
        return ""

    # One line, because it is embedded in a shell string that is itself
    # embedded in an echo. A here-string keeps the loop in the current shell so
    # the accumulator survives it; a pipe would put it in a subshell and the
    # results would vanish with it.
    cases = "".join(
        '%s/*) _bc_hits="$_bc_hits\n  $_bc_name  (%s)" ;; ' % (shlex.quote(root), label)
        for label, root in roots
    )
    return (
        '_bc_hits=""; '
        "while read -r _bc_key _bc_path; do "
        '[ -z "$_bc_key" ] && continue; '
        '_bc_ver="REZ_${_bc_key}_VERSION"; '
        "_bc_name=\"$(printf '%s' \"$_bc_key\" | tr 'A-Z' 'a-z')-${!_bc_ver}\"; "
        'case "$_bc_path" in ' + cases + "esac; "
        "done <<< \"$(env | sed -n "
        "'s/^REZ_\\([A-Z0-9_]*\\)_ROOT=\\(.*\\)$/\\1 \\2/p' | sort)\"; "
        'if [ -n "$_bc_hits" ]; then '
        'printf \"BootyCall: resolved from your own package roots:%b\\n\" '
        '"$_bc_hits"; '
        "else "
        'printf \"BootyCall: none of your local or dev packages are in this '
        'environment.\\n\"; '
        "fi; echo"
    )


def context_preamble(command: str, roots: Sequence[tuple[str, str]] = ()) -> str:
    """Print the resolved context, then become the application.

    ``exec`` on purpose: the shell replaces itself with the DCC rather than
    sitting around as its parent, so the process tree is the same as it would
    have been without the wrapper.

    ``rez-context`` prints the same table rez shows when you enter an
    interactive resolved shell -- requested packages, resolved packages, the
    lot -- and colours it when stdout is a terminal, which here it is.
    :func:`mine_summary` then says which of those forty-odd lines are yours,
    which rez cannot know.
    """
    parts = ["rez-context 2>/dev/null", "echo"]
    summary = mine_summary(roots)
    if summary:
        parts.append(summary)
    parts.append("exec %s" % shlex.quote(command))
    return "; ".join(parts)


def rez_argv(
    packages: Sequence[str],
    command: str = "",
    show_info: bool | None = None,
    roots: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """The rez invocation itself, without a terminal around it.

    With no command this is a bare ``rez-env``, which drops you in an
    interactive resolved shell -- and rez prints the context on the way in, for
    free. With a command there is no shell to do that, so unless asked not to,
    the command is run behind :func:`context_preamble` to get the same report.
    """
    argv = ["rez-env", *packages]
    if not command:
        return argv

    if show_info is None:
        show_info = config.show_resolve_info()
    if show_info:
        argv += ["--", "bash", "-c", context_preamble(command, roots)]
    else:
        argv += ["--", command]
    return argv


def build_script(
    packages: Sequence[str],
    command: str = "",
    roots: Sequence[tuple[str, str]] = (),
) -> str:
    """A shell one-liner that echoes the command, runs it, and holds on failure.

    The window closing on failure is the single most annoying way for a
    launcher to break: the error is written and then thrown away faster than
    anyone can read it. So the script prints what it is about to run, and on a
    non-zero exit says so and waits for Enter.

    Echoing the command is worth the line on its own -- when a resolve fails,
    the first question is always what was actually asked for.
    """
    inner = " ".join(
        shlex.quote(part) for part in rez_argv(packages, command, roots=roots)
    )
    hold = config.HOLD_TERMINAL

    if hold == "never":
        return inner

    condition = 'true' if hold == "always" else '[ "$rc" -ne 0 ]'
    return (
        'echo "+ {inner}"; echo; '
        "{inner}; rc=$?; "
        'if {condition}; then echo; '
        'echo "BootyCall: command exited with status $rc"; '
        'read -r -p "Press Enter to close this window... " _; fi'
    ).format(inner=inner, condition=condition)


def expand(
    template: Sequence[str],
    packages: Sequence[str],
    command: str = "",
    roots: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """Build an argv from ``template``.

    ``{script}`` becomes the shell one-liner from :func:`build_script`.
    ``{packages}`` becomes one argument per request rather than a single
    space-joined string, so requests survive as separate argv entries.
    ``{command}`` becomes the executable to run in the resolved context.
    """
    argv: list[str] = []
    for part in template:
        if "{script}" in part:
            argv.append(build_script(packages, command, roots))
        elif "{packages}" in part:
            argv.extend(packages)
        elif "{command}" in part:
            if not command:
                # No application to run: drop this part, and the separator that
                # introduces it, so the template collapses to a plain shell.
                if argv and argv[-1] == "--":
                    argv.pop()
                continue
            argv.append(part.format(command=command))
        else:
            argv.append(part)
    return argv


def build_command(
    packages: Sequence[str],
    command: str,
    roots: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """Argv that resolves ``packages`` and runs ``command`` in a terminal."""
    return expand(config.LAUNCH_COMMAND, packages, command, roots)


def build_terminal_command(packages: Sequence[str]) -> list[str]:
    """Argv that resolves ``packages`` and leaves an interactive shell."""
    return expand(config.TERMINAL_COMMAND, packages)


def _preview(project: Project, argv: Sequence[str]) -> str:
    return "cd %s && %s" % (
        shlex.quote(str(project.path)),
        " ".join(shlex.quote(part) for part in argv),
    )


def command_preview(
    project: Project,
    packages: Sequence[str],
    command: str,
    roots: Sequence[tuple[str, str]] = (),
) -> str:
    """A copy-pasteable representation of what :func:`launch` will run."""
    return _preview(project, build_command(packages, command, roots))


def terminal_preview(project: Project, packages: Sequence[str]) -> str:
    """A copy-pasteable representation of what :func:`open_terminal` will run."""
    return _preview(project, build_terminal_command(packages))


def launch(
    project: Project,
    packages: Sequence[str],
    command: str,
    exclude_roots: Sequence[str] = (),
    include_roots: Sequence[str] = (),
    dry_run: bool = False,
    roots: Sequence[tuple[str, str]] = (),
) -> subprocess.Popen | None:
    """Resolve ``packages`` and start ``command``, detached."""
    return _spawn(
        project,
        build_command(packages, command, roots),
        exclude_roots,
        include_roots,
        dry_run,
    )


def open_terminal(
    project: Project,
    packages: Sequence[str],
    exclude_roots: Sequence[str] = (),
    include_roots: Sequence[str] = (),
    dry_run: bool = False,
) -> subprocess.Popen | None:
    """Open a shell resolved against ``packages``, detached."""
    return _spawn(
        project,
        build_terminal_command(packages),
        exclude_roots,
        include_roots,
        dry_run,
    )


def _spawn(
    project: Project,
    argv: list[str],
    exclude_roots: Sequence[str] = (),
    include_roots: Sequence[str] = (),
    dry_run: bool = False,
) -> subprocess.Popen | None:
    if dry_run:
        return None

    env = os.environ.copy()
    env["ILP_SHOW"] = project.name
    env["BOOTYCALL_SHOW"] = project.name

    # Two reasons to rewrite the path. Switching off a package section means
    # its packages must not reach the resolve, and they are not in the request
    # -- they arrive through the packages path. And a show package lives under
    # a root rez has no reason to know about, so requesting it without adding
    # that root would fail to resolve.
    paths, _note = filtered_packages_path(exclude_roots, include_roots)
    if paths:
        env["REZ_PACKAGES_PATH"] = os.pathsep.join(paths)

    kwargs: dict = {
        # The show folder as cwd: a bootstrap's __file__-relative lookups and
        # anything the DCC opens by relative path both expect to start there.
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
