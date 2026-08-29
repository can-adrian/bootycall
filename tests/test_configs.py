"""Checks for the saved-setup store."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from bootycall.configs import ConfigStore, SavedConfig  # noqa: E402

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


tmp = Path(tempfile.mkdtemp(prefix="bootycall-cfg-"))
path = tmp / "nested" / "configs.json"

print("empty store")
store = ConfigStore(path)
check("starts empty", len(store) == 0)
check("no error for missing file", store.load_error == "")
check("file not created until a save", not path.exists())

print("\nadd + persist")
check(
    "add succeeds",
    store.add(SavedConfig("Nightly comp", "batman_returns", "nuke", "nuke16")) == "",
)
check("parent dirs created", path.exists())
check("length", len(store) == 1)
check("created stamped", bool(store.get("Nightly comp").created))

store.add(SavedConfig("FX lookdev", "dune_pt3", "houdini", "houdinifx"))
store.add(SavedConfig("Anim", "combat_2", "maya", "maya"))
check("three saved", len(store) == 3)
check(
    "insertion order preserved",
    store.names() == ["Nightly comp", "FX lookdev", "Anim"],
    str(store.names()),
)

print("\nreload from disk")
reloaded = ConfigStore(path)
check("all three read back", len(reloaded) == 3)
check("order survives", reloaded.names() == store.names(), str(reloaded.names()))
first = reloaded.get("Nightly comp")
check("show round-trips", first.show == "batman_returns")
check("dcc round-trips", first.dcc == "nuke")
check("tool round-trips", first.tool == "nuke16")
check("summary", first.summary == "batman_returns - nuke16", first.summary)

print("\non-disk shape")
raw = json.loads(path.read_text())
check("versioned", raw.get("version") == 1, str(raw.get("version")))
check("configs is a list", isinstance(raw.get("configs"), list))

print("\nreplace by name keeps position")
store.add(SavedConfig("FX lookdev", "dune_pt3", "houdini", "prmanfx"))
check("no duplicate", len(store) == 3)
check(
    "position held",
    store.names() == ["Nightly comp", "FX lookdev", "Anim"],
    str(store.names()),
)
check("value replaced", store.get("FX lookdev").tool == "prmanfx")

print("\nremove")
check("remove succeeds", store.remove("FX lookdev") == "")
check("length drops", len(store) == 2)
check("gone", store.get("FX lookdev") is None)
check("removing a missing name is a no-op", store.remove("nope") == "")
check("still two", len(store) == 2)
check("removal persisted", len(ConfigStore(path)) == 2)

print("\nsuggested names avoid collisions")
fresh = ConfigStore(tmp / "fresh.json")
check("plain suggestion", fresh.suggest_name("dune_pt3", "Nuke 16.0") == "dune_pt3 - Nuke 16.0")
fresh.add(SavedConfig("dune_pt3 - Nuke 16.0", "dune_pt3", "nuke", "nuke16"))
check(
    "collision numbered",
    fresh.suggest_name("dune_pt3", "Nuke 16.0") == "dune_pt3 - Nuke 16.0 (2)",
    fresh.suggest_name("dune_pt3", "Nuke 16.0"),
)
fresh.add(SavedConfig("dune_pt3 - Nuke 16.0 (2)", "dune_pt3", "nuke", "nuke16"))
check(
    "second collision numbered",
    fresh.suggest_name("dune_pt3", "Nuke 16.0") == "dune_pt3 - Nuke 16.0 (3)",
)

print("\ncorrupt file degrades quietly")
bad = tmp / "bad.json"
bad.write_text("{ not json at all")
broken = ConfigStore(bad)
check("empty rather than raising", len(broken) == 0)
check("reason recorded", "Could not read" in broken.load_error, broken.load_error)

wrong = tmp / "wrong.json"
wrong.write_text(json.dumps({"version": 1, "configs": "nope"}))
odd = ConfigStore(wrong)
check("non-list configs handled", len(odd) == 0)
check("reason recorded", "Unexpected contents" in odd.load_error, odd.load_error)

print("\npartial entries are dropped, good ones kept")
mixed = tmp / "mixed.json"
mixed.write_text(
    json.dumps(
        {
            "version": 1,
            "configs": [
                {"name": "good", "show": "s", "dcc": "nuke", "tool": "nuke16"},
                {"name": "missing tool", "show": "s", "dcc": "nuke"},
                {"name": "", "show": "s", "dcc": "nuke", "tool": "nuke16"},
                "not a dict",
                {"name": "good", "show": "dup", "dcc": "maya", "tool": "maya"},
            ],
        }
    )
)
partial = ConfigStore(mixed)
check("only the valid one kept", partial.names() == ["good"], str(partial.names()))
check("first duplicate wins", partial.get("good").show == "s")
check("no load error for droppable rows", partial.load_error == "")

print("\nbare list (hand-edited file) is accepted")
legacy = tmp / "legacy.json"
legacy.write_text(
    json.dumps([{"name": "a", "show": "s", "dcc": "maya", "tool": "maya"}])
)
check("bare list read", ConfigStore(legacy).names() == ["a"])

print("\nreorder")
order = ConfigStore(tmp / "order.json")
for n in ("a", "b", "c"):
    order.add(SavedConfig(n, "s", "nuke", "nuke16"))
check("move down", order.move("a", 1) == "" and order.names() == ["b", "a", "c"], str(order.names()))
check("move up", order.move("a", -1) == "" and order.names() == ["a", "b", "c"], str(order.names()))
check("past the top is a no-op", order.move("a", -1) == "" and order.names() == ["a", "b", "c"])
check("past the bottom is a no-op", order.move("c", 1) == "" and order.names() == ["a", "b", "c"])
check("unknown name reports", "No favourite named" in order.move("ghost", 1))
check("order persisted", ConfigStore(tmp / "order.json").names() == ["a", "b", "c"])

print("\nrename")
check("renames in place", order.rename("b", "bee") == "" and order.names() == ["a", "bee", "c"], str(order.names()))
check("fields carried over", order.get("bee").show == "s" and order.get("bee").tool == "nuke16")
check("created stamp kept", bool(order.get("bee").created))
check("collision refused", "already exists" in order.rename("bee", "a"))
check("blank refused", "needs a name" in order.rename("bee", "  "))
check("unknown refused", "No favourite named" in order.rename("ghost", "x"))
check("no-op rename is fine", order.rename("bee", "bee") == "")
check("still three", len(order) == 3)
check("rename persisted", ConfigStore(tmp / "order.json").names() == ["a", "bee", "c"])

print("\nvisible-software preference")
prefs = ConfigStore(tmp / "prefs.json")
check("unset reads as None, not empty", prefs.visible_software() is None)
check("set persists", prefs.set_visible_software(["maya", "nuke"]) == "")
check("round-trips", ConfigStore(tmp / "prefs.json").visible_software() == ("maya", "nuke"))
check("duplicates collapsed", prefs.set_visible_software(["maya", "maya", "nuke"]) == "" and prefs.visible_software() == ("maya", "nuke"))
check(
    "empty list is a real answer, distinct from unset",
    prefs.set_visible_software([]) == "" and ConfigStore(tmp / "prefs.json").visible_software() == (),
)
check("None clears back to unset", prefs.set_visible_software(None) == "" and ConfigStore(tmp / "prefs.json").visible_software() is None)

prefs.add(SavedConfig("keep me", "s", "nuke", "nuke16"))
prefs.set_visible_software(["maya"])
again = ConfigStore(tmp / "prefs.json")
check("preferences and configs share the file", again.names() == ["keep me"] and again.visible_software() == ("maya",))
check("old files without a preferences key still load", ConfigStore(legacy).visible_software() is None)
check("junk preference value ignored", True)
junk = tmp / "junk.json"
junk.write_text(json.dumps({"version": 1, "configs": [], "preferences": {"visible_software": "nope"}}))
check("non-list preference reads as unset", ConfigStore(junk).visible_software() is None)

print("\npinned shows")
pins = ConfigStore(tmp / "pins.json")
check("none by default", pins.pinned_shows() == ())
check("no selection by default", pins.selected_show() is None)
check("set persists", pins.set_pinned_shows(["a", "b"]) == "" and ConfigStore(tmp / "pins.json").pinned_shows() == ("a", "b"))
check("order kept", ConfigStore(tmp / "pins.json").pinned_shows() == ("a", "b"))
check("duplicates collapsed", pins.set_pinned_shows(["a", "a", "b"]) == "" and pins.pinned_shows() == ("a", "b"))
check("selection persists", pins.set_selected_show("b") == "" and ConfigStore(tmp / "pins.json").selected_show() == "b")
check("selection can be cleared", pins.set_selected_show(None) == "" and ConfigStore(tmp / "pins.json").selected_show() is None)
check("empty string is not a selection", pins.set_selected_show("") == "" and pins.selected_show() is None)
check("emptying the pins is allowed", pins.set_pinned_shows([]) == "" and ConfigStore(tmp / "pins.json").pinned_shows() == ())
badpins = tmp / "badpins.json"
badpins.write_text(json.dumps({"version": 1, "configs": [], "preferences": {"pinned_shows": "nope", "selected_show": 7}}))
check("junk pins ignored", ConfigStore(badpins).pinned_shows() == ())
check("junk selection ignored", ConfigStore(badpins).selected_show() is None)

print("\npath overrides")
paths = ConfigStore(tmp / "paths.json")
check("none by default", paths.path_overrides() == {})
check("set persists", paths.set_path_overrides({"shows_root": "/mnt/shows"}) == "")
check("round-trips", ConfigStore(tmp / "paths.json").path_overrides() == {"shows_root": "/mnt/shows"})
check("None clears", paths.set_path_overrides(None) == "" and ConfigStore(tmp / "paths.json").path_overrides() == {})
check("empty dict clears too", paths.set_path_overrides({}) == "" and paths.path_overrides() == {})
paths.set_path_overrides({"shows_root": "/a", "local_root": "  ", "junk": "/b"})
check("blank values dropped on read", "local_root" not in paths.path_overrides(), str(paths.path_overrides()))
badpaths = tmp / "badpaths.json"
badpaths.write_text(json.dumps({"version": 1, "configs": [], "preferences": {"paths": "nope"}}))
check("junk ignored", ConfigStore(badpaths).path_overrides() == {})

print("\nUI state saved on launch")
ui = ConfigStore(tmp / "ui.json")
check("nothing to begin with", ui.selected_dcc() is None and ui.variants() == {})
check(
    "one call writes all three",
    ui.save_ui_state("batman_returns", "nuke", {"nuke": "nuke16", "maya": "maya_ziva"}) == "",
)
back = ConfigStore(tmp / "ui.json")
check("show", back.selected_show() == "batman_returns", str(back.selected_show()))
check("software", back.selected_dcc() == "nuke", str(back.selected_dcc()))
check("variants", back.variants() == {"nuke": "nuke16", "maya": "maya_ziva"}, str(back.variants()))
check("clearing works", ui.save_ui_state(None, None, None) == "" and ConfigStore(tmp / "ui.json").selected_dcc() is None)
check("compact off by default", ui.compact() is False)
check(
    "compact round-trips",
    ui.save_ui_state("s", "nuke", {"nuke": "nuke16"}, compact=True) == ""
    and ConfigStore(tmp / "ui.json").compact() is True,
)
check(
    "and clears",
    ui.save_ui_state("s", "nuke", {"nuke": "nuke16"}) == ""
    and ConfigStore(tmp / "ui.json").compact() is False,
)
badui = tmp / "badui.json"
badui.write_text(json.dumps({"version": 1, "configs": [], "preferences": {"selected_dcc": 7, "variants": "nope"}}))
check("junk software ignored", ConfigStore(badui).selected_dcc() is None)
check("junk variants ignored", ConfigStore(badui).variants() == {})

print("\npackage-section switches")
use = ConfigStore(tmp / "use.json")
check("both on by default", use.use_local() is True and use.use_dev() is True)
check("turning dev off persists", use.set_package_use(True, False) == "" and ConfigStore(tmp / "use.json").use_dev() is False)
check("and local stays on", ConfigStore(tmp / "use.json").use_local() is True)
check(
    "only the off one is written - absent means on",
    "use_local" not in json.loads((tmp / "use.json").read_text())["preferences"],
    str(json.loads((tmp / "use.json").read_text())["preferences"]),
)
check("turning it back on removes the key", use.set_package_use(True, True) == "" and "use_dev" not in json.loads((tmp / "use.json").read_text())["preferences"])
check("both off at once", use.set_package_use(False, False) == "" and ConfigStore(tmp / "use.json").use_local() is False and ConfigStore(tmp / "use.json").use_dev() is False)
check("an old file with no switches reads as on", ConfigStore(legacy).use_local() is True and ConfigStore(legacy).use_dev() is True)

print("\ninterrupted save leaves no stray temp file")
check("no .tmp beside configs", not list(path.parent.glob("*.tmp")))

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    raise SystemExit(1)
print("all config-store checks passed")
