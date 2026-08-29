"""Checks for the AST bootstrap parser and the DCC filter."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from bootycall import config  # noqa: E402
from bootycall.discovery import available_dccs  # noqa: E402
from bootycall.parser import BootstrapParseError, parse_file, parse_source  # noqa: E402

SAMPLE = Path(__file__).with_name("sample_bootstrap.py")

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


print("parse sample bootstrap")
bs = parse_file(SAMPLE)

check("class detected", bs.class_name == "ProjectBootstrap", bs.class_name)
check("tool count", len(bs.packages) >= 35, str(len(bs.packages)))
check("nothing unresolved", not bs.unresolved, str(bs.unresolved))

print("\nname resolution")
check(
    "base_package expanded inside maya",
    "base-6" in bs.packages["maya"],
    str(bs.packages["maya"][:4]),
)
check(
    "tuple concatenation (maya = maya + mtoa + tools + utils + prep)",
    len(bs.packages["maya"]) == 11 + 2 + 8 + 8 + 1,
    str(len(bs.packages["maya"])),
)
check("mtoa merged into maya", "mtoa-5" in bs.packages["maya"])
check(
    "houdini uses htoa not htoa_test",
    "htoa-6.4.4" in bs.packages["houdini"]
    and "htoa-6.4.5" not in bs.packages["houdini"],
)
check("dev_houdini uses htoa_test", "htoa-6.4.5" in bs.packages["dev_houdini"])
check("prep_package appended to nuke", bs.packages["nuke"][-1] == "prep_utils-1")
check("nuke16 pinned to nuke-16.0", bs.packages["nuke16"][0] == "nuke-16.0")
check("single-element tuple", bs.packages["depview"] == ("ilp_sg_dependency_viewer-0",))

print("\nsubscript aliasing")
check("obj2abc aliases maya", bs.packages["obj2abc"] == bs.packages["maya"])
check("houdinicore aliases houdini", bs.packages["houdinicore"] == bs.packages["houdini"])
check(
    "houdinifx reassigned to houdini",
    bs.packages["houdinifx"] == bs.packages["houdini"],
    "later packages['houdinifx'] = packages['houdini'] must win over the dict entry",
)
check("dashed key kept", "das-element" in bs.packages)

print("\ngroups and scalars")
check("maya_package group captured", "maya_package" in bs.groups)
check("houdini_package group captured", "houdini_package" in bs.groups)
check("scalar captured", bs.scalars.get("review_machine_name") == "omg-05.ilpvfx.hq")

print("\nDCC filter (hard-coded, filtered by what exists)")
entries = available_dccs(bs)
names = [d.name for d, _ in entries]
check(
    "six of seven DCCs present",
    names == ["houdinicore", "houdinifx", "maya", "nuke", "hiero", "blender"],
    str(names),
)
check(
    "nukestudio absent - this bootstrap defines no such key",
    "nukestudio" not in names,
    str(names),
)
by_name = {d.name: keys for d, keys in entries}
check(
    "houdinicore variants, with the houdini alias deduped away",
    by_name["houdinicore"] == ("houdinicore", "prman", "dev_houdini"),
    str(by_name["houdinicore"]),
)
check(
    "houdinifx variants",
    by_name["houdinifx"] == ("houdinifx", "prmanfx"),
    str(by_name["houdinifx"]),
)
check("nuke variants", by_name["nuke"] == ("nuke", "nuke16"), str(by_name["nuke"]))
check(
    "maya variants, with obj2abc and the duplicate remapper deduped away",
    by_name["maya"] == ("maya", "maya_ziva", "maya_reference_remap"),
    str(by_name["maya"]),
)
check("hiero", by_name["hiero"] == ("hiero",), str(by_name["hiero"]))
check("blender", by_name["blender"] == ("blender",), str(by_name["blender"]))

print("\ndedupe only collapses byte-identical package sets")
check(
    "prman kept though it shares the houdini base",
    bs.packages["prman"] != bs.packages["houdini"],
)
check(
    "obj2abc really was identical to maya",
    bs.packages["obj2abc"] == bs.packages["maya"],
)

print("\nfilter drops what a show does not define")
partial = parse_source(
    "from ilp_bootstrap import Bootstrap\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    base = 'base-6'\n"
    "    packages = dict(nuke=('nuke-16.0', base), rv=('rv-2023',))\n"
)
partial_names = [d.name for d, _ in available_dccs(partial)]
check("only nuke offered", partial_names == ["nuke"], str(partial_names))

print("\nerror handling")
try:
    parse_source("x = 1\n")
except BootstrapParseError as exc:
    check("missing packages raises", "no 'packages'" in str(exc))
else:
    check("missing packages raises", False)

try:
    parse_source("def broken(:\n")
except BootstrapParseError:
    check("syntax error raises BootstrapParseError", True)
else:
    check("syntax error raises BootstrapParseError", False)

print("\nunresolvable entries are reported, not fatal")
odd = parse_source(
    "from ilp_bootstrap import Bootstrap\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    packages = dict(maya=('maya-2026.3',), weird=some_function())\n"
)
check("good entry kept", "maya" in odd.packages)
check("bad entry skipped", "weird" not in odd.packages)
check("bad entry reported", any("weird" in u for u in odd.unresolved), str(odd.unresolved))

print("\nargv expansion")
from bootycall import launcher  # noqa: E402

argv = launcher.expand(
    ("term", "-e", "rez-env", "{packages}", "--", "{command}"),
    ("a-1", "b-2"),
    "maya",
)
check("packages become separate entries", argv == ["term", "-e", "rez-env", "a-1", "b-2", "--", "maya"], str(argv))

argv = launcher.expand(("term", "-e", "rez-env", "{packages}", "--", "{command}"), ("a-1",), "")
check(
    "no command drops the separator too, rather than leaving a bare --",
    argv == ["term", "-e", "rez-env", "a-1"],
    str(argv),
)

argv = launcher.expand(("term", "-e", "rez-env", "{packages}"), (), "")
check("no packages, no filler", argv == ["term", "-e", "rez-env"], str(argv))

print("\npath settings layer")
check("three settable paths", config.PATH_KEYS == ("shows_root", "local_root", "dev_root"))
check("defaults cover them all", set(config.path_defaults()) == set(config.PATH_KEYS))
check("no overrides to begin with", config.path_overrides() == {})
config.set_path_overrides({"shows_root": "/mnt/elsewhere"})
check("override wins", config.shows_root() == "/mnt/elsewhere", config.shows_root())
check("others untouched", config.local_root_template() == config.path_defaults()["local_root"])
config.set_path_overrides({"shows_root": "   "})
check("a blank override falls back to the default", config.shows_root() == config.path_defaults()["shows_root"])
config.set_path_overrides({"nonsense": "/x"})
check("unknown keys are ignored", config.path_overrides() == {}, str(config.path_overrides()))
config.set_path_overrides(None)
check("cleared", config.shows_root() == config.path_defaults()["shows_root"])
check("dev is a reserved package name", config.RESERVED_PACKAGE_NAMES == ("dev",))

print("\nregistry sanity")
check("seven DCCs configured", len(config.DCCS) == 7)
check(
    "two DCCs shown by default, which with Terminal is the starting row",
    config.DEFAULT_VISIBLE_SOFTWARE == ("houdinicore", "maya"),
    str(config.DEFAULT_VISIBLE_SOFTWARE),
)
check(
    "Houdini Core is labelled just Houdini, and FX is HouFX",
    [d.label for d in config.DCCS if d.name.startswith("houdini")]
    == ["Houdini", "HouFX"],
    str([d.label for d in config.DCCS if d.name.startswith("houdini")]),
)
check(
    "the labels stay distinct, or two tiles would read the same",
    len({d.label for d in config.DCCS}) == len(config.DCCS),
    str([d.label for d in config.DCCS]),
)
check(
    "the long tail is off by default",
    not any(d.default_visible for d in config.DCCS if d.name in ("nukestudio", "hiero", "blender")),
)
check("every key has a label", all(k in d.variant_labels for d in config.DCCS for k in d.keys))

print("\nDCC executables")
check(
    "houdini core runs houdinicore, fx runs houdini",
    config.dcc_by_name("houdinicore").run_command == "houdinicore"
    and config.dcc_by_name("houdinifx").run_command == "houdini",
)
check(
    "everything else falls back to its lowercase name",
    all(
        d.run_command == d.name.lower()
        for d in config.DCCS
        if d.name != "houdinifx"
    ),
    str({d.name: d.run_command for d in config.DCCS}),
)
check(
    "no executable is empty",
    all(d.run_command for d in config.DCCS),
)

print("\nterminal emulator detection")
import shutil as _shutil  # noqa: E402

_known = [name for name, _args in config.TERMINAL_EMULATORS]
check("several candidates, best-first", len(_known) >= 5, str(_known))
check("gnome-terminal is tried first - Rocky and RHEL default to GNOME", _known[0] == "gnome-terminal")
check(
    "the Debian-only name is last, not first",
    _known[-1] == "x-terminal-emulator",
    str(_known),
)
check(
    "gnome-terminal uses -- rather than the removed -e",
    dict(config.TERMINAL_EMULATORS)["gnome-terminal"] == ("--",),
)
detected = config.detect_terminal()
check("detection returns argv, not a bare name", isinstance(detected, tuple) and detected)
check(
    "it picks something installed, or falls back to xterm",
    _shutil.which(detected[0]) is not None or detected == ("xterm", "-e"),
    str(detected),
)

print("\nlaunch template")
check("launch opens a terminal", config.LAUNCH_COMMAND[0] == detected[0], str(config.LAUNCH_COMMAND[:2]))
check(
    "and runs a shell script in it, so the window can be held open",
    config.LAUNCH_COMMAND[-3:] == ("bash", "-c", "{script}"),
    str(config.LAUNCH_COMMAND[-3:]),
)
check(
    "the terminal action uses the same shape",
    config.TERMINAL_COMMAND[-3:] == ("bash", "-c", "{script}"),
    str(config.TERMINAL_COMMAND[-3:]),
)
check(
    "hold defaults to on-error, not always",
    config.HOLD_TERMINAL == "error",
    config.HOLD_TERMINAL,
)

print("\nthe script itself")
check(
    "rez_argv puts the executable after --",
    launcher.rez_argv(("a-1", "b-2"), "maya") == ["rez-env", "a-1", "b-2", "--", "maya"],
    str(launcher.rez_argv(("a-1", "b-2"), "maya")),
)
check(
    "and omits it entirely for a shell",
    launcher.rez_argv(("a-1",)) == ["rez-env", "a-1"],
    str(launcher.rez_argv(("a-1",))),
)
_script = launcher.build_script(("a-1",), "maya")
check("the command is echoed first", _script.startswith('echo "+ rez-env a-1 -- maya"'), _script[:60])
check("the status is captured and reported", "rc=$?" in _script and "$rc" in _script)
check("and the window waits before closing", "read -r -p" in _script)
check(
    "requests with spaces are quoted, not split",
    "'a b-1'" in launcher.build_script(("a b-1",), "maya"),
    launcher.build_script(("a b-1",), "maya")[:70],
)

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    raise SystemExit(1)
print("all checks passed")
