# Changelog

The version in `package.py`, `pyproject.toml` and `bootycall/__init__.py` is
bumped **in the same commit as the change it describes**, and every bump gets an
entry here. `tests/test_packaging.py` fails if the three versions disagree or if
the newest entry below is not the current version — that is what stops a build
going out indistinguishable from the one before it.

Breaking changes to how a launch is assembled bump the minor; everything else
bumps the patch. The window title carries the version, so an artist reporting a
problem is reporting it against something specific.

## 0.10.0

Minor: what the resolve is handed changed, and so did what it reports.

- **The show name goes into more than two variables.** A show package's
  `commands()` runs *inside* the resolve, and some of them read the show out of
  the environment expecting the bootstrap to have exported it. Going straight
  to rez, we hadn't. `diner_bear_s3` reads `ILP_CONTEXT_SHOW` and died with
  `PackageCommandError: 'ILP_CONTEXT_SHOW'` while every other show launched
  fine. The default set is now
  `ILP_SHOW:ILP_CONTEXT_SHOW:SHOW:BOOTYCALL_SHOW`, and
  **`BOOTYCALL_SHOW_ENV_VARS`** sets it — whatever a `PackageCommandError`
  names goes in that list.

- **Diagnostics reads the show package and says what it wants.** A new section
  lists every variable the definition asks the environment for — `os.environ[…]`,
  `os.getenv`, rex's `env.FOO` — and marks the ones nothing sets with `***`.
  Reads only; `env.FOO = …` and `env.PATH.prepend(…)` are writes and are not
  listed. Next time a show fails and its neighbour doesn't, that section is the
  answer rather than a week of guessing.

- **Installing a dev package reloads the whole window**, not just the two
  package lists. A new package changes which requests are outranked and
  invalidates the cached resolve probe; refreshing only the lists left both
  stale.

- **Dev packages print orange, local ones green.** rez already marks its own
  local path green, so green-on-green said nothing. Symlinked installs now say
  `(symlinked)` — asked of the filesystem with `-L`, so a link made by hand
  counts the same as one BootyCall made.

- **`tests/fixture.py` builds the sample studio the suites run against.** It
  never existed: `/tmp/ice` had been made by hand once and every run since
  depended on it still being there. It passed on one machine and nowhere else,
  and the day it was deleted six suites failed with an `IndexError` that said
  nothing about why. It is code now, rebuilt from scratch on every run, and any
  suite can be run on its own.

## 0.9.0

Minor: the launch is a script on disk now, not a shell one-liner.

- **The preamble is written to a file and rez is pointed at it.** rez does not
  run the argv it is handed — it writes the whole thing into a `rez-shell.sh`
  of its own, *inside double quotes*, and runs that. Everything quoted stops
  being quoted on the way through: the single quotes round the awk program go
  literal, `$1` inside it gets expanded by the shell, and the `$(...)` runs at
  the wrong moment. What came out was `syntax error near unexpected token '('`
  and a failed launch.

  Two releases went out trying to write a one-liner that survives that. There
  isn't one. The argv is now `rez-env <pkgs> -- bash /tmp/bootycall-<uid>/launch-xxxx.sh`
  — four bare words with nothing in them for a shell to get wrong.

- **The script is readable, and it stays.** Real lines, real indentation,
  comments. It is not deleted after the launch (a detached DCC is still the
  child of a shell reading it), so the last thing you ran is sitting there to
  be looked at when a launch goes somewhere you did not expect. Anything older
  than a day is cleared out on the way in.

- **`BOOTYCALL_SCRIPT_DIR`** picks where they go. Unset means `$TMPDIR`, then
  the platform default — the same rule everything else on the box follows.
  Point it at `/var/tmp` to keep scripts across a reboot. rez's own
  `rez_context_*` directories are its business and follow `$TMPDIR` too.

- Tests now paste the argv into a script the way rez does and run *that*. The
  previous two versions passed every check and could not launch.

## 0.8.1

Patch: the report from 0.8.0 ran, then died on the shell it was written for.

- **Dropped `${!var}` indirect expansion and the here-string.** Pairing each
  `REZ_<NAME>_ROOT` with its `REZ_<NAME>_VERSION` was done in the shell, which
  needed indirect expansion — bash before 5.1 rejects it outright with
  `invalid indirect expansion`, which is what Rocky 9 said. One `awk` pass now
  does the pairing *and* the root matching and prints finished lines; the shell
  only decides whether there were any. No bashisms left: rez writes the command
  into a script of its own and runs it with whatever shell the site configured,
  so it has to be portable shell.
- Roots reach `awk` as `-v` assignments rather than pasted into the program.
- Tests run the banner under `sh`, `dash` and `bash` and require a clean exit
  with an empty stderr in each. `bash -n` said the previous version parsed;
  parsing was never the problem.

## 0.8.0

Minor: the report from 0.7.0 never actually ran, and the shell never got one.

- **Fixed the launch report, which printed nothing.** Two bugs, both in the
  generated shell rather than in what it said. The per-root branch was built
  with a real newline where a two-character `\n` was meant, splitting the
  one-liner in half; and the whole argv was interpolated into `echo "+ ..."`,
  where the quoting flipped partway through and the outer shell began
  expanding and running fragments of the command it was only supposed to
  display. What reached the terminal was `invalid indirect expansion` followed
  by a syntax error — on a good day. 0.7.0 shipped a banner that was assembled
  correctly and could not run.
- **The terminal gets the report too.** `rez_argv` returned early whenever
  there was no application to run, so the shell was the one launch path
  nothing could be wrapped around. It now starts behind the same preamble when
  there is something to say — `rez-context` for rez's table, then the report,
  then the shell. With nothing to say it stays a bare `rez-env`, so rez's own
  entry banner is untouched.
- **The echoed command line is the request again**, not the reporting wrapper.
  With the banner in, the real argv is a screenful of quoted shell, and a line
  nobody reads answers no questions. You get `+ rez-env base-6 rig_utils --
  maya`; the wrapper is still there, just not in your face.
- Tests now hand the generated script to `bash -n` and run the banner against a
  faked resolved environment. Every existing check passed against 0.7.0's
  broken shell, because a string can contain every right substring and still be
  shell that will not parse.

## 0.7.0

Minor: the launch argv carries more than it did.

- **Symlink installs under the name the package declares**, not the folder it
  lives in — and under its declared version as a directory level. A checkout
  called `rig-utils-WIP` whose `package.py` says `name = "rig_utils"` was being
  linked as `rig-utils-WIP`, producing precisely the name mismatch the package
  lists flag in red, and a package rez reads and then discards. Now it lands at
  `<dev root>/rig_utils/1.8.666`.
- **The launch prints a short report under rez's table**, in colour on a
  terminal and plain when piped:

  ```
  BootyCall - what this window changed about the environment
    Local packages are switched OFF for this launch
    Dev packages switched off: houdini_utils
    your packages in this environment:
      rig_utils-1.8.666  (dev)
      base-6.56.1  (local)
  ```

  The warnings come from the window, because rez cannot know you switched a
  root off — that happened somewhere it never saw. The package list comes from
  `REZ_<NAME>_ROOT` in the resolved environment, because nothing else knows what
  really happened. Escape codes are set once behind `[ -t 1 ]`, so a launch
  whose output lands in a log file has no colour codes in it.

## 0.6.4

- **Symlinked installs read `(symlinked)`**, with the working copy's path on the
  tooltip. They behave differently from built ones in three ways — live edits, no
  staleness, and a different delete — and nothing said which kind you were
  looking at.
- **Deleting a symlinked package removes the link and nothing else.** It used to
  refuse outright, which was safe and useless: Delete silently did nothing to
  the one kind of install you most often want to undo. The link's *own* path is
  checked against the root without resolving it, so the working copy's location
  is never consulted, and the confirmation says how many of the selection are
  links before you press the button.
- **Tooltips are readable.** There was no `QToolTip` rule, so tooltips took
  their text colour from the general `QWidget` rule and their background from
  the platform's pale tooltip palette — light text on a light ground. Every
  tooltip in the app was affected, which is most of the explanations BootyCall
  has been adding for the last several versions.

## 0.6.3

- **Update Dev Installs and Launch says why it did nothing.** It was not dead —
  it was finding nothing to update and reporting that as a five-second status
  message before launching normally, which from the outside is exactly what a
  broken menu item looks like. Four different situations produced it: the
  section switched off, nothing in play, a dev working location that does not
  exist or holds no packages, and — the likeliest — a working location whose
  folder names do not match any installed dev package. Each is now named, with
  the paths and both lists of names, and offers Launch Anyway rather than
  launching as though the update had run.
- **A three-pixel progress bar during the rebuild**, along the bottom edge, in
  compact mode as well. Overlaid on the central widget rather than placed in the
  layout, so showing it cannot resize a window that is sized to the pixel. It
  steps *before* each build rather than after: a rez build is slow enough that a
  bar which only moves on completion spends most of its life looking stuck.

## 0.6.2

- **"Overridden" is now "outranked"**, matching the word the rows already use.
  A header reading *2 overridden* above a row reading *outranked by 1.9.0* makes
  you stop and work out whether they mean the same thing. And the two ways of
  losing are counted apart, because they are not the same problem: *1 outranked*
  (a higher version won) and *1 unusable* (the version could never satisfy the
  request).
- **Installed Dev Packages opens by default.** It is the section you watch while
  working; the other two stay closed.
- **Its path line is gone.** A section that stays open pays for that row every
  time you look at the window, and the path does not change. The root and the
  "not in your rez packages path" warning moved to the header's tooltip, so
  nothing is lost. Local packages keep theirs, since that section is usually
  shut.

## 0.6.1

- **File → Reload** replaces *Reload shows* and reloads all of it: the shows
  list, the selected show's bootstrap, both package roots, the saved settings,
  and rez's cached packages path. Re-listing one of those and not the others
  left a window half stale, which is worse than wholly stale — you cannot tell
  which half you are looking at.
- **The Settings menu is gone.** The action is in File, and one door per room.
- **"In use" and "overridden" are counted apart**, amber and red:
  `1 in use   2 overridden`. They are different facts — a build the resolve
  will get, against one the resolve names and then takes from somewhere else —
  and reporting the second as the first is what sent a week of debugging after
  an install that was never broken.
- The resolve list now only marks a request *overridden by your local build*
  when that build actually wins. A mark that says the question is answered when
  it is not is worse than no mark.

## 0.6.0

**The launch now says which resolved packages are yours.** Minor, because the
launch argv changed again.

rez marks packages from its own configured local packages path green and
`(local)` in the context table. A dev root BootyCall puts on the path gets no
such mark — rez has no reason to think it is special — so a correctly resolved
dev build sat in a forty-line table looking exactly like the other thirty-nine,
and was missed. That was the last of it: the package had been resolving
correctly for some time.

Under rez's table the launch now prints:

```
BootyCall: resolved from your own package roots:
  rig_utils-1.8.666  (dev)
  base-6.56.1  (local)
```

- Read from `REZ_<NAME>_ROOT` in the resolved environment, not from anything
  BootyCall predicted — this line has to be true.
- The dev root is matched before the local root it lives inside, or every dev
  package would be labelled `(local)`.
- **When nothing matches it says so**, which is the line that matters most:
  *none of your local or dev packages are in this environment.*

## 0.5.5

**Edit → Test resolve with rez** runs the actual resolve and reports what rez
chose, instead of predicting it.

Everything BootyCall said about which package wins was inference from directory
listings. A listing can rank version numbers; it cannot evaluate the `requires`
of every package in the graph, and one `requires = ["rig_utils-1.7"]` anywhere
pins a version the ranking says should have won. 0.5.3 predicted a dev build
would win when it did not — this is the difference between predicting and
measuring, and it is why the feature exists.

- Runs `rez-env <requests> -- printenv` with the same environment a launch gets
  and reads `REZ_<NAME>_VERSION` / `REZ_<NAME>_ROOT` back. Those are a documented
  contract; `rez-context`'s table is not.
- Reports your newest build against what rez actually resolved and from which
  root, flags the disagreement, and points at `rez-context --graph`.
- A resolve that fails outright is reported as the answer, in rez's own words —
  nothing was picked up because nothing resolved.

## 0.5.4

- **Compact keeps its title bar**, titled `B.C.` — short enough that a bar the
  width of one tile shows all of it, where "BootyCall 0.5.4" was truncated and an
  empty title had the window manager substituting the application name. The
  frameless experiment and the drag-anywhere it needed are both gone.
- **Collapsing holds the corner the window is nearest.** Qt resizes about the
  top-left, so a launcher parked bottom-right used to skate up and left away from
  where it was put. It now keeps whichever corner it is closest to, and expanding
  grows back out of that same corner, clamped so it cannot grow off the screen.

## 0.5.3

**BootyCall now works out which copy of a package rez will actually choose**, and
says so, instead of calling everything in your roots an override.

rez takes the highest version satisfying the request from anywhere on the path;
path order only settles ties between equal versions. So a dev build sitting
first on the path, correctly installed, correctly named, can still lose to a
newer studio build of the same name — which is exactly what a real diagnostics
report showed: `rig_utils-1.7.666` in the dev root against a request of
`rig_utils-1`, with a higher `1.x` in a studio root.

- Lists now read **`outranked by 1.9.0`** for a build that loses, in grey,
  instead of an amber `overrides` it does not do.
- Diagnostics marks the winner with `>>>` and the loser with `***`, naming the
  version and the root that beat it.
- `resolves_to()` does the scan across every root on the path. It is a directory
  scan, so it answers "which version is highest", not "what will the full
  resolve do" — it does not evaluate variants or a package's own requires.

## 0.5.2

- **Background is `#0c1927`.** The whole surface ladder scaled proportionally, so
  the hue is unchanged and only the depth moved.
- **An install that exits clean but puts nothing in the dev root is a failure.**
  Exit zero is the build's opinion, not evidence: a build system that ignores
  the prefix and installs to rez's configured local packages path exits happily,
  and BootyCall was reporting that as "Installed". It now checks the package
  actually arrived and, when it has not, says where it looked and keeps the
  build's output, which usually names where it really went.
- **The reason a build failed is in the dialog, not behind Show Details.** A
  dialog that says "it failed, click to find out why" is a dialog that gets
  dismissed.

## 0.5.1

- **Edit → Diagnostics** puts everything that decides whether a package reaches
  the environment into one copyable report: what rez is configured to read, the
  path this launch will actually use, which roots only BootyCall knows about,
  every package found with the name and version its own definition declares, the
  request that names it, and the command that would run.
- **Packages rez would silently skip are flagged.** BootyCall lists by directory;
  rez resolves by what the definition says. A folder called `nuke_utils` whose
  `package.py` declares a different name, a `1.0.0` directory declaring `1.0.1`,
  or a definition that does not parse — all in the list, in the right root, on
  the path, and invisible to every resolve. Read with `ast`, never imported.
- **The window is `#1f4060`.** The neutral greys moved to the same ladder in
  navy; the amber, red, green and blue accents are untouched.
- **Compact mode has no title bar.** Clearing the title was not enough — with an
  empty name most window managers fall back to the application name and draw a
  bar around it, so compact wore a truncated "bootycall". The decoration is gone
  instead, and the window can be dragged from anywhere on it.
- Switching a package section off no longer warns "nothing was excluded" when the
  root was never on rez's path to begin with. That is the normal case now, and
  the warning fired every time.

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
