"""
Window-manager hints that Qt has no portable API for.

"Always on top" is a Qt flag and works everywhere. "Show on every workspace" is
not: it is the X11 ``_NET_WM_STATE_STICKY`` property, and there is no Qt call
for it. So it is done through whichever helper the host happens to have, and it
is treated as a nicety -- a session that cannot set it still gets a working
compact window, with a note saying what was skipped.

Every function here is best-effort and returns a message rather than raising.
Failing to pin a launcher to all desktops is not worth an exception.
"""

from __future__ import annotations

import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

#: Seconds to wait on a helper. These are local X11 calls; if one blocks for
#: longer than this, something is wrong and waiting will not fix it.
_TIMEOUT = 2.0


def set_always_on_top(window, enabled: bool) -> None:
    """Keep ``window`` above others. Portable, and cheap.

    Changing window flags makes Qt drop and recreate the native window, which
    hides it, so the geometry is put back afterwards.
    """
    if bool(window.windowFlags() & Qt.WindowStaysOnTopHint) == bool(enabled):
        return
    geometry = window.geometry()
    visible = window.isVisible()
    window.setWindowFlag(Qt.WindowStaysOnTopHint, bool(enabled))
    if visible:
        window.show()
        window.setGeometry(geometry)


def is_x11() -> bool:
    return QGuiApplication.platformName() == "xcb"


def set_visible_on_all_workspaces(window, enabled: bool) -> str:
    """Pin ``window`` to every workspace. Returns "" or why it did not happen.

    X11 only. Wayland deliberately has no equivalent, and macOS and Windows
    manage this themselves, so on those the answer is a note rather than a
    failure.
    """
    if not is_x11():
        return "sticky windows need X11 (this session is '%s')" % (
            QGuiApplication.platformName() or "unknown"
        )

    try:
        win_id = int(window.winId())
    except (TypeError, ValueError):
        return "no native window id yet"

    tried = []
    for command in _sticky_commands(win_id, enabled):
        if shutil.which(command[0]) is None:
            continue
        tried.append(command[0])
        if not _run(command):
            continue
        # Exit zero is the helper's opinion. wmctrl sends a ClientMessage to
        # whatever window id it was given and reports success without checking
        # that the id exists, let alone that the window manager acted on it --
        # so the one run that mattered was the one nobody verified. Ask X.
        state = sticky_state(win_id)
        if state is None or state is enabled:
            return ""

    if not tried:
        return "install wmctrl or xdotool to pin the compact window to all workspaces"
    return (
        "%s ran but the window manager did not make the window sticky"
        % " and ".join(tried)
    )


def _run(command: list[str]) -> bool:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            timeout=_TIMEOUT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def sticky_state(win_id: int) -> bool | None:
    """Is the window sticky according to X? ``None`` when it cannot be asked.

    ``None`` is not "no": without ``xprop`` there is no way to check, and
    treating that as failure would report a working setup as broken.
    """
    if shutil.which("xprop") is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603
            ["xprop", "-id", window_arg(win_id), "_NET_WM_STATE"],
            timeout=_TIMEOUT,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return "_NET_WM_STATE_STICKY" in result.stdout


def window_arg(win_id: int) -> str:
    """A window id these helpers will read as the number we meant.

    Hex, with the ``0x``. ``wmctrl -i`` parses its argument as base 16, so a
    decimal id was silently read as a different, usually nonexistent window --
    and because wmctrl does not check that the window exists, it then exited
    zero. Installed, ran, reported success, did nothing.

    ``0x``-prefixed is unambiguous to every one of these: wmctrl, xdotool and
    xprop all take it.
    """
    return "0x%08x" % win_id


def _sticky_commands(win_id: int, enabled: bool) -> list[list[str]]:
    """Helpers to try, in order of how well they do this job."""
    action = "add" if enabled else "remove"
    # 0xFFFFFFFF is "all desktops" in the EWMH spec; -1 is xdotool's spelling.
    desktop = "-1" if enabled else "0"
    return [
        ["wmctrl", "-i", "-r", window_arg(win_id), "-b", "%s,sticky" % action],
        ["xdotool", "set_desktop_for_window", window_arg(win_id), desktop],
    ]
