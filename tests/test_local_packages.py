"""Checks for local dev package discovery and override detection."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

os.environ["BOOTYCALL_LOCAL_PACKAGES_ROOT"] = "/tmp/ice/rez/packages/local/{user}"
os.environ["BOOTYCALL_REZ_USER"] = "adrian"

import importlib  # noqa: E402

from bootycall import local_packages as lp  # noqa: E402

importlib.reload(lp)

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


print("root resolution")
check("user honoured", lp.current_user() == "adrian", lp.current_user())
check(
    "local root",
    str(lp.local_root()) == "/tmp/ice/rez/packages/local/adrian",
    str(lp.local_root()),
)
check(
    "dev root sits inside it",
    str(lp.dev_root()) == "/tmp/ice/rez/packages/local/adrian/dev",
    str(lp.dev_root()),
)
check(
    "template substitutes any user",
    str(lp.local_root("someone_else")).endswith("/local/someone_else"),
    str(lp.local_root("someone_else")),
)

print("\nlocal root scan skips the nested dev root")
local = lp.list_local_packages(lp.local_root())
local_requests = [p.request for p in local]
check(
    "four local packages",
    sorted(local_requests)
    == ["houdini_utils-6.0.5", "maya_utils-3.2.0", "my_local_tool-1.0.0", "nuke_plugins-4.1.0"],
    str(local_requests),
)
check(
    "no package called 'dev'",
    not any(p.name == "dev" for p in local),
    str(local_requests),
)
check(
    "'dev' is skipped by default, no argument needed",
    not any(p.name == "dev" for p in lp.list_local_packages(lp.local_root())),
)
check(
    "without the blacklist it would mis-read dev as a package",
    any(p.name == "dev" for p in lp.list_local_packages(lp.local_root(), exclude=())),
    "the reserved name is load-bearing, not decoration",
)
check(
    "the dev root is scanned with the same rule and is unaffected",
    len(lp.list_local_packages(lp.dev_root())) == 8,
)

print("\ndev root scan")
packages = lp.list_local_packages(lp.dev_root())
requests = [p.request for p in packages]
check("found the expected set", len(packages) == 8, str(requests))
check("dotfile dir skipped", not any(p.name.startswith(".") for p in packages))
check(
    "version dir without a definition skipped",
    "nuke_utils-build_tmp" not in requests,
    str(requests),
)
check("yaml definition accepted", "yaml_pkg-1.0.0" in requests, str(requests))
check(
    "unversioned package uses bare name",
    "scratch_tool" in requests,
    str(requests),
)

print("\nordering")
nuke_versions = [p.version for p in packages if p.name == "nuke_utils"]
check(
    "newest version first, numeric-aware (4.10 before 4.9)",
    nuke_versions == ["4.10.0", "4.9.0", "4.2.1"],
    str(nuke_versions),
)
names = [p.name for p in packages]
check(
    "names grouped and alphabetical",
    names == sorted(names, key=str.lower) or names == list(dict.fromkeys(names)) + [],
    str(names),
)
check(
    "each name contiguous",
    len(list(dict.fromkeys(names))) == len({n for n in names}),
    str(names),
)
check("first name is axiom", names[0] == "axiom", str(names))

print("\ndefinition file recorded")
scratch = next(p for p in packages if p.name == "scratch_tool")
check("definition filename", scratch.definition == "package.py", scratch.definition)
check("path points at the package dir", scratch.path.name == "scratch_tool")
yaml_pkg = next(p for p in packages if p.name == "yaml_pkg")
check("yaml definition filename", yaml_pkg.definition == "package.yaml", yaml_pkg.definition)

print("\nrequest name parsing")
check("versioned", lp.request_name("nuke_utils-4") == "nuke_utils")
check("dotted version", lp.request_name("point_render-1.3") == "point_render")
check("year version", lp.request_name("maya-2026.3") == "maya")
check("bare name", lp.request_name("prep_utils") == "prep_utils")

print("\noverride detection")
nuke_resolve = ("nuke-16.0", "base-6", "nuke_utils-4", "nuke_plugins-4", "cattery-1")
hits = lp.shadowed_requests(packages, nuke_resolve)
check("nuke_utils flagged", hits.get("nuke_utils") == "nuke_utils-4", str(hits))
check("only the overlap", set(hits) == {"nuke_utils"}, str(hits))

houdini_resolve = ("houdini-21.0", "houdini_utils-6", "axiom-3")
hits = lp.shadowed_requests(packages, houdini_resolve)
check(
    "two overlaps found",
    set(hits) == {"houdini_utils", "axiom"},
    str(hits),
)
check(
    "version mismatch still counts (dev 6.1.0 vs request 6)",
    hits["houdini_utils"] == "houdini_utils-6",
    str(hits),
)

check("empty resolve, no hits", lp.shadowed_requests(packages, ()) == {})
check("no local packages, no hits", lp.shadowed_requests([], nuke_resolve) == {})
check(
    "unrelated dev package never matches",
    "my_experiment" not in lp.shadowed_requests(packages, nuke_resolve),
)

print("\nthe same name can live in both roots")
both = {p.name for p in local} & {p.name for p in packages}
check("houdini_utils is in both", both == {"houdini_utils"}, str(both))
check(
    "with different versions",
    next(p for p in local if p.name == "houdini_utils").version == "6.0.5"
    and next(p for p in packages if p.name == "houdini_utils").version == "6.1.0",
)

print("\ndeleting a package from disk")
import shutil as _shutil  # noqa: E402

sandbox = Path(tempfile.mkdtemp(prefix="bootycall-del-"))
def _make(rel):
    d = sandbox / rel
    d.mkdir(parents=True)
    (d / "package.py").write_text("name = 'x'\n")
    return d

_make("keeper/1.0.0")
_make("doomed/1.0.0")
_make("doomed/2.0.0")
found = lp.list_local_packages(sandbox)
check("three to start", len(found) == 3, str([p.request for p in found]))

one = next(p for p in found if p.name == "doomed" and p.version == "1.0.0")
check("delete succeeds", lp.delete_package(one, sandbox) == "")
check("the version directory is gone", not (sandbox / "doomed" / "1.0.0").exists())
check("the sibling version survives", (sandbox / "doomed" / "2.0.0").exists())
check("the name directory survives while it still has versions", (sandbox / "doomed").exists())

two = next(p for p in lp.list_local_packages(sandbox) if p.name == "doomed")
check("delete the last version", lp.delete_package(two, sandbox) == "")
check(
    "the now-empty name directory is pruned, not left looking like a package",
    not (sandbox / "doomed").exists(),
)
check("other packages untouched", [p.request for p in lp.list_local_packages(sandbox)] == ["keeper-1.0.0"])

print("\ndeletion refuses anything outside the root")
outside_dir = Path(tempfile.mkdtemp(prefix="bootycall-outside-"))
(outside_dir / "package.py").write_text("name = 'x'\n")
outside = lp.LocalPackage(name="x", version="", path=outside_dir)
err = lp.delete_package(outside, sandbox)
check("refused", "not inside" in err, err)
check("and it is still there", outside_dir.exists())

err = lp.delete_package(lp.LocalPackage(name="r", version="", path=sandbox), sandbox)
check("the root itself is refused", "not inside" in err, err)
check("root still there", sandbox.exists())

print("\nsymlinked packages are refused, not followed")
real = Path(tempfile.mkdtemp(prefix="bootycall-real-"))
(real / "package.py").write_text("name = 'x'\n")
link = sandbox / "linked"
try:
    link.symlink_to(real, target_is_directory=True)
except OSError:
    check("symlink refused", True, "(skipped: cannot create symlinks here)")
else:
    err = lp.delete_package(lp.LocalPackage(name="linked", version="", path=link), sandbox)
    check("symlink refused", "symlink" in err, err)
    check("the target it pointed at is untouched", (real / "package.py").exists())
    link.unlink()

print("\ndeleting something already gone reports rather than raising")
ghost = lp.LocalPackage(name="ghost", version="1", path=sandbox / "ghost" / "1")
err = lp.delete_package(ghost, sandbox)
check("reported", "no longer there" in err or "not inside" in err, err)

_shutil.rmtree(sandbox, ignore_errors=True)
_shutil.rmtree(real, ignore_errors=True)
_shutil.rmtree(outside_dir, ignore_errors=True)

print("\nmissing root is not an error")
missing = Path(tempfile.mkdtemp(prefix="bootycall-local-")) / "nope" / "dev"
check("empty list", lp.list_local_packages(missing) == [])

print("\nempty root")
empty = Path(tempfile.mkdtemp(prefix="bootycall-empty-"))
check("empty list", lp.list_local_packages(empty) == [])

print("\nunreadable root raises")
locked = Path(tempfile.mkdtemp(prefix="bootycall-locked-"))
(locked / "pkg").mkdir()
os.chmod(locked, 0o000)
try:
    lp.list_local_packages(locked)
except lp.LocalPackagesUnavailable:
    check("raises LocalPackagesUnavailable", True)
except Exception as exc:  # noqa: BLE001
    check("raises LocalPackagesUnavailable", False, type(exc).__name__)
else:
    # Running as root defeats the permission bit; not a real failure.
    check("raises LocalPackagesUnavailable", True, "(skipped: running as root)")
finally:
    os.chmod(locked, 0o755)

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    raise SystemExit(1)
print("all local-package checks passed")
