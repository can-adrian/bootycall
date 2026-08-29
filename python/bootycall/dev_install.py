"""
Getting a dev package from where you edit it to where rez can resolve it.

Two locations, and the whole module is about the gap between them:

* the **working location** (``~/dev`` by default) -- checkouts you are editing;
* the **installed dev root** (``<local>/dev``) -- what rez actually resolves.

Editing the installed copy directly is how a half-written build ends up inside
a running DCC, so BootyCall never blurs the two. It installs from one to the
other, and it tells you when what you are about to launch is older than what
you have been writing.

Nothing here imports rez. Installing shells out to ``rez-build``, because a
package that builds is the only kind rez guarantees is complete -- build
commands, variants and requires are the package's own business, and
reimplementing any of that here would be a second, worse rez.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from . import config
from .local_packages import (
    DEFINITION_FILES,
    LocalPackage,
    dev_working_root,
    version_key,
)

#: Shown on the Launch menu. Kept here so the label and the behaviour that
#: implements it cannot drift apart.
MENU_LABEL = "Update Dev Installs and Launch"

#: Whether that menu item does anything yet. It does.
IMPLEMENTED = True


@dataclass(frozen=True)
class WorkingPackage:
    """A directory in the working location, and whether it is a rez package."""

    name: str
    path: Path
    #: The definition filename found, or "" when this is not a package.
    definition: str = ""
    #: Why it cannot be installed, when it cannot. Empty means it can.
    problem: str = ""

    @property
    def is_package(self) -> bool:
        return bool(self.definition) and not self.problem


def _definition_in(directory: Path) -> str:
    for filename in DEFINITION_FILES:
        if (directory / filename).is_file():
            return filename
    return ""


def list_working_packages(root: Path | str | None = None) -> list[WorkingPackage]:
    """Everything in the working location, packages and not.

    Non-packages are returned rather than filtered out, with ``problem`` saying
    why: a browser that silently omits the folder you were looking for is worse
    than one that shows it greyed out with a reason. A missing root is not an
    error -- most people have not made one yet -- and yields an empty list.
    """
    root_path = Path(root) if root is not None else dev_working_root()
    try:
        entries = sorted(os.scandir(root_path), key=lambda e: e.name.lower())
    except OSError:
        return []

    found: list[WorkingPackage] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue

        path = Path(entry.path)
        definition = _definition_in(path)
        problem = "" if definition else "no package definition in it"
        found.append(
            WorkingPackage(
                name=entry.name, path=path, definition=definition, problem=problem
            )
        )
    return found


# ---------------------------------------------------------------------------
# Installing
# ---------------------------------------------------------------------------


def install_command(dest_root: Path | str) -> list[str]:
    """The argv that builds and installs a working copy."""
    return [
        part.replace("{dest}", str(dest_root)) for part in config.dev_install_command()
    ]


def install(source: Path | str, dest_root: Path | str) -> tuple[bool, str]:
    """Build ``source`` into ``dest_root``. Returns ``(ok, output)``.

    The output is returned whether it worked or not, because a failed rez build
    says why in its own words and paraphrasing that would only lose detail.
    """
    source_path = Path(source)
    if not _definition_in(source_path):
        return False, "%s has no package definition in it" % source_path

    dest = Path(dest_root)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, "cannot create %s: %s" % (dest, exc)

    argv = install_command(dest)
    try:
        result = subprocess.run(  # noqa: S603
            argv,
            cwd=str(source_path),
            capture_output=True,
            text=True,
            timeout=config.dev_install_timeout(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "the build was still going after %gs and was given up on" % (
            config.dev_install_timeout()
        )
    except OSError as exc:
        return False, "could not run %s: %s" % (argv[0], exc)

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return False, output.strip() or "%s exited %d" % (argv[0], result.returncode)
    return True, output.strip()


def symlink(source: Path | str, dest_root: Path | str) -> tuple[bool, str]:
    """Link ``source`` into ``dest_root`` instead of building it.

    The live option: edits in the working copy are picked up by the next
    resolve with no install step, which is what you want while you are actually
    changing something every few minutes.

    It is not the default, and the difference is worth stating. A symlink skips
    the build, so a package whose payload is produced by one is incomplete; and
    it makes the staleness check meaningless, because the installed copy *is*
    the working copy and can never be behind it. It also means a broken save is
    live in every DCC you launch, immediately.
    """
    source_path = Path(source).resolve()
    if not _definition_in(source_path):
        return False, "%s has no package definition in it" % source_path

    dest = Path(dest_root) / source_path.name
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, "cannot create %s: %s" % (dest.parent, exc)

    if dest.is_symlink() or dest.exists():
        # Replacing a link is routine; replacing a real installed package is
        # not something to do behind the user's back.
        if not dest.is_symlink():
            return False, (
                "%s is already installed as a real directory - remove it first "
                "if you mean to replace it with a link" % dest
            )
        try:
            dest.unlink()
        except OSError as exc:
            return False, "cannot replace %s: %s" % (dest, exc)

    try:
        dest.symlink_to(source_path, target_is_directory=True)
    except OSError as exc:
        return False, "cannot link %s: %s" % (dest, exc)
    return True, "%s -> %s" % (dest, source_path)


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def newest_mtime(path: Path | str, ignore: Sequence[str] = ()) -> float:
    """The most recent modification time anywhere under ``path``.

    Build products and version-control directories are skipped: their times
    move for reasons that have nothing to do with the source, and counting them
    would report everything as permanently out of date -- a warning that is
    always on being one nobody reads.
    """
    skip = set(ignore or config.DEV_MTIME_IGNORE)
    root = Path(path)
    try:
        newest = root.stat().st_mtime
    except OSError:
        return 0.0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for name in filenames:
            if name in skip or name.endswith(".pyc"):
                continue
            try:
                newest = max(newest, os.stat(os.path.join(dirpath, name)).st_mtime)
            except OSError:
                continue
    return newest


@dataclass(frozen=True)
class StaleInstall:
    """An installed dev package older than the working copy it came from."""

    package: LocalPackage
    source: Path
    installed_mtime: float
    source_mtime: float

    @property
    def name(self) -> str:
        return self.package.name

    @property
    def behind_by(self) -> float:
        return self.source_mtime - self.installed_mtime

    def describe(self) -> str:
        return "%s (working copy is %s newer)" % (
            self.package.request,
            _duration(self.behind_by),
        )


def _duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 90:
        return "%d seconds" % int(seconds)
    if seconds < 5400:
        return "%d minutes" % int(seconds // 60)
    if seconds < 172800:
        return "%d hours" % int(seconds // 3600)
    return "%d days" % int(seconds // 86400)


def stale_installs(
    installed: Iterable[LocalPackage], working_root: Path | str | None = None
) -> list[StaleInstall]:
    """Which installed dev packages are behind their working copies.

    Matched by directory name, which is what the working location and the dev
    root have in common. A package with no working copy is not stale -- it was
    installed from somewhere else, and calling that out of date would be an
    invention.

    A symlinked install is never stale either: it *is* the working copy, so the
    two times are the same by construction.

    Only the newest version of each name is checked. Older versions are history,
    and telling someone their 0.9.0 is behind the source that now builds 1.0.0
    is noise.
    """
    root = Path(working_root) if working_root is not None else dev_working_root()
    sources = {p.name: p for p in list_working_packages(root) if p.is_package}
    if not sources:
        return []

    newest: dict[str, LocalPackage] = {}
    for package in installed:
        current = newest.get(package.name)
        if current is None or version_key(package.version) > version_key(
            current.version
        ):
            newest[package.name] = package

    stale: list[StaleInstall] = []
    for name, package in newest.items():
        source = sources.get(name)
        if source is None or package.path.is_symlink():
            continue
        source_time = newest_mtime(source.path)
        installed_time = newest_mtime(package.path)
        if source_time > installed_time:
            stale.append(
                StaleInstall(
                    package=package,
                    source=source.path,
                    installed_mtime=installed_time,
                    source_mtime=source_time,
                )
            )
    stale.sort(key=lambda s: s.name.lower())
    return stale


def update_installs(
    stale: Sequence[StaleInstall], dest_root: Path | str
) -> tuple[list[str], list[str]]:
    """Re-install each stale package. Returns ``(updated, failures)``.

    Every one is attempted even after a failure: an artist with four stale
    builds wants the three that work, and a list of what did not rather than a
    stop at the first.
    """
    updated: list[str] = []
    failures: list[str] = []
    for item in stale:
        ok, output = install(item.source, dest_root)
        if ok:
            updated.append(item.name)
        else:
            failures.append("%s: %s" % (item.name, _last_line(output)))
    return updated, failures


def _last_line(text: str) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1][:300] if lines else "no output"


def remove_installed(package: LocalPackage, dest_root: Path | str) -> str:
    """Remove one installed dev package. Returns "" or an error.

    A symlink is unlinked, never followed: following it would delete the
    working copy, which is the one thing here that is not reproducible.
    """
    target = package.path
    root = Path(dest_root).resolve()

    if target.is_symlink():
        try:
            target.unlink()
        except OSError as exc:
            return "could not unlink %s: %s" % (target, exc)
        return ""

    try:
        resolved = target.resolve()
    except OSError as exc:
        return "could not resolve %s: %s" % (target, exc)
    if resolved == root or root not in resolved.parents:
        return "refusing to remove %s: it is not inside %s" % (resolved, root)
    try:
        shutil.rmtree(resolved)
    except OSError as exc:
        return "could not remove %s: %s" % (resolved, exc)
    return ""


# ---------------------------------------------------------------------------
# Using only some of them
# ---------------------------------------------------------------------------


def view_root() -> Path:
    """Where the filtered view of the dev root is built."""
    from .configs import default_config_path

    return default_config_path().parent / "devview"


def selection_view(
    dev_root_path: Path | str,
    disabled: Sequence[str],
    view: Path | str | None = None,
) -> tuple[Path | None, str]:
    """A dev root containing only the packages that are switched on.

    Returns ``(path, error)``. ``path`` is ``None`` when the real dev root can
    be used as-is, which is the common case.

    Why a directory of links rather than telling rez to exclude something: a
    package filter excludes a *name*, and the studio almost certainly ships a
    package with the same name as your dev build -- that is the entire reason
    you made one. Excluding by name would take the studio copy out too and fail
    the resolve. A root that simply does not contain the package you switched
    off has none of that ambiguity: rez looks, does not find it there, and
    carries on to the next root exactly as it would if you had never built it.

    Rebuilt from scratch each time rather than patched, because reasoning about
    a stale link is harder than making a new directory.
    """
    source = Path(dev_root_path)
    off = {str(n) for n in disabled}
    if not off:
        return None, ""

    target = Path(view) if view is not None else view_root()
    try:
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "could not prepare %s: %s" % (target, exc)

    linked = 0
    try:
        names = [
            entry.name
            for entry in os.scandir(source)
            # Hidden directories are not packages -- rez keeps its own .cache
            # in a package root -- and linking them in would only give rez more
            # to scan on every resolve.
            if entry.is_dir() and not entry.name.startswith(".")
        ]
    except OSError as exc:
        return None, "could not read %s: %s" % (source, exc)

    for name in names:
        if name in off:
            continue
        try:
            (target / name).symlink_to(source / name, target_is_directory=True)
            linked += 1
        except OSError as exc:
            return None, "could not link %s: %s" % (name, exc)

    if not linked:
        # Everything switched off is the same as the section switched off, and
        # an empty root on the path is a root rez wastes time reading.
        return None, ""
    return target, ""
