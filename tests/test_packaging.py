"""
Checks that the three places a version is written agree, and that the rez
package describes what is actually in the repository.

A rez package whose version has drifted from the code it installs is the kind
of thing nobody notices until a rollback pulls the wrong build.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import bootycall  # noqa: E402

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


def rez_package() -> dict:
    """Evaluate package.py the way rez does: as plain Python."""
    namespace: dict = {}
    exec(compile((ROOT / "package.py").read_text(), "package.py", "exec"), namespace)
    return namespace


print("the rez package parses")
package = rez_package()
check("name", package.get("name") == "bootycall", str(package.get("name")))
check("has a version", bool(package.get("version")), str(package.get("version")))
check("has a description", bool(package.get("description")))
check("declares a build command", "rezbuild.py" in package.get("build_command", ""))
check("exposes the tool", package.get("tools") == ["bootycall"], str(package.get("tools")))
check("has a commands() hook", callable(package.get("commands")))

print("\nversions agree")
pyproject = (ROOT / "pyproject.toml").read_text()
pyproject_version = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
check(
    "package.py matches bootycall.__version__",
    package["version"] == bootycall.__version__,
    "%s vs %s" % (package["version"], bootycall.__version__),
)
check(
    "pyproject.toml matches too",
    pyproject_version == bootycall.__version__,
    "%s vs %s" % (pyproject_version, bootycall.__version__),
)

print("\nrequirements match what the code imports")
requires = " ".join(package.get("requires", []))
check("needs PySide6", "PySide6" in requires, requires)
check("needs a python", "python-" in requires, requires)
check(
    "does not claim to need rez",
    "rez" not in requires,
    "BootyCall shells out to rez and parses bootstraps with ast; it never "
    "imports rez, and saying otherwise would drag it into every resolve",
)

print("\ncommands() puts the payload on the right paths")
source = (ROOT / "package.py").read_text()
check("PYTHONPATH gets python/", 'env.PYTHONPATH.prepend("{root}/python")' in source)
check("PATH gets bin/", 'env.PATH.prepend("{root}/bin")' in source)

print("\nthe payload exists where the build script expects it")
build_source = (ROOT / "rezbuild.py").read_text()
payload = ast.literal_eval(
    re.search(r"^PAYLOAD = (\(.*?\))", build_source, re.M | re.S).group(1)
)
check("payload is python and bin", payload == ("python", "bin"), str(payload))
for name in payload:
    check("%s/ is in the repository" % name, (ROOT / name).is_dir())
check("the package module is under python/", (ROOT / "python" / "bootycall" / "__init__.py").is_file())
check("the entry point is under bin/", (ROOT / "bin" / "bootycall").is_file())
check(
    "tests are not shipped",
    "tests" not in payload,
    "installing the test suite into every rez resolve helps nobody",
)

print("\nthe entry point calls the app")
entry = (ROOT / "bin" / "bootycall").read_text()
check("imports main", "from bootycall.app import main" in entry)
check("exits with its return code", "sys.exit(main())" in entry)

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    raise SystemExit(1)
print("all packaging checks passed")
