"""
Checks for pinning a bootstrap to the versions a resolve produced.

No rez here. What matters is that the right string literals are found, that
the file comes out byte-identical everywhere else, and that the cases this
refuses stay refused.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from bootycall import pinning  # noqa: E402
from bootycall.parser import parse_source  # noqa: E402

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


SOURCE = '''\
"""A show bootstrap, near enough."""

from ilp_bootstrap import Bootstrap


class ProjectBootstrap(Bootstrap):

    base_package = "base-6"
    review_machine_name = "omg-05.ilpvfx.hq"

    mtoa_package = (
        "mtoa-5",
        # a comment that must survive
        'mtoa_base-9',
    )

    packages = dict(
        maya=("maya-2026", "rig_utils-1.7") + mtoa_package + (base_package,),
        nuke=("nuke-16.0", "rig_utils-1.7"),
    )
'''

RESOLVED = {
    "maya": ("2026.0.1", "/ice/rez/packages/int"),
    "rig_utils": ("1.7.8", "/ice/rez/packages/int"),
    "mtoa": ("5.4.2", "/ice/rez/packages/int"),
    "mtoa_base": ("9.1.0", "/ice/rez/packages/int"),
    "base": ("6.2.0", "/ice/rez/packages/int"),
    "nuke": ("16.0.3", "/ice/rez/packages/int"),
}

print("what the file actually asks for")
bootstrap = parse_source(SOURCE, "config.py")
requests = pinning.requests_in(bootstrap)
check(
    "every request in packages is in scope, from the groups too",
    sorted(requests)
    == ["base-6", "maya-2026", "mtoa-5", "mtoa_base-9", "nuke-16.0", "rig_utils-1.7"],
    str(sorted(requests)),
)
check(
    "and the hostname is not, because it is not in a package list -- which is "
    "the only reason needed, and does not depend on what it looks like",
    "omg-05.ilpvfx.hq" not in requests,
    str(requests),
)

print("\nwhat pinning would do")
pins = pinning.plan(bootstrap, RESOLVED)
by_name = {p.name: p for p in pins}
check(
    "a range becomes the version that resolved",
    by_name["rig_utils"].pinned == "rig_utils-1.7.8",
    by_name["rig_utils"].pinned,
)
check("and it counts as a change", by_name["rig_utils"].changes)
check(
    "every request comes back, pinned or not - a list of only the changes "
    "cannot be read for what is being left alone",
    len(pins) == len(requests),
    "%d of %d" % (len(pins), len(requests)),
)

_shallow = pinning.plan(bootstrap, RESOLVED, depth=2)
check(
    "a depth cuts the version to that many components",
    {p.name: p.pinned for p in _shallow}["maya"] == "maya-2026.0",
    str({p.name: p.pinned for p in _shallow}),
)
check(
    "a request that already names exactly that much is simply unchanged",
    {p.name: (p.pinned, p.blocked, p.changes) for p in _shallow}["nuke"]
    == ("nuke-16.0", "", False),
    str({p.name: (p.pinned, p.blocked, p.changes) for p in _shallow}["nuke"]),
)
# The real hazard: pinning a second time at a shallower depth. Somebody locked
# rig_utils to a patch last month; a dialog left on "feature" must not quietly
# hand those patches back.
_locked = parse_source(SOURCE.replace("rig_utils-1.7", "rig_utils-1.7.8"), "config.py")
_widened = {p.name: p for p in pinning.plan(_locked, RESOLVED, depth=2)}["rig_utils"]
check(
    "and one already pinned tighter is left exactly as it is",
    (_widened.pinned, _widened.blocked) == ("rig_utils-1.7.8", "already pinned tighter"),
    "%s / %s" % (_widened.pinned, _widened.blocked),
)
check("so nothing is ever widened by pinning it", not _widened.changes)

print("\nwhat pinning refuses")
_mine = dict(RESOLVED)
_mine["rig_utils"] = ("1.7.9", "/ice/rez/packages/local/adts/dev")
_refused = pinning.plan(
    bootstrap,
    _mine,
    own_roots=(("dev", "/ice/rez/packages/local/adts/dev"),),
)
_rig = {p.name: p for p in _refused}["rig_utils"]
check(
    "a version that only exists in your own root is not written",
    not _rig.changes and "only in your dev" in _rig.blocked,
    "%s / %s" % (_rig.pinned, _rig.blocked),
)
check(
    "and it still reports the version and where it came from, so the refusal "
    "can be read rather than just obeyed",
    _rig.version == "1.7.9" and _rig.root.endswith("adts/dev"),
    "%s %s" % (_rig.version, _rig.root),
)
_sibling = pinning.plan(
    bootstrap, RESOLVED, own_roots=(("dev", "/ice/rez/packages/local/adts/dev"),)
)
check(
    "a root that merely starts with the same characters is not yours",
    {p.name: p for p in _sibling}["rig_utils"].changes,
)

_missing = pinning.plan(bootstrap, {"maya": ("2026.0.1", "/ice/rez/packages/int")})
check(
    "a package this resolve never mentioned is left alone and says so",
    {p.name: p.blocked for p in _missing}["rig_utils"] == "not in this resolve",
    str({p.name: p.blocked for p in _missing}),
)

print("\nrewriting the file")
pinned_text, count = pinning.rewrite(SOURCE, pins)
check("something was written", count >= 6, str(count))
check(
    "the request is pinned where packages names it",
    '"rig_utils-1.7.8"' in pinned_text,
    pinned_text,
)
check(
    "and where a group names it, so the file cannot contradict itself",
    '"mtoa-5.4.2"' in pinned_text and "'mtoa_base-9.1.0'" in pinned_text,
    pinned_text,
)
check(
    "single quotes stay single - this is somebody's source file",
    "'mtoa_base-9.1.0'" in pinned_text and '"mtoa_base' not in pinned_text,
    pinned_text,
)
check(
    "the comment survives",
    "# a comment that must survive" in pinned_text,
    pinned_text,
)
check(
    "the hostname is untouched",
    '"omg-05.ilpvfx.hq"' in pinned_text,
    pinned_text,
)
check(
    "every line that had nothing to pin comes out byte-identical",
    [
        line
        for line in SOURCE.splitlines()
        if not any(r in line for r in ("rig_utils", "mtoa", "maya-", "nuke-", "base-6"))
    ]
    == [
        line
        for line in pinned_text.splitlines()
        if not any(
            r in line
            for r in ("rig_utils", "mtoa", "maya-", "nuke-", "base-6", "base-6.2.0")
        )
    ],
)
check(
    "and the result still parses as the same bootstrap",
    parse_source(pinned_text, "config.py").packages["maya"]
    == ("maya-2026.0.1", "rig_utils-1.7.8", "mtoa-5.4.2", "mtoa_base-9.1.0", "base-6.2.0"),
    str(parse_source(pinned_text, "config.py").packages["maya"]),
)
_again, _again_count = pinning.rewrite(
    pinned_text, pinning.plan(parse_source(pinned_text, "config.py"), RESOLVED)
)
check(
    "pinning an already-pinned file changes nothing, so running it per tool "
    "accumulates instead of fighting itself",
    _again == pinned_text and _again_count == 0,
    str(_again_count),
)
check(
    "nothing to pin leaves the source object itself alone",
    pinning.rewrite(SOURCE, []) == (SOURCE, 0),
)

print("\nthe backup beside an overwritten bootstrap")
_dir = Path(tempfile.mkdtemp(prefix="bootycall-pin-"))
_original = _dir / "config.py"
_original.write_text(SOURCE)
_first = pinning.backup_path(_original, "adts", date(2026, 9, 24))
check(
    "named for the file, the user and the day",
    _first.name == "config.py.adts.24092026",
    _first.name,
)
check("and beside the original", _first.parent == _original.parent)
_first.write_text(SOURCE)
_second = pinning.backup_path(_original, "adts", date(2026, 9, 24))
check(
    "a second pin on the same day does not write over the morning's backup",
    _second.name == "config.py.adts.24092026.2",
    _second.name,
)

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    raise SystemExit(1)
print("all pinning checks passed")
