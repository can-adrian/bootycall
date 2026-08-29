"""
Standalone probe: ask a show's bootstrap what it actually resolves.

This file is never imported by BootyCall. It is handed to a *separate* Python
interpreter -- one that can import ``rez`` and ``ilp_bootstrap`` -- and asked to
report on one bootstrap module::

    python probe_main.py /ice/shows/combat_2/.ilp/pipeline/bootstrap.py

The point is to stop guessing. BootyCall's static reader is fast and needs
nothing installed, but it can only see what is written literally in the file; a
bootstrap that computes a package list, or that a future ``ilp_bootstrap``
changes the meaning of, is beyond it. Running the real module answers the same
question the way the pipeline itself would.

That is also why this runs out of process: importing a bootstrap executes show
code, and show code has no business inside the UI's interpreter. If the import
explodes, takes forever, or leaks state, it takes a throwaway process with it
and BootyCall carries on with the static answer.

The report is a single JSON line on stdout, prefixed with a sentinel, because
imported show code is entirely within its rights to print things. Anything
without the prefix is noise and is ignored by the reader.

Deliberately written to run on old interpreters (no f-strings, no typing) --
the interpreter that can import rez is not necessarily a new one.
"""

from __future__ import print_function

import json
import os
import sys
import traceback

#: Prefix for the one line of output that matters. Also defined in probe.py.
SENTINEL = "BOOTYCALL-PROBE "


def _load_module(path):
    """Import ``path`` as a module, without putting it on ``sys.modules``."""
    name = "_bootycall_probe_target"

    # A bootstrap is normally imported by machinery that has already arranged
    # for its neighbours to be importable, so give it the same courtesy: its
    # own directory, then the show folder we were started in.
    for entry in (os.path.dirname(os.path.abspath(path)), os.getcwd()):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    if sys.version_info[0] >= 3:
        import importlib.util

        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load %s" % path)
        module = importlib.util.module_from_spec(spec)
        # Registered before execution: a bootstrap that imports itself, or that
        # relies on ``sys.modules`` during class body evaluation, would fail
        # otherwise.
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    import imp  # noqa: F401  (python 2 fallback)

    return imp.load_source(name, path)


def _candidate_classes(module):
    """Bootstrap classes to consider, best first.

    A show's bootstrap ends with ``ilp_bootstrap.Bootstrap = ProjectBootstrap``,
    so the installed package holds the authoritative answer after the import --
    including any subclassing the site does. The module's own namespace is the
    fallback for a bootstrap that does not perform that assignment.
    """
    out = []
    try:
        import ilp_bootstrap

        installed = getattr(ilp_bootstrap, "Bootstrap", None)
        if installed is not None:
            out.append(installed)
    except Exception:  # noqa: BLE001 - absence is a normal outcome here
        pass

    for value in vars(module).values():
        if isinstance(value, type) and hasattr(value, "packages"):
            if value not in out:
                out.append(value)
    return out


def _instance(cls):
    """The class, or an instance of it when one can be made cheaply.

    ``_get_show_packages`` is an instance method, so an instance is worth
    having; but a bootstrap whose ``__init__`` wants arguments is not worth
    failing the whole probe over.
    """
    try:
        return cls()
    except Exception:  # noqa: BLE001
        return cls


def _packages(obj):
    """``{tool: [request, ...]}`` from a bootstrap's ``packages`` mapping."""
    raw = getattr(obj, "packages", None)
    if not isinstance(raw, dict):
        raise TypeError("bootstrap has no usable 'packages' mapping")

    out = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, str):
            value = (value,)
        try:
            requests = [str(item) for item in value]
        except TypeError:
            continue
        out[key] = requests
    return out


def _show_packages(obj):
    """What ``_get_show_packages()`` adds to every resolve, if anything.

    Failure here is not failure of the probe: the package list is the valuable
    part, and a searcher that cannot reach a package root should not cost us
    that.
    """
    getter = getattr(obj, "_get_show_packages", None)
    if getter is None:
        return [], ""
    try:
        return [str(item) for item in (getter() or ())], ""
    except Exception as exc:  # noqa: BLE001
        return [], "%s: %s" % (type(exc).__name__, exc)


def probe(path):
    module = _load_module(path)

    errors = []
    for cls in _candidate_classes(module):
        obj = _instance(cls)
        try:
            packages = _packages(obj)
        except (TypeError, AttributeError) as exc:
            errors.append("%s: %s" % (getattr(cls, "__name__", cls), exc))
            continue
        if not packages:
            errors.append("%s: empty packages mapping" % getattr(cls, "__name__", cls))
            continue

        show_packages, show_error = _show_packages(obj)
        return {
            "ok": True,
            "class_name": getattr(cls, "__name__", ""),
            "packages": packages,
            "show_packages": show_packages,
            "show_packages_error": show_error,
            "path": os.path.abspath(path),
        }

    raise RuntimeError(
        "no bootstrap class with a packages mapping"
        + (" (%s)" % "; ".join(errors) if errors else "")
    )


def main(argv):
    if len(argv) != 2:
        print("usage: probe_main.py <bootstrap.py>", file=sys.stderr)
        return 2

    try:
        report = probe(argv[1])
    except Exception as exc:  # noqa: BLE001 - every failure is reportable data
        report = {
            "ok": False,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc(),
        }

    # One line, on stdout, behind the sentinel. Anything the imported module
    # printed is above it and is ignored by the reader.
    sys.stdout.write("\n" + SENTINEL + json.dumps(report) + "\n")
    sys.stdout.flush()
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
