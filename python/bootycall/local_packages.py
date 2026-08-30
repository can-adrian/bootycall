"""
Local dev package discovery.

Rez local packages live at ``<root>/<name>/<version>/package.py``, with the
version level omitted for unversioned packages. There are two per-user roots::

    /ice/rez/packages/local/<user>          local packages
    /ice/rez/packages/local/<user>/dev      dev packages

The second is nested inside the first. ``dev`` is a reserved name (see
:data:`config.RESERVED_PACKAGE_NAMES`) and is skipped in every scan, which makes
the nesting harmless -- no rez package is ever called ``dev``.

Anything found in either sits in front of the studio packages on a normal
``REZ_PACKAGES_PATH``, so a local build of ``nuke_utils`` silently replaces the
studio one in every resolve. That shadowing is the reason these lists are worth
showing next to the resolve: it is the usual answer to "why does it work on my
machine and nowhere else".
"""

from __future__ import annotations

import getpass
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from . import config

#: Definition filenames rez recognises, best-first.
DEFINITION_FILES = ("package.py", "package.yaml", "package.yml", "package.txt")


def current_user() -> str:
    """The user whose dev packages we show."""
    override = os.environ.get("BOOTYCALL_REZ_USER")
    if override:
        return override
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - getuser() raises bare KeyError on some hosts
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def local_root(user: str | None = None) -> Path:
    """Path to the current user's local package root."""
    return Path(config.local_root_template().format(user=user or current_user()))


def dev_root(user: str | None = None) -> Path:
    """Path to the current user's dev package root, inside the local root."""
    local = local_root(user)
    return Path(
        config.dev_root_template().format(local=local, user=user or current_user())
    )


def dev_working_root(user: str | None = None) -> Path:
    """Where the user edits dev packages, before they are installed.

    Separate from :func:`dev_root` on purpose: one is a checkout you are
    changing, the other is what rez resolves. Editing the installed copy
    directly is how a half-written build ends up inside a running DCC.
    """
    name = user or current_user()
    return Path(
        config.dev_working_root_template().format(
            user=name, home=os.path.expanduser("~"), local=local_root(name)
        )
    ).expanduser()


@dataclass(frozen=True)
class LocalPackage:
    """One versioned package directory under the dev root."""

    name: str
    version: str
    path: Path
    definition: str = ""

    @property
    def request(self) -> str:
        """How this package would be written in a rez request."""
        return "%s-%s" % (self.name, self.version) if self.version else self.name

    def __str__(self) -> str:
        return self.request


class LocalPackagesUnavailable(Exception):
    """Raised when the dev root exists but cannot be listed."""


def version_key(version: str) -> list[tuple[int, object]]:
    """Sort key that orders 2.10 after 2.9 rather than before it."""
    key: list[tuple[int, object]] = []
    for part in re.split(r"[._-]+", version):
        if part.isdigit():
            key.append((0, int(part)))
        elif part:
            key.append((1, part))
    return key


def _definition_in(directory: Path) -> str:
    for filename in DEFINITION_FILES:
        if (directory / filename).is_file():
            return filename
    return ""


def _subdirs(directory: Path) -> list[Path]:
    try:
        return [
            Path(entry.path)
            for entry in os.scandir(directory)
            if not entry.name.startswith(".") and entry.is_dir()
        ]
    except OSError:
        return []


def list_local_packages(
    root: Path | str | None = None,
    exclude: Sequence[str] | None = None,
) -> list[LocalPackage]:
    """Return the packages under ``root``, newest version of each first.

    ``exclude`` names directories that are not packages; it defaults to
    :data:`config.RESERVED_PACKAGE_NAMES`, which holds ``dev``. The dev root is
    nested inside the local root, and without the skip it reads as a package
    named ``dev`` whose "versions" are the dev package names -- a quietly wrong
    list rather than a visible error. Blacklisting the name is safe: no rez
    package is ever called ``dev``.

    A missing root is not an error -- most people have never made a local
    package -- and yields an empty list. A root that exists but cannot be read
    raises :class:`LocalPackagesUnavailable`.
    """
    root_path = Path(root) if root is not None else local_root()
    if not root_path.exists():
        return []
    try:
        os.scandir(root_path)
    except OSError as exc:
        raise LocalPackagesUnavailable(
            "cannot list %s: %s" % (root_path, exc)
        ) from exc

    skip = set(
        config.RESERVED_PACKAGE_NAMES if exclude is None else exclude
    )
    found: list[LocalPackage] = []
    for name_dir in _subdirs(root_path):
        name = name_dir.name
        if name in skip:
            continue

        # Unversioned: <root>/<name>/package.py
        definition = _definition_in(name_dir)
        if definition:
            found.append(
                LocalPackage(name=name, version="", path=name_dir, definition=definition)
            )
            continue

        versions: list[LocalPackage] = []
        for version_dir in _subdirs(name_dir):
            definition = _definition_in(version_dir)
            if not definition:
                # Not a package version -- could be a stray build folder.
                continue
            versions.append(
                LocalPackage(
                    name=name,
                    version=version_dir.name,
                    path=version_dir,
                    definition=definition,
                )
            )
        # Newest first: with dev packages you almost always want the latest.
        versions.sort(key=lambda p: version_key(p.version), reverse=True)
        found.extend(versions)

    found.sort(key=lambda p: (p.name.lower(), version_key(p.version)))
    # Re-apply newest-first within each name after the name sort.
    regrouped: list[LocalPackage] = []
    for pkg_name in dict.fromkeys(p.name for p in found):
        group = [p for p in found if p.name == pkg_name]
        group.sort(key=lambda p: version_key(p.version), reverse=True)
        regrouped.extend(group)
    return regrouped


def delete_package(package: LocalPackage, root: Path | str) -> str:
    """Delete one package directory from disk. Returns "" or an error message.

    Guarded rather than trusting the caller: this removes a directory tree, and
    the two cheap checks below are the difference between deleting a dev build
    and deleting whatever it happened to point at.

    * the target must live strictly **inside** the root it was listed from, so
      a path that escaped by any route cannot be removed;
    * a symlinked package is refused outright -- following it would delete the
      shared location it points to, not the user's copy.

    A version directory left as the only child of its package-name directory
    takes the empty parent with it, so removing your last ``nuke_utils`` build
    does not leave an empty ``nuke_utils/`` behind to look like a package.
    """
    root_path = Path(root).resolve()
    target = package.path

    if target.is_symlink():
        return "%s is a symlink; delete it where it really lives" % target

    try:
        resolved = target.resolve()
    except OSError as exc:
        return "could not resolve %s: %s" % (target, exc)

    if resolved == root_path or root_path not in resolved.parents:
        return "refusing to delete %s: it is not inside %s" % (resolved, root_path)

    if not resolved.is_dir():
        return "%s is no longer there" % resolved

    try:
        shutil.rmtree(resolved)
    except OSError as exc:
        return "could not delete %s: %s" % (resolved, exc)

    parent = resolved.parent
    if parent != root_path:
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            # An empty directory left behind is untidy, not a failure.
            pass
    return ""


def request_name(request: str) -> str:
    """The package name part of a rez request (``nuke_utils-4`` -> ``nuke_utils``)."""
    return request.split("-", 1)[0].strip()


def request_range(request: str) -> str:
    """The version part of a rez request (``nuke_utils-4`` -> ``4``)."""
    _, _, rest = request.partition("-")
    return rest.strip()


def satisfies(version: str, request: str) -> bool | None:
    """Can ``version`` be used for ``request``? ``None`` when we cannot tell.

    Only the request forms the bootstraps actually use are decided here:

    * no version at all (``base``) -- anything satisfies it;
    * a prefix range (``nuke-16.0``, ``base-6``) -- rez reads this as "any
      version starting 16.0", so ``16.0.3`` satisfies it and ``16.1`` does not;
    * a lower bound (``python-3+``).

    Everything else -- explicit ranges, unions, exclusions -- returns ``None``,
    and callers must treat that as "no claim". Guessing at a range this does
    not understand would trade a warning that is sometimes missing for one that
    is sometimes wrong, which is the worse of the two.
    """
    wanted = request_range(request)
    if not wanted:
        return True
    if any(c in wanted for c in "<>,|"):
        return None
    if not version:
        # An unversioned package satisfies only an unversioned request.
        return False

    if wanted.endswith("+"):
        base = wanted[:-1].strip()
        if not base:
            return True
        return version_key(version) >= version_key(base)

    if ".." in wanted:
        return None

    # A prefix range: every part the request names must match, and the version
    # may carry more parts after them.
    wanted_parts = re.split(r"[._-]+", wanted)
    version_parts = re.split(r"[._-]+", version)
    if len(wanted_parts) > len(version_parts):
        return False
    return all(a == b for a, b in zip(wanted_parts, version_parts))


@dataclass(frozen=True)
class Shadow:
    """A local build that the resolve names, and whether it can actually be used."""

    name: str
    #: The request from the show's package list that names it.
    request: str
    #: False when the build provably cannot satisfy that request, so rez will
    #: never choose it. None when the request form is one we do not decide.
    usable: bool | None = True

    @property
    def blocked(self) -> bool:
        return self.usable is False


def shadowed_requests(
    packages: Iterable[LocalPackage], requests: Sequence[str]
) -> dict[str, Shadow]:
    """Map local package name -> what the resolve asks of it.

    Names are matched first, then the version is checked against the request.
    Both halves matter, and the second one used to be missing: a dev
    ``nuke_utils-4.9.0`` against a request of ``nuke_utils-4.10`` is not an
    override, it is a build rez will not look at twice.

    Even a usable one is only a *candidate*. rez picks the highest version
    satisfying the request across every package path, and path order breaks
    ties between equal versions rather than beating a higher one -- so a studio
    build newer than yours still wins. That is a fact about rez, not something
    BootyCall can see without asking it, so the wording it drives has to stay
    "overrides" rather than "will be used".
    """
    by_name = {request_name(r): r for r in requests}
    hits: dict[str, Shadow] = {}
    for package in packages:
        request = by_name.get(package.name)
        if request is None:
            continue
        # Keep the first (newest) build of a name: the list is newest-first,
        # and an older one losing tells you nothing.
        if package.name in hits:
            continue
        hits[package.name] = Shadow(
            name=package.name,
            request=request,
            usable=satisfies(package.version, request),
        )
    return hits
