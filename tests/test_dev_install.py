"""
Checks for the dev working location: discovery, installing, staleness, and the
filtered view that per-package checkboxes launch through.

No rez here, so the install itself is exercised with a stand-in command. What
matters is that BootyCall runs the right thing in the right directory and
reports what came back, not that rez-build works.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from bootycall import config, dev_install  # noqa: E402
from bootycall import dev_install as di  # noqa: E402
from bootycall import local_packages as lp  # noqa: E402
from bootycall.local_packages import (  # noqa: E402
    LocalPackage,
    definition_mismatch,
    list_local_packages,
)

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


import tempfile  # noqa: E402

ROOT = Path(tempfile.mkdtemp(prefix="bootycall-devwork-"))
WORKING = ROOT / "dev"
INSTALLED = ROOT / "installed"
WORKING.mkdir()
INSTALLED.mkdir()


def make_package(parent: Path, name: str, version: str = "", body: str = "") -> Path:
    directory = parent / name / version if version else parent / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.py").write_text(
        body or "name = '%s'\nversion = '%s'\n" % (name, version or "1.0.0")
    )
    return directory


print("what is in the working location")
make_package(WORKING, "nuke_utils")
make_package(WORKING, "anim_tools")
(WORKING / "notes").mkdir()  # a folder, but not a package
(WORKING / "scratch.txt").write_text("not a directory\n")
(WORKING / ".hidden").mkdir()

found = dev_install.list_working_packages(WORKING)
check("folders listed, files ignored", [p.name for p in found] == ["anim_tools", "notes", "nuke_utils"], str([p.name for p in found]))
check("hidden folders skipped", all(not p.name.startswith(".") for p in found))
check(
    "packages recognised by their definition",
    sorted(p.name for p in found if p.is_package) == ["anim_tools", "nuke_utils"],
    str([p.name for p in found if p.is_package]),
)
check(
    "a folder that is not a package is kept, with the reason",
    [p for p in found if p.name == "notes"][0].problem == "no package definition in it",
)
check("a missing working root is empty, not an error",
      dev_install.list_working_packages(ROOT / "nope") == [])

print("\ninstalling")
log = ROOT / "install.log"
saved_command = config.DEV_INSTALL_COMMAND
config.DEV_INSTALL_COMMAND = (
    "bash",
    "-c",
    'echo "built $(basename $PWD) into $1" >> %s; '
    "mkdir -p $1/$(basename $PWD)/1.0.0; "
    "cp package.py $1/$(basename $PWD)/1.0.0/" % log,
    "bootycall-install",
    "{dest}",
)

ok, output = dev_install.install(WORKING / "nuke_utils", INSTALLED)
check("install reports success", ok, output)
check(
    "it ran in the package's own directory, and was told where to put it",
    log.read_text().strip() == "built nuke_utils into %s" % INSTALLED,
    log.read_text().strip(),
)
check(
    "and the package landed",
    (INSTALLED / "nuke_utils" / "1.0.0" / "package.py").is_file(),
)

bad, message = dev_install.install(WORKING / "notes", INSTALLED)
check("a folder with no definition is refused before running anything", not bad)
check("and says why", "no package definition" in message, message)

config.DEV_INSTALL_COMMAND = ("bash", "-c", "echo 'build blew up' >&2; exit 2")
failed, message = dev_install.install(WORKING / "anim_tools", INSTALLED)
check("a failing build is reported as a failure", not failed)
check("with the build's own words", "build blew up" in message, message)

config.DEV_INSTALL_COMMAND = ("definitely-not-a-real-build-tool",)
missing, message = dev_install.install(WORKING / "anim_tools", INSTALLED)
check("a missing build tool is a message, not a crash", not missing)
check("naming what could not be run", "could not run" in message, message)
config.DEV_INSTALL_COMMAND = saved_command

print("\na build that exits clean but installs nothing")
config.DEV_INSTALL_COMMAND = ("bash", "-c", "echo 'installed to /somewhere/else'; exit 0")
lied, message = dev_install.install(WORKING / "nuke_utils", ROOT / "empty_dest")
check("exit zero is not taken as evidence", not lied)
check(
    "and the message says where it looked",
    "nothing appeared at" in message and "nuke_utils" in message,
    message,
)
check(
    "keeping the build's own output, which usually says where it went",
    "installed to /somewhere/else" in message,
    message,
)
config.DEV_INSTALL_COMMAND = saved_command

print("\nsymlinking")
ok, message = dev_install.symlink(WORKING / "anim_tools", INSTALLED)
check("linked", ok, message)
# rez finds a package by directory and reads its name from the definition, so
# the link has to be laid out <root>/<declared name>/<declared version>.
_linked_at = INSTALLED / "anim_tools" / "1.0.0"
check("and it is a link, not a copy", _linked_at.is_symlink(), str(_linked_at))
check(
    "pointing at the working copy",
    _linked_at.resolve() == (WORKING / "anim_tools").resolve(),
)
ok, message = dev_install.symlink(WORKING / "anim_tools", INSTALLED)
check("re-linking replaces the old link rather than failing", ok, message)

refused, message = dev_install.symlink(WORKING / "nuke_utils", INSTALLED)
check("but it will not quietly replace a real installed package", not refused)
check("saying so plainly", "real directory" in message, message)

print("\na checkout folder named something else still links correctly")
_odd = ROOT / "checkouts" / "rig-utils-WIP"
_odd.mkdir(parents=True)
(_odd / "package.py").write_text("name = 'rig_utils'\nversion = '1.8.666'\n")
# Its own destination: the shared one is enumerated by later checks, and a
# fixture that quietly grows is a fixture that starts failing elsewhere.
_odd_dest = ROOT / "odd_dest"
_odd_dest.mkdir()
ok, message = dev_install.symlink(_odd, _odd_dest)
check("linked", ok, message)
check(
    "under the name the package declares, not the folder it lives in",
    (_odd_dest / "rig_utils" / "1.8.666").is_symlink(),
    str(sorted(p.name for p in _odd_dest.iterdir())),
)
check(
    "and nothing is named after the checkout folder",
    not (_odd_dest / "rig-utils-WIP").exists(),
)
_found_odd = list_local_packages(_odd_dest, exclude=())
check("rez sees one package there", len(_found_odd) == 1, str(_found_odd))
check(
    "with the version the definition declares",
    _found_odd[0].version == "1.8.666",
    _found_odd[0].version,
)
check(
    "and no name or version mismatch, which is what used to make it invisible",
    definition_mismatch(_found_odd[0]) == "",
    definition_mismatch(_found_odd[0]),
)

print("\nwhich installs are behind their working copies")
installed_packages = list_local_packages(INSTALLED, exclude=())
check(
    "both are installed",
    sorted({p.name for p in installed_packages}) == ["anim_tools", "nuke_utils"],
    str(sorted({p.name for p in installed_packages})),
)
check("nothing stale yet", dev_install.stale_installs(installed_packages, WORKING) == [])

time.sleep(0.01)
(WORKING / "nuke_utils" / "tool.py").write_text("# an edit\n")
stale = dev_install.stale_installs(installed_packages, WORKING)
check("editing the working copy makes it stale", [s.name for s in stale] == ["nuke_utils"], str([s.name for s in stale]))
check("and it says how far behind", "newer" in stale[0].describe(), stale[0].describe())

time.sleep(0.01)
(WORKING / "anim_tools" / "rig.py").write_text("# also edited\n")
stale = dev_install.stale_installs(installed_packages, WORKING)
check(
    "a symlinked install is never stale - it is the working copy",
    [s.name for s in stale] == ["nuke_utils"],
    str([s.name for s in stale]),
)

print("\nnoise that must not count as an edit")
time.sleep(0.01)
build_dir = WORKING / "nuke_utils" / "build"
build_dir.mkdir()
(build_dir / "artifact.o").write_text("x")
(WORKING / "nuke_utils" / "__pycache__").mkdir()
(WORKING / "nuke_utils" / "__pycache__" / "tool.pyc").write_text("x")
(WORKING / "nuke_utils" / ".git").mkdir()
(WORKING / "nuke_utils" / ".git" / "index").write_text("x")

before = dev_install.newest_mtime(WORKING / "nuke_utils")
time.sleep(0.01)
(build_dir / "artifact.o").write_text("changed again")
check(
    "a rebuilt artifact does not read as a source edit",
    dev_install.newest_mtime(WORKING / "nuke_utils") == before,
    "%s vs %s" % (dev_install.newest_mtime(WORKING / "nuke_utils"), before),
)

only_source = ROOT / "quiet"
make_package(only_source, "thing")
check(
    "an untouched package still reports a time",
    dev_install.newest_mtime(only_source / "thing") > 0,
)

print("\nupdating the stale ones")
config.DEV_INSTALL_COMMAND = (
    "bash",
    "-c",
    "mkdir -p $1/$(basename $PWD)/1.0.0; touch $1/$(basename $PWD)/1.0.0/package.py",
    "bootycall-install",
    "{dest}",
)
stale = dev_install.stale_installs(list_local_packages(INSTALLED, exclude=()), WORKING)
updated, problems = dev_install.update_installs(stale, INSTALLED)
check("the stale one was rebuilt", updated == ["nuke_utils"], str(updated))
check("nothing went wrong", problems == [], str(problems))
check(
    "and it is no longer behind",
    dev_install.stale_installs(list_local_packages(INSTALLED, exclude=()), WORKING) == [],
)

config.DEV_INSTALL_COMMAND = ("bash", "-c", "echo nope >&2; exit 1")
time.sleep(0.01)
(WORKING / "nuke_utils" / "tool.py").write_text("# edited once more\n")
stale = dev_install.stale_installs(list_local_packages(INSTALLED, exclude=()), WORKING)
updated, problems = dev_install.update_installs(stale, INSTALLED)
check("a failed update is reported", updated == [] and len(problems) == 1, str(problems))
check("naming the package that failed", problems[0].startswith("nuke_utils:"), problems[0])
config.DEV_INSTALL_COMMAND = saved_command

print("\nthe filtered view behind the per-package checkboxes")
view_dir = ROOT / "view"
none_off, error = dev_install.selection_view(INSTALLED, [], view_dir)
check("nothing switched off means the real root is used", none_off is None and error == "", error)

view, error = dev_install.selection_view(INSTALLED, ["nuke_utils"], view_dir)
check("switching one off builds a view", view is not None, error)
check(
    "holding only the ones still wanted",
    sorted(p.name for p in view.iterdir()) == ["anim_tools"],
    str(sorted(p.name for p in view.iterdir())),
)
check("as links, so nothing is copied", (view / "anim_tools").is_symlink())
check(
    "and rez can still read the package through it",
    [p.name for p in list_local_packages(view, exclude=())] == ["anim_tools"],
    str([p.name for p in list_local_packages(view, exclude=())]),
)
check(
    "the real root is untouched",
    sorted({p.name for p in list_local_packages(INSTALLED, exclude=())})
    == ["anim_tools", "nuke_utils"],
)

view2, error = dev_install.selection_view(INSTALLED, ["anim_tools"], view_dir)
check(
    "rebuilding the view forgets the previous selection",
    sorted(p.name for p in view2.iterdir()) == ["nuke_utils"],
    str(sorted(p.name for p in view2.iterdir())),
)

everything_off, error = dev_install.selection_view(
    INSTALLED, ["anim_tools", "nuke_utils"], view_dir
)
check(
    "switching everything off is the same as switching the section off",
    everything_off is None and error == "",
    error,
)

print("\nremoving an installed one")
link_target = (INSTALLED / "anim_tools").resolve()
linked = [p for p in list_local_packages(INSTALLED, exclude=()) if p.name == "anim_tools"][0]
check("the install under test is the link", linked.path.is_symlink(), str(linked.path))
error = dev_install.remove_installed(linked, INSTALLED)
check("removing a linked install works", error == "", error)
check("and leaves the working copy alone", link_target.is_dir(), str(link_target))

outsider = LocalPackage(name="elsewhere", version="", path=ROOT / "quiet" / "thing")
error = dev_install.remove_installed(outsider, INSTALLED)
check("something outside the root is refused", "refusing" in error, error)
check("and is still there", (ROOT / "quiet" / "thing").is_dir())

print("\nthe install check looks for the name the package declares")
# The bug this replaced: a checkout called rig_utils-alembic-properties whose
# package.py says name = "rig_utils_alembic_properties" installs correctly and
# was then reported as a failed build, because the check looked for a directory
# named after the folder rather than the package.
_odd = Path(tempfile.mkdtemp(prefix="bootycall-oddname-"))
_odd_src = _odd / "rig_utils-alembic-properties"
_odd_src.mkdir()
(_odd_src / "package.py").write_text(
    'name = "rig_utils_alembic_properties"\nversion = "0.3.1"\n'
)
_odd_dest = _odd / "installed"
_odd_dest.mkdir()

_where = [str(x) for x in di.installed_paths(_odd_src, _odd_dest)]
check(
    "the declared name and version come first",
    _where[0] == str(_odd_dest / "rig_utils_alembic_properties" / "0.3.1"),
    str(_where),
)
check(
    "the folder name is kept as a fallback, not dropped",
    str(_odd_dest / "rig_utils-alembic-properties") in _where,
    str(_where),
)

_saved_cmd = config.DEV_INSTALL_COMMAND
# Behaves like rez: installs under <prefix>/<name>/<version>.
config.DEV_INSTALL_COMMAND = (
    "bash", "-c",
    "mkdir -p $1/rig_utils_alembic_properties/0.3.1 && "
    "cp package.py $1/rig_utils_alembic_properties/0.3.1/",
    "x", "{dest}",
)
_ok, _out = di.install(_odd_src, _odd_dest)
check("a build under the declared name is a success", _ok, _out[:200])

# And the check still has to catch the thing it was written for.
config.DEV_INSTALL_COMMAND = ("bash", "-c", "echo built somewhere else; exit 0")
_ok, _out = di.install(_odd_src, _odd_dest / "empty")
check("a build that produces nothing is still caught", not _ok, _out[:120])
check(
    "and the path it names is the one rez would have used",
    "rig_utils_alembic_properties/0.3.1" in _out,
    _out.splitlines()[0] if _out else "",
)
config.DEV_INSTALL_COMMAND = _saved_cmd

print("\nnothing in the working location is ever removed")
_guard = Path(tempfile.mkdtemp(prefix="bootycall-guard-"))
_guard_work = _guard / "dev"
(_guard_work / "my_tool" / "1.0.0").mkdir(parents=True)
(_guard_work / "my_tool" / "1.0.0" / "package.py").write_text(
    'name = "my_tool"\nversion = "1.0.0"\n'
)
_saved_paths = dict(config.PATH_OVERRIDES) if hasattr(config, "PATH_OVERRIDES") else None
config.set_path_overrides(
    # The setting anyone could make: the working location inside the dev root,
    # where a Remove would otherwise walk straight into the source.
    {"dev_root": str(_guard), "dev_working_root": str(_guard_work)}
)
_victim = lp.LocalPackage(
    name="my_tool", version="1.0.0", path=_guard_work / "my_tool" / "1.0.0"
)
_refusal = lp.delete_package(_victim, _guard)
check("it refuses", _refusal != "", _refusal)
check("and says why", "working location" in _refusal, _refusal)
check(
    "and the working copy is still there",
    (_guard_work / "my_tool" / "1.0.0" / "package.py").is_file(),
)

# A real installed package beside it is still removable: the guard must not
# turn Remove off altogether.
(_guard / "other_tool" / "2.0.0").mkdir(parents=True)
(_guard / "other_tool" / "2.0.0" / "package.py").write_text('name = "other_tool"\n')
_fine = lp.LocalPackage(
    name="other_tool", version="2.0.0", path=_guard / "other_tool" / "2.0.0"
)
check("an installed package next door still goes", lp.delete_package(_fine, _guard) == "", "")
check("really gone", not (_guard / "other_tool").exists())
config.set_path_overrides({})

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all dev-install checks passed")
