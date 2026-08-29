# BootyCall

A PySide6 front end for the pipeline bootstrap files. Pick a show, pick a DCC,
see exactly which rez packages the show would resolve, launch it.

## Build and run

It ships as a rez package:

```
rez-build --install          # or: rez-release
rez-env bootycall -- bootycall
```

From a checkout, without building:

```
PYTHONPATH=python python -m bootycall
```

`package.py` requires only `python` and `PySide6`. **It does not require rez** —
BootyCall reads bootstrap files with `ast` and shells out to `rez-env`, so it
never imports rez, and declaring a dependency would drag it into every resolve
that wants the launcher.

Site defaults (shows root, package roots, launch and terminal commands) are
commented out in `package.py`'s `commands()` — uncommenting one moves the
default for everybody. Per-user Settings still take precedence.

## Tests

```
./run_tests.sh
```

Five suites, no framework: each is a plain script that prints `ok` / `FAIL`
lines and exits non-zero on failure. The UI ones run against Qt's `offscreen`
platform and write screenshots to `shots/`, so they work over SSH and in CI.

The tagline under the logo is drawn at random each launch from
`ui/main_window.py` → `TAGLINES`.

## What it does

1. Lists every show folder under `/ice/shows/` into an autocomplete field.
   Matching is substring and case-insensitive — typing `mba` finds `combat_2`,
   typing `orc` finds `ORCA_ep01`. The popup opens on focus and on Down, so it
   also works as a browser when you can't remember the show code.
2. **Enter pins the show as a chip.** The chips are your shortlist; one is
   selected at a time, and that selection is what the rest of the window
   describes. Finds the selected show's bootstrap and reads its `packages`.
3. Filters a **hard-coded** DCC list down to what the show actually defines.
   The row shows Houdini Core, Houdini FX, Maya, Nuke and Terminal by default;
   it wraps, and ends in a small **⋯** button. Each tile carries its chosen
   variant's version in grey underneath.
4. Shows the resolved package request for the selected variant, your local
   packages and your dev packages, in three collapsible sections (all closed by
   default).
5. Launches it detached, so closing BootyCall doesn't take the DCC with it.

## The show field

A token input, the way a mail client tokenises recipients: the pinned shows are
rounded chips *inside* the field, with the text entry as the last item on the
same wrapping row.

```
┌───────────────────────────────────────────────────────┐
│ (batman_returns ✕) (dune_pt3 ✕) (combat_2 ✕) Add a... │
└───────────────────────────────────────────────────────┘
```

Typing a show and pressing Enter pins it; clicking a chip selects it, clicking
its ✕ unpins it. Exactly one chip is selected, because everything under the
field — DCC, variant, package list, Launch — describes a single show.

The entry takes whatever width the chips leave and drops to a new line when they
fill one, and the field grows to match. The prompt shortens to "Add a show…"
once chips are sharing the space.

Enter on a show that's already pinned selects it instead of adding a second chip
— hitting Enter twice on the same name should be idempotent, not an error. The
field clears itself after each pin so you can type the next one straight away.
**Backspace on an empty entry** removes the last chip, as a token field should.

The border and focus ring belong to the box; the entry inside is chrome-free, so
the validity tint lands on the *text* (green for a match, red for no match)
rather than fighting the box's own border.

Removing the **selected** chip lands on its neighbour rather than dropping to
nothing: unpinning one of three shows should leave you working. Removing the
last one empties the window properly — no tiles, no stale package list.

The chips and which one was selected are saved with your favourites and restored
next launch. Pins pointing at shows that have since been archived are dropped on
startup and the status bar says which — silently forgetting a pin would look
like the app lost it.

Chips are keyboard-reachable: Tab to one, Space/Enter selects, Delete unpins.

The window is sized for a 705px-wide default — narrow enough to park beside a
DCC rather than owning the screen.

## The three package sections

All closed on startup — the resolve alone is 30-odd lines you rarely need — but
each header carries a badge so it still reports what's inside while shut:

```
▸ Resolved packages                      nuke - 30 packages   2 overridden locally
▸ Local packages                              4 packages      1 in use
▸ Dev packages                                8 packages      1 in use
```

Opening a section grows the window if it would otherwise squash the list;
closing never shrinks it, since that would undo a size you chose.

| Section | Root |
|---|---|
| Local packages | `/ice/rez/packages/local/<user>` |
| Dev packages | `/ice/rez/packages/local/<user>/dev` |

Both read the standard rez layout (`<name>/<version>/package.py`, version level
omitted for unversioned packages). `package.yaml` counts too, and a version
folder with no definition file — a stray build dir — is skipped.

**The dev root lives inside the local root**, so `dev` is a *reserved package
name* (`config.RESERVED_PACKAGE_NAMES`) and is skipped in every scan. Without
that, `dev` reads as a package whose "versions" are your dev package names — a
quietly wrong list rather than a visible error, which is why there's a test
asserting the blacklist is load-bearing. Blacklisting the word is safe on the
assumption no rez package will ever be called `dev`.

### Overrides

The sections cross-reference each other, which is the point of showing them
together. Anything in either root sits in front of the studio packages on a
normal `REZ_PACKAGES_PATH`, so a local build of `nuke_utils` silently replaces
the studio one in every resolve. That's the usual answer to "why does it work on
my machine and nowhere else", so BootyCall says it out loud: the overridden
request is flagged amber in the resolve **and names which root** it came from,
and the package that wins is flagged in that root's list.

When a package is in **both** roots, the resolve says `overridden by your local
and dev builds` and the tooltip adds that which one wins depends on your
`REZ_PACKAGES_PATH` order — BootyCall can't see that, so it names both rather
than picking one and being wrong half the time.

Only the **highest** version of a name *within a root* is marked as winning —
rez resolves the highest version satisfying the request, so marking all three of
your `nuke_utils` builds would say the opposite of what happens. The rest are
greyed as `(older build)`. Version comparison is numeric-aware, so 4.10 sorts
above 4.9.

Matching is by package name, not version: a dev `nuke_utils` takes precedence
whatever version the show asked for, so a version match isn't required for the
override to bite.

Both lists refresh on startup, on F5, and every time you open a section — it's
one `scandir`, so they're never stale. A missing root is not an error; most
people have never made a package in one, and the section just says so.

### Deleting a package

Right-click a row in either list for **Browse folder**, **Copy path** and
**Delete from disk**. Browse opens the package directory in the desktop file
manager, stopping at five at once rather than carpeting the desktop.
Multi-select works; right-clicking outside the selection targets the row you
clicked, as lists normally do. Deleting asks first, lists the exact paths, and
defaults to No.

`delete_package()` guards the two ways this could go badly wrong rather than
trusting the caller:

- the target must live **strictly inside** the root it was listed from, so a
  path that escaped by any route is refused;
- a **symlinked** package is refused outright — following it would delete the
  shared location it points at, not your copy.

Deleting the last version of a package takes its now-empty name directory with
it, so removing your final `nuke_utils` build doesn't leave an empty
`nuke_utils/` behind looking like a package.

The confirmation and the failure report both live in the caller, not in
`delete_packages()` — which keeps the delete path callable from a test without a
modal blocking it.

## Variants live on the tile

There is no variant dropdown. **Right-click a tile** for the variants this show
defines, and the version of the one you picked shows in grey under the software
name:

```
   ┌──────────────┐            ✓ Houdini Core          (21.0)
   │      HC      │              Houdini + RenderMan   (21.0 · RenderMan)
   │ Houdini Core │              Houdini (dev)         (21.0 · dev)
   │     21.0     │
   └──────────────┘
```

The choice belongs to the thing it describes, and it's remembered per DCC — set
Maya to the Ziva build, switch to Nuke and back, and Maya is still on Ziva. A
variant this show doesn't define is dropped rather than carried over.

**The default is the newest variant the bootstrap defines**, by version rather
than by registry order: Nuke opens on 16.0, not the 13.2 that happens to be
listed first. Versions compare numerically, so 16.0 beats 13.2 rather than
losing a string comparison. Where a DCC's variants share a version — three
Houdini entries all on 21.0 — the version can't settle it, so registry order
does, and the tile appends a short tag (`21.0 · RenderMan`) so you can still
tell which is selected.

Which package carries the version is per-DCC (`Dcc.version_package`): Hiero
names `nuke`, since that's what it ships inside.

Picking a variant also selects that tile — it's a statement about which tool you
want, not a quiet edit to a tile you aren't looking at.

The active software **sticks across shows**: switch from `batman_returns` to
`dune_pt3` and you stay on Nuke, unless the new show doesn't offer it.

## Terminal

The **Terminal** tile in the software row opens a shell resolved against
whatever package set is currently selected. It is not part of the exclusive DCC
group — it is an action, not one of the show's software choices, so it is drawn
with a dashed border and stays available whatever is selected. Ctrl+T does the
same.

It goes **straight to rez** rather than through the bootstrap:

```
cd <show> && x-terminal-emulator -e rez-env <the resolved request list>
```

BootyCall already knows the exact request list, and there is no documented
bootstrap entry point for an interactive shell, so inventing one would have been
a guess on top of a guess. Override the whole argv with
`BOOTYCALL_TERMINAL_COMMAND`; `{packages}` expands to one argument per request,
not a single space-joined blob.

The show's own `show_<name>` package is appended when
`<show>/.ilp/packages/show_<name>` exists, because `_get_show_packages()` adds it
to every resolve — leaving it out would hand you a shell subtly unlike the one
the DCC gets. BootyCall can't run rez's validator from here, so it checks the
directory exists rather than guessing.

## Favourites

The small **⋯** button at the end of the software row (or Ctrl+B) opens a
separate, non-modal window over the same saved-setup store the File menu uses. The menu is fine for *picking* a
setup but a bad place to *manage* one — menus close on every click, and a menu
row has no room for reorder or rename — so this window carries Add current,
Rename, Move up/down and Remove, with double-click to load.

Both views stay in step: reorder in the window and the File menu shows the new
order; save from the menu and the window refreshes.

## Compact mode

The **chevron button left of Launch** (or Ctrl+M) collapses the window to just
the selected show chip, the selected software tile, and Launch — about the size
of a tile plus padding, small enough to park in a corner between launches. The
chevrons flip to point down, and clicking again restores the full window.

The whole collapsed window is **no wider than one software tile plus its
margins**. Three things had to give for that:

- The buttons left-justify, so the window isn't as wide as a right-justified
  footer needs, and margins tighten from 22px to 10px.
- **Launch becomes GO!**, and grows to fill the width the chevron leaves so its
  right edge lands on the tile's. That needed two overrides: Fusion gives
  buttons a generous minimum width of their own (which would have made the
  footer, not the tile, set the window width), and the footer's leading
  `addStretch` had to be collapsed by changing the spacer's *size policy*
  rather than its stretch factor — a stretch spacer stays Expanding, and when
  every factor is zero QBoxLayout still shares leftover space among expanding
  items, so the spacer ate the width the button was meant to take.
- **The show chip elides.** Show codes are longer than a tile, and without this
  one chip would set the width of the whole window. It elides in the *middle*,
  so `ORCA_ep01` keeps its episode number rather than losing the end; the full
  name stays in the tooltip.

One subtlety behind that: `FlowLayout.minimumSize()` had to start skipping
hidden widgets. The show field's text entry has a 170px minimum, and while
hidden in compact mode it was still setting the floor for the entire window.

Everything is hidden rather than removed, so expanding brings back exactly what
was there — open package sections included, and the window's previous size.
While compact, the view follows the selection: switch chip or tile and the one
on show changes with it.

The menu bar and status bar are hidden too. Everything they hold is reachable
again one click away, and leaving them visible would have made "compact" a
half-measure.

### Staying put

Compact mode asks the window manager for two things, and drops both when you
expand — a full-size window that refuses to go behind anything is a nuisance.

- **Always on top** is a Qt flag and works everywhere. Setting it makes Qt
  recreate the native window, so the geometry is restored afterwards.
- **Visible on all workspaces** is X11's `_NET_WM_STATE_STICKY`, which Qt has
  no API for. It's done through `wmctrl` or `xdotool`, whichever is installed,
  and it is a nicety: a session without either still gets a working compact
  window, and the toggle's tooltip says what was skipped. Wayland has no
  equivalent by design; macOS and Windows manage this themselves.

## One instance per user

A second launch doesn't open a second window — it raises the running one, which
is what clicking the icon again means.

`single_instance.py` uses a `QLocalServer` rather than a lock file: the socket
tells us not just *that* another instance exists but lets us talk to it, and the
OS cleans it up when the process dies. A lock file left by a crash needs its own
staleness dance; a stale socket is found by failing to connect and removed.

A bare connection is how a starting instance *probes* for a running one, so only
an explicit `show` payload counts as a request — otherwise merely checking
whether BootyCall is running would raise it. The socket name includes the user
name, so two people on one host don't block each other. If the lock can't be
taken *and* nothing answers, BootyCall starts anyway rather than refusing to
run.

## The Launch button's right-click menu

Right-clicking Launch, in either mode, offers **Launch** and **Update Dev
Installs and Launch**.

The update step's behaviour isn't defined yet. Rather than guess, it lives in
`bootycall/dev_install.py` behind an `IMPLEMENTED` flag: while that's False the
menu entry explains itself and **does not launch**. A plain launch dressed up as
an update would be worse than no update at all — you'd believe your dev builds
were current when nothing had touched them. `update_dev_installs()` also raises
rather than returning quietly, so a caller that skips the flag check fails
loudly.

To wire it up: fill in that function and flip the flag. Nothing else changes.

## Launch remembers where you were

Pressing **Launch** saves the current show, the active software, whether you
were compact, and *every* tile's variant choice — not just the active one, so Maya is still on the Ziva
build next session even if you launched from Nuke. Reopening comes back to that
state.

It saves on Launch rather than on every click: launching is the moment that says
"this is the setup I meant", and it keeps the config file off the write path of
ordinary browsing. All three values go in a single write, so a network home
directory can't leave the file half-updated.

## Saved setups

**File → Save current setup…** (or Ctrl+S, or the favourites window's **Add
current**) stores
the current show + DCC + variant under a name you pick. Every saved setup then
appears in the File menu, with the show and tool shown greyed on the right and
an **✕** on the far right:

```
File
  Save current setup...            Ctrl+S
  ─────────────────────────────────────────
  Saved setups
    Nightly comp      batman_returns - nuke16  ✕
    FX lookdev           dune_pt3 - houdinifx  ✕
    Anim dailies            combat_2 - maya    ✕
  ─────────────────────────────────────────
  Reload shows                         F5
  Find show                        Ctrl+F
  Quit
```

Clicking the row restores that state and closes the menu. Clicking the ✕ deletes
it and **leaves the menu open**, so you can clear several in one visit.

Each row is a `QWidgetAction` — a plain `QAction` can't carry a clickable
control on its right-hand side.

Setups live in `~/.config/bootycall/configs.json` (override with
`BOOTYCALL_CONFIG_FILE`), written atomically via write-then-rename. The file is
plain JSON and safe to hand-edit or drop into dotfiles. A corrupt or
partially-valid file never stops the app from opening: unreadable rows are
dropped, the rest load, and the reason goes to the status bar.

Setups are validated on use, not on load — shows get archived and bootstraps get
edited. If a saved setup points at a show that's gone, a DCC the show no longer
offers, or a variant that's been removed, BootyCall says which of the three
broke instead of failing silently or half-applying.

## The bootstrap is read, not imported

`bootycall/parser.py` reads the bootstrap with `ast`. Importing it would run
show code and would require `rez` and `ilp_bootstrap` to be importable in the
UI's own interpreter — neither is true, and neither should be needed to draw a
list of buttons.

The parser understands the constructs these files actually use: string
constants, tuple literals, references to earlier class attributes
(`base_package`), `+` concatenation across several groups, `dict(...)` calls,
and the trailing `packages["obj2abc"] = packages["maya"]` aliases. Anything it
can't reduce is skipped and reported in `Bootstrap.unresolved` rather than
taking the whole show down.

## The DCC registry

`bootycall/config.py` → `DCCS`. Each entry lists candidate `packages` keys,
best-first, plus a display label per key:

| DCC | shown by default | keys tried |
|---|---|---|
| Houdini Core | yes | `houdinicore`, `houdini`, `prman`, `dev_houdini` |
| Houdini FX | yes | `houdinifx`, `prmanfx` |
| Maya | yes | `maya`, `maya_ziva`, `maya_reference_remap`, `maya_reference_remapper`, `obj2abc` |
| Nuke | yes | `nuke`, `nuke16` |
| Nuke Studio | no | `nukestudio`, `nuke_studio`, `nuke_studio16`, `nukex` |
| Hiero | no | `hiero` |
| Blender | no | `blender` |

Out of the box the row is **Houdini Core, Houdini FX, Maya, Nuke, Terminal**.
Nuke Studio, Hiero and Blender stay in the registry but start switched off — a
row of nine tiles buries the four people actually reach for. The **Software**
menu has a checkbox per entry plus *Reset to defaults*; the choice is saved
alongside the favourites and survives restarts.

Turning one on puts its tile back in **registry order**, not click order, so the
row doesn't reshuffle depending on what you enabled first.

A show that defines only hidden software says so — *"this show offers Hiero,
Blender, all hidden. Turn them on in the Software menu."* Reporting that as "not
configured" would be a lie, and would send someone to edit a bootstrap for no
reason. When some are hidden and some aren't, the status line notes it quietly:
`.ilp/pipeline/config.py - 40 tools   (Hiero, Blender hidden)`.

Only keys present in the selected show's bootstrap are offered. A finishing-only
show that defines just `nuke16` gets one Nuke button and no variant dropdown.
Adding a DCC is one entry in that tuple — no other file changes.

**Nuke Studio will not appear against the bootstrap you sent**, because that
file has no `nukestudio` key — nothing to launch, so no button. The four names
above are guesses at what such a key would be called; tell me the real one (or
add it to the bootstrap) and it lights up like the rest. Hiero and Blender both
appear, since your bootstrap does define them.

Variants whose package tuples are byte-identical are collapsed to the first.
The bootstraps alias heavily — `packages["houdinicore"] = packages["houdini"]`,
`packages["obj2abc"] = packages["maya"]` — and offering two variants that
produce the same environment is a choice with no content. So Houdini Core shows
`houdinicore / prman / dev_houdini`, not four entries with a duplicate.

## Settings

**Settings → Settings…** (or the File menu, or Ctrl+,) edits the three roots:

| Field | Feeds |
|---|---|
| Shows root | the show field and Resolved packages |
| Local packages | the Local packages section |
| Dev packages | the Dev packages section |

Each row shows what its path resolves to and whether that folder exists — a typo
in a network path is otherwise invisible until the section it feeds comes up
empty. A missing folder is flagged but not blocked: a dev root you haven't made
yet is normal.

Leave a field **blank** to use the default, shown greyed as the placeholder. The
local root takes a `{user}` placeholder and the dev root takes `{local}` as well,
so the shipped `{local}/dev` keeps the two together when you move the local one.

Settings are saved per user alongside the favourites, and applied immediately —
shows are re-listed and both package roots rescanned.

## Configuration

Paths resolve in three layers, most specific last: the shipped constant, an
environment variable, then the Settings dialog. The environment variables are
the ones below, and are handy for pointing a session at a test tree:

| Variable | Default |
|---|---|
| `BOOTYCALL_SHOWS_ROOT` | `/ice/shows` |
| `BOOTYCALL_BOOTSTRAP_GLOBS` | `.ilp/pipeline/*.py:.ilp/bootstrap/*.py:.ilp/*/*.py:.ilp/*.py` |
| `BOOTYCALL_LAUNCH_COMMAND` | `ilp_bootstrap:{tool}` |
| `BOOTYCALL_TERMINAL_COMMAND` | `x-terminal-emulator:-e:rez-env:{packages}` |
| `BOOTYCALL_CONFIG_FILE` | `$XDG_CONFIG_HOME/bootycall/configs.json` |
| `BOOTYCALL_LOCAL_PACKAGES_ROOT` | `/ice/rez/packages/local/{user}` |
| `BOOTYCALL_DEV_PACKAGES_ROOT` | `{local}/dev` |
| `BOOTYCALL_REZ_USER` | the logged-in user |

**`BOOTYCALL_LAUNCH_COMMAND` is a guess** — it's the one thing here I couldn't
infer from the bootstrap file. Set it to whatever your desktop wrappers actually
invoke. It's run with the show folder as cwd, which is what the bootstrap's
`__file__`-relative `_get_show_packages()` lookup expects. The **Copy command**
button prints exactly what will run, so you can check it before wiring it up.

`BOOTSTRAP_GLOBS` is also a guess, derived from the three `os.path.dirname()`
calls in `_get_show_packages()` — that puts the bootstrap three levels below the
show root. If your real layout differs, the first pattern is the one to change.

## Layout

```
package.py               rez package definition
rezbuild.py              copies python/ and bin/ into the install
run_tests.sh
bin/bootycall            console entry point, put on PATH by the package
python/bootycall/
  config.py          shows root, bootstrap globs, the hard-coded DCC registry
  configs.py         saved-setup store (JSON, Qt-free)
  local_packages.py  local/dev root scans + override detection (Qt-free)
  discovery.py       list shows, locate + load a bootstrap, filter DCCs
  parser.py          AST reader for bootstrap modules
  launcher.py        argv construction + detached launch
  ui/
    chips.py            pinned-show chips, single selection
    collapsible.py      the expandable section widget
    completer.py        the show autocomplete field
    config_menu.py      saved-setup menu row, with the ✕
    favorites_window.py the favourites manager
    flow_layout.py      wrapping layout for the software row
    main_window.py
    style.py
  app.py             application entry point
tests/
  test_packaging.py      version agreement and rez payload checks
  sample_bootstrap.py    the file you sent, re-indented
  test_parser.py         32 parser + filter checks
  test_configs.py        52 store checks incl. corrupt files, reorder, rename
  test_local_packages.py local/dev root + override checks
  smoke_ui.py            drives the window offscreen, writes shots/
  shot_menu.py           renders the File menu on its own
```

`smoke_ui.py` uses a throwaway config file and throwaway package roots, so
running it never touches your real saved setups.

## One thing the parser turned up

In the bootstrap you sent, the trailing alias block ends with:

```python
packages["houdinifx"] = packages["houdini"]
```

`houdinifx` is already a key in the `dict(...)` above, defined as
`houdini_package + houdini_tools_package + htoa_package + utils_package +
ilp_ocean_package + hou_fx_plugins`. The later assignment overwrites it with
plain `houdini`, so **`axiom-3` never reaches a `houdinifx` session** — the
`hou_fx_plugins` in that entry is dead. `prmanfx` is unaffected; it keeps its
own entry.

BootyCall reports what the file evaluates to, not what it looks like it means,
so Houdini FX shows 29 packages rather than 30. If that overwrite is
unintentional, deleting that one line restores it.
