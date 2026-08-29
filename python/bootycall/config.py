"""
BootyCall configuration.

Central place for site paths and the hard-coded DCC registry.
Everything here can be overridden with environment variables so the tool can be
pointed at a test tree without editing code.
"""

from __future__ import annotations

import os
import shutil
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

#: Where you *work* on dev packages, as opposed to where installed ones land.
#: A working copy is a checkout you edit; an installed one is what rez resolves.
#: Keeping them apart is the whole point -- editing a package rez is currently
#: resolving is how you get a half-written build inside a running DCC.
#:
#: ``{user}`` is the username and ``{home}`` the home directory, so the default
#: is simply the user's own ~/dev.
DEV_WORKING_ROOT_TEMPLATE = os.environ.get(
    "BOOTYCALL_DEV_WORKING_ROOT", "{home}/dev"
)

#: Where a user's own packages live. The bootstrap's ``_get_show_packages()``
#: searches this alongside the show's own package directory, and looks here
#: first -- so a user can shadow a show package with their own copy.
USER_PACKAGES_ROOT = os.environ.get("BOOTYCALL_USER_PACKAGES_ROOT", "~/packages")

#: Path inside a show that holds its own packages, relative to the show folder.
SHOW_PACKAGES_SUBPATH = os.environ.get(
    "BOOTYCALL_SHOW_PACKAGES_SUBPATH", ".ilp/packages"
)

#: Directory names that are never a package, whatever root they turn up in.
#: ``dev`` is a package root nested inside the local root; treating it as a
#: reserved name is cheaper and clearer than special-casing the parent scan,
#: and no rez package is ever going to be called "dev".
RESERVED_PACKAGE_NAMES: tuple[str, ...] = ("dev",)

#: Runtime overrides from the Settings dialog. Empty until one is set.
_PATH_OVERRIDES: dict[str, str] = {}

#: The settable paths, in the order the Settings dialog shows them.
PATH_KEYS: tuple[str, ...] = (
    "shows_root",
    "local_root",
    "dev_root",
    "dev_working_root",
)


def path_defaults() -> dict[str, str]:
    """What each path would be with no user setting applied."""
    return {
        "shows_root": SHOWS_ROOT,
        "local_root": LOCAL_ROOT_TEMPLATE,
        "dev_root": DEV_ROOT_TEMPLATE,
        "dev_working_root": DEV_WORKING_ROOT_TEMPLATE,
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


def user_packages_root() -> str:
    return os.path.expanduser(USER_PACKAGES_ROOT)


def local_root_template() -> str:
    return path_setting("local_root")


def dev_root_template() -> str:
    return path_setting("dev_root")


def dev_working_root_template() -> str:
    return path_setting("dev_working_root")


# ---------------------------------------------------------------------------
# Installing dev packages
# ---------------------------------------------------------------------------

#: How a working copy becomes an installed dev package. Run with the working
#: copy as cwd; ``{dest}`` is the installed dev root.
#:
#: ``rez-build`` rather than a copy, because a package that builds is the only
#: kind rez guarantees is complete: build_command, variants and requires are the
#: package's own business, and reimplementing any of it here would be a second,
#: worse rez. Colon-separated in the environment variable.
DEV_INSTALL_COMMAND: Sequence[str] = tuple(
    os.environ["BOOTYCALL_DEV_INSTALL_COMMAND"].split(":")
    if os.environ.get("BOOTYCALL_DEV_INSTALL_COMMAND")
    else ("rez-build", "--clean", "--install", "--prefix", "{dest}")
)

#: How long an install is given before it is called a failure. Builds compile
#: things; this is generous on purpose.
DEV_INSTALL_TIMEOUT = float(os.environ.get("BOOTYCALL_DEV_INSTALL_TIMEOUT", "600"))

#: Files whose modification times say nothing about the package's source, and
#: which would otherwise make everything look permanently out of date.
DEV_MTIME_IGNORE: tuple[str, ...] = (
    ".git",
    ".svn",
    "__pycache__",
    "build",
    ".rez",
    ".DS_Store",
)


def dev_install_command() -> tuple[str, ...]:
    return tuple(DEV_INSTALL_COMMAND)


def dev_install_timeout() -> float:
    return DEV_INSTALL_TIMEOUT

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
# Bootstrap probe
# ---------------------------------------------------------------------------
#
# The static reader is always used: it is instant, needs nothing installed, and
# is what the UI draws from the moment a show is picked. The probe is the
# second opinion -- it imports the real bootstrap in a throwaway interpreter and
# reports what that module actually says, which catches anything computed at
# import time and anything a change to ilp_bootstrap alters underneath us.
#
# It is a second opinion rather than the only one because it needs an
# interpreter that can import rez and ilp_bootstrap, and BootyCall's own cannot
# be assumed to be one.

#: ``auto`` runs the probe in the background and prefers its answer when it
#: arrives; ``off`` never runs it and leaves BootyCall entirely static.
PROBE_MODE = os.environ.get("BOOTYCALL_PROBE_MODE", "auto").strip().lower()

#: Argv template for the probe, colon-separated in the environment variable.
#: ``{script}`` is bootycall's probe_main.py, ``{bootstrap}`` the module to read.
#:
#: The default assumes ``python`` on PATH can import rez -- true inside a rez
#: session, not necessarily true elsewhere. Sites where it is not should point
#: this at one that can, e.g.
#: BOOTYCALL_PROBE_COMMAND="rez-env:ilp_bootstrap:--:python:{script}:{bootstrap}"
PROBE_COMMAND: Sequence[str] = tuple(
    os.environ["BOOTYCALL_PROBE_COMMAND"].split(":")
    if os.environ.get("BOOTYCALL_PROBE_COMMAND")
    else ("python", "{script}", "{bootstrap}")
)

#: Seconds before the probe is given up on. Importing rez is not fast, but a
#: bootstrap that takes longer than this has something wrong with it and the
#: static answer is the better one to keep.
PROBE_TIMEOUT = float(os.environ.get("BOOTYCALL_PROBE_TIMEOUT", "20"))


def probe_enabled() -> bool:
    return PROBE_MODE not in ("off", "0", "no", "false")


def probe_command() -> tuple[str, ...]:
    return tuple(PROBE_COMMAND)


def probe_timeout() -> float:
    return PROBE_TIMEOUT


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------

#: Terminal emulators to look for, best-first, with the flag each one uses to
#: mean "run this command". There is no portable name for a terminal:
#: ``x-terminal-emulator`` is a Debian alternatives link and does not exist on
#: RHEL or Rocky, so hardcoding any single one of these is wrong somewhere.
TERMINAL_EMULATORS: Sequence[tuple[str, tuple[str, ...]]] = (
    ("gnome-terminal", ("--",)),
    ("konsole", ("-e",)),
    ("xfce4-terminal", ("-x",)),
    ("alacritty", ("-e",)),
    ("kitty", ()),
    ("xterm", ("-e",)),
    ("x-terminal-emulator", ("-e",)),
)


def detect_terminal() -> tuple[str, ...]:
    """The first terminal emulator on PATH, as argv up to the command.

    Falls back to ``xterm`` when nothing is found, so the failure names a
    program that is missing rather than dying somewhere less obvious. Override
    the choice with BOOTYCALL_TERMINAL_EMULATOR (colon-separated), or replace
    the whole argv with BOOTYCALL_LAUNCH_COMMAND.
    """
    override = os.environ.get("BOOTYCALL_TERMINAL_EMULATOR")
    if override:
        return tuple(p for p in override.split(":") if p)
    for name, args in TERMINAL_EMULATORS:
        if shutil.which(name):
            return (name,) + args
    return ("xterm", "-e")


#: When to keep the terminal open after the command finishes:
#: ``error`` (default), ``always``, or ``never``. A terminal that closes on
#: failure takes the error message with it, which is the single most annoying
#: way for a launcher to break.
HOLD_TERMINAL = os.environ.get("BOOTYCALL_HOLD_TERMINAL", "error").strip().lower()


#: Argv template for launching a DCC: resolve the context, open a terminal, run
#: the application in it.
#:
#: ``{script}`` expands to a shell one-liner that echoes the command, runs it,
#: and holds the window open per :data:`HOLD_TERMINAL`. ``{packages}`` and
#: ``{command}`` are still available for sites that want the bare argv instead:
#: ``{packages}`` becomes one argument per request, ``{command}`` the
#: executable.
#:
#: Both templates go straight to rez rather than through the show's bootstrap.
#: BootyCall already knows the exact request list, so routing it back through a
#: wrapper would only add a layer that can disagree with what the UI is showing.
#:
#: Override with BOOTYCALL_LAUNCH_COMMAND (colon-separated argv).
LAUNCH_COMMAND: Sequence[str] = tuple(
    os.environ["BOOTYCALL_LAUNCH_COMMAND"].split(":")
    if os.environ.get("BOOTYCALL_LAUNCH_COMMAND")
    else detect_terminal() + ("bash", "-c", "{script}")
)

#: The same, without an application: an interactive shell in the resolve.
#:
#: Override with BOOTYCALL_TERMINAL_COMMAND (colon-separated argv).
TERMINAL_COMMAND: Sequence[str] = tuple(
    os.environ["BOOTYCALL_TERMINAL_COMMAND"].split(":")
    if os.environ.get("BOOTYCALL_TERMINAL_COMMAND")
    else detect_terminal() + ("bash", "-c", "{script}")
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
    #: Whether this tile is in the row before anyone changes it. The default
    #: row is Houdini, Maya and Terminal -- the three that cover most of a day.
    #: Everything else is one click away in the Softwares menu.
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
        label="Houdini",
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
        label="HouFX",
        package_group="hou_fx_plugins",
        icon_text="FX",
        accent="#ffa04d",
        keys=("houdinifx", "prmanfx"),
        variant_labels={
            "houdinifx": "Houdini FX",
            "prmanfx": "Houdini FX + RenderMan",
        },
        default_visible=False,
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
        default_visible=False,
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
