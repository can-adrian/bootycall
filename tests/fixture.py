"""Builds the sample studio the tests run against.

Until this file existed the suites read a ``/tmp/ice`` tree that nothing
created: it had been made by hand once, and every run afterwards depended on it
still being there. It passed on the machine it was built on and nowhere else,
and the day it was deleted six suites failed with an IndexError that said
nothing about the cause.

So the fixture is code now. ``ensure()`` builds the whole tree, is safe to call
repeatedly, and rebuilds from scratch each time so a leftover directory from a
half-finished run cannot change an answer.

The shapes here are load-bearing, not decorative. ``nuke_plugins-4.1.0``
satisfies one variant's request and fails another's on purpose; ``build_tmp``
is a version directory with no definition in it; ``.cache`` is rez's own, and
is there to be skipped. Read the assertion before changing a version number.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path("/tmp/ice")
SHOWS = ROOT / "shows"
LOCAL = ROOT / "rez/packages/local/adrian"
DEV = LOCAL / "dev"
USER_PACKAGES = ROOT / "userpackages"

#: Copied verbatim into batman_returns. Retyping it would change the package
#: counts the smoke test asserts on (29 for houdini, 30 for maya).
SAMPLE_BOOTSTRAP = Path(__file__).resolve().parent / "sample_bootstrap.py"

_PACKAGE = 'name = "%s"\n\nversion = "%s"\n\nrequires = []\n'

_BOOTSTRAP_HEAD = "from ilp_bootstrap import Bootstrap\n\n\nclass ProjectBootstrap(Bootstrap):\n\n"

#: Two shows with the same Maya pair. Neither may define a nuke key: the
#: window remembers the chosen nuke variant across shows, and a show offering
#: `nuke` would reset a test that has just pinned `nuke16`.
_MAYA_ONLY = _BOOTSTRAP_HEAD + (
    '    base_package = "base-6"\n'
    '    maya_package = ("maya-2026.3", base_package, "maya_base-7")\n\n'
    "    packages = dict(\n"
    "        maya=maya_package,\n"
    '        maya_ziva=("maya-2023", base_package, "maya_base-6", "ziva_vfx-2"),\n'
    "    )\n"
)

_SHOWS: dict[str, str] = {
    # Nuke 16 only, no show package: the "one variant, nothing else" show.
    "finishing_only": _BOOTSTRAP_HEAD
    + (
        '    base_package = "base-6"\n\n'
        "    packages = dict(\n"
        '        nuke16=("nuke-16.0", base_package, "nuke_base-6"),\n'
        "    )\n"
    ),
    "combat_2": _MAYA_ONLY,
    "ORCA_ep01": _MAYA_ONLY,
    "ATLAS_2": _MAYA_ONLY,
    "dune_pt3": _BOOTSTRAP_HEAD
    + (
        '    base_package = "base-6"\n'
        '    houdini_package = ("houdini-21.0", base_package, "houdini_base-7")\n'
        '    maya_package = ("maya-2026.3", base_package, "maya_base-7")\n\n'
        "    packages = dict(\n"
        '        houdinifx=houdini_package + ("hou_fx_utils-1",),\n'
        "        maya=maya_package,\n"
        "    )\n"
    ),
    # Parses cleanly, defines nothing the DCC registry knows: the show that
    # has to explain itself rather than show an empty row.
    "ingest_farm": _BOOTSTRAP_HEAD
    + (
        '    base_package = "base-6"\n\n'
        "    packages = dict(\n"
        '        ingest=("ingest_apps_ingest-1", "ingest_utils-2"),\n'
        '        ingest_prep=(base_package, "prep_utils-1"),\n'
        '        transcode=("ffmpeg-6", base_package),\n'
        "    )\n"
    ),
    # An unclosed paren: named config.py and mentioning Bootstrap and packages
    # so the finder picks it, and unparseable so the reader has to say so.
    "broken_show": _BOOTSTRAP_HEAD
    + ("    packages = dict(\n" '        maya=("maya-2026.3",\n' "    )\n"),
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _package(root: Path, name: str, version: str = "") -> None:
    """A minimal rez package whose definition agrees with its directories.

    Agreeing matters: BootyCall lists by directory and rez resolves by what the
    definition declares, and a package where they differ is shown with a
    warning rather than plainly. Every package here is meant to be the boring
    kind.
    """
    where = root / name / version if version else root / name
    _write(where / "package.py", _PACKAGE % (name, version or "0.1.0"))


def ensure() -> Path:
    """Build the whole tree from scratch and return its root."""
    shutil.rmtree(ROOT, ignore_errors=True)

    for name, version in (
        ("houdini_utils", "6.0.5"),
        ("maya_utils", "3.2.0"),
        ("my_local_tool", "1.0.0"),
        # Satisfies nuke16's nuke_plugins-4 and fails nuke's nuke_plugins-3.
        # Both halves are asserted; do not renumber it.
        ("nuke_plugins", "4.1.0"),
    ):
        _package(LOCAL, name, version)

    for name, version in (
        ("axiom", "3.1.0"),
        # Higher than the local 6.0.5, so the two roots disagree on purpose.
        ("houdini_utils", "6.1.0"),
        ("my_experiment", "0.1.0"),
        ("nuke_utils", "4.10.0"),
        ("nuke_utils", "4.9.0"),
        ("nuke_utils", "4.2.1"),
    ):
        _package(DEV, name, version)

    # Unversioned, sitting directly in the name directory. This is also what
    # makes the local root read `dev` as a package when the blacklist is
    # switched off, which is the thing the blacklist exists to prevent.
    _package(DEV, "scratch_tool")
    _write(DEV / "yaml_pkg/1.0.0/package.yaml", "name: yaml_pkg\nversion: 1.0.0\n")
    # A version directory with no definition in it, and rez's own cache.
    (DEV / "nuke_utils/build_tmp").mkdir(parents=True, exist_ok=True)
    (DEV / ".cache/latest").mkdir(parents=True, exist_ok=True)

    # The user's own copy of combat_2's show package, which has to win over
    # the show's. Nothing else belongs here.
    _package(USER_PACKAGES, "show_combat_2", "1.0.0")

    _write(
        SHOWS / "batman_returns/.ilp/pipeline/config.py",
        SAMPLE_BOOTSTRAP.read_text(encoding="utf-8"),
    )
    _package(SHOWS / "batman_returns/.ilp/packages", "show_batman_returns", "1.0.0")

    for name, source in _SHOWS.items():
        _write(SHOWS / name / ".ilp/pipeline/config.py", source)

    _package(SHOWS / "combat_2/.ilp/packages", "show_combat_2", "1.0.0")
    # Empty: a package directory with nothing in it is not a package, and the
    # scan has to say so rather than adding an empty folder to the resolve.
    (SHOWS / "dune_pt3/.ilp/packages/show_dune_pt3").mkdir(parents=True, exist_ok=True)

    # A show folder with a pipeline directory and no .py in it at all.
    (SHOWS / "no_pipeline_show/.ilp/pipeline").mkdir(parents=True, exist_ok=True)

    # Three entries the show scan must skip: a dot directory, a name on the
    # exclude list, and a plain file.
    (SHOWS / ".snapshot").mkdir(parents=True, exist_ok=True)
    (SHOWS / "lost+found").mkdir(parents=True, exist_ok=True)
    _write(SHOWS / "README.txt", "Shows live here.\n")

    return ROOT


if __name__ == "__main__":
    print(ensure())
