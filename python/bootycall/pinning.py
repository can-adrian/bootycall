"""
Pin a bootstrap's package requests to the versions a resolve actually produced.

A show's bootstrap asks for ranges -- ``rig_utils-1.7`` means "any 1.7" -- and
that is what you want while a show is being built. It is not what you want when
it is being finished: a patch release lands upstream and the shot that rendered
on Tuesday resolves to something else on Thursday, with nothing in the show
saying what changed.

So: take what rez *actually* resolved and write those versions back into the
bootstrap's own strings. ``rig_utils-1.7`` becomes ``rig_utils-1.7.8``.

Three things this deliberately does not do.

It does not invent syntax. Every pin is written in the same ``name-range`` form
the file already uses, at a depth you choose. rez also has ``==`` for an exact
version, and it is not used here: a prefix range at full depth still admits a
deeper version if one is ever published, which is a smaller risk than writing a
form into a production bootstrap that nobody here has watched rez read.

It does not widen. A request that is already narrower than the pin would be --
somebody pinned it last month -- is left exactly as it is and reported. A
feature that quietly unlocked itself because a dialog defaulted to two
components is the opposite of what this is for.

It does not touch a string it cannot account for. Only literals whose value is
a request the parser found in ``packages`` are eligible, so a hostname that
happens to contain a hyphen is never in scope, whatever it looks like.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .local_packages import request_name, request_range

#: Version components, for trimming a resolved version to a pin depth. Only
#: dots: rez reads ``-`` inside a version as a token separator too, but no
#: bootstrap here pins below the dotted part and splitting there would make
#: ``1.7.8-beta`` trim to something nobody asked for.
_DOT = re.compile(r"\.")


@dataclass(frozen=True)
class Pin:
    """One request, and what pinning it would do."""

    name: str
    #: The request exactly as the file writes it.
    request: str
    #: What the resolve produced, and the root it came from.
    version: str = ""
    root: str = ""
    #: What would be written. Equal to ``request`` when nothing would change.
    pinned: str = ""
    #: Why this one is being left alone, when it is.
    blocked: str = ""

    @property
    def changes(self) -> bool:
        return bool(self.pinned) and self.pinned != self.request and not self.blocked


def trim(version: str, depth: int = 0) -> str:
    """``version`` cut to ``depth`` components. ``0`` keeps all of it."""
    if depth < 1:
        return version
    parts = _DOT.split(version)
    return ".".join(parts[:depth])


def pin_request(request: str, version: str, depth: int = 0) -> str:
    """``rig_utils-1.7`` and ``1.7.8`` -> ``rig_utils-1.7.8``."""
    name = request_name(request)
    if not name or not version:
        return request
    return "%s-%s" % (name, trim(version, depth))


def _depth_of(text: str) -> int:
    """How many components a version range names. ``""`` is zero."""
    text = text.strip()
    return len(_DOT.split(text)) if text else 0


def _under(path: str, root: str) -> bool:
    if not path or not root:
        return False
    try:
        return Path(path).resolve() == Path(root).resolve() or Path(
            root
        ).resolve() in Path(path).resolve().parents
    except OSError:
        return False


def requests_in(bootstrap) -> tuple[str, ...]:
    """Every request string the bootstrap's ``packages`` actually uses.

    Read off the parsed result rather than off the file, which is what keeps a
    string that merely looks like a request out of scope. If it is not in a
    package list the parser resolved, it is not a package request, whatever it
    is spelled like.
    """
    seen: dict[str, None] = {}
    for group in bootstrap.packages.values():
        for request in group:
            seen.setdefault(str(request), None)
    for request in getattr(bootstrap, "show_packages", ()) or ():
        seen.setdefault(str(request), None)
    return tuple(seen)


def plan(
    bootstrap,
    resolved: dict,
    depth: int = 0,
    own_roots: tuple = (),
) -> list[Pin]:
    """What pinning this bootstrap against ``resolved`` would do, per request.

    ``resolved`` is :attr:`ResolveProbe.resolved` -- name -> (version, root).
    ``own_roots`` are roots that belong to this user; a version that only
    exists in one of those is reported blocked, because a bootstrap pinned to
    it resolves on this machine and nowhere else, and a show bootstrap is the
    worst place in the building to find that out.

    Every request comes back, pinned or not. A dialog that lists only what it
    is about to change cannot be read for what it is about to leave alone.
    """
    pins: list[Pin] = []
    for request in requests_in(bootstrap):
        name = request_name(request)
        version, root = resolved.get(name, ("", ""))
        if not version:
            pins.append(
                Pin(
                    name=name,
                    request=request,
                    blocked="not in this resolve",
                )
            )
            continue

        mine = [label for label, path in own_roots if _under(root, path)]
        if mine:
            pins.append(
                Pin(
                    name=name,
                    request=request,
                    version=version,
                    root=root,
                    blocked="only in your %s packages" % mine[0],
                )
            )
            continue

        candidate = pin_request(request, version, depth)
        if _depth_of(request_range(candidate)) < _depth_of(request_range(request)):
            # Already pinned tighter than this would pin it. Writing the wider
            # range would unlock something somebody locked on purpose, which
            # is a strange thing for a button called Pin to do.
            pins.append(
                Pin(
                    name=name,
                    request=request,
                    version=version,
                    root=root,
                    pinned=request,
                    blocked="already pinned tighter",
                )
            )
            continue

        pins.append(
            Pin(
                name=name,
                request=request,
                version=version,
                root=root,
                pinned=candidate,
            )
        )
    return pins


def _offsets(source: str) -> list[int]:
    """Absolute offset of the start of each line, 1-indexed by ast's count."""
    offsets = [0, 0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def rewrite(source: str, pins) -> tuple[str, int]:
    """Apply ``pins`` to bootstrap ``source``. Returns the text and how many.

    Only the string literal's own characters are replaced -- ``ast`` gives the
    span -- so comments, blank lines, quote style and the rest of the file come
    out byte-identical. A show's bootstrap is somebody's source file and
    reformatting it would be a change nobody asked for.

    Every occurrence of a request is rewritten, not the first: a bootstrap
    routinely lists the same package in two groups, and pinning one of them
    would produce a file that contradicts itself.
    """
    wanted = {p.request: p.pinned for p in pins if p.changes}
    if not wanted:
        return source, 0

    tree = ast.parse(source)
    starts = _offsets(source)
    edits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        replacement = wanted.get(node.value)
        if replacement is None:
            continue
        begin = starts[node.lineno] + node.col_offset
        end = starts[node.end_lineno] + node.end_col_offset
        literal = source[begin:end]
        quote = literal[0] if literal[:1] in ("'", '"') else '"'
        if literal[:3] in ('"""', "'''"):
            # A triple-quoted request is not something any bootstrap writes,
            # and guessing at the quoting would be the one edit that silently
            # breaks the file.
            continue
        edits.append((begin, end, "%s%s%s" % (quote, replacement, quote)))

    # Back to front, so an earlier edit cannot move a later span.
    edits.sort(reverse=True)
    text = source
    for begin, end, replacement in edits:
        text = text[:begin] + replacement + text[end:]
    return text, len(edits)


def backup_path(original: Path | str, user: str, when: date | None = None) -> Path:
    """Where the untouched original goes when a bootstrap is overwritten.

    ``config.py`` -> ``config.py.adts.24092026``, beside it. Numbered if that
    name is taken: pinning twice in one day is ordinary, and quietly writing
    over this morning's backup with this afternoon's is the one mistake here
    that cannot be undone.
    """
    original = Path(original)
    stamp = (when or date.today()).strftime("%d%m%Y")
    candidate = original.with_name("%s.%s.%s" % (original.name, user, stamp))
    suffix = 2
    while candidate.exists():
        candidate = original.with_name(
            "%s.%s.%s.%d" % (original.name, user, stamp, suffix)
        )
        suffix += 1
    return candidate
