"""Checks for the bootstrap probe: the runner, the reader, and the merge.

The probe's whole job is to be a better answer when it can be, and to be
harmless when it cannot -- so most of what is worth checking here is the
failure side: noisy imports, exploding imports, and interpreters that do not
exist must all leave the static read standing.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from bootycall import config, probe  # noqa: E402
from bootycall.discovery import apply_probe  # noqa: E402
from bootycall.parser import Bootstrap  # noqa: E402

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


tmp = Path(tempfile.mkdtemp(prefix="bootycall-probe-"))


def write(name: str, source: str) -> Path:
    path = tmp / name
    path.write_text(source, encoding="utf-8")
    return path


# A bootstrap that does not import rez, so the test can run anywhere. The probe
# does not care: it looks for a class with a packages mapping.
PLAIN = write(
    "plain_bootstrap.py",
    '''
class ProjectBootstrap(object):
    base = ("base-6",)
    packages = dict(
        maya=("maya-2026.3",) + base,
        nuke=("nuke-16.0",) + base,
    )

    # Computed at import time, which is exactly what a static read cannot see.
    packages["houdini"] = tuple("houdini-%s" % v for v in ("21.0",)) + base

    def _get_show_packages(self):
        return ("show_combat_2",)
''',
)

NOISY = write(
    "noisy_bootstrap.py",
    '''
import sys

print("loading the pipeline...")
print("a warning nobody asked for", file=sys.stderr)


class ProjectBootstrap(object):
    packages = {"maya": ("maya-2024",)}
''',
)

ANGRY = write(
    "angry_bootstrap.py",
    '''
raise RuntimeError("the site config is missing")
''',
)

EMPTY = write("empty_bootstrap.py", "x = 1\n")

SHOW_PKG_FAILS = write(
    "show_pkg_fails_bootstrap.py",
    '''
class ProjectBootstrap(object):
    packages = {"maya": ("maya-2024",)}

    def _get_show_packages(self):
        raise OSError("no such package root")
''',
)


print("running the probe")
plain = probe.run(PLAIN, cwd=tmp)
check("plain bootstrap read", plain.ok, plain.error)
check("class name reported", plain.class_name == "ProjectBootstrap", plain.class_name)
check("tools found", sorted(plain.packages) == ["houdini", "maya", "nuke"],
      str(sorted(plain.packages)))
check(
    "name reference expanded by the interpreter",
    plain.packages.get("maya") == ("maya-2026.3", "base-6"),
    str(plain.packages.get("maya")),
)
check(
    "computed entry seen",
    plain.packages.get("houdini") == ("houdini-21.0", "base-6"),
    str(plain.packages.get("houdini")),
)
check(
    "show packages reported",
    plain.show_packages == ("show_combat_2",),
    str(plain.show_packages),
)

print("\nnoise and failure")
noisy = probe.run(NOISY, cwd=tmp)
check("printing on import does not break the read", noisy.ok, noisy.error)
check("noisy tools", sorted(noisy.packages) == ["maya"], str(sorted(noisy.packages)))

angry = probe.run(ANGRY, cwd=tmp)
check("import failure is not ok", not angry.ok)
check("import failure names the error", "site config is missing" in angry.error,
      angry.error)

empty = probe.run(EMPTY, cwd=tmp)
check("module with no bootstrap class is not ok", not empty.ok)

partial = probe.run(SHOW_PKG_FAILS, cwd=tmp)
check(
    "a failing _get_show_packages still yields the package list",
    partial.ok and sorted(partial.packages) == ["maya"],
    partial.error,
)
check(
    "and says why the show packages are missing",
    "no such package root" in partial.detail,
    partial.detail,
)

print("\nunrunnable probe command")
saved = config.PROBE_COMMAND
config.PROBE_COMMAND = ("definitely-not-a-real-interpreter", "{script}", "{bootstrap}")
missing = probe.run(PLAIN, cwd=tmp)
config.PROBE_COMMAND = saved
check("missing interpreter is a note, not a crash", not missing.ok)
check("missing interpreter explains itself", "could not run" in missing.error,
      missing.error)

print("\nreading output")
check(
    "output without a sentinel is not ok",
    not probe.parse_output("hello\n", "traceback here\n").ok,
)
check(
    "the last sentinel line wins",
    probe.parse_output(
        probe.SENTINEL + '{"ok": false, "error": "first"}\n'
        + probe.SENTINEL + '{"ok": true, "packages": {"maya": ["maya-2024"]}}\n'
    ).packages
    == {"maya": ("maya-2024",)},
)
check(
    "unreadable json is a note, not a crash",
    "unreadable" in probe.parse_output(probe.SENTINEL + "{not json}\n").error,
)

print("\nmerging with the static read")
static = {"maya": ("maya-2024",), "gone": ("x-1",)}
merged, note = probe.merge(static, plain)
check("probe wins", merged == plain.packages, str(sorted(merged)))
check("note mentions the additions", "only the bootstrap knows" in note, note)
check("note mentions the disappearance", "not defined" in note, note)

same = probe.ProbeResult(ok=True, packages={"maya": ("maya-2024",)})
_merged, quiet = probe.merge({"maya": ("maya-2024",)}, same)
check("agreement says nothing", quiet == "", quiet)

failed = probe.ProbeResult(ok=False, error="nope")
kept, silent = probe.merge(static, failed)
check("a failed probe changes nothing", kept == static and silent == "")

print("\nfolding into a parsed bootstrap")
bs = Bootstrap(path=PLAIN, class_name="Guess", packages=dict(static),
               unresolved=("something",))
apply_probe(bs, plain)
check("source marked", bs.source == "bootstrap", bs.source)
check("packages replaced", bs.packages == plain.packages)
check("show packages carried over", bs.show_packages == ("show_combat_2",))
check("unresolved caveat dropped", bs.unresolved == (), str(bs.unresolved))
check("class name taken from the module", bs.class_name == "ProjectBootstrap",
      bs.class_name)

untouched = Bootstrap(path=PLAIN, packages=dict(static))
apply_probe(untouched, failed)
check("a failed probe leaves the static read alone",
      untouched.packages == static and untouched.source == "static")

print("\ncommand building")
argv = probe.command("/ice/shows/combat_2/.ilp/bootstrap.py")
check("script path substituted", str(probe.script_path()) in argv, str(argv))
check("bootstrap path substituted",
      "/ice/shows/combat_2/.ilp/bootstrap.py" in argv, str(argv))
check("probe script exists", probe.script_path().is_file(), str(probe.script_path()))

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all probe checks passed")
