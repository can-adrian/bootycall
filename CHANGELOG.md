# Changelog

The version in `package.py`, `pyproject.toml` and `bootycall/__init__.py` is
bumped **in the same commit as the change it describes**, and every bump gets an
entry here. `tests/test_packaging.py` fails if the three versions disagree or if
the newest entry below is not the current version — that is what stops a build
going out indistinguishable from the one before it.

Breaking changes to how a launch is assembled bump the minor; everything else
bumps the patch. The window title carries the version, so an artist reporting a
problem is reporting it against something specific.

## 0.2.1

- **Houdini Core is now just Houdini, and Houdini FX is HouFX.** The row is read
  at a glance, and the long names were the reason it could not be.
- **Every tile is the same size**, measured from the widest label in the row
  rather than hardcoded, so a rename cannot leave it stale. Terminal is measured
  with the rest, since it sits in the same row and looked wrong at any other
  width.
- **The default row is Houdini, Maya and Terminal.** The others are one click
  away in the Softwares menu, and whatever you turn on is remembered.
- **The Resolved packages checkbox is gone.** It could never be unticked, so it
  was a greyed-out control that only invited the question.

## 0.2.0

Everything between the first working build and here. Released as one version
because it was developed as one — the individual steps went out as patches
against an unchanged `0.1.0`, which is exactly the mistake this file exists to
prevent from recurring.

- **Launch actually launches.** It resolves the context with rez, opens a
  terminal, and runs the DCC's own executable — `houdinicore` for Houdini Core,
  `houdini` for Houdini FX, the lowercased name otherwise.
- **The terminal is detected, not assumed.** `x-terminal-emulator` is Debian-only
  and does not exist on Rocky; the emulator is now found on PATH from a
  best-first list.
- **The error survives.** The launch shell echoes what it is about to run and
  holds the window open on a non-zero exit instead of closing with the message
  still in it.
- **The bootstrap is asked, not only read.** After the static read draws the
  window, a throwaway interpreter imports the real bootstrap and reports what it
  actually resolves, including anything computed at import time. Every way that
  can fail leaves the static answer standing.
- **Show packages follow the bootstrap's own rules** — `~/packages` before the
  show's `.ilp/packages`, validated rather than assumed, and the root prepended
  to `REZ_PACKAGES_PATH` so rez can find it.
- **Package sections can be switched off.** Unchecking local or dev rewrites the
  packages path handed to the launch, so it excludes them in fact and not just
  on screen. Resolved is locked on.
- Pill-shaped chips, click-to-pin from the autocomplete list, no popup at
  startup, the version in the window title, and compact mode made read-only.
- Shipped as a rez package requiring only `python` and `PySide6`.

## 0.1.0

First working build: show field with chips, the DCC row with variants on
right-click, the three package sections, favourites, saved setups, compact mode,
and single-instance handling.
