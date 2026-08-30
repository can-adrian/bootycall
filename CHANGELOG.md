# Changelog

The version in `package.py`, `pyproject.toml` and `bootycall/__init__.py` is
bumped **in the same commit as the change it describes**, and every bump gets an
entry here. `tests/test_packaging.py` fails if the three versions disagree or if
the newest entry below is not the current version — that is what stops a build
going out indistinguishable from the one before it.

Breaking changes to how a launch is assembled bump the minor; everything else
bumps the patch. The window title carries the version, so an artist reporting a
problem is reporting it against something specific.

## 0.5.0

Two bugs with the same symptom: a local or dev package shown as overriding the
resolve that neither Launch nor Terminal actually picked up.

- **The per-user roots are now put on `REZ_PACKAGES_PATH`.** BootyCall showed
  your local and dev packages, told you which ones override, and then left
  getting those roots onto the path to the site's rez config -- assuming the two
  agreed. Where they did not, the package sat in the list marked as overriding
  and never reached a single launch. Roots the site already lists are left
  exactly where they are, so this changes nothing at a site that was already
  configured for it. Dev goes ahead of local.
- **Each section says when rez does not know its root**, under the path, so the
  case above is visible rather than inferred -- and it warns you that anything
  launched outside BootyCall will not see those packages.
- **Overrides are checked against the version, not just the name.** A dev
  `nuke_utils-4.9.0` against a request for `nuke_utils-4.10` was reported as an
  override; rez will not look at it twice. Those rows now read *does not satisfy
  <request>* in red and are not counted as in use. The prefix and `X+` request
  forms are decided; anything more complex makes no claim rather than a wrong
  one.
- The override tooltip now says the thing that was missing: rez picks the
  highest version satisfying the request across every package path, so a newer
  studio build of the same name still wins. Path order only settles ties between
  equal versions -- being earlier on the path does not beat a higher version.

## 0.4.0

Minor rather than patch because the launch argv changed: a DCC now starts behind
`rez-context` rather than directly.

- **Launch prints the resolve, the way Terminal always has.** `rez-env pkgs` with
  no command leaves you in an interactive rez shell and rez prints its requested/
  resolved table on the way in; `rez-env pkgs -- app` has a command to run, so no
  shell announces anything. The app now runs behind `rez-context`, which prints
  the same table, in colour, and then `exec`s the application so nothing extra is
  left in the process tree. `BOOTYCALL_SHOW_RESOLVE_INFO=0` turns it off.
- **Overriding packages sort to the top** of the local and dev lists. They are
  the rows that change what you are about to launch; a root with thirty builds
  buries the two that matter.
- **Copy command moved to a new Edit menu** (Ctrl+C) and is gone from the footer.
- **Minimum width is 428px**, a quarter narrower. Two things had to be fixed to
  make that width honest: the tile row was laid out across two lines but only
  given one line's height, so the second row of tiles was drawn outside the
  container; and section headers cut the *title* off mid-word rather than the
  count beside it. The count now elides, with the full text on hover.
- **The "Add a show..." prompt is gone once a show is pinned.** The chips say
  what the field is for.
- **Nuke Studio removed** from the registry entirely.

## 0.3.0

Dev packages get a working location, and BootyCall stops assuming what is
installed is what you have been writing. Minor rather than patch: the packages
path a launch is built from can now differ from the dev root on disk.

- **New path setting: Dev working location**, defaulting to `~/dev`. Where you
  edit, as against Dev packages -- renamed **Installed Dev Packages** -- which is
  what rez resolves.
- **Install Package** on the Installed Dev Packages right-click menu, including
  on empty space where someone with nothing installed will click. It lists the
  working location, marks which folders are packages and why the others are not,
  and either builds one in (`rez-build`) or symlinks it for live editing.
- **Launch checks for stale installs.** If an installed dev package is older than
  its working copy you get Update and Launch, Launch Anyway, or Cancel. Build
  products, `__pycache__` and version-control directories do not count as edits;
  symlinked installs can never be stale. This is what **Update Dev Installs and
  Launch** has been a placeholder for since 0.1.0.
- **A tick per installed dev package.** Untick one and the studio version is used
  instead -- done by putting a filtered view of the dev root on the packages
  path, because a rez package filter excludes a name and would take the studio
  copy with it. Only the off ones are saved.
- An unticked dev package no longer claims to override anything in the resolve
  list. It is not on the path, so it does not.

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
