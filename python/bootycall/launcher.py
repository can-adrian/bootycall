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
import tempfile
import time
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
    overrides = dict(config.show_env(project.name))
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


#: Colour per note level, as a shell variable name.
_LEVELS = {"ok": "_bcG", "warn": "_bcY", "error": "_bcR", "": "_bcD"}

#: Colour per highlighted root label, as a shell variable name. rez already
#: marks its own local path green, so local packages keep green and dev ones
#: get orange -- they are the ones with no marking of their own, and the ones
#: you most want to notice.
_ROOT_COLOURS = {"dev": "_bcO", "local": "_bcG"}


def _escape(text: str) -> str:
    """Text safe inside a double-quoted shell string."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


def launch_banner(
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> str:
    """Shell that reports what BootyCall did to this environment.

    rez's own table says what resolved. It cannot say which of those forty
    lines are yours, and it has no idea you switched a whole package root off
    before launching -- that happened in a window it never saw. Both are things
    you want to know in the first two seconds of a session that behaves oddly.

    ``notes`` are decided in Python, where the switches live. The package list
    is read from ``REZ_<NAME>_ROOT`` in the resolved environment, because that
    is the only place that knows what actually happened.

    Returned as ordinary multi-line shell, because it goes into a file. See
    :func:`preamble_text` for why that matters.
    """
    if not roots and not notes:
        return ""

    lines = [
        "if [ -t 1 ]; then",
        "    _bcB=$(printf '\\033[1m')",
        "    _bcG=$(printf '\\033[32m')",
        "    _bcY=$(printf '\\033[33m')",
        "    _bcR=$(printf '\\033[31m')",
        # 256-colour orange rather than yellow: the point is that a dev
        # package is not a local one, and next to green at a glance yellow
        # reads as "the same but brighter".
        "    _bcO=$(printf '\\033[38;5;208m')",
        "    _bcD=$(printf '\\033[2m')",
        "    _bc0=$(printf '\\033[0m')",
        "else",
        "    _bcB= _bcG= _bcY= _bcR= _bcO= _bcD= _bc0=",
        "fi",
        "",
        "printf '%s\\n' \"${_bcB}BootyCall${_bc0}${_bcD}"
        " - what this window changed about the environment${_bc0}\"",
    ]

    for level, text in notes:
        lines.append(
            "printf '%%s\\n' \"${%s}  %s${_bc0}\"" % (_LEVELS.get(level, "_bcD"), _escape(text))
        )

    if roots:
        # One awk pass pairs every REZ_<NAME>_ROOT with its
        # REZ_<NAME>_VERSION, works out which of our roots the path sits
        # under, and prints the finished line. Doing the pairing in shell
        # needs ${!var} indirect expansion, which bash before 5.1 refuses
        # here -- and this script has to run under whatever shell the site
        # configured, not the one it was written on.
        #
        # Slicing by $1 rather than splitting on "=" keeps values containing
        # "=" intact, which paths occasionally do. Roots arrive as -v
        # assignments so no path is ever pasted into the program text.
        assigns = " ".join(
            "-v r%d=%s -v l%d=%s" % (i, shlex.quote(root), i, shlex.quote(label))
            for i, (label, root) in enumerate(roots)
        )
        # First match wins, so the caller's order decides: the dev root is
        # nested inside the local one, and reversed every dev package would
        # be reported as local.
        tests = "\n".join(
            # The matched root goes out with the line: the symlink walk below
            # needs somewhere to stop, and "the root this package was found
            # under" is the only honest boundary.
            '            if (index(p, r%d "/") == 1) '
            '{ print n, l%d, r%d, p; continue }' % (i, i, i)
            for i in range(len(roots))
        )
        # Colour per label, chosen in the shell rather than baked into awk's
        # output, so the lines stay plain text when stdout is not a terminal.
        cases = "\n".join(
            "            %s) _bc_c=$%s ;;" % (shlex.quote(label), colour)
            for label, colour in sorted(
                {(label, _ROOT_COLOURS.get(label, "_bcG")) for label, _ in roots}
            )
        )
        lines += [
            "",
            "_bc_hits=$(env | awk -F= %s '" % assigns,
            "    /^REZ_[A-Z0-9_]*_ROOT=/ {",
            "        k = substr($1, 5, length($1) - 9)",
            "        root[k] = substr($0, length($1) + 2)",
            "    }",
            "    /^REZ_[A-Z0-9_]*_VERSION=/ {",
            "        k = substr($1, 5, length($1) - 12)",
            "        ver[k] = substr($0, length($1) + 2)",
            "    }",
            "    END {",
            "        for (k in root) {",
            '            n = (ver[k] != "" ? tolower(k) "-" ver[k] : tolower(k))',
            "            p = root[k]",
            tests,
            "        }",
            "    }' | sort)",
            "",
            'if [ -n "$_bc_hits" ]; then',
            "    printf '%s\\n'"
            ' "${_bcG}  your packages in this environment:${_bc0}"',
            # A pipeline, so this loop runs in a subshell -- fine, because it
            # prints as it goes rather than accumulating anything the rest of
            # the script needs.
            "    printf '%s\\n' \"$_bc_hits\" |",
            "    while read -r _bc_name _bc_label _bc_root _bc_path; do",
            "        _bc_c=$_bcG",
            '        case "$_bc_label" in',
            cases,
            "        esac",
            # Asked of the filesystem, not predicted from what BootyCall
            # thinks it installed: a link someone made by hand counts too.
            #
            # Every level between the package and the root it was found under,
            # because which level is the link depends on how it was made -- the
            # version directory for a versioned install, the name directory for
            # an unversioned one, and neither if someone linked by hand
            # somewhere else. Stopping at the root matters: at a site where
            # /ice is itself a symlink, walking past it would report every
            # package in the studio as symlinked.
            "        _bc_link=",
            '        _bc_walk=${_bc_path%/}',
            '        while [ -n "$_bc_walk" ] && [ "$_bc_walk" != "$_bc_root" ] \\',
            '              && [ "$_bc_walk" != "/" ]; do',
            '            if [ -L "$_bc_walk" ]; then',
            "                _bc_link='  (symlinked)'",
            "                break",
            "            fi",
            '            _bc_walk=${_bc_walk%/*}',
            "        done",
            "        printf '%s\\n'"
            ' "    ${_bc_c}${_bc_name}  (${_bc_label})${_bc_link}${_bc0}"',
            "    done",
            "else",
            "    printf '%s\\n'"
            ' "${_bcR}  none of your local or dev packages are in this'
            ' environment${_bc0}"',
            "fi",
        ]

    lines.append("")
    lines.append("echo")
    return "\n".join(lines)


def preamble_text(
    command: str = "",
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> str:
    """The whole script: print the context, print the report, then hand over.

    ``rez-context`` prints the same table rez shows on the way into an
    interactive resolved shell -- requested packages, resolved packages, the
    lot -- and colours it when stdout is a terminal, which here it is.
    :func:`launch_banner` then says which of those forty-odd lines are yours,
    and what this window switched off, neither of which rez can know.

    ``exec`` on purpose: the shell replaces itself with the application rather
    than sitting around as its parent, so the process tree is the same as it
    would have been without the wrapper. With no ``command`` it execs a shell
    instead, which is the terminal case.
    """
    body = [
        "# Written by BootyCall. Read it, run it, delete it -- nothing here",
        "# is precious, and it is here to be looked at when a launch goes",
        "# somewhere you did not expect.",
        "",
        "rez-context 2>/dev/null",
        "echo",
        "",
    ]
    banner = launch_banner(roots, notes)
    if banner:
        body.append(banner)
        body.append("")
    body.append("exec %s" % shlex.quote(command or "bash"))
    body.append("")
    return "\n".join(body)


def script_dir() -> str:
    """Where launch scripts are written, created if need be.

    ``$TMPDIR`` when the environment sets one, otherwise the platform default
    -- the same rule everything else on the box follows, so a site that
    redirects temporary files redirects these too. Per-user and 0700, because
    the script names the shows and packages you are working on.
    """
    base = config.SCRIPT_DIR or tempfile.gettempdir()
    path = os.path.join(base, "bootycall-%d" % os.getuid())
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _prune_scripts(path: str, max_age: float = 86400.0) -> None:
    """Delete launch scripts older than a day.

    They cannot be deleted after use: the launch is detached, and a DCC that
    takes a minute to start is still the child of a shell reading this file.
    So they are cleaned up on the way in instead, which also leaves the last
    one you ran sitting there to be read.
    """
    now = time.time()
    try:
        names = os.listdir(path)
    except OSError:
        return
    for name in names:
        full = os.path.join(path, name)
        try:
            if now - os.path.getmtime(full) > max_age:
                os.unlink(full)
        except OSError:
            pass


def write_preamble(
    command: str = "",
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> str:
    """Write the preamble to a file and return its path, or ``""`` on failure.

    A file rather than ``bash -c '<one-liner>'`` because rez re-quotes the
    command it is handed: it writes the whole thing into a ``rez-shell.sh`` of
    its own inside double quotes, where our single quotes stop quoting, ``$1``
    in an awk program gets expanded by the shell, and ``$(...)`` runs at the
    wrong moment. Two releases went out trying to write a one-liner that
    survives that, which is not a thing that exists. A path has nothing in it
    for a shell to get wrong.

    Returning ``""`` rather than raising: a temporary directory that cannot be
    written to is a reason to launch without the report, not a reason not to
    launch.
    """
    text = preamble_text(command, roots, notes)
    try:
        path = script_dir()
        _prune_scripts(path)
        handle, name = tempfile.mkstemp(
            prefix="launch-", suffix=".sh", dir=path, text=True
        )
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
        return name
    except OSError:
        return ""


def rez_argv(
    packages: Sequence[str],
    command: str = "",
    show_info: bool | None = None,
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """The rez invocation itself, without a terminal around it.

    With no command this drops you in an interactive resolved shell. Bare
    ``rez-env`` prints rez's context on the way in for free, so that is what
    runs when there is nothing of our own to add. When there *is* -- a root
    switched off, a dev package to point at, an application to run -- it goes
    behind :func:`preamble_text`, written to a file by :func:`write_preamble`.

    A file, not ``bash -c``: rez re-quotes whatever command it is given, and
    nothing quoted survives the trip. See :func:`write_preamble`.
    """
    argv = ["rez-env", *packages]
    if show_info is None:
        show_info = config.show_resolve_info()

    wanted = show_info and (command or roots or notes)
    script = write_preamble(command, roots, notes) if wanted else ""
    if script:
        return argv + ["--", "bash", script]

    if command:
        argv += ["--", command]
    return argv


def build_script(
    packages: Sequence[str],
    command: str = "",
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> str:
    """A shell one-liner that echoes the command, runs it, and holds on failure.

    The window closing on failure is the single most annoying way for a
    launcher to break: the error is written and then thrown away faster than
    anyone can read it. So the script prints what it is about to run, and on a
    non-zero exit says so and waits for Enter.

    Echoing the command is worth the line on its own -- when a resolve fails,
    the first question is always what was actually asked for. So the echoed
    line is the bare request, not the reporting wrapper around it: with the
    banner in, the real argv is a screen of quoted shell, and a line nobody
    reads answers no questions.

    The echo goes through a single-quoted ``printf`` argument rather than
    ``echo "..."``. The argv is quoted shell full of quotes, ``$``, and
    ``$(...)``; inside a double-quoted string the quoting flips halfway
    through and the outer shell starts expanding and running pieces of the
    command it was only meant to display -- which broke the whole script.
    """
    inner = " ".join(
        shlex.quote(part)
        for part in rez_argv(packages, command, roots=roots, notes=notes)
    )
    shown = " ".join(
        shlex.quote(part)
        for part in rez_argv(packages, command, show_info=False)
    )
    hold = config.HOLD_TERMINAL

    if hold == "never":
        return inner

    condition = 'true' if hold == "always" else '[ "$rc" -ne 0 ]'
    return (
        "printf '+ %s\\n\\n' {shown}; "
        "{inner}; rc=$?; "
        'if {condition}; then echo; '
        'echo "BootyCall: command exited with status $rc"; '
        'read -r -p "Press Enter to close this window... " _; fi'
    ).format(inner=inner, shown=shlex.quote(shown), condition=condition)


def expand(
    template: Sequence[str],
    packages: Sequence[str],
    command: str = "",
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
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
            argv.append(build_script(packages, command, roots, notes))
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
    notes: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """Argv that resolves ``packages`` and runs ``command`` in a terminal."""
    return expand(config.LAUNCH_COMMAND, packages, command, roots, notes)


def build_terminal_command(
    packages: Sequence[str],
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> list[str]:
    """Argv that resolves ``packages`` and leaves an interactive shell."""
    return expand(config.TERMINAL_COMMAND, packages, "", roots, notes)


def _preview(project: Project, argv: Sequence[str]) -> str:
    return "cd %s && %s" % (
        shlex.quote(str(project.path)),
        " ".join(shlex.quote(part) for part in argv),
    )


def rez_preview(packages: Sequence[str], command: str = "") -> str:
    """Just the rez invocation, ready to paste into a shell.

    Not the terminal wrapper, not the ``cd``, not the reporting preamble: those
    are how BootyCall runs it, and none of them are what you want in your hand
    when you are about to run the same resolve yourself.

    ``show_info=False`` also keeps this side-effect free. The full argv writes a
    launch script to disk to get a path to point rez at, and building a preview
    is not a reason to write a file.
    """
    return " ".join(
        shlex.quote(part)
        for part in rez_argv(packages, command, show_info=False)
    )


def command_preview(
    project: Project,
    packages: Sequence[str],
    command: str,
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> str:
    """A copy-pasteable representation of what :func:`launch` will run."""
    return _preview(project, build_command(packages, command, roots, notes))


def terminal_preview(
    project: Project,
    packages: Sequence[str],
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> str:
    """A copy-pasteable representation of what :func:`open_terminal` will run."""
    return _preview(project, build_terminal_command(packages, roots, notes))


def launch(
    project: Project,
    packages: Sequence[str],
    command: str,
    exclude_roots: Sequence[str] = (),
    include_roots: Sequence[str] = (),
    dry_run: bool = False,
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> subprocess.Popen | None:
    """Resolve ``packages`` and start ``command``, detached."""
    return _spawn(
        project,
        build_command(packages, command, roots, notes),
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
    roots: Sequence[tuple[str, str]] = (),
    notes: Sequence[tuple[str, str]] = (),
) -> subprocess.Popen | None:
    """Open a shell resolved against ``packages``, detached."""
    return _spawn(
        project,
        build_terminal_command(packages, roots, notes),
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
    # A show package's commands() runs during the resolve and may read the show
    # out of the environment, expecting the bootstrap to have put it there. We
    # went straight to rez, so it has to come from here -- and a show whose
    # package reads a name nobody set fails the whole resolve with
    # PackageCommandError, naming the variable.
    env.update(config.show_env(project.name))

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
