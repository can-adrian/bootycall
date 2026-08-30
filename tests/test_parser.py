"""Checks for the AST bootstrap parser and the DCC filter."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
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
    "every registered DCC this bootstrap defines gets a tile",
    names == ["houdinicore", "houdinifx", "maya", "nuke", "hiero", "blender"],
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
check(
    "four settable paths",
    config.PATH_KEYS
    == ("shows_root", "local_root", "dev_root", "dev_working_root"),
    str(config.PATH_KEYS),
)
check(
    "the working location defaults into the user's home, not a package root",
    config.path_defaults()["dev_working_root"] == "{home}/dev",
    config.path_defaults()["dev_working_root"],
)
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
check("six DCCs configured", len(config.DCCS) == 6, str([d.name for d in config.DCCS]))
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
    not any(
        d.default_visible
        for d in config.DCCS
        if d.name in ("houdinifx", "nuke", "hiero", "blender")
    ),
)
check(
    "nuke studio is gone from the registry entirely",
    "nukestudio" not in [d.name for d in config.DCCS],
    str([d.name for d in config.DCCS]),
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
    launcher.rez_argv(("a-1", "b-2"), "maya", show_info=False)
    == ["rez-env", "a-1", "b-2", "--", "maya"],
    str(launcher.rez_argv(("a-1", "b-2"), "maya", show_info=False)),
)
check(
    "and omits it entirely for a shell",
    launcher.rez_argv(("a-1",)) == ["rez-env", "a-1"],
    str(launcher.rez_argv(("a-1",))),
)

print("\nlaunching reports the resolve, the way a terminal always did")
_with_info = launcher.rez_argv(("a-1",), "maya")
check(
    "the app runs behind rez-context",
    _with_info[:4] == ["rez-env", "a-1", "--", "bash"],
    str(_with_info),
)
check(
    "the argv is a bare path, with nothing in it for a shell to get wrong",
    _with_info[-1] == shlex.quote(_with_info[-1]),
    _with_info[-1],
)
_written = Path(_with_info[-1]).read_text()
check(
    "which prints the same table an interactive rez shell prints",
    "rez-context" in _written,
    _written[:120],
)
check(
    "and execs the app, so nothing extra is left in the process tree",
    "exec maya" in _written,
    _written[-40:],
)
check(
    "a missing rez-context does not stop the launch",
    "2>/dev/null" in _written,
    _written[:120],
)
check(
    "a shell needs none of it - rez prints the table itself on the way in",
    launcher.rez_argv(("a-1",)) == ["rez-env", "a-1"],
    str(launcher.rez_argv(("a-1",))),
)
_saved_info = config.SHOW_RESOLVE_INFO
config.SHOW_RESOLVE_INFO = False
check(
    "and it can be switched off",
    launcher.rez_argv(("a-1",), "maya") == ["rez-env", "a-1", "--", "maya"],
    str(launcher.rez_argv(("a-1",), "maya")),
)
config.SHOW_RESOLVE_INFO = _saved_info

print("\nsaying which resolved packages are the user's own")
_roots = (("dev", "/ice/local/adts/dev"), ("local", "/ice/local/adts"))
_summary = launcher.launch_banner(_roots)
check("it reads the resolved environment, not our predictions", "REZ_" in _summary and "_ROOT" in _summary, _summary[:80])
check(
    "both roots are handed to it as data, not pasted into the program",
    "r0=/ice/local/adts/dev" in _summary and "r1=/ice/local/adts" in _summary,
    _summary[:200],
)
check(
    "and it says so when none of them made it in",
    "none of your local or dev packages" in _summary,
    _summary[-160:],
)
check("nothing to say, nothing printed", launcher.launch_banner() == "")

print("\nand what this window switched off, which rez cannot know")
_noted = launcher.launch_banner(
    _roots, (("warn", "Local packages are switched OFF for this launch"),)
)
check(
    "the note is in the banner",
    "Local packages are switched OFF" in _noted,
    _noted[:200],
)
check(
    "coloured by level",
    "_bcY" in _noted and "_bcG" in _noted and "_bcR" in _noted,
    _noted[:200],
)
check(
    "and colour is dropped when the output is not a terminal",
    "[ -t 1 ]" in _noted,
    _noted[:120],
)
check(
    "notes alone are enough to earn a banner",
    launcher.launch_banner((), (("warn", "x"),)) != "",
)
_nasty = launcher.launch_banner((), (("warn", 'a "quote" and $VAR and `cmd`'),))
check(
    "note text cannot break out of its shell string",
    '\\"quote\\"' in _nasty and "\\$VAR" in _nasty and "\\`cmd\\`" in _nasty,
    _nasty,
)

_argv = launcher.rez_argv(("a-1",), "maya", roots=_roots)
_written = Path(_argv[-1]).read_text()
check(
    "the launch carries it",
    "your packages in this environment" in _written,
    _written[:120],
)
check(
    "and still execs the application afterwards",
    _written.rstrip().endswith("exec maya"),
    _written[-40:],
)
check(
    "the dev root is tested before the local one it sits inside",
    _written.index("l0=dev") < _written.index("l1=local"),
    "dev must be tested first, or every dev package inside the local root "
    "reports as local",
)

_script = launcher.build_script(("a-1",), "maya")
check(
    "the request is echoed first, not the reporting wrapper around it",
    _script.startswith("printf '+ %s\\n\\n' 'rez-env a-1 -- maya'"),
    _script[:70],
)
check("the status is captured and reported", "rc=$?" in _script and "$rc" in _script)
check("and the window waits before closing", "read -r -p" in _script)
check(
    "requests with spaces are quoted, not split",
    "'a b-1'" in launcher.build_script(("a b-1",), "maya"),
    launcher.build_script(("a b-1",), "maya")[:70],
)

print("\nand the generated shell is shell bash can actually run")
# Everything above reads the script as a string. A string can contain every
# right substring and still be broken shell: for a release the banner was
# assembled correctly and then dropped inside echo "...", where the quoting
# flipped halfway through, and nothing printed at all. So hand it to bash.
_banner_script = launcher.build_script(("a-1",), "maya", _roots)
_parsed = subprocess.run(
    ["bash", "-n"], input=_banner_script, capture_output=True, text=True
)
check(
    "bash parses it",
    _parsed.returncode == 0,
    _parsed.stderr.strip()[:200],
)
check(
    "and it is one line -- a real newline splits the one-liner in half",
    "\n" not in _banner_script,
    repr(_banner_script[:200]),
)

# Run the banner for real against a faked resolved environment, which is the
# only way to know the reporting loop reads REZ_*_ROOT the way rez writes it.
_ran = subprocess.run(
    ["bash", "-c", launcher.launch_banner(_roots, (("warn", "off"),))],
    capture_output=True,
    text=True,
    env={
        "PATH": os.environ.get("PATH", ""),
        "REZ_RIG_UTILS_ROOT": "/ice/local/adts/dev/rig_utils/1.8.666",
        "REZ_RIG_UTILS_VERSION": "1.8.666",
        "REZ_BASE_ROOT": "/ice/local/adts/base/6.56.1",
        "REZ_BASE_VERSION": "6.56.1",
    },
)
check("it runs clean", _ran.returncode == 0 and not _ran.stderr, _ran.stderr[:200])
check("the note prints", "off" in _ran.stdout, _ran.stdout)
check(
    "the dev package is named with its version",
    "rig_utils-1.8.666  (dev)" in _ran.stdout,
    _ran.stdout,
)
check(
    "the local one is labelled local",
    "base-6.56.1  (local)" in _ran.stdout,
    _ran.stdout,
)

# rez writes the command into a script of its own and runs it with whatever
# shell the site configured, so the banner has to be portable shell rather
# than bash-with-extras. The first attempt used ${!var} and a here-string and
# failed on the exact Rocky boxes it was written for.
for _shell in ("sh", "dash", "bash"):
    if shutil.which(_shell) is None:
        continue
    _out = subprocess.run(
        [_shell, "-c", launcher.launch_banner(_roots, (("warn", "off"),))],
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "REZ_RIG_UTILS_ROOT": "/ice/local/adts/dev/rig_utils/1.8.666",
            "REZ_RIG_UTILS_VERSION": "1.8.666",
        },
    )
    check(
        "it runs under %s with nothing on stderr" % _shell,
        _out.returncode == 0
        and not _out.stderr
        and "rig_utils-1.8.666  (dev)" in _out.stdout,
        (_out.stderr or _out.stdout)[:200],
    )

print("\nand it survives rez re-quoting the command")
# rez does not run the argv it is handed. It writes the whole thing into a
# rez-shell.sh of its own, inside double quotes, and runs that. Anything
# quoted stops being quoted on the way through: single quotes go literal, $1
# in an awk program gets expanded, $(...) runs at the wrong moment. Two
# releases went out trying to write a one-liner that survives it.
#
# So: paste the argv into a script the way rez does, and run it.
_requote_argv = launcher.rez_argv(("a-1",), "true", roots=_roots)
_after = _requote_argv[_requote_argv.index("--") + 1:]
_requoted = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
_requoted.write("#!/bin/bash\n")
for _k, _v in (
    ("REZ_RIG_UTILS_ROOT", "/ice/local/adts/dev/rig_utils/1.8.666"),
    ("REZ_RIG_UTILS_VERSION", "1.8.666"),
):
    _requoted.write("export %s=%s\n" % (_k, _v))
_requoted.write("%s\n" % " ".join(_after))
_requoted.close()
_out = subprocess.run(
    ["bash", _requoted.name], capture_output=True, text=True
)
check(
    "the command rez pastes into its own script still runs",
    _out.returncode == 0 and not _out.stderr,
    (_out.stderr or "clean")[:300],
)
check(
    "and still reports",
    "rig_utils-1.8.666  (dev)" in _out.stdout,
    _out.stdout[:300],
)
check(
    "because every argument is a bare word rez cannot damage",
    all(part == shlex.quote(part) for part in _after),
    str(_after),
)

print("\nthe terminal gets the report too")
_term = Path(launcher.rez_argv((), "", roots=_roots)[-1]).read_text()
check(
    "a shell with something to report is started behind the banner",
    _term.rstrip().endswith("exec bash")
    and "your packages in this environment" in _term,
    _term[-60:],
)
check(
    "with nothing to report it stays a bare rez-env, which prints rez's own",
    launcher.rez_argv(("a-1",)) == ["rez-env", "a-1"],
    str(launcher.rez_argv(("a-1",))),
)

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    raise SystemExit(1)
print("all checks passed")
