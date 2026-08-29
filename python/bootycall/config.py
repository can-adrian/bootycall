"""
BootyCall configuration.

Central place for site paths and the hard-coded DCC registry.
Everything here can be overridden with environment variables so the tool can be
pointed at a test tree without editing code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
#
# Three roots, each overridable in three layers, most specific last:
#   1. the constant below
#   2. an environment variable (for pointing a session at a test tree)
#   3. a per-user setting saved from the Settings dialog
#
# Read them through the accessor functions, never the constants, or a setting
# the user changed at runtime will be ignored.

#: Root folder that contains one directory per show/project.
SHOWS_ROOT = os.environ.get("BOOTYCALL_SHOWS_ROOT", "/ice/shows")

#: Template for the per-user local package root. ``{user}`` is substituted.
LOCAL_ROOT_TEMPLATE = os.environ.get(
    "BOOTYCALL_LOCAL_PACKAGES_ROOT", "/ice/rez/packages/local/{user}"
)

#: Template for the per-user dev package root. ``{local}`` is the resolved
#: local root, so moving the local root moves this with it by default.
DEV_ROOT_TEMPLATE = os.environ.get("BOOTYCALL_DEV_PACKAGES_ROOT", "{local}/dev")

#: Directory names that are never a package, whatever root they turn up in.
#: ``dev`` is a package root nested inside the local root; treating it as a
#: reserved name is cheaper and clearer than special-casing the parent scan,
#: and no rez package is ever going to be called "dev".
RESERVED_PACKAGE_NAMES: tuple[str, ...] = ("dev",)

#: Runtime overrides from the Settings dialog. Empty until one is set.
_PATH_OVERRIDES: dict[str, str] = {}

#: The three settable paths, in the order the Settings dialog shows them.
PATH_KEYS: tuple[str, ...] = ("shows_root", "local_root", "dev_root")


def path_defaults() -> dict[str, str]:
    """What each path would be with no user setting applied."""
    return {
        "shows_root": SHOWS_ROOT,
        "local_root": LOCAL_ROOT_TEMPLATE,
        "dev_root": DEV_ROOT_TEMPLATE,
    }


def path_overrides() -> dict[str, str]:
    """The user's settings, if any. Keys absent means "use the default"."""
    return dict(_PATH_OVERRIDES)


def set_path_overrides(overrides: dict[str, str] | None) -> None:
    """Replace the runtime overrides. Blank values fall back to the default."""
    _PATH_OVERRIDES.clear()
    for key, value in (overrides or {}).items():
        if key in PATH_KEYS and str(value).strip():
            _PATH_OVERRIDES[key] = str(value).strip()


def path_setting(key: str) -> str:
    """The effective value for one path key."""
    return _PATH_OVERRIDES.get(key) or path_defaults()[key]


def shows_root() -> str:
    return path_setting("shows_root")


def local_root_template() -> str:
    return path_setting("local_root")


def dev_root_template() -> str:
    return path_setting("dev_root")

#: Folder names under SHOWS_ROOT that are never real shows.
SHOW_EXCLUDES = ("lost+found", "_template", "_archive", "tmp")

#: Relative glob patterns, searched in order, used to locate a show's
#: bootstrap module. The first pattern that yields a file defining a
#: ``Bootstrap`` subclass wins.
BOOTSTRAP_GLOBS: Sequence[str] = tuple(
    p
    for p in os.environ.get(
        "BOOTYCALL_BOOTSTRAP_GLOBS",
        ".ilp/pipeline/*.py:.ilp/bootstrap/*.py:.ilp/*/*.py:.ilp/*.py",
    ).split(":")
    if p
)

#: Text that must appear in a candidate file for it to be treated as a
#: bootstrap module. Cheap pre-filter before we pay for an AST parse.
BOOTSTRAP_MARKER = "Bootstrap"


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------

#: Argv template for launching a DCC: resolve the context, open a terminal, run
#: the application in it. ``{packages}`` expands to the resolved requests as
#: separate arguments and ``{command}`` to the DCC's executable.
#:
#: Both templates go straight to rez rather than through the show's bootstrap.
#: BootyCall already knows the exact request list, so routing it back through a
#: wrapper would only add a layer that can disagree with what the UI is showing.
#:
#: Override with BOOTYCALL_LAUNCH_COMMAND (colon-separated argv).
LAUNCH_COMMAND: Sequence[str] = tuple(
    os.environ.get(
        "BOOTYCALL_LAUNCH_COMMAND",
        "x-terminal-emulator:-e:rez-env:{packages}:--:{command}",
    ).split(":")
)

#: The same, without an application: an interactive shell in the resolve.
#:
#: Override with BOOTYCALL_TERMINAL_COMMAND (colon-separated argv).
TERMINAL_COMMAND: Sequence[str] = tuple(
    os.environ.get(
        "BOOTYCALL_TERMINAL_COMMAND", "x-terminal-emulator:-e:rez-env:{packages}"
    ).split(":")
)


# ---------------------------------------------------------------------------
# DCC registry (hard-coded, filtered by what a show actually defines)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Dcc:
    """A DCC we know how to launch.

    ``keys`` are candidate entries in a bootstrap's ``packages`` dict, listed
    best-first. Only the keys a given show actually defines are offered.
    """

    name: str
    label: str
    keys: tuple[str, ...]
    package_group: str = ""
    icon_text: str = ""
    accent: str = "#6c7a89"
    variant_labels: dict[str, str] = field(default_factory=dict)
    #: The rez package that carries this DCC's version, used to pick the newest
    #: variant and to label the tile. Hiero ships inside Nuke, so it names
    #: ``nuke`` rather than itself.
    version_package: str = ""
    #: Short qualifiers, used only where two variants share a version and the
    #: number alone would not say which is which.
    variant_tags: dict[str, str] = field(default_factory=dict)
    #: The executable to run inside the resolved context. Defaults to the DCC's
    #: own name in lowercase; set it only where the binary is named differently
    #: from the thing people call it.
    command: str = ""
    #: Shown without the user turning it on. The long tail (Nuke Studio, Hiero,
    #: Blender) is real but rarely wanted, and a row of nine tiles buries the
    #: four people actually reach for.
    default_visible: bool = True

    def available_keys(self, packages: dict) -> tuple[str, ...]:
        """Return this DCC's keys that exist in ``packages``, order preserved."""
        return tuple(k for k in self.keys if k in packages)

    def label_for(self, key: str) -> str:
        return self.variant_labels.get(key, key)

    @property
    def run_command(self) -> str:
        """The executable this DCC launches."""
        return self.command or self.name.lower()


#: The DCCs BootyCall exposes. Deliberately hard-coded: the shows' bootstrap
#: files carry dozens of one-off entries, and we only ever want to surface
#: these, filtered down to whatever the selected show defines.
DCCS: tuple[Dcc, ...] = (
    Dcc(
        name="houdinicore",
        version_package="houdini",
        variant_tags={"prman": "RenderMan", "dev_houdini": "dev"},
        label="Houdini Core",
        package_group="houdini_package",
        icon_text="HC",
        accent="#ff7a18",
        keys=("houdinicore", "houdini", "prman", "dev_houdini"),
        variant_labels={
            "houdinicore": "Houdini Core",
            "houdini": "Houdini",
            "prman": "Houdini + RenderMan",
            "dev_houdini": "Houdini (dev)",
        },
    ),
    Dcc(
        name="houdinifx",
        # SideFX names it the other way round from how people say it: the FX
        # binary is `houdini`, and `houdinicore` is Core.
        command="houdini",
        version_package="houdini",
        variant_tags={"prmanfx": "RenderMan"},
        label="Houdini FX",
        package_group="hou_fx_plugins",
        icon_text="FX",
        accent="#ffa04d",
        keys=("houdinifx", "prmanfx"),
        variant_labels={
            "houdinifx": "Houdini FX",
            "prmanfx": "Houdini FX + RenderMan",
        },
    ),
    Dcc(
        name="maya",
        version_package="maya",
        variant_tags={
            "maya_ziva": "Ziva",
            "maya_reference_remap": "remap",
            "maya_reference_remapper": "remapper",
            "obj2abc": "obj2abc",
        },
        label="Maya",
        package_group="maya_package",
        icon_text="M",
        accent="#3fa9f5",
        keys=(
            "maya",
            "maya_ziva",
            "maya_reference_remap",
            "maya_reference_remapper",
            "obj2abc",
        ),
        variant_labels={
            "maya": "Maya",
            "maya_ziva": "Maya (Ziva)",
            "maya_reference_remap": "Maya Reference Remap",
            "maya_reference_remapper": "Maya Reference Remapper",
            "obj2abc": "Maya (obj2abc)",
        },
    ),
    Dcc(
        name="nuke",
        version_package="nuke",
        label="Nuke",
        package_group="nuke",
        icon_text="N",
        accent="#f2c94c",
        keys=("nuke", "nuke16"),
        variant_labels={
            "nuke": "Nuke 13.2",
            "nuke16": "Nuke 16.0",
        },
    ),
    Dcc(
        name="nukestudio",
        version_package="nuke",
        variant_tags={"nukex": "NukeX"},
        default_visible=False,
        label="Nuke Studio",
        package_group="nuke",
        icon_text="NS",
        accent="#d4a72c",
        keys=("nukestudio", "nuke_studio", "nuke_studio16", "nukex"),
        variant_labels={
            "nukestudio": "Nuke Studio",
            "nuke_studio": "Nuke Studio",
            "nuke_studio16": "Nuke Studio 16.0",
            "nukex": "NukeX",
        },
    ),
    Dcc(
        name="hiero",
        version_package="nuke",
        default_visible=False,
        label="Hiero",
        package_group="hiero_base",
        icon_text="Hi",
        accent="#8fb339",
        keys=("hiero",),
        variant_labels={"hiero": "Hiero"},
    ),
    Dcc(
        name="blender",
        version_package="blender",
        default_visible=False,
        label="Blender",
        package_group="blender_base",
        icon_text="B",
        accent="#e87d0d",
        keys=("blender",),
        variant_labels={"blender": "Blender"},
    ),
)


#: Names shown when the user has expressed no preference.
DEFAULT_VISIBLE_SOFTWARE: tuple[str, ...] = tuple(
    d.name for d in DCCS if d.default_visible
)


def dcc_by_name(name: str) -> Dcc | None:
    for dcc in DCCS:
        if dcc.name == name:
            return dcc
    return None
