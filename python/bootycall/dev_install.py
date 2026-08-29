"""
"Update Dev Installs and Launch".

The behaviour of this step is not specified yet, so this module is the seam it
will drop into rather than a guess at what it does. :data:`IMPLEMENTED` is the
switch the UI reads: while it is False the menu entry explains itself and
**does not launch**, because a plain launch dressed up as an update is worse
than no update at all -- you would believe your dev builds were current when
nothing had touched them.

To wire it up: fill in :func:`update_dev_installs` and flip :data:`IMPLEMENTED`.
Nothing else in the UI needs to change.
"""

from __future__ import annotations

from typing import Sequence

#: Flip to True once :func:`update_dev_installs` actually does something.
IMPLEMENTED = False

#: Shown in the Launch button's context menu.
MENU_LABEL = "Update Dev Installs and Launch"

#: Shown when the entry is chosen while unimplemented.
NOT_IMPLEMENTED_NOTE = (
    "The update step has not been defined yet, so nothing was launched.\n\n"
    "Once you describe what 'update dev installs' should do, it goes in "
    "bootycall/dev_install.py and this entry starts working. Use Launch for a "
    "normal start in the meantime."
)


def update_dev_installs(project, packages: Sequence[str]) -> str:
    """Bring the user's dev installs up to date before a launch.

    Should return "" on success or a message describing what went wrong.
    Raises while unimplemented so a caller that skips the :data:`IMPLEMENTED`
    check fails loudly rather than silently doing nothing.
    """
    raise NotImplementedError(
        "update_dev_installs is not written yet; check IMPLEMENTED first"
    )
