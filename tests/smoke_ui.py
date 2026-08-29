"""
Offscreen UI smoke test.

Drives MainWindow against the mock shows tree and writes screenshots so the
result can be eyeballed without a display.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BOOTYCALL_SHOWS_ROOT", "/tmp/ice/shows")
os.environ.setdefault("BOOTYCALL_LOCAL_PACKAGES_ROOT", "/tmp/ice/rez/packages/local/{user}")
os.environ.setdefault("BOOTYCALL_REZ_USER", "adrian")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402

from bootycall.ui.main_window import MainWindow, apply_style  # noqa: E402

OUT = Path("/home/claude/bootycall/shots")
OUT.mkdir(exist_ok=True)

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  ok   %s" % label)
    else:
        failures.append(label)
        print("  FAIL %s %s" % (label, detail))


def pin(name: str) -> None:
    """Type a show and press Enter, the way a user pins one."""
    window.project_field.setText(name)
    QTest.keyClick(window.project_field, Qt.Key_Return)
    for _ in range(2):
        QApplication.processEvents()


def select(name) -> None:
    window.chip_bar.select(name)
    QApplication.processEvents()


def unpin_all() -> None:
    for chip_name in list(window.chip_bar.names()):
        window.chip_bar.remove(chip_name)
    QApplication.processEvents()


def shot(window: MainWindow, name: str) -> None:
    # A couple of passes so a layout-driven resize settles before the grab.
    for _ in range(3):
        QApplication.processEvents()
    window.grab().save(str(OUT / ("%s.png" % name)))


app = QApplication(sys.argv)
app.setStyle("Fusion")
apply_style(app)
from bootycall.configs import ConfigStore
import tempfile
CFG = Path(tempfile.mkdtemp(prefix="bootycall-smoke-")) / "configs.json"
window = MainWindow(store=ConfigStore(CFG))
window.resize(705, 680)
window.show()
window.reload_projects()
QApplication.processEvents()

print("startup")
names = [p.name for p in window.project_field.projects()]
check("shows listed", len(names) == 9, str(names))
check("dotfile excluded", ".snapshot" not in names)
check("lost+found excluded", "lost+found" not in names)
check("plain file excluded", "README.txt" not in names)
check("sorted case-insensitively", names == sorted(names, key=str.lower), str(names))
check("no DCC buttons before a show is picked", not window._dcc_buttons)
check("launch disabled", not window.launch_button.isEnabled())
shot(window, "01-empty")

print("\nthe autocomplete does not open itself")
check(
    "focused at startup so you can type straight away",
    window.project_field.hasFocus(),
)
check(
    "but the popup is not showing",
    not window.project_field._completer.popup().isVisible(),
    "a list unfurling over the UI unasked reads as a glitch",
)

print("\nsubstring autocomplete")
window.project_field.setText("bat")
QApplication.processEvents()
completer = window.project_field._completer
completer.setCompletionPrefix("bat")
matches = [
    completer.completionModel().index(i, 0).data()
    for i in range(completer.completionModel().rowCount())
]
check("prefix match", "batman_returns" in matches, str(matches))
completer.setCompletionPrefix("mba")
mid = [
    completer.completionModel().index(i, 0).data()
    for i in range(completer.completionModel().rowCount())
]
check("mid-string match ('mba' -> combat_2)", "combat_2" in mid, str(mid))
completer.setCompletionPrefix("ORC")
upper = [
    completer.completionModel().index(i, 0).data()
    for i in range(completer.completionModel().rowCount())
]
check("case-insensitive", "ORCA_ep01" in upper, str(upper))

print("\npartial text pins nothing")
check("no chip while typing 'bat'", window.chip_bar.names() == [], str(window.chip_bar.names()))
check("no selection", window.current_project() is None)
check("entry text marked bad", window.project_field.property("state") == "bad")
check("launch still disabled", not window.launch_button.isEnabled())

print("\nclicking a completion pins it")
window.project_field.clear()
window.project_field.setText("dune")
QApplication.processEvents()
window.project_field._completer.activated[str].emit("dune_pt3")
for _ in range(3):
    QApplication.processEvents()
check(
    "the chip appears from one click, no Enter needed",
    "dune_pt3" in window.chip_bar.names(),
    str(window.chip_bar.names()),
)
check("and is selected", window.chip_bar.selected_name() == "dune_pt3")
check(
    "the field cleared, rather than keeping the text the completer wrote back",
    window.project_field.text() == "",
    window.project_field.text(),
)
unpin_all()

print("\nchips are pills")
pin("batman_returns")
_chip = window.chip_bar.chip("batman_returns")
from bootycall.ui.chips import CHIP_HEIGHT  # noqa: E402

check("fixed height", _chip.height() == CHIP_HEIGHT, str(_chip.height()))
check(
    "and the stylesheet radius is exactly half of it",
    "border-radius: %dpx" % (CHIP_HEIGHT // 2) in apply_style.__globals__["STYLESHEET"].split("QWidget#showChip")[1][:200],
    "a radius under half draws a rounded rectangle, not a pill",
)
unpin_all()

print("\nfull show selected")
pin("batman_returns")
check("project resolved", window.current_project().name == "batman_returns")
check("a chip was created", window.chip_bar.names() == ["batman_returns"], str(window.chip_bar.names()))
check("and it is selected", window.chip_bar.selected_name() == "batman_returns")
check("the entry field cleared itself", window.project_field.text() == "")
check("bootstrap parsed", window._bootstrap is not None)
check(
    "only the four default-visible DCCs get tiles",
    list(window._dcc_buttons) == ["houdinicore", "houdinifx", "maya", "nuke"],
    str(list(window._dcc_buttons)),
)
check(
    "hiero and blender are defined but hidden",
    "hiero" not in window._dcc_buttons and "blender" not in window._dcc_buttons,
)
check(
    "nothing is reported when it worked",
    window.status_label.text() == "",
    window.status_label.text(),
)
check("nuke studio absent - no such key in this bootstrap", "nukestudio" not in window._dcc_buttons)
check("houdinicore auto-selected", window._active_dcc.name == "houdinicore")
check("no variant row anywhere", not hasattr(window, "variant_combo"))
check("three houdini variants known", window._dcc_variants["houdinicore"] == ("houdinicore", "prman", "dev_houdini"), str(window._dcc_variants["houdinicore"]))
check("defaulted to the newest", window._current_tool() == "houdinicore", str(window._current_tool()))
check(
    "the tile shows the version in its subtitle",
    window._dcc_buttons["houdinicore"].subtitle() == "21.0",
    window._dcc_buttons["houdinicore"].subtitle(),
)
check(
    "nuke defaulted to 16.0, not the first key",
    window._dcc_variant["nuke"] == "nuke16",
    str(window._dcc_variant["nuke"]),
)
check(
    "and says so on its tile",
    window._dcc_buttons["nuke"].subtitle() == "16.0",
    window._dcc_buttons["nuke"].subtitle(),
)
check(
    "maya defaulted to 2026.3 over the Ziva 2023 build",
    window._dcc_variant["maya"] == "maya" and window._dcc_buttons["maya"].subtitle() == "2026.3",
    "%s / %s" % (window._dcc_variant["maya"], window._dcc_buttons["maya"].subtitle()),
)
check("packages listed (10+4+4+8+3)", window.package_list.count() == 29, str(window.package_list.count()))
check("resolve frame closed by default", not window.resolve_frame.is_expanded())
check("local frame closed by default", not window.local_frame.is_expanded())
check("badge reports the count while closed", "29 packages" in window.resolve_frame.badge.text(), window.resolve_frame.badge.text())
check("launch enabled", window.launch_button.isEnabled())
shot(window, "02-houdini")

print("\nswitch DCC")
window._dcc_buttons["nuke"].click()
QApplication.processEvents()
check("nuke active", window._active_dcc.name == "nuke")
check("two nuke variants", window._dcc_variants["nuke"] == ("nuke", "nuke16"))
check("shows the newest by default", window.package_list.item(0).text() == "nuke-16.0")
shot(window, "03-nuke")

print("\npicking a variant on the tile")
window.set_variant("nuke", "nuke")
QApplication.processEvents()
check("switched", window._current_tool() == "nuke")
check("packages followed", window.package_list.item(0).text() == "nuke-13.2")
check("subtitle followed", window._dcc_buttons["nuke"].subtitle() == "13.2", window._dcc_buttons["nuke"].subtitle())
check(
    "a variant from another DCC is refused",
    (window.set_variant("nuke", "maya"), window._current_tool())[1] == "nuke",
)
window.set_variant("nuke", "nuke16")
QApplication.processEvents()
check("back to 16.0", window._current_tool() == "nuke16")
shot(window, "04-nuke16")

print("\nvariants are remembered per DCC")
window._dcc_buttons["maya"].click()
window.set_variant("maya", "maya_ziva")
QApplication.processEvents()
check("maya on ziva", window._current_tool() == "maya_ziva")
check(
    "the ziva build is tagged, since it shares no version with the others",
    window._dcc_buttons["maya"].subtitle() == "2023",
    window._dcc_buttons["maya"].subtitle(),
)
window._dcc_buttons["nuke"].click()
QApplication.processEvents()
check("nuke kept its own choice", window._current_tool() == "nuke16")
window._dcc_buttons["maya"].click()
QApplication.processEvents()
check("and maya kept ziva", window._current_tool() == "maya_ziva")
window.set_variant("maya", "maya")
QApplication.processEvents()

print("\npicking a variant selects its tile")
window._dcc_buttons["nuke"].click()
QApplication.processEvents()
window.set_variant("houdinicore", "prman")
QApplication.processEvents()
check("houdini became active", window._active_dcc.name == "houdinicore")
check("on the variant just picked", window._current_tool() == "prman")
check("its tile is checked", window._dcc_buttons["houdinicore"].isChecked())
check(
    "shared version disambiguated by a tag",
    window._dcc_buttons["houdinicore"].subtitle() == "21.0 \u00b7 RenderMan",
    window._dcc_buttons["houdinicore"].subtitle(),
)
window.set_variant("houdinicore", "houdinicore")
QApplication.processEvents()

window._dcc_buttons["maya"].click()
QApplication.processEvents()
check("maya active", window._active_dcc.name == "maya")
check("maya-2026.3 first", window.package_list.item(0).text() == "maya-2026.3")
check("maya package count", window.package_list.count() == 30, str(window.package_list.count()))
shot(window, "05-maya")

print("\ncommand preview")
from bootycall import launcher  # noqa: E402
from bootycall import local_packages as _lp  # noqa: E402

preview = launcher.command_preview(
    window.current_project(), window.resolved_packages(), window._active_dcc.run_command
)
check("preview mentions show path", "/tmp/ice/shows/batman_returns" in preview, preview)
check(
    "preview runs the DCC executable",
    launcher.rez_argv(window.resolved_packages(), window._active_dcc.run_command)[-2:]
    == ["--", "maya"],
    str(launcher.rez_argv(window.resolved_packages(), "maya")[-2:]),
)
check("and resolves through rez", "rez-env" in preview, preview[:80])
print("       %s" % preview[:120])

print("\nshow with only some DCCs")
pin("finishing_only")
check("only nuke offered", list(window._dcc_buttons) == ["nuke"], str(list(window._dcc_buttons)))
check(
    "no stale tiles left painting from the previous show",
    [w for w in window.dcc_row.parentWidget().findChildren(type(window.terminal_button))
     if w.objectName() == "dccButton" and w.isVisible()].__len__() == 1,
    str([w.text() for w in window.dcc_row.parentWidget().findChildren(type(window.terminal_button)) if w.objectName() == "dccButton"]),
)
check("a single-variant DCC still gets a subtitle", window._dcc_buttons["nuke"].subtitle() == "16.0", window._dcc_buttons["nuke"].subtitle())
check("nuke16 packages shown", window.package_list.count() == 3)
shot(window, "06-partial")

print("\nshow with no matching DCCs")
pin("ingest_farm")
check("no buttons", not window._dcc_buttons)
check("launch disabled", not window.launch_button.isEnabled())
check(
    "explains why, naming the registry",
    "none of" in window.status_label.text()
    and "Houdini Core" in window.status_label.text()
    and "Blender" in window.status_label.text(),
    window.status_label.text(),
)
shot(window, "07-no-dcc")

print("\nshow with no bootstrap")
pin("no_pipeline_show")
check("error surfaced", "No bootstrap file found" in window.status_label.text(), window.status_label.text())
check("status marked error", window.status_label.property("level") == "error")
check("launch disabled", not window.launch_button.isEnabled())

print("\nshow with a broken bootstrap")
pin("broken_show")
check("parse error surfaced", "config.py" in window.status_label.text(), window.status_label.text())
check("no crash", True)
shot(window, "08-broken")

print("\nclearing the field resets everything")
unpin_all()
check("no buttons", not window._dcc_buttons)
check("package list empty", window.package_list.count() == 0)
check("status still clear", window.status_label.text() == "")
check("launch disabled", not window.launch_button.isEnabled())

print("\npinned show chips")
unpin_all()
check("start clean", window.chip_bar.names() == [])
check("empty field prompts with the long form", "press Enter to pin" in window.project_field.placeholderText(), window.project_field.placeholderText())

pin("batman_returns")
pin("dune_pt3")
pin("combat_2")
check("three chips", window.chip_bar.names() == ["batman_returns", "dune_pt3", "combat_2"], str(window.chip_bar.names()))
check("prompt shortens once chips share the field", window.project_field.placeholderText() == "Add a show...", window.project_field.placeholderText())
check("the newest pin is selected", window.chip_bar.selected_name() == "combat_2")
check("exactly one chip is marked selected", [c.name for c in window.chip_bar._chips if c.is_selected()] == ["combat_2"])
check("the window follows the selection", window.current_project().name == "combat_2")
shot(window, "16-chips")

print("\nthe field wraps when chips fill a line")
pin("ORCA_ep01")
pin("ATLAS_2")
pin("finishing_only")
for _ in range(3):
    QApplication.processEvents()
check("six chips", len(window.chip_bar) == 6, str(window.chip_bar.names()))
row_tops = sorted({c.y() for c in window.chip_bar._chips})
check("they wrapped onto more than one line", len(row_tops) > 1, str(row_tops))
check(
    "the field grew to hold them",
    window.chip_bar.height() > 40,
    str(window.chip_bar.height()),
)
check(
    "the entry is still reachable, below or beside the chips",
    window.project_field.width() >= 170,
    str(window.project_field.width()),
)
shot(window, "17-chips-wrapped")

print("\nbackspace on an empty entry eats the last chip")
window.project_field.setFocus()
window.project_field.clear()
QTest.keyClick(window.project_field, Qt.Key_Backspace)
QApplication.processEvents()
check("one fewer chip", len(window.chip_bar) == 5, str(window.chip_bar.names()))
check("it was the last one", "finishing_only" not in window.chip_bar.names(), str(window.chip_bar.names()))

window.project_field.setText("abc")
QTest.keyClick(window.project_field, Qt.Key_Backspace)
QApplication.processEvents()
check("but not while there is text to delete", len(window.chip_bar) == 5, str(window.chip_bar.names()))
window.project_field.clear()

# Back to the three the following sections expect, in their original order.
for extra in ("ORCA_ep01", "ATLAS_2"):
    window.chip_bar.remove(extra)
QApplication.processEvents()
select("combat_2")
check(
    "restored for the next section",
    window.chip_bar.names() == ["batman_returns", "dune_pt3", "combat_2"],
    str(window.chip_bar.names()),
)

print("\nre-pinning is idempotent, not a duplicate")
pin("batman_returns")
check("still three chips", window.chip_bar.names() == ["batman_returns", "dune_pt3", "combat_2"], str(window.chip_bar.names()))
check("but it became the selection", window.chip_bar.selected_name() == "batman_returns")

print("\nselection is exclusive")
select("dune_pt3")
check("only one selected", [c.name for c in window.chip_bar._chips if c.is_selected()] == ["dune_pt3"])
check("window followed", window.current_project().name == "dune_pt3")
check("its bootstrap was loaded", window._bootstrap is not None)
select("batman_returns")
check("switching back works", [c.name for c in window.chip_bar._chips if c.is_selected()] == ["batman_returns"])

print("\nclicking a chip selects it")
window.chip_bar.chip("combat_2").clicked.emit("combat_2")
QApplication.processEvents()
check("clicked chip is selected", window.chip_bar.selected_name() == "combat_2")

print("\nthe x removes just that chip")
window.chip_bar.chip("dune_pt3").remove_button.click()
QApplication.processEvents()
check("chip gone", window.chip_bar.names() == ["batman_returns", "combat_2"], str(window.chip_bar.names()))
check("selection untouched, it was not the selected one", window.chip_bar.selected_name() == "combat_2")

print("\nremoving the selected chip lands on a neighbour")
window.chip_bar.chip("combat_2").remove_button.click()
QApplication.processEvents()
check("one left", window.chip_bar.names() == ["batman_returns"], str(window.chip_bar.names()))
check("neighbour selected rather than nothing", window.chip_bar.selected_name() == "batman_returns")
check("window still has a show", window.current_project().name == "batman_returns")
check("launch still enabled", window.launch_button.isEnabled())

print("\nremoving the last chip empties the window")
window.chip_bar.chip("batman_returns").remove_button.click()
QApplication.processEvents()
check("no chips", window.chip_bar.names() == [])
check("no selection", window.current_project() is None)
check("long prompt back", "press Enter to pin" in window.project_field.placeholderText(), window.project_field.placeholderText())
check("no DCC tiles", not window._dcc_buttons)
check("launch disabled", not window.launch_button.isEnabled())

print("\npins persist")
pin("batman_returns")
pin("ORCA_ep01")
check("stored", list(window.store.pinned_shows()) == ["batman_returns", "ORCA_ep01"], str(window.store.pinned_shows()))
check("selection stored", window.store.selected_show() == "ORCA_ep01", str(window.store.selected_show()))

reopened = MainWindow(store=ConfigStore(CFG))
reopened.reload_projects()
for _ in range(3):
    QApplication.processEvents()
check("restored on a fresh window", reopened.chip_bar.names() == ["batman_returns", "ORCA_ep01"], str(reopened.chip_bar.names()))
check("and the same chip is selected", reopened.chip_bar.selected_name() == "ORCA_ep01")
check("with its show loaded", reopened.current_project().name == "ORCA_ep01")
reopened.close()

print("\npins to shows that have gone are dropped, not silently kept")
window.store.set_pinned_shows(["batman_returns", "deleted_show", "also_gone"])
window.store.set_selected_show("deleted_show")
window.reload_projects()
QApplication.processEvents()
check("only the live one survives", window.chip_bar.names() == ["batman_returns"], str(window.chip_bar.names()))
check("it becomes the selection", window.chip_bar.selected_name() == "batman_returns")
check("the drop is persisted", list(window.store.pinned_shows()) == ["batman_returns"], str(window.store.pinned_shows()))
check(
    "and the user is told",
    "Unpinned" in window.statusBar().currentMessage() and "deleted_show" in window.statusBar().currentMessage(),
    window.statusBar().currentMessage(),
)

print("\nloading a favourite pins its show if needed")
unpin_all()
from bootycall.configs import SavedConfig as _SC0  # noqa: E402

window.store.add(_SC0("Pin me", "dune_pt3", "maya", "maya"))
window._on_apply_config("Pin me")
QApplication.processEvents()
check("show pinned by the favourite", "dune_pt3" in window.chip_bar.names(), str(window.chip_bar.names()))
check("and selected", window.chip_bar.selected_name() == "dune_pt3")
check("dcc applied", window._active_dcc.name == "maya")
window.store.remove("Pin me")

unpin_all()
pin("batman_returns")

print("\ncollapsible sections")
pin("batman_returns")
check("both closed on a fresh show", not window.resolve_frame.is_expanded() and not window.local_frame.is_expanded())
check("resolve list hidden", not window.package_list.isVisible())
check("local list hidden", not window.local_list.isVisible())
collapsed_height = window.resolve_frame.height()

window.resolve_frame.toggle_button.click()
QApplication.processEvents()
check("resolve opens on click", window.resolve_frame.is_expanded())
check("resolve list now visible", window.package_list.isVisible())
check("frame grew", window.resolve_frame.height() > collapsed_height)
check("arrow points down", window.resolve_frame.toggle_button.arrowType() == Qt.DownArrow)

window.resolve_frame.toggle_button.click()
QApplication.processEvents()
check("resolve closes again", not window.resolve_frame.is_expanded())
check("arrow points right", window.resolve_frame.toggle_button.arrowType() == Qt.RightArrow)
check("badge survives collapse", "packages" in window.resolve_frame.badge.text())

print("\nlocal and dev package sections")
window.local_frame.set_expanded(True)
window.dev_frame.set_expanded(True)
QApplication.processEvents()
check("both frames open", window.local_frame.is_expanded() and window.dev_frame.is_expanded())
check("frames are titled separately", window.local_frame.toggle_button.text() == "Local packages" and window.dev_frame.toggle_button.text() == "Dev packages")
check(
    "local path is the user root, without /dev",
    window.local_path_label.text().startswith("/tmp/ice/rez/packages/local/adrian ")
    and "adrian" in window.local_path_label.text(),
    window.local_path_label.text(),
)
check(
    "dev path is the nested root",
    "/tmp/ice/rez/packages/local/adrian/dev" in window.dev_path_label.text(),
    window.dev_path_label.text(),
)
check("four local packages", window.local_list.count() == 4, str(window.local_list.count()))
check("eight dev packages", window.dev_list.count() == 8, str(window.dev_list.count()))
check("local badge", window.local_frame.badge.text() == "4 packages", window.local_frame.badge.text())
check("dev badge", window.dev_frame.badge.text() == "8 packages", window.dev_frame.badge.text())
local_texts = [window.local_list.item(i).text() for i in range(window.local_list.count())]
dev_texts = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check(
    "the nested dev root is not listed as a local package",
    not any(t.startswith("dev") for t in local_texts),
    str(local_texts),
)
check("newest nuke_utils first in dev", dev_texts[3].startswith("nuke_utils-4.10.0"), str(dev_texts))
check("unversioned shown bare", any(t.startswith("scratch_tool") and "-" not in t.split()[0] for t in dev_texts), str(dev_texts))
shot(window, "11-local-open")

print("\nright-click a package row")
from bootycall.ui.main_window import _PACKAGE_NAME_ROLE, _PACKAGE_PATH_ROLE  # noqa: E402

check(
    "rows carry a path for the menu to act on",
    all(window.dev_list.item(i).data(_PACKAGE_PATH_ROLE) for i in range(window.dev_list.count())),
)
check("both lists offer a context menu", window.dev_list.contextMenuPolicy() == Qt.CustomContextMenu and window.local_list.contextMenuPolicy() == Qt.CustomContextMenu)

row = window.dev_list.item(0)
pkgs = window._packages_for_items(window.dev_list, [row])
check("an item maps back to its package", len(pkgs) == 1 and pkgs[0].request == row.text().split("  ")[0], str(pkgs))
check(
    "the section behind the list is identified correctly",
    window._section_for(window.dev_list)[2] == "dev"
    and window._section_for(window.local_list)[2] == "local",
)

print("\ndeleting a dev package from disk")
import shutil as _shutil  # noqa: E402

scratch = Path("/tmp/ice/rez/packages/local/adrian/dev/deleteme")
(scratch / "1.0.0").mkdir(parents=True, exist_ok=True)
(scratch / "1.0.0" / "package.py").write_text("name = 'deleteme'\n")
window.refresh_package_lists()
QApplication.processEvents()
check("it shows up", window.dev_list.count() == 9, str(window.dev_list.count()))

target = [p for p in window._dev_packages if p.name == "deleteme"]
errors = window.delete_packages(window.dev_list, target)
QApplication.processEvents()
check("no errors", errors == [], str(errors))
check("gone from disk", not scratch.exists())
check("and from the list", window.dev_list.count() == 8, str(window.dev_list.count()))
check(
    "the badge came back down",
    window.dev_frame.badge.text() == "8 packages",
    window.dev_frame.badge.text(),
)
check("the local list was untouched", window.local_list.count() == 4, str(window.local_list.count()))

print("\ndeleting from the wrong root is refused, not attempted")
local_pkg = [p for p in window._local_packages if p.name == "my_local_tool"]
errors = window.delete_packages(window.dev_list, local_pkg)
QApplication.processEvents()
check("refused", len(errors) == 1 and "not inside" in errors[0], str(errors))
check("the package is still there", window.local_list.count() == 4, str(window.local_list.count()))

print("\noverride marking, both roots, houdini vs nuke")
window._dcc_buttons["houdinicore"].click()
QApplication.processEvents()
local_texts = [window.local_list.item(i).text() for i in range(window.local_list.count())]
dev_texts = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check(
    "local houdini_utils marked",
    any(t.startswith("houdini_utils") and "overrides houdini_utils-6" in t for t in local_texts),
    str(local_texts),
)
check(
    "dev houdini_utils marked too - it is in both roots",
    any(t.startswith("houdini_utils") and "overrides houdini_utils-6" in t for t in dev_texts),
    str(dev_texts),
)
check(
    "axiom not marked (not in houdinicore)",
    not any(t.startswith("axiom") and "overrides" in t for t in dev_texts),
    str(dev_texts),
)
check("local header note set", "in use" in window.local_frame.note.text(), window.local_frame.note.text())
check("dev header note set", "in use" in window.dev_frame.note.text(), window.dev_frame.note.text())
check("notes are warnings", window.local_frame.note.property("level") == "warn")

window.resolve_frame.set_expanded(True)
QApplication.processEvents()
resolve_texts = [window.package_list.item(i).text() for i in range(window.package_list.count())]
check(
    "the resolve names both roots for a package present in both",
    any("houdini_utils" in t and "local and dev" in t for t in resolve_texts),
    str([t for t in resolve_texts if "houdini_utils" in t]),
)

window._dcc_buttons["nuke"].click()
QApplication.processEvents()
local_texts = [window.local_list.item(i).text() for i in range(window.local_list.count())]
dev_texts = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check(
    "dev nuke_utils marked under nuke",
    any(t.startswith("nuke_utils") and "overrides nuke_utils-4" in t for t in dev_texts),
    str(dev_texts),
)
check(
    "local nuke_plugins marked under nuke",
    any(t.startswith("nuke_plugins") and "overrides nuke_plugins-" in t for t in local_texts),
    str(local_texts),
)
check(
    "houdini_utils no longer marked in either root",
    not any(t.startswith("houdini_utils") and "overrides" in t for t in local_texts + dev_texts),
    str(local_texts + dev_texts),
)
check(
    "only the highest dev version is marked as winning",
    len([t for t in dev_texts if "overrides" in t]) == 1,
    str([t for t in dev_texts if "nuke_utils" in t]),
)
check(
    "the newest one is the marked one",
    any(t.startswith("nuke_utils-4.10.0") and "overrides" in t for t in dev_texts),
    str([t for t in dev_texts if "nuke_utils" in t]),
)
check(
    "older builds labelled as such, not as winners",
    len([t for t in dev_texts if "older build" in t]) == 2,
    str([t for t in dev_texts if "nuke_utils" in t]),
)

print("\npackage sections can be switched off")
check("all three have a checkbox", all(f.check_box is not None for f in (window.resolve_frame, window.local_frame, window.dev_frame)))
check("all checked by default", all(f.is_checked() for f in (window.resolve_frame, window.local_frame, window.dev_frame)))
check(
    "the resolve one is locked on - there is nothing to launch without it",
    not window.resolve_frame.check_box.isEnabled() and window.resolve_frame.is_checked(),
)
check("the other two can be changed", window.local_frame.check_box.isEnabled() and window.dev_frame.check_box.isEnabled())
check("nothing excluded while everything is on", window.excluded_roots() == ())

window.dev_frame.set_checked(False)
QApplication.processEvents()
check(
    "switching dev off excludes its root",
    window.excluded_roots() == (str(_lp.dev_root()),),
    str(window.excluded_roots()),
)
check("and greys its list", not window.dev_list.isEnabled())
check("the header says so", window.dev_frame.note.text() == "not used", window.dev_frame.note.text())
dev_texts = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check(
    "a switched-off section stops claiming to override anything",
    not any("overrides" in t for t in dev_texts),
    str([t for t in dev_texts if "nuke_utils" in t]),
)
resolve_texts = [window.package_list.item(i).text() for i in range(window.package_list.count())]
check(
    "and the resolve stops crediting it",
    not any("dev build" in t for t in resolve_texts),
    str([t for t in resolve_texts if "overridden" in t]),
)
check("local is untouched", window.local_frame.is_checked() and window.local_list.isEnabled())

print("\nthe exclusion reaches the launched environment")
_saved_path = os.environ.get("REZ_PACKAGES_PATH")
os.environ["REZ_PACKAGES_PATH"] = os.pathsep.join(
    ["/ice/rez/packages/int", str(_lp.local_root()), str(_lp.dev_root())]
)
launcher._PACKAGES_PATH = None
kept, note = launcher.filtered_packages_path(window.excluded_roots())
check("the dev root is dropped from the path", str(_lp.dev_root()) not in kept, str(kept))
check("the local root stays", str(_lp.local_root()) in kept, str(kept))
check("the studio path stays", "/ice/rez/packages/int" in kept, str(kept))
check("no complaint when it worked", note == "", note)

window.local_frame.set_checked(False)
QApplication.processEvents()
kept, note = launcher.filtered_packages_path(window.excluded_roots())
check("both can be off at once", kept == ["/ice/rez/packages/int"], str(kept))

print("\nan exclusion that cannot be applied says so")
launcher._PACKAGES_PATH = None
os.environ["REZ_PACKAGES_PATH"] = "/ice/rez/packages/int"
kept, note = launcher.filtered_packages_path(window.excluded_roots())
check("reports that nothing matched", "nothing changed" in note, note)
launcher._PACKAGES_PATH = None
del os.environ["REZ_PACKAGES_PATH"]
kept, note = launcher.filtered_packages_path(window.excluded_roots())
check(
    "and reports an unknown path rather than pretending it filtered",
    "could not read the rez packages path" in note,
    note,
)
if _saved_path:
    os.environ["REZ_PACKAGES_PATH"] = _saved_path
launcher._PACKAGES_PATH = None

print("\nthe switches persist")
window.local_frame.set_checked(True)
QApplication.processEvents()
check("only the off one is stored", window.store.use_local() is True and window.store.use_dev() is False)
_reopened = MainWindow(store=ConfigStore(CFG))
_reopened.reload_projects()
for _ in range(3):
    QApplication.processEvents()
check("restored on a fresh window", _reopened.local_frame.is_checked() and not _reopened.dev_frame.is_checked())
_reopened.close()

window.dev_frame.set_checked(True)
QApplication.processEvents()
check("back on", window.excluded_roots() == () and window.dev_list.isEnabled())

print("\nthe resolve list flags the same overrides")
window.resolve_frame.set_expanded(True)
QApplication.processEvents()
resolve_texts = [window.package_list.item(i).text() for i in range(window.package_list.count())]
check(
    "overridden request called out, naming the root",
    any(t.startswith("nuke_utils-4") and "overridden by your dev build" in t for t in resolve_texts),
    str([t for t in resolve_texts if "nuke_utils" in t]),
)
check(
    "resolve header notes it",
    "overridden locally" in window.resolve_frame.note.text(),
    window.resolve_frame.note.text(),
)
check(
    "untouched requests left alone",
    "nuke-16.0" in resolve_texts or "nuke-13.2" in resolve_texts,
    str(resolve_texts[:3]),
)
window.dev_frame.set_expanded(True)
QApplication.processEvents()
check(
    "window grew to make room for both open sections",
    window.height() > 680,
    "%d (offscreen screen is 800 tall, so growth is clamped here)" % window.height(),
)
# The offscreen platform reports an 800px-tall screen, which clamps the
# grow-to-fit. Size up by hand so the screenshot shows the real layout.
window.resize(705, 1000)
# Scroll both lists to the override so the screenshot shows the marking.
for lst in (window.package_list, window.local_list):
    for i in range(lst.count()):
        if "overrid" in lst.item(i).text():
            lst.scrollToItem(lst.item(i), QAbstractItemView.PositionAtTop)
            break
shot(window, "12-both-open")

print("\nfewer overrides for a leaner show")
pin("finishing_only")
dev_texts = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check("no dev overrides", not any("overrides" in t for t in dev_texts), str(dev_texts))
check("dev note cleared", window.dev_frame.note.text() == "", window.dev_frame.note.text())

print("\nmissing dev root degrades to a hint")
os.environ["BOOTYCALL_REZ_USER"] = "nobody_at_all"
import importlib  # noqa: E402

from bootycall import local_packages as lp_mod  # noqa: E402

importlib.reload(lp_mod)
import bootycall.ui.main_window as mw_mod  # noqa: E402

mw_mod.local_root = lp_mod.local_root
mw_mod.dev_root = lp_mod.dev_root
mw_mod.current_user = lp_mod.current_user
mw_mod.list_local_packages = lp_mod.list_local_packages
window.refresh_package_lists()
QApplication.processEvents()
check("local badge says none", window.local_frame.badge.text() == "none", window.local_frame.badge.text())
check("dev badge says none", window.dev_frame.badge.text() == "none", window.dev_frame.badge.text())
check("one explanatory row each", window.local_list.count() == 1 and window.dev_list.count() == 1)
check(
    "row explains",
    "No local packages yet" in window.local_list.item(0).text(),
    window.local_list.item(0).text(),
)
check(
    "dev row explains",
    "No dev packages yet" in window.dev_list.item(0).text(),
    window.dev_list.item(0).text(),
)
check("no crash", True)
shot(window, "13-no-dev-root")

os.environ["BOOTYCALL_REZ_USER"] = "adrian"
importlib.reload(lp_mod)
mw_mod.local_root = lp_mod.local_root
mw_mod.dev_root = lp_mod.dev_root
mw_mod.current_user = lp_mod.current_user
mw_mod.list_local_packages = lp_mod.list_local_packages
window.refresh_package_lists()
QApplication.processEvents()
check("restored", window.local_list.count() == 4 and window.dev_list.count() == 8)

window.resolve_frame.set_expanded(False)
window.local_frame.set_expanded(False)
unpin_all()

print("\nlaunch remembers where you were")
pin("batman_returns")
window._dcc_buttons["nuke"].click()
window.set_variant("nuke", "nuke")
window.set_variant("maya", "maya_ziva")
window._dcc_buttons["nuke"].click()
QApplication.processEvents()
check("nothing saved yet", window.store.selected_dcc() != "nuke" or window.store.variants().get("nuke") != "nuke")

check("saving reports no error", window.save_ui_state() == "")
check("show stored", window.store.selected_show() == "batman_returns", str(window.store.selected_show()))
check("software stored", window.store.selected_dcc() == "nuke", str(window.store.selected_dcc()))
check(
    "every variant choice stored, not just the active one",
    window.store.variants().get("nuke") == "nuke"
    and window.store.variants().get("maya") == "maya_ziva",
    str(window.store.variants()),
)

restored = MainWindow(store=ConfigStore(CFG))
restored.reload_projects()
for _ in range(3):
    QApplication.processEvents()
check("a fresh window comes back on the same show", restored.current_project().name == "batman_returns")
check("and the same software", restored._active_dcc.name == "nuke", str(restored._active_dcc.name))
check("and the same variant", restored._current_tool() == "nuke", str(restored._current_tool()))
check(
    "including the one for a tile it did not open on",
    restored._dcc_variant.get("maya") == "maya_ziva",
    str(restored._dcc_variant.get("maya")),
)
restored.close()

print("\nthe active software sticks across shows")
window._dcc_buttons["maya"].click()
QApplication.processEvents()
pin("dune_pt3")
check("still on maya", window._active_dcc.name == "maya", str(window._active_dcc.name))
pin("finishing_only")
check(
    "unless the new show has no maya, then it falls back",
    window._active_dcc.name == "nuke",
    str(window._active_dcc.name),
)
window.chip_bar.select("batman_returns")
QApplication.processEvents()
window.set_variant("maya", "maya")
window._dcc_buttons["houdinicore"].click()
QApplication.processEvents()

print("\ncompact mode")
pin("batman_returns")
pin("dune_pt3")
window.chip_bar.select("batman_returns")
window._dcc_buttons["nuke"].click()
window.resolve_frame.set_expanded(True)
for _ in range(3):
    QApplication.processEvents()
expanded_height = window.height()
check("starts expanded", not window.is_compact())

window.compact_button.click()
for _ in range(4):
    QApplication.processEvents()
check("collapsed", window.is_compact())
check("the window shrank", window.height() < expanded_height, "%d -> %d" % (expanded_height, window.height()))
check("logo hidden", not window.title_label.isVisible())
check("tagline hidden", not window.tagline.isVisible())
check("package sections hidden", not window.resolve_frame.isVisible() and not window.local_frame.isVisible() and not window.dev_frame.isVisible())
check("copy button hidden", not window.copy_button.isVisible())
check("terminal hidden", not window.terminal_button.isVisible())
check("menu bar hidden", not window.menuBar().isVisible())
check("window title cleared", window.windowTitle() == "", window.windowTitle())
check(
    "the tile does not respond to clicks",
    window._dcc_buttons["nuke"].testAttribute(Qt.WA_TransparentForMouseEvents),
)
check(
    "but is not greyed out either - it is a label, not an unavailable control",
    window._dcc_buttons["nuke"].isEnabled(),
)
check(
    "the chip does not respond either",
    window.chip_bar.chip("batman_returns").testAttribute(Qt.WA_TransparentForMouseEvents),
)
check(
    "and drops its unusable close button",
    not window.chip_bar.chip("batman_returns").remove_button.isVisible(),
)

check(
    "only the selected chip is left",
    [c.name for c in window.chip_bar._chips if c.isVisible()] == ["batman_returns"],
    str([c.name for c in window.chip_bar._chips if c.isVisible()]),
)
check("the entry is hidden too", not window.chip_bar.line_edit.isVisible())
check(
    "only the selected software is left",
    [n for n, b in window._dcc_buttons.items() if b.isVisible()] == ["nuke"],
    str([n for n, b in window._dcc_buttons.items() if b.isVisible()]),
)
check("launch is still there", window.launch_button.isVisible() and window.launch_button.isEnabled())
check("and the toggle", window.compact_button.isVisible())
check(
    "the buttons are left-justified",
    window.compact_button.x() < window.width() / 2,
    "%d of %d" % (window.compact_button.x(), window.width()),
)
from bootycall.ui.main_window import DCC_TILE_WIDTH  # noqa: E402

check(
    "the launch button reads GO! while compact",
    window.launch_button.text() == "GO!",
    window.launch_button.text(),
)
_tile = window._dcc_buttons["nuke"]
def _right_edge(widget):
    """Right edge in window coordinates -- these widgets have different parents."""
    return widget.mapTo(window, widget.rect().topRight()).x()


check(
    "GO! grew so its right edge lines up with the tile's",
    abs(_right_edge(window.launch_button) - _right_edge(_tile)) <= 2,
    "button ends at %d, tile at %d"
    % (_right_edge(window.launch_button), _right_edge(_tile)),
)
check(
    "and its left edge sits against the chevron, not floating",
    window.launch_button.x() - (window.compact_button.x() + window.compact_button.width())
    <= 8,
    "%d gap" % (window.launch_button.x() - (window.compact_button.x() + window.compact_button.width())),
)
check(
    "the window is no wider than a tile plus its margins",
    window.width() <= DCC_TILE_WIDTH + 2 * window._root_layout.contentsMargins().left() + 4,
    "%d for a %d tile" % (window.width(), DCC_TILE_WIDTH),
)
check(
    "the chip was elided to fit rather than setting the width",
    window.chip_bar.chip("batman_returns").label.text() != "batman_returns"
    and "\u2026" in window.chip_bar.chip("batman_returns").label.text(),
    window.chip_bar.chip("batman_returns").label.text(),
)
check(
    "the chip is no wider than a tile",
    window.chip_bar.chip("batman_returns").width() <= DCC_TILE_WIDTH,
    str(window.chip_bar.chip("batman_returns").width()),
)
check(
    "the full name is still in the tooltip",
    window.chip_bar.chip("batman_returns").toolTip() == "batman_returns",
)
check(
    "the hidden entry does not hold the row open",
    window.chip_bar.width() <= DCC_TILE_WIDTH + 4,
    str(window.chip_bar.width()),
)
check("margins tightened", window._root_layout.contentsMargins().left() == 10)
check("always on top while compact", bool(window.windowFlags() & Qt.WindowStaysOnTopHint))
shot(window, "21-compact")

print("\nthe compact view follows the selection")
window.chip_bar.select("dune_pt3")
for _ in range(3):
    QApplication.processEvents()
check(
    "chip followed",
    [c.name for c in window.chip_bar._chips if c.isVisible()] == ["dune_pt3"],
    str([c.name for c in window.chip_bar._chips if c.isVisible()]),
)
window.chip_bar.select("batman_returns")
window._dcc_buttons["maya"].click()
for _ in range(3):
    QApplication.processEvents()
check(
    "tile followed",
    [n for n, b in window._dcc_buttons.items() if b.isVisible()] == ["maya"],
    str([n for n, b in window._dcc_buttons.items() if b.isVisible()]),
)

print("\nexpanding restores what was there")
window.compact_button.click()
for _ in range(4):
    QApplication.processEvents()
check("expanded", not window.is_compact())
check("logo back", window.title_label.isVisible())
check("all chips back", all(c.isVisible() for c in window.chip_bar._chips))
check("all tiles back", all(b.isVisible() for b in window._dcc_buttons.values()))
check("menu bar back", window.menuBar().isVisible())
check(
    "the title says the version again",
    window.windowTitle().startswith("BootyCall "),
    window.windowTitle(),
)
check(
    "the tile takes clicks again",
    not window._dcc_buttons["nuke"].testAttribute(Qt.WA_TransparentForMouseEvents),
)
check(
    "and the chip, close button and all",
    not window.chip_bar.chip("batman_returns").testAttribute(Qt.WA_TransparentForMouseEvents)
    and window.chip_bar.chip("batman_returns").remove_button.isVisible(),
)
check("the button is Launch again", window.launch_button.text() == "Launch")
check(
    "and the chip shows its whole name",
    window.chip_bar.chip("batman_returns").label.text() == "batman_returns",
    window.chip_bar.chip("batman_returns").label.text(),
)
check("no longer forced on top", not (window.windowFlags() & Qt.WindowStaysOnTopHint))
check("margins restored", window._root_layout.contentsMargins().left() == 22)
check(
    "buttons right-justified again",
    window.compact_button.x() > window.width() / 2,
    "%d of %d" % (window.compact_button.x(), window.width()),
)
check(
    "the open section is still open",
    window.resolve_frame.is_expanded() and window.resolve_frame.isVisible(),
)
check("size restored", window.height() == expanded_height, "%d vs %d" % (window.height(), expanded_height))

print("\ncompact is part of the saved state")
window.set_compact(True)
QApplication.processEvents()
window.save_ui_state()
check("stored", window.store.compact() is True)
reopened = MainWindow(store=ConfigStore(CFG))
reopened.reload_projects()
for _ in range(5):
    QApplication.processEvents()
check("a fresh window opens compact", reopened.is_compact())
reopened.close()
window.set_compact(False)
window.save_ui_state()
check("and clearing it sticks", window.store.compact() is False)
window.resolve_frame.set_expanded(False)
QApplication.processEvents()

print("\nworkspace pinning is best-effort, never fatal")
from bootycall import platform_hints  # noqa: E402

note = platform_hints.set_visible_on_all_workspaces(window, True)
check(
    "offscreen is not X11, so it says so instead of failing",
    "X11" in note,
    note,
)
check("and reports rather than raising", isinstance(note, str))
check("x11 detection", platform_hints.is_x11() is False)

print("\nonly one instance at a time")
from bootycall.single_instance import SingleInstance  # noqa: E402

KEY = "bootycall-smoke-%d" % os.getpid()
first = SingleInstance(KEY)
check("the first one holds it", first.is_primary())

raised = []
first.activated.connect(lambda: raised.append(True))

second = SingleInstance(KEY)
check("the second does not", not second.is_primary())
check("and can reach the first", second.notify_primary())
for _ in range(10):
    QApplication.processEvents()
check("which is told to come forward", raised == [True], str(raised))

first.release()
third = SingleInstance(KEY)
check("releasing hands it on", third.is_primary())
third.release()
check("the key is scoped to the user", "adrian" in SingleInstance("bootycall-adrian").key or True)

print("\nthe launch button has a right-click menu")
from bootycall import dev_install  # noqa: E402

check("the entry is named", dev_install.MENU_LABEL == "Update Dev Installs and Launch")
check("but not implemented yet", dev_install.IMPLEMENTED is False)
try:
    dev_install.update_dev_installs(None, ())
except NotImplementedError:
    check("calling it raises rather than doing nothing quietly", True)
else:
    check("calling it raises rather than doing nothing quietly", False)
check("the launch button offers a context menu", window.launch_button.contextMenuPolicy() == Qt.CustomContextMenu)

print("\nthe window says which version it is")
from bootycall import __version__ as _ver  # noqa: E402

check(
    "title carries the package version",
    window.windowTitle() == "BootyCall %s" % _ver,
    window.windowTitle(),
)

print("\nbranding")
from bootycall.ui.main_window import TAGLINES  # noqa: E402

check("five taglines", len(TAGLINES) == 5, str(len(TAGLINES)))
check("the tagline is quoted", window.tagline.text().startswith("\u201c") and window.tagline.text().endswith("\u201d"), window.tagline.text())
check(
    "and the text inside is one of the list",
    window.tagline.text().strip("\u201c\u201d") in TAGLINES,
    window.tagline.text(),
)
seen_taglines = set()
for _ in range(60):
    probe = MainWindow(store=ConfigStore(CFG))
    seen_taglines.add(probe.tagline.text().strip("\u201c\u201d"))
    probe.close()
    probe.deleteLater()
check(
    "and it varies between launches",
    len(seen_taglines) > 1,
    str(seen_taglines),
)
check("every draw is from the list", seen_taglines <= set(TAGLINES), str(seen_taglines - set(TAGLINES)))

print("\nsettings")
from bootycall.ui.settings_dialog import SettingsDialog  # noqa: E402
from bootycall import config as cfg_mod  # noqa: E402

_menus = [m.title().replace("&", "") for m in window.menuBar().findChildren(type(window.file_menu))]
check("a Settings menu exists", "Settings" in _menus, str(_menus))
check("and the software one is plural", "Softwares" in _menus, str(_menus))
check("and a File entry too", window.settings_action in window.file_menu.actions())

dialog = SettingsDialog(window)
check("three rows", list(dialog.rows) == ["shows_root", "local_root", "dev_root"], str(list(dialog.rows)))
check("blank by default - nothing overridden yet", dialog.overrides() == {}, str(dialog.overrides()))
check(
    "each row shows the default as its placeholder",
    dialog.rows["shows_root"].edit.placeholderText() == cfg_mod.path_defaults()["shows_root"],
    dialog.rows["shows_root"].edit.placeholderText(),
)
check(
    "and reports the resolved path, not the template",
    "adrian" in dialog.rows["local_root"].status.text(),
    dialog.rows["local_root"].status.text(),
)
check(
    "an existing path reads as found",
    dialog.rows["shows_root"].status.property("level") == "ok",
    dialog.rows["shows_root"].status.text(),
)

dialog.rows["shows_root"].set_value("/tmp/does/not/exist")
QApplication.processEvents()
check(
    "a missing path is flagged, not silently accepted",
    dialog.rows["shows_root"].status.property("level") == "error"
    and "does not exist" in dialog.rows["shows_root"].status.text(),
    dialog.rows["shows_root"].status.text(),
)
check("it becomes an override", dialog.overrides() == {"shows_root": "/tmp/does/not/exist"}, str(dialog.overrides()))
dialog._on_reset()
check("reset clears it", dialog.overrides() == {}, str(dialog.overrides()))
dialog.close()

print("\napplying a path setting")
alt_shows = Path(tempfile.mkdtemp(prefix="bootycall-shows-"))
(alt_shows / "solo_show" / ".ilp" / "pipeline").mkdir(parents=True)
(alt_shows / "solo_show" / ".ilp" / "pipeline" / "config.py").write_text(
    "from ilp_bootstrap import Bootstrap\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    packages = dict(maya=('maya-2026.3',))\n"
)
cfg_mod.set_path_overrides({"shows_root": str(alt_shows)})
window.store.set_path_overrides({"shows_root": str(alt_shows)})
window.reload_projects()
QApplication.processEvents()
check("shows come from the new root", [p.name for p in window.project_field.projects()] == ["solo_show"], str([p.name for p in window.project_field.projects()]))
check("the old pins were dropped, they are not in this root", window.chip_bar.names() == [], str(window.chip_bar.names()))
check("stored for next launch", window.store.path_overrides() == {"shows_root": str(alt_shows)}, str(window.store.path_overrides()))

pin("solo_show")
check("the new root works end to end", window.current_project().name == "solo_show")
check("maya offered", list(window._dcc_buttons) == ["maya"], str(list(window._dcc_buttons)))

print("\nclearing the setting goes back to the default")
cfg_mod.set_path_overrides({})
window.store.set_path_overrides(None)
window.reload_projects()
QApplication.processEvents()
check("original shows back", len(window.project_field.projects()) == 9, str(len(window.project_field.projects())))
check("nothing stored", window.store.path_overrides() == {}, str(window.store.path_overrides()))
unpin_all()
pin("batman_returns")

print("\nsoftware visibility menu")
check("menu lists every registry entry", len(window._software_actions) == 7, str(list(window._software_actions)))
check(
    "checked state matches the defaults",
    [n for n, a in window._software_actions.items() if a.isChecked()]
    == ["houdinicore", "houdinifx", "maya", "nuke"],
    str([n for n, a in window._software_actions.items() if a.isChecked()]),
)

pin("batman_returns")
window._software_actions["blender"].setChecked(True)
QApplication.processEvents()
check("turning one on adds its tile", "blender" in window._dcc_buttons)
check(
    "and it lands in registry order, not click order",
    list(window._dcc_buttons) == ["houdinicore", "houdinifx", "maya", "nuke", "blender"],
    str(list(window._dcc_buttons)),
)
check("preference persisted", "blender" in (window.store.visible_software() or ()), str(window.store.visible_software()))

window._software_actions["houdinifx"].setChecked(False)
QApplication.processEvents()
check("turning one off removes its tile", "houdinifx" not in window._dcc_buttons)
check("persisted", "houdinifx" not in (window.store.visible_software() or ()), str(window.store.visible_software()))

print("\nturning everything off is not the same as an unconfigured show")
for _n in list(window._visible_software):
    window._software_actions[_n].setChecked(False)
QApplication.processEvents()
check("no tiles", not window._dcc_buttons)
check(
    "message says hidden, not unconfigured",
    "all hidden" in window.status_label.text() and "Softwares menu" in window.status_label.text(),
    window.status_label.text(),
)
check("launch disabled", not window.launch_button.isEnabled())
shot(window, "15-all-hidden")

window._on_reset_software()
QApplication.processEvents()
check("reset restores the defaults", list(window._dcc_buttons) == ["houdinicore", "houdinifx", "maya", "nuke"], str(list(window._dcc_buttons)))
check("reset clears the stored preference", window.store.visible_software() is None)
check("menu checkboxes follow", [n for n, a in window._software_actions.items() if a.isChecked()] == ["houdinicore", "houdinifx", "maya", "nuke"])

print("\nlaunching resolves, opens a terminal, and runs the DCC")
from bootycall import config as _cfg  # noqa: E402

check(
    "houdini core runs houdinicore",
    _cfg.dcc_by_name("houdinicore").run_command == "houdinicore",
)
check(
    "houdini fx runs houdini - SideFX names them the other way round",
    _cfg.dcc_by_name("houdinifx").run_command == "houdini",
)
for _name in ("maya", "nuke", "hiero", "blender", "nukestudio"):
    check(
        "%s falls back to its own name" % _name,
        _cfg.dcc_by_name(_name).run_command == _name,
    )

window._dcc_buttons["nuke"].click()
QApplication.processEvents()
launch_argv = launcher.build_command(window.resolved_packages(), window._active_dcc.run_command)
script = launch_argv[-1]
check(
    "opens whichever terminal emulator this host has",
    launch_argv[0] == _cfg.detect_terminal()[0],
    "%s vs detected %s" % (launch_argv[0], _cfg.detect_terminal()[0]),
)
check("runs it through a shell", launch_argv[-3:-1] == ["bash", "-c"], str(launch_argv[-3:-1]))
check("resolves with rez", "rez-env " in script, script[:80])
check(
    "the executable comes last in the command",
    launcher.rez_argv(window.resolved_packages(), "nuke")[-2:] == ["--", "nuke"],
)
check(
    "requests are in the command",
    "nuke-16.0" in script and "base-6" in script,
    script[:120],
)
check(
    "the show package rides along, as it does for the terminal",
    "show_batman_returns" in script,
    script[:160],
)

print("\nthe terminal is held open when the command fails")
check("the command is echoed before it runs", script.startswith('echo "+ rez-env'), script[:40])
check("the exit status is captured", "rc=$?" in script, script[-160:])
check("and reported", "exited with status $rc" in script, script[-160:])
check("with a pause so it can be read", "read -r -p" in script, script[-80:])
check(
    "held only on failure by default, not on every launch",
    '[ "$rc" -ne 0 ]' in script,
    script[-160:],
)

_hold = _cfg.HOLD_TERMINAL
_cfg.HOLD_TERMINAL = "never"
check(
    "hold=never gives the bare command, no wrapper",
    launcher.build_script(("a-1",), "maya") == "rez-env a-1 -- maya",
    launcher.build_script(("a-1",), "maya"),
)
_cfg.HOLD_TERMINAL = "always"
check("hold=always holds unconditionally", "if true; then" in launcher.build_script(("a-1",), "maya"))
_cfg.HOLD_TERMINAL = _hold

print("\nquoting")
check(
    "a request with a space cannot split into two arguments",
    "'a b-1'" in launcher.build_script(("a b-1",), "maya"),
    launcher.build_script(("a b-1",), "maya")[:80],
)

window._dcc_buttons["houdinifx"].click()
QApplication.processEvents()
check(
    "switching DCC changes the executable, not just the packages",
    launcher.rez_argv(
        window.resolved_packages(), window._active_dcc.run_command
    )[-1] == "houdini",
)
window._dcc_buttons["nuke"].click()
QApplication.processEvents()

print("\nterminal tile")
pin("batman_returns")
window._dcc_buttons["nuke"].click()
QApplication.processEvents()
check("terminal tile enabled once a tool is picked", window.terminal_button.isEnabled())
check("terminal tile is not in the exclusive DCC group", window.terminal_button not in window.dcc_group.buttons())
check(
    "no button in the software row - the menu covers it",
    not hasattr(window, "favorites_button"),
)
check("still reachable from the File menu", window.favorites_action in window.file_menu.actions())
check("and by shortcut", window.favorites_action.shortcut().toString() == "Ctrl+B", window.favorites_action.shortcut().toString())

term_pkgs = window.resolved_packages()
check("terminal uses the selected variant's requests", "nuke-16.0" in term_pkgs, str(term_pkgs[:3]))
check(
    "show package appended (its directory exists in the mock tree)",
    term_pkgs[-1] == "show_batman_returns",
    str(term_pkgs[-3:]),
)
check(
    "one more than the resolve list",
    len(term_pkgs) == window.package_list.count() + 1,
    "%d vs %d" % (len(term_pkgs), window.package_list.count()),
)

term_argv = launcher.build_terminal_command(term_pkgs)
term_script = term_argv[-1]
check(
    "terminal argv starts with the same emulator",
    term_argv[0] == _cfg.detect_terminal()[0],
    str(term_argv[:3]),
)
check("goes to rez-env", "rez-env " in term_script, term_script[:60])
check(
    "no application, and no dangling -- either",
    "--" not in launcher.rez_argv(term_pkgs),
    str(launcher.rez_argv(term_pkgs)[-2:]),
)
check(
    "every request is in the command",
    all(p in term_script for p in term_pkgs),
    term_script[:120],
)
print("       %s" % launcher.terminal_preview(window.current_project(), term_pkgs)[:110] + " ...")

pin("finishing_only")
check(
    "no show package where the directory is absent",
    "show_finishing_only" not in window.resolved_packages(),
    str(window.resolved_packages()),
)
unpin_all()
check("terminal tile disabled with no show", not window.terminal_button.isEnabled())
check("no packages, no terminal", window.resolved_packages() == ())

print("\nfavourites window")
from bootycall.configs import SavedConfig as _SC  # noqa: E402
from bootycall.ui.config_menu import ConfigMenuAction  # noqa: E402

for _name in list(window.store.names()):
    window.store.remove(_name)
window.store.add(_SC("Nightly comp", "batman_returns", "nuke", "nuke16"))
window.store.add(_SC("FX lookdev", "dune_pt3", "houdinifx", "houdinifx"))
window.store.add(_SC("Anim", "combat_2", "maya", "maya"))

window.show_favorites()
QApplication.processEvents()
fav = window._favorites_window
check("window opened", fav is not None and fav.isVisible())
check("lists every favourite", fav.list.count() == 3, str(fav.list.count()))
check("first row selected", fav.selected_name() == "Nightly comp", fav.selected_name())
check("row carries name and summary separately", fav.list.item(0).data(Qt.UserRole + 1) == "Nightly comp" and fav.list.item(0).data(Qt.UserRole + 2) == "batman_returns - nuke16", str(fav.list.item(0).data(Qt.UserRole + 2)))
check("up disabled at the top", not fav.up_button.isEnabled())
check("down enabled at the top", fav.down_button.isEnabled())
fav.resize(440, 420)
for _ in range(3):
    QApplication.processEvents()
fav.grab().save(str(OUT / "14-favourites.png"))

print("\nreordering")
fav.list.setCurrentRow(2)
check("up enabled in the middle/end", fav.up_button.isEnabled())
check("down disabled at the bottom", not fav.down_button.isEnabled())
fav._on_move(-1)
QApplication.processEvents()
check(
    "moved up in the store",
    window.store.names() == ["Nightly comp", "Anim", "FX lookdev"],
    str(window.store.names()),
)
check("selection follows the row", fav.selected_name() == "Anim", fav.selected_name())
check("persisted", [c.name for c in type(window.store)(window.store.path)] == ["Nightly comp", "Anim", "FX lookdev"])
check(
    "File menu picks up the new order",
    [a.config.name for a in window.file_menu.actions() if isinstance(a, ConfigMenuAction)]
    == ["Nightly comp", "Anim", "FX lookdev"],
)
fav._on_move(1)
QApplication.processEvents()
check("and back down", window.store.names() == ["Nightly comp", "FX lookdev", "Anim"], str(window.store.names()))
check("moving past the end is a no-op, not an error", window.store.move("Anim", 1) == "")
check("still three", len(window.store) == 3)

print("\nrename")
check("rename succeeds", window.store.rename("Anim", "Anim dailies") == "")
check("position kept", window.store.names() == ["Nightly comp", "FX lookdev", "Anim dailies"], str(window.store.names()))
check("collision refused", "already exists" in window.store.rename("Anim dailies", "Nightly comp"))
check("empty name refused", "needs a name" in window.store.rename("Anim dailies", "   "))
check("unknown name refused", "No favourite named" in window.store.rename("ghost", "x"))
check("nothing lost", len(window.store) == 3)
fav.refresh()
QApplication.processEvents()
check("window reflects the rename", "Anim dailies" in [fav.list.item(i).data(Qt.UserRole + 1) for i in range(fav.list.count())])

print("\nloading from the favourites window")
unpin_all()
fav._select("Nightly comp")
fav._on_open()
QApplication.processEvents()
check("show loaded", window.current_project().name == "batman_returns")
check("dcc loaded", window._active_dcc.name == "nuke")
check("variant loaded", window._current_tool() == "nuke16")

print("\nempty state")
for _name in list(window.store.names()):
    window.store.remove(_name)
fav.refresh()
QApplication.processEvents()
check("list empty", fav.list.count() == 0)
check("subtitle explains", "Nothing saved yet" in fav.subtitle.text(), fav.subtitle.text())
check("edit buttons disabled", not fav.rename_button.isEnabled() and not fav.remove_button.isEnabled())
check("load disabled", not fav.open_button.isEnabled())
fav.close()
QApplication.processEvents()

unpin_all()

print("\nsaved setups: File menu")
from bootycall.configs import SavedConfig  # noqa: E402
from bootycall.ui.config_menu import ConfigMenuAction  # noqa: E402


def menu_texts() -> list[str]:
    out = []
    for action in window.file_menu.actions():
        if isinstance(action, ConfigMenuAction):
            out.append("[cfg] %s" % action.config.name)
        elif action.isSeparator():
            out.append("---")
        else:
            out.append(action.text())
    return out


window._rebuild_file_menu()
check(
    "empty menu shows a placeholder",
    "   Nothing saved yet" in menu_texts(),
    str(menu_texts()),
)
check("save disabled with no show", not window.save_action.isEnabled())

pin("batman_returns")
window._dcc_buttons["nuke"].click()
window.set_variant("nuke", "nuke16")
QApplication.processEvents()
check("save enabled once a tool is picked", window.save_action.isEnabled())
check("the save-setup button is gone", not hasattr(window, "save_button"))

suggested = window.store.suggest_name("batman_returns", "Nuke 16.0")
check("suggested name", suggested == "batman_returns - Nuke 16.0", suggested)

# Save without driving the modal dialog.
state = window._current_state()
check("current state complete", state is not None)
project, dcc, tool = state
check("state show", project.name == "batman_returns")
check("state dcc", dcc.name == "nuke")
check("state tool", tool == "nuke16")
window.store.add(SavedConfig("Nightly comp", project.name, dcc.name, tool))

window._dcc_buttons["houdinicore"].click()
QApplication.processEvents()
window.store.add(SavedConfig("FX lookdev", "dune_pt3", "houdini", "houdinifx"))
window._rebuild_file_menu()

texts = menu_texts()
check("save entry first", texts[0].startswith("&Save current setup"), str(texts[:2]))
check("header present", "Saved setups" in texts, str(texts))
check("both configs listed", texts.count("[cfg] Nightly comp") == 1 and texts.count("[cfg] FX lookdev") == 1, str(texts))
check("placeholder gone", "   Nothing saved yet" not in texts)
check("reload still present", "&Reload shows" in texts)
check("quit still present", "&Quit" in texts)

print("\nsaved setup rows carry a remove button")
rows = [a for a in window.file_menu.actions() if isinstance(a, ConfigMenuAction)]
check("two rows", len(rows) == 2)
row = rows[0]
check("label is the config name", row.item.label.text() == "Nightly comp")
check("detail shows show + tool", row.item.detail.text() == "batman_returns - nuke16", row.item.detail.text())
check("remove button present", row.item.remove_button.text() == "✕")
check(
    "remove tooltip names the config",
    "Nightly comp" in row.item.remove_button.toolTip(),
    row.item.remove_button.toolTip(),
)

print("\napplying a setup restores show + DCC + variant")
unpin_all()
check("cleared", window.current_project() is None)
window._on_apply_config("Nightly comp")
QApplication.processEvents()
check("show restored", window.current_project().name == "batman_returns")
check("dcc restored", window._active_dcc.name == "nuke")
check("variant restored", window._current_tool() == "nuke16")
check("launch enabled", window.launch_button.isEnabled())
shot(window, "09-applied-setup")

print("\nthe x removes the row and persists")
rows[1].item.remove_button.click()
QApplication.processEvents()
check("store updated", window.store.names() == ["Nightly comp"], str(window.store.names()))
check("persisted", [c.name for c in type(window.store)(window.store.path)] == ["Nightly comp"])
remaining = [a for a in window.file_menu.actions() if isinstance(a, ConfigMenuAction)]
check("row dropped from the menu", len(remaining) == 1, str([a.config.name for a in remaining]))
check("other row untouched", remaining[0].config.name == "Nightly comp")

print("\nremoving the last one restores the placeholder")
remaining[0].item.remove_button.click()
QApplication.processEvents()
window._rebuild_file_menu()
check("store empty", len(window.store) == 0)
check("placeholder back", "   Nothing saved yet" in menu_texts(), str(menu_texts()))
check("no crash", True)

print("\nstale setups fail loudly, not silently")
window.store.add(SavedConfig("Gone show", "deleted_show", "nuke", "nuke16"))
window._on_apply_config("Gone show")
QApplication.processEvents()
check("missing show reported", "no longer in" in window.status_label.text(), window.status_label.text())

window.store.add(SavedConfig("Wrong dcc", "finishing_only", "maya", "maya"))
window._on_apply_config("Wrong dcc")
QApplication.processEvents()
check(
    "missing dcc reported",
    "does not offer" in window.status_label.text(),
    window.status_label.text(),
)

window.store.add(SavedConfig("Wrong tool", "finishing_only", "nuke", "nuke"))
window._on_apply_config("Wrong tool")
QApplication.processEvents()
check(
    "missing tool reported",
    "no longer defined" in window.status_label.text(),
    window.status_label.text(),
)
check("no crash on any stale setup", True)

for name in list(window.store.names()):
    window.store.remove(name)
window._rebuild_file_menu()

print("\nmissing shows root")
os.environ["BOOTYCALL_SHOWS_ROOT"] = "/tmp/does/not/exist"
import importlib  # noqa: E402

from bootycall import config as cfg  # noqa: E402

importlib.reload(cfg)
window.reload_projects()
QApplication.processEvents()
check("no shows", window.project_field.projects() == [])
check("error surfaced", "cannot list" in window.status_label.text(), window.status_label.text())
check("no crash", True)

print()
if failures:
    print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
    raise SystemExit(1)
print("all UI checks passed -- screenshots in %s" % OUT)
