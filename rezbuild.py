"""
Build script for the rez package.

There is nothing to compile -- BootyCall is pure Python -- so a build is a copy
of the payload into the build directory, and an install is the same copy into
the install directory. Both are done here rather than in a Makefile so the
package builds identically on any workstation with Python and no other tooling.

Invoked by rez as ``python {root}/rezbuild.py {install}``; the ``install``
argument is present only on ``rez-build --install``.
"""

from __future__ import annotations

import os
import shutil
import sys

#: Directories copied into the package. Tests, screenshots and packaging
#: metadata stay in the repository -- they are not part of what gets installed.
PAYLOAD = ("python", "bin")


def _copy_tree(source: str, destination: str) -> None:
    if not os.path.isdir(source):
        return
    if os.path.isdir(destination):
        # A rebuild into a dirty directory would leave files from the previous
        # build behind, which is how a deleted module keeps working locally and
        # breaks for everyone else.
        shutil.rmtree(destination)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def build(source_path: str, build_path: str, install_path: str, targets) -> None:
    for name in PAYLOAD:
        _copy_tree(os.path.join(source_path, name), os.path.join(build_path, name))

    if "install" in targets:
        for name in PAYLOAD:
            _copy_tree(
                os.path.join(source_path, name), os.path.join(install_path, name)
            )
        _make_executable(os.path.join(install_path, "bin", "bootycall"))


def _make_executable(path: str) -> None:
    if not os.path.isfile(path):
        return
    mode = os.stat(path).st_mode
    os.chmod(path, mode | 0o111)


if __name__ == "__main__":
    build(
        source_path=os.environ["REZ_BUILD_SOURCE_PATH"],
        build_path=os.environ["REZ_BUILD_PATH"],
        install_path=os.environ["REZ_BUILD_INSTALL_PATH"],
        targets=sys.argv[1:],
    )
