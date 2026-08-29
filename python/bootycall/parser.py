"""
Static parser for pipeline bootstrap modules.

A show's bootstrap is a Python module that subclasses ``ilp_bootstrap.Bootstrap``
and declares a class-level ``packages`` dict mapping a tool name to a tuple of
rez package requests, e.g.::

    class ProjectBootstrap(Bootstrap):
        base_package = "base-6"
        maya_package = ("maya-2026.3", base_package, "maya_base-7")
        mtoa_package = ("mtoa-5", "mtoa_base-9")

        packages = dict(
            maya=maya_package + mtoa_package,
            ...
        )

        packages["obj2abc"] = packages["maya"]

We read this with :mod:`ast` rather than importing it. Importing would execute
show code and would require ``rez`` and ``ilp_bootstrap`` to be importable in
the UI's own interpreter -- neither is true, and neither should be needed just
to draw a list of buttons.

Supported constructs: string constants, tuple/list literals, name references to
earlier class attributes, ``+`` concatenation of any of those, ``dict(...)``
calls, dict literals, and ``packages[key] = packages[other]`` aliasing.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


class BootstrapParseError(Exception):
    """Raised when a bootstrap module cannot be understood."""


@dataclass
class Bootstrap:
    """The interesting parts of a parsed bootstrap module."""

    path: Path
    class_name: str = ""
    #: tool name -> tuple of rez package requests
    packages: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: class attribute name -> resolved value (tuple of requests, or string)
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: scalar class attributes such as ``review_machine_name``
    scalars: dict[str, str] = field(default_factory=dict)
    #: names that appear in the source but could not be statically resolved
    unresolved: tuple[str, ...] = ()
    #: Where ``packages`` came from: ``static`` (this parser) or ``bootstrap``
    #: (the module itself, via :mod:`bootycall.probe`). Displayed, so that a
    #: list read from a running import is never mistaken for a guess.
    source: str = "static"
    #: Requests the bootstrap adds to every resolve, from ``_get_show_packages``.
    #: Only the probe can know these; the static reader leaves it empty and
    #: BootyCall falls back to looking for the package on disk itself.
    show_packages: tuple[str, ...] = ()

    def tools(self) -> tuple[str, ...]:
        return tuple(sorted(self.packages))


# ---------------------------------------------------------------------------
# Value resolution
# ---------------------------------------------------------------------------


class _Unresolved(Exception):
    """Internal: a node could not be reduced to a literal."""


class _Resolver:
    def __init__(self) -> None:
        self.env: dict[str, object] = {}
        self.packages: dict[str, tuple[str, ...]] = {}
        self.misses: list[str] = []

    # -- node evaluation ---------------------------------------------------

    def eval(self, node: ast.AST) -> object:
        """Reduce ``node`` to a str, a tuple of str, or raise ``_Unresolved``."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return node.value
            raise _Unresolved(repr(node.value))

        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            out: list[str] = []
            for element in node.elts:
                out.extend(self._as_sequence(self.eval(element)))
            return tuple(out)

        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.env[node.id]
            raise _Unresolved(node.id)

        if isinstance(node, ast.Attribute):
            # e.g. ProjectBootstrap.review_machine_name
            if node.attr in self.env:
                return self.env[node.attr]
            raise _Unresolved(node.attr)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._as_sequence(self.eval(node.left))
            right = self._as_sequence(self.eval(node.right))
            return tuple(left) + tuple(right)

        if isinstance(node, ast.Subscript):
            return self._eval_subscript(node)

        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "dict":
                return self._eval_dict_call(node)
            if name == "tuple":
                if not node.args:
                    return ()
                return tuple(self._as_sequence(self.eval(node.args[0])))
            raise _Unresolved(name or "call")

        if isinstance(node, ast.Dict):
            mapping: dict[str, tuple[str, ...]] = {}
            for key_node, value_node in zip(node.keys, node.values):
                if key_node is None:
                    continue
                key = self.eval(key_node)
                if not isinstance(key, str):
                    continue
                mapping[key] = tuple(self._as_sequence(self.eval(value_node)))
            return mapping

        raise _Unresolved(type(node).__name__)

    def _eval_subscript(self, node: ast.Subscript) -> object:
        base = node.value
        index = node.slice
        if isinstance(index, ast.Index):  # Python < 3.9 compatibility
            index = index.value  # type: ignore[attr-defined]
        key = self.eval(index)
        if not isinstance(key, str):
            raise _Unresolved("subscript")
        if isinstance(base, ast.Name) and base.id == "packages":
            if key in self.packages:
                return self.packages[key]
            raise _Unresolved("packages[%s]" % key)
        container = self.eval(base)
        if isinstance(container, dict) and key in container:
            return container[key]
        raise _Unresolved("subscript")

    def _eval_dict_call(self, node: ast.Call) -> dict[str, tuple[str, ...]]:
        mapping: dict[str, tuple[str, ...]] = {}
        for arg in node.args:  # dict(other_mapping)
            value = self.eval(arg)
            if isinstance(value, dict):
                mapping.update(value)
        for keyword in node.keywords:
            if keyword.arg is None:  # dict(**other)
                value = self.eval(keyword.value)
                if isinstance(value, dict):
                    mapping.update(value)
                continue
            try:
                mapping[keyword.arg] = tuple(
                    self._as_sequence(self.eval(keyword.value))
                )
            except _Unresolved as exc:
                self.misses.append("%s (%s)" % (keyword.arg, exc))
        return mapping

    @staticmethod
    def _as_sequence(value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        raise _Unresolved(type(value).__name__)

    # -- statement walking -------------------------------------------------

    def visit_body(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                self._visit_assign(stmt)
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                self._visit_single_target(stmt.target, stmt.value)

    def _visit_assign(self, stmt: ast.Assign) -> None:
        for target in stmt.targets:
            self._visit_single_target(target, stmt.value)

    def _visit_single_target(self, target: ast.expr, value_node: ast.expr) -> None:
        # packages["das-element"] = packages["das_element"]
        if isinstance(target, ast.Subscript):
            base = target.value
            index = target.slice
            if isinstance(index, ast.Index):  # Python < 3.9
                index = index.value  # type: ignore[attr-defined]
            if isinstance(base, ast.Name) and base.id == "packages":
                try:
                    key = self.eval(index)
                    value = self.eval(value_node)
                except _Unresolved:
                    return
                if isinstance(key, str):
                    self.packages[key] = tuple(self._as_sequence(value))
            return

        if not isinstance(target, ast.Name):
            return

        name = target.id
        try:
            value = self.eval(value_node)
        except _Unresolved as exc:
            self.misses.append("%s (%s)" % (name, exc))
            return

        self.env[name] = value
        if name == "packages" and isinstance(value, dict):
            self.packages.update(value)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def parse_source(source: str, path: Path | str = "<string>") -> Bootstrap:
    """Parse bootstrap ``source`` into a :class:`Bootstrap`."""
    path = Path(path)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise BootstrapParseError("%s: %s" % (path.name, exc)) from exc

    resolver = _Resolver()
    class_name = ""

    # Module-level assignments first, so a class body can reference them.
    resolver.visit_body([s for s in tree.body if not isinstance(s, ast.ClassDef)])

    for stmt in tree.body:
        if not isinstance(stmt, ast.ClassDef):
            continue
        base_names = {
            getattr(b, "id", None) or getattr(b, "attr", None) for b in stmt.bases
        }
        if "Bootstrap" not in base_names:
            continue
        class_name = stmt.name
        resolver.visit_body(stmt.body)
        break

    if not class_name:
        # No Bootstrap subclass -- fall back to whatever the module declared.
        resolver.visit_body(tree.body)

    if not resolver.packages:
        raise BootstrapParseError("no 'packages' mapping found in %s" % path.name)

    groups: dict[str, tuple[str, ...]] = {}
    scalars: dict[str, str] = {}
    for key, value in resolver.env.items():
        if key == "packages":
            continue
        if isinstance(value, str):
            scalars[key] = value
        elif isinstance(value, tuple):
            groups[key] = value

    return Bootstrap(
        path=path,
        class_name=class_name,
        packages=dict(resolver.packages),
        groups=groups,
        scalars=scalars,
        unresolved=tuple(dict.fromkeys(resolver.misses)),
    )


def parse_file(path: Path | str) -> Bootstrap:
    """Parse the bootstrap module at ``path``."""
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise BootstrapParseError("cannot read %s: %s" % (path, exc)) from exc
    return parse_source(source, path)
