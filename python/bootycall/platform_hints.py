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

    for command in _sticky_commands(win_id, enabled):
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(  # noqa: S603
                command,
                timeout=_TIMEOUT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return ""

    return "install wmctrl or xdotool to pin the compact window to all workspaces"


def _sticky_commands(win_id: int, enabled: bool) -> list[list[str]]:
    """Helpers to try, in order of how well they do this job."""
    action = "add" if enabled else "remove"
    # 0xFFFFFFFF is "all desktops" in the EWMH spec; -1 is xdotool's spelling.
    desktop = "-1" if enabled else "0"
    return [
        ["wmctrl", "-i", "-r", str(win_id), "-b", "%s,sticky" % action],
        ["xdotool", "set_desktop_for_window", str(win_id), desktop],
    ]
