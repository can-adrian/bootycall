"""
One report answering "why is my package not in the environment?".

Every part of that question has a different answer and they are not visible
from the same place: rez's own configuration, the path BootyCall hands the
launch, what is on disk, what the definitions declare, and what the show
actually asked for. Chasing them one at a time is how a ten-minute problem
becomes an afternoon.

So this collects all of it into text you can read, paste into a ticket, or send
to whoever maintains the site's rez config. It is deliberately plain -- no
colour, no widgets -- so it survives being pasted anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from . import __version__, config, launcher
from .local_packages import (
    LocalPackage,
    current_user,
    definition_fields,
    definition_mismatch,
    request_name,
    satisfies,
)


def _heading(text: str) -> str:
    return "\n%s\n%s" % (text, "-" * len(text))


def _yes_no(value: bool) -> str:
    return "yes" if value else "NO"


def package_report(
    packages: Sequence[LocalPackage],
    requests: Sequence[str],
    root: Path | str,
    on_path: bool,
) -> list[str]:
    """One root's worth of findings, in the order they stop a package working."""
    lines = ["  root: %s" % root]
    lines.append("  exists on disk: %s" % _yes_no(Path(root).is_dir()))
    lines.append("  on the path the launch will use: %s" % _yes_no(on_path))

    if not packages:
        lines.append("  no packages found here")
        return lines

    by_name = {request_name(r): r for r in requests}
    for package in packages:
        lines.append("")
        lines.append("  %s" % package.request)
        lines.append("    path: %s" % package.path)

        fields = definition_fields(package.path)
        lines.append(
            "    definition declares: name=%s version=%s"
            % (fields.get("name", "<none>"), fields.get("version", "<none>"))
        )
        problem = definition_mismatch(package)
        if problem:
            lines.append("    *** rez will skip this: %s" % problem)

        request = by_name.get(package.name)
        if request is None:
            lines.append("    not named by this resolve, so it changes nothing here")
            continue

        lines.append("    the show asks for: %s" % request)
        verdict = satisfies(package.version, request)
        if verdict is False:
            lines.append(
                "    *** this version cannot satisfy that request - rez will "
                "use the studio build"
            )
        elif verdict is None:
            lines.append(
                "    that request form is not one BootyCall decides; no claim made"
            )
        else:
            lines.append(
                "    version satisfies it, so this is a candidate - rez still "
                "picks the highest version satisfying it across every root"
            )
    return lines


def report(window) -> str:
    """The whole picture, for the window's current selection."""
    project = window.current_project()
    tool = window._current_tool()
    dcc = window._active_dcc

    lines = ["BootyCall %s diagnostics" % __version__, "user: %s" % current_user()]
    lines.append(
        "show: %s" % (project.name if project is not None else "<none selected>")
    )
    lines.append("tool: %s" % (tool or "<none selected>"))

    lines.append(_heading("what rez itself is configured to read"))
    from_env = os.environ.get("REZ_PACKAGES_PATH", "")
    lines.append(
        "REZ_PACKAGES_PATH in this environment: %s" % (from_env or "<not set>")
    )
    known = launcher.packages_path()
    if known:
        for entry in known:
            lines.append("  %s" % entry)
    else:
        lines.append(
            "  <could not read it - REZ_PACKAGES_PATH is unset and rez-config "
            "could not be run. BootyCall cannot filter or verify roots without "
            "this.>"
        )

    lines.append(_heading("the path this launch will actually use"))
    paths, note = launcher.filtered_packages_path(
        window.excluded_roots(), window.included_roots()
    )
    if paths:
        for entry in paths:
            lines.append("  %s" % entry)
    else:
        lines.append("  <unchanged - the launch inherits the environment above>")
    if note:
        lines.append("  note: %s" % note)

    missing = window.missing_from_rez_path()
    if missing:
        lines.append("")
        lines.append(
            "  These roots are only on the path because BootyCall puts them "
            "there.\n  Anything launched outside BootyCall will not see them:"
        )
        for entry in missing:
            lines.append("    %s" % entry)

    requests = window.resolved_packages()

    lines.append(_heading("installed dev packages"))
    lines.append("  section switched on: %s" % _yes_no(window.dev_frame.is_checked()))
    if window._disabled_dev:
        lines.append("  switched off by name: %s" % ", ".join(sorted(window._disabled_dev)))
    dev_root_path = window.dev_root_path()
    effective = {os.path.normpath(p) for p in (paths or known)}
    view = window._dev_view_root()
    dev_on_path = os.path.normpath(str(dev_root_path)) in effective or (
        view is not None and os.path.normpath(str(view)) in effective
    )
    lines.extend(package_report(window.enabled_dev_packages(), requests, dev_root_path, dev_on_path))
    if view is not None:
        lines.append("")
        lines.append(
            "  Some dev packages are switched off, so the path carries a "
            "filtered view\n  of this root rather than the root itself: %s" % view
        )

    lines.append(_heading("local packages"))
    lines.append("  section switched on: %s" % _yes_no(window.local_frame.is_checked()))
    local_root_path = window.local_root_path()
    lines.extend(
        package_report(
            window._local_packages if window.local_frame.is_checked() else [],
            requests,
            local_root_path,
            os.path.normpath(str(local_root_path))
            in {os.path.normpath(p) for p in paths or known},
        )
    )

    lines.append(_heading("the dev working location"))
    lines.append("  %s" % window.dev_working_root_path())
    lines.append(
        "  (nothing resolves out of here - it is where Install Package reads "
        "from)"
    )

    lines.append(_heading("what will be run"))
    if project is not None and dcc is not None:
        lines.append(
            "  %s" % launcher.command_preview(project, requests, dcc.run_command)
        )
    else:
        lines.append("  <pick a show and a tool>")

    lines.append(_heading("the request list"))
    for request in requests:
        lines.append("  %s" % request)

    lines.append("")
    lines.append(
        "If a package above is in a root marked 'on the path: yes', has no "
        "*** line,\nand the show asks for it, then rez is choosing a higher "
        "version of the same\nname from another root. Compare with: rez-search "
        "<name> --paths <root>"
    )
    return "\n".join(lines)


def site_summary() -> str:
    """The two settings that decide whether any of this can work at all."""
    return "\n".join(
        [
            "shows root:        %s" % config.shows_root(),
            "local root:        %s" % config.local_root_template(),
            "dev root:          %s" % config.dev_root_template(),
            "dev working root:  %s" % config.dev_working_root_template(),
        ]
    )
