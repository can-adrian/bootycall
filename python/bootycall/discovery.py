"""
Show discovery.

Lists projects from :data:`bootycall.config.SHOWS_ROOT` and locates each
project's bootstrap module. Both operations are cheap enough to run on the UI
thread, but results are cached because ``/ice/shows`` is on a network mount and
a cold listing is not free.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import config
from .local_packages import request_name, version_key
from .parser import Bootstrap, BootstrapParseError, parse_file


@dataclass(frozen=True)
class Project:
    """A show folder under the shows root."""

    name: str
    path: Path

    def __str__(self) -> str:  # so the completer model shows the bare name
        return self.name


class ProjectsUnavailable(Exception):
    """Raised when the shows root cannot be listed at all."""


def list_projects(root: str | Path | None = None) -> list[Project]:
    """Return the show folders under ``root``, sorted case-insensitively.

    Only directories are considered. Dotfiles, and anything named in
    :data:`config.SHOW_EXCLUDES`, are skipped.
    """
    root_path = Path(root or config.shows_root())
    try:
        entries = list(os.scandir(root_path))
    except OSError as exc:
        raise ProjectsUnavailable("cannot list %s: %s" % (root_path, exc)) from exc

    projects: list[Project] = []
    for entry in entries:
        name = entry.name
        if name.startswith(".") or name in config.SHOW_EXCLUDES:
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        projects.append(Project(name=name, path=Path(entry.path)))

    projects.sort(key=lambda p: p.name.lower())
    return projects


def find_bootstrap(project: Project | Path | str) -> Path | None:
    """Locate a project's bootstrap module, or ``None`` if there isn't one."""
    root = project.path if isinstance(project, Project) else Path(project)
    for pattern in config.BOOTSTRAP_GLOBS:
        for candidate in sorted(root.glob(pattern)):
            if not candidate.is_file() or candidate.name.startswith("_"):
                continue
            try:
                head = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if config.BOOTSTRAP_MARKER in head and "packages" in head:
                return candidate
    return None


def load_bootstrap(project: Project) -> tuple[Bootstrap | None, str]:
    """Return ``(bootstrap, message)`` for ``project``.

    ``bootstrap`` is ``None`` when nothing usable was found; ``message`` always
    explains what happened and is safe to show in the UI.
    """
    path = find_bootstrap(project)
    if path is None:
        return None, "No bootstrap file found under %s" % project.path

    try:
        bootstrap = parse_file(path)
    except BootstrapParseError as exc:
        return None, str(exc)

    message = "%s - %d tools" % (
        os.path.relpath(path, project.path),
        len(bootstrap.packages),
    )
    if bootstrap.unresolved:
        message += "  (%d entries not statically resolvable)" % len(
            bootstrap.unresolved
        )
    return bootstrap, message


def available_dccs(bootstrap: Bootstrap) -> list[tuple[config.Dcc, tuple[str, ...]]]:
    """Filter the hard-coded DCC registry down to what this show defines.

    Returns ``(dcc, keys)`` pairs for every DCC with at least one matching entry
    in the bootstrap's ``packages`` mapping.

    Keys that resolve to an identical package tuple are collapsed to the first
    one: the bootstraps alias heavily (``packages["houdinicore"] =
    packages["houdini"]``), and offering two variants that produce byte-for-byte
    the same environment is a choice with no content.
    """
    out: list[tuple[config.Dcc, tuple[str, ...]]] = []
    for dcc in config.DCCS:
        keys = dcc.available_keys(bootstrap.packages)
        if not keys:
            continue
        unique: list[str] = []
        seen: list[tuple[str, ...]] = []
        for key in keys:
            packages = bootstrap.packages.get(key, ())
            if packages in seen:
                continue
            seen.append(packages)
            unique.append(key)
        out.append((dcc, tuple(unique)))
    return out


def variant_version(packages: Sequence[str], version_package: str) -> str:
    """The version of ``version_package`` inside one variant's request list.

    ``("nuke-16.0", "base-6", ...)`` with ``version_package="nuke"`` gives
    ``"16.0"``. Empty when the variant does not name it -- some shows build a
    tool out of parts that never mention the application package.
    """
    if not version_package:
        return ""
    for request in packages:
        if request_name(request) == version_package and "-" in request:
            return request.split("-", 1)[1]
    return ""


def newest_variant(
    bootstrap: Bootstrap, dcc: config.Dcc, keys: Sequence[str]
) -> str:
    """The variant to select by default: the highest version among ``keys``.

    Versions compare numerically, so Nuke 16.0 beats 13.2 rather than losing a
    string comparison. Ties keep registry order -- three Houdini variants all on
    21.0 is not a choice the version can settle, so the best-first order in the
    registry decides.
    """
    if not keys:
        return ""
    best = keys[0]
    best_key = version_key(
        variant_version(bootstrap.packages.get(best, ()), dcc.version_package)
    )
    for key in keys[1:]:
        candidate = version_key(
            variant_version(bootstrap.packages.get(key, ()), dcc.version_package)
        )
        if candidate > best_key:
            best, best_key = key, candidate
    return best


def show_package(project: Project) -> str | None:
    """The show's own rez package, if it has one.

    The bootstrap's ``_get_show_packages()`` looks for a package named
    ``show_<folder>`` under ``<show>/.ilp/packages`` and appends it to every
    resolve. We can't run rez's validator from here, but we can check the
    directory exists, which is enough to include it in a terminal request
    instead of silently dropping it.
    """
    name = "show_%s" % project.name
    if (project.path / ".ilp" / "packages" / name).is_dir():
        return name
    return None
