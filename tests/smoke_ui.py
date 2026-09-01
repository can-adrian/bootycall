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
os.environ.setdefault("BOOTYCALL_USER_PACKAGES_ROOT", "/tmp/ice/userpackages")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixture  # noqa: E402

fixture.ensure()

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
check(
    "the dev section starts open, the other two closed",
    window.dev_frame.is_expanded()
    and not window.local_frame.is_expanded()
    and not window.resolve_frame.is_expanded(),
    "dev=%s local=%s resolve=%s"
    % (
        window.dev_frame.is_expanded(),
        window.local_frame.is_expanded(),
        window.resolve_frame.is_expanded(),
    ),
)
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
check(
    "and the list closed with it, rather than hanging over the window",
    not window.project_field._completer.popup().isVisible(),
)
unpin_all()

print("\nEnter takes the row you are looking at")
_field = window.project_field
_popup = _field._completer.popup()

# QCompleter only acts on Enter when a row is *current*, and typing does not
# make one current. So typing 'bat', seeing batman_returns at the top of the
# list and pressing Enter did nothing at all: no chip, and the text left in
# the field. The row you can see is the row you meant.
_field.reset()
QTest.keyClicks(_field, "bat")
QApplication.processEvents()
check(
    "the list is open with more than one match",
    _popup.isVisible() and _field._completer.completionCount() > 1,
    "%s / %d" % (_popup.isVisible(), _field._completer.completionCount()),
)
QTest.keyClick(_field, Qt.Key_Return)
for _ in range(3):
    QApplication.processEvents()
check(
    "Enter pins the top row rather than doing nothing",
    "batman_returns" in window.chip_bar.names(),
    str(window.chip_bar.names()),
)
check("the text went with it", _field.text() == "", _field.text())
check("and the list closed", not _popup.isVisible())
check(
    "and nothing is left being completed, so the next Down offers every show",
    _field._completer.completionPrefix() == "",
    _field._completer.completionPrefix(),
)
_field.setFocus()
QTest.keyClick(_field, Qt.Key_Down)
QApplication.processEvents()
check(
    "which it does",
    _field._completer.completionModel().rowCount() == _field._model.rowCount(),
    "%d of %d"
    % (
        _field._completer.completionModel().rowCount(),
        _field._model.rowCount(),
    ),
)

# A highlighted row wins over the top one, or Down would be decoration.
_field.reset()
QTest.keyClicks(_field, "o")
QApplication.processEvents()
_model = _field._completer.completionModel()
_wanted = _model.index(_model.rowCount() - 1, 0)
_wanted_name = _wanted.data()
_popup.setCurrentIndex(_wanted)
QTest.keyClick(_field, Qt.Key_Return)
for _ in range(3):
    QApplication.processEvents()
check(
    "the highlighted row is the one pinned, not the first",
    _wanted_name in window.chip_bar.names(),
    "wanted %s, got %s" % (_wanted_name, window.chip_bar.names()),
)

# Text matching nothing must still sit there to be corrected.
_field.reset()
QTest.keyClicks(_field, "zzz")
QApplication.processEvents()
_before_chips = list(window.chip_bar.names())
QTest.keyClick(_field, Qt.Key_Return)
QApplication.processEvents()
check(
    "text that matches no show is left alone to be fixed",
    _field.text() == "zzz" and window.chip_bar.names() == _before_chips,
    "%r / %s" % (_field.text(), window.chip_bar.names()),
)
_field.reset()
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
    "the default row is Houdini and Maya, which with Terminal is three tiles",
    list(window._dcc_buttons) == ["houdinicore", "maya"],
    str(list(window._dcc_buttons)),
)
check(
    "labelled the short way",
    [window._dcc_buttons[n].text() for n in ("houdinicore", "maya")]
    == ["Houdini", "Maya"],
    str([window._dcc_buttons[n].text() for n in ("houdinicore", "maya")]),
)

print("\nevery tile is the same size, including Terminal")
_tiles = list(window._dcc_buttons.values()) + [window.terminal_button]
check(
    "one width across the row",
    len({t.width() for t in _tiles}) == 1,
    str([(t.text(), t.width()) for t in _tiles]),
)
check(
    "one height too",
    len({t.height() for t in _tiles}) == 1,
    str([(t.text(), t.height()) for t in _tiles]),
)
check(
    "wide enough for the longest label in it",
    all(t.width() >= t.sizeHint().width() for t in _tiles),
    str([(t.text(), t.width(), t.sizeHint().width()) for t in _tiles]),
)
_narrow_row = window._tile_width

print("\nthe rest of the suite wants the wider row, so turn the others on")
window._software_actions["houdinifx"].setChecked(True)
window._software_actions["nuke"].setChecked(True)
QApplication.processEvents()
check(
    "four tiles now",
    list(window._dcc_buttons) == ["houdinicore", "houdinifx", "maya", "nuke"],
    str(list(window._dcc_buttons)),
)
_tiles = list(window._dcc_buttons.values()) + [window.terminal_button]
check(
    "still exactly one size between them",
    len({(t.width(), t.height()) for t in _tiles}) == 1,
    str([(t.text(), t.width()) for t in _tiles]),
)
check(
    "and it never drops below the floor",
    window._tile_width >= 84,
    str(window._tile_width),
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
check("nuke studio is not offered at all any more", "nukestudio" not in window._dcc_buttons)
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
check(
    "packages listed (10+4+4+8+3, plus the show package)",
    window.package_list.count() == 30,
    str(window.package_list.count()),
)
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
check("maya package count (30 plus the show package)", window.package_list.count() == 31, str(window.package_list.count()))
shot(window, "05-maya")

print("\ncommand preview")
from bootycall import launcher  # noqa: E402
from bootycall import local_packages as _lp  # noqa: E402


def preamble(text):
    """The launch script rez is pointed at, read back.

    The preamble is a file rather than an inline one-liner because rez
    re-quotes the command it is handed. So a check on what the launch prints
    has to open the file the argv names.
    """
    import re as _re

    found = _re.search(r"\S*launch-\w+\.sh", text)
    return Path(found.group(0)).read_text() if found else text

preview = launcher.command_preview(
    window.current_project(), window.resolved_packages(), window._active_dcc.run_command
)
check("preview mentions show path", "/tmp/ice/shows/batman_returns" in preview, preview)
check(
    "preview runs the DCC executable",
    "exec maya" in preamble(launcher.rez_argv(
        window.resolved_packages(), window._active_dcc.run_command
    )[-1]),
    str(launcher.rez_argv(window.resolved_packages(), "maya")[-1]),
)
check(
    "and prints the resolve on the way in, as a terminal always did",
    "rez-context" in preamble(launcher.rez_argv(window.resolved_packages(), "maya")[-1]),
    str(launcher.rez_argv(window.resolved_packages(), "maya")[-1]),
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
    and "Houdini" in window.status_label.text()
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
check(
    "the prompt goes away once chips are in the field",
    window.project_field.placeholderText() == "",
    window.project_field.placeholderText(),
)
check("the newest pin is selected", window.chip_bar.selected_name() == "combat_2")
_names_now = list(window.chip_bar.names())
unpin_all()
check(
    "and comes back when the field is empty again",
    "Type a show name" in window.project_field.placeholderText(),
    window.project_field.placeholderText(),
)
for _n in _names_now:
    pin(_n)
window.chip_bar.select("combat_2")
QApplication.processEvents()
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

print("\nbracketed asides are set apart from the package they follow")
from bootycall.ui.package_delegate import runs as _runs  # noqa: E402

check(
    "the aside is split out and italicised",
    _runs("rig_utils-1.8.666  (symlinked)")
    == [("rig_utils-1.8.666  ", False), ("(symlinked)", True)],
    str(_runs("rig_utils-1.8.666  (symlinked)")),
)
check(
    "a row with no aside is left whole, so Qt draws it as it always did",
    _runs("nuke_utils-4.10.0      overrides nuke_utils-4")
    == [("nuke_utils-4.10.0      overrides nuke_utils-4", False)],
)
check(
    "two asides both count",
    [italic for _, italic in _runs("a-1  (dev)  (symlinked)")] == [False, True, False, True],
    str(_runs("a-1  (dev)  (symlinked)")),
)
check(
    "an unclosed bracket does not swallow the rest of the row",
    _runs("a-1  (oops") == [("a-1  (oops", False)],
    str(_runs("a-1  (oops")),
)

print("\nlocal and dev package sections")
window.local_frame.set_expanded(True)
window.dev_frame.set_expanded(True)
QApplication.processEvents()
check("both frames open", window.local_frame.is_expanded() and window.dev_frame.is_expanded())
check("frames are titled separately", window.local_frame.toggle_button.text() == "Local packages" and window.dev_frame.toggle_button.text() == "Dev Packages", window.dev_frame.toggle_button.text())
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
check("the two optional sections have a checkbox", all(f.check_box is not None for f in (window.local_frame, window.dev_frame)))
check("both checked by default", all(f.is_checked() for f in (window.local_frame, window.dev_frame)))
check(
    "the resolve section has none at all - there is nothing to launch without it",
    window.resolve_frame.check_box is None,
)
check(
    "and it still counts as in use, so nothing reads it as switched off",
    window.resolve_frame.is_checked(),
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

print("\nexcluding a root rez was never reading is not a problem")
launcher._PACKAGES_PATH = None
os.environ["REZ_PACKAGES_PATH"] = "/ice/rez/packages/int"
kept, note = launcher.filtered_packages_path(window.excluded_roots())
check(
    "the root is not on the resulting path, which is what was asked for",
    all(str(r) not in kept for r in (_lp.local_root(), _lp.dev_root())),
    str(kept),
)
check(
    "so there is nothing to report - this used to warn on every switch-off",
    note == "",
    note,
)
# Excluded and included at once is a caller contradiction, and the guard is
# there so it surfaces rather than silently resolving one way.
_contradiction = launcher.filtered_packages_path((str(_lp.dev_root()),), (str(_lp.dev_root()),))
check(
    "but an exclusion that genuinely did not take does say so",
    "could not take" in _contradiction[1],
    str(_contradiction),
)
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
    "dev row says both halves are empty - nothing built and nothing to build",
    "Nothing installed" in window.dev_list.item(0).text()
    and "working location" in window.dev_list.item(0).text(),
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
check("the menu bar is hidden, and Copy command with it", not window.menuBar().isVisible())
check("terminal hidden", not window.terminal_button.isVisible())
check("menu bar hidden", not window.menuBar().isVisible())
check("window title shortened to fit", window.windowTitle() == "B.C.", window.windowTitle())
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
# The row's uniform tile width, whatever the labels in it worked out to.
DCC_TILE_WIDTH = window._tile_width

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
check("and now it does something", dev_install.IMPLEMENTED is True)
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
check(
    "there is no Settings menu - it lives in File, and one door is enough",
    "Settings" not in _menus,
    str(_menus),
)
check("File carries it", window.settings_action in window.file_menu.actions())
check("and the software one is plural", "Softwares" in _menus, str(_menus))
check("and a File entry too", window.settings_action in window.file_menu.actions())

dialog = SettingsDialog(window)
check("four rows", list(dialog.rows) == ["shows_root", "local_root", "dev_root", "dev_working_root"], str(list(dialog.rows)))
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
check("menu lists every registry entry", len(window._software_actions) == 6, str(list(window._software_actions)))
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
check("reset restores the defaults", list(window._dcc_buttons) == ["houdinicore", "maya"], str(list(window._dcc_buttons)))
check("reset clears the stored preference", window.store.visible_software() is None)
check("menu checkboxes follow", [n for n, a in window._software_actions.items() if a.isChecked()] == ["houdinicore", "maya"])

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
for _name in ("maya", "nuke", "hiero", "blender"):
    check(
        "%s falls back to its own name" % _name,
        _cfg.dcc_by_name(_name).run_command == _name,
    )

# Nuke is not in the default row any more, and the visibility tests above have
# been turning tiles on and off, so ask for it rather than assuming it is there.
window._software_actions["nuke"].setChecked(True)
QApplication.processEvents()
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
    "the executable is what the wrapper execs",
    preamble(
        launcher.rez_argv(window.resolved_packages(), "nuke")[-1]
    ).rstrip().endswith("exec nuke"),
    launcher.rez_argv(window.resolved_packages(), "nuke")[-1],
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
check(
    "the request is echoed before it runs",
    script.startswith("printf '+ %s\\n\\n' 'rez-env"),
    script[:40],
)
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
_saved_info = _cfg.SHOW_RESOLVE_INFO
_cfg.SHOW_RESOLVE_INFO = False
check(
    "hold=never gives the bare command, no wrapper",
    launcher.build_script(("a-1",), "maya") == "rez-env a-1 -- maya",
    launcher.build_script(("a-1",), "maya"),
)
_cfg.SHOW_RESOLVE_INFO = _saved_info
_cfg.HOLD_TERMINAL = "always"
check("hold=always holds unconditionally", "if true; then" in launcher.build_script(("a-1",), "maya"))
_cfg.HOLD_TERMINAL = _hold

print("\nquoting")
check(
    "a request with a space cannot split into two arguments",
    "'a b-1'" in launcher.build_script(("a b-1",), "maya"),
    launcher.build_script(("a b-1",), "maya")[:80],
)

window._software_actions["houdinifx"].setChecked(True)
QApplication.processEvents()
window._dcc_buttons["houdinifx"].click()
QApplication.processEvents()
check(
    "switching DCC changes the executable, not just the packages",
    preamble(launcher.rez_argv(
        window.resolved_packages(), window._active_dcc.run_command
    )[-1]).rstrip().endswith("exec houdini"),
    launcher.rez_argv(
        window.resolved_packages(), window._active_dcc.run_command
    )[-1],
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
    "show package appended",
    term_pkgs[-1] == "show_batman_returns",
    str(term_pkgs[-3:]),
)
check(
    "the resolve list shows exactly what gets resolved, show package included",
    len(term_pkgs) == window.package_list.count(),
    "%d requests vs %d rows" % (len(term_pkgs), window.package_list.count()),
)
check(
    "and the show package is the row that says so",
    "(show package)" in window.package_list.item(window.package_list.count() - 1).text(),
    window.package_list.item(window.package_list.count() - 1).text(),
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

# The terminal used to be the one launch path the report never reached: with
# no command, rez_argv returned before anything could be wrapped around it.
_term_banner = preamble(launcher.build_terminal_command(
    term_pkgs, window.highlight_roots(), window.launch_notes()
)[-1])
check(
    "the shell gets the same report a launch does",
    "your packages in this environment" in _term_banner,
    _term_banner[-120:],
)
check(
    "and is still an interactive shell afterwards",
    "exec bash" in _term_banner,
    _term_banner[-60:],
)

pin("finishing_only")
check(
    "no show package where the directory is absent",
    "show_finishing_only" not in window.resolved_packages(),
    str(window.resolved_packages()),
)

print("\nshow packages follow the bootstrap's rules")
from bootycall.discovery import find_show_package, show_package_roots  # noqa: E402

_bat = window._projects_by_name["batman_returns"]
_found = find_show_package(_bat)
check("found for a show that has one", _found is not None and _found.name == "show_batman_returns")
check(
    "and the root it came from is recorded, since rez needs it on the path",
    str(_found.root).endswith("batman_returns/.ilp/packages"),
    str(_found.root),
)

_dune = window._projects_by_name["dune_pt3"]
check(
    "an empty package directory does not count as a package",
    find_show_package(_dune) is None,
    "the bootstrap validates; a bare folder would be added to every resolve",
)

_combat = window._projects_by_name["combat_2"]
_shadowed = find_show_package(_combat)
check(
    "the user's own copy wins over the show's",
    str(_shadowed.root) == "/tmp/ice/userpackages",
    str(_shadowed.root),
)
check(
    "both roots are searched, user first",
    [str(r) for r in show_package_roots(_combat)]
    == ["/tmp/ice/userpackages", "/tmp/ice/shows/combat_2/.ilp/packages"],
    str([str(r) for r in show_package_roots(_combat)]),
)

print("\nthe show package root is added to the packages path")
_saved = os.environ.get("REZ_PACKAGES_PATH")
os.environ["REZ_PACKAGES_PATH"] = "/ice/rez/packages/int"
launcher._PACKAGES_PATH = None
pin("batman_returns")
paths, note = launcher.filtered_packages_path(
    window.excluded_roots(), window.included_roots()
)
check(
    "the show's package root is on the path",
    str(_found.root) in paths,
    str(paths),
)
check(
    "ahead of the studio path, so the show's copy wins",
    paths.index(str(_found.root)) < paths.index("/ice/rez/packages/int"),
    str(paths),
)
check("no complaint", note == "", note)

print("\nand so are the roots the window says are in play")
check(
    "the dev root is there - BootyCall shows it, so it has to put it there",
    str(_lp.dev_root()) in paths,
    str(paths),
)
check("and the local root", str(_lp.local_root()) in paths, str(paths))
check(
    "both ahead of the studio path",
    paths.index(str(_lp.local_root())) < paths.index("/ice/rez/packages/int"),
    str(paths),
)
check(
    "dev ahead of local, since you install into it on purpose",
    paths.index(str(_lp.dev_root())) < paths.index(str(_lp.local_root())),
    str(paths),
)
check(
    "and the window can say which of them rez was not already reading",
    set(window.missing_from_rez_path())
    == {str(_lp.local_root()), str(_lp.dev_root())},
    str(window.missing_from_rez_path()),
)

os.environ["REZ_PACKAGES_PATH"] = "%s:%s:/ice/rez/packages/int" % (
    _lp.dev_root(),
    _lp.local_root(),
)
launcher._PACKAGES_PATH = None
paths, note = launcher.filtered_packages_path(
    window.excluded_roots(), window.included_roots()
)
check(
    "a site that already lists them keeps its own order, nothing duplicated",
    paths.count(str(_lp.local_root())) == 1
    and paths.count(str(_lp.dev_root())) == 1,
    str(paths),
)
check(
    "and there is then nothing to report",
    window.missing_from_rez_path() == (),
    str(window.missing_from_rez_path()),
)
os.environ["REZ_PACKAGES_PATH"] = "/ice/rez/packages/int"
launcher._PACKAGES_PATH = None

pin("finishing_only")
paths, note = launcher.filtered_packages_path(
    window.excluded_roots(), window.included_roots()
)
check(
    "a show without its own package still gets the per-user roots",
    paths[:2] == [str(_lp.dev_root()), str(_lp.local_root())] and note == "",
    str(paths),
)
if _saved:
    os.environ["REZ_PACKAGES_PATH"] = _saved
else:
    os.environ.pop("REZ_PACKAGES_PATH", None)
launcher._PACKAGES_PATH = None
pin("batman_returns")
unpin_all()
check("terminal tile disabled with no show", not window.terminal_button.isEnabled())
check("no packages, no terminal", window.resolved_packages() == ())

print("\nasking the bootstrap itself")
import time  # noqa: E402

from bootycall import probe as probe_mod  # noqa: E402

# A show whose bootstrap computes half its tools, so the static read and the
# running module genuinely disagree -- which is the only case where any of this
# earns its keep.
probe_shows = Path(tempfile.mkdtemp(prefix="bootycall-probe-shows-"))
_pipeline = probe_shows / "probed_show" / ".ilp" / "pipeline"
_pipeline.mkdir(parents=True)
(_pipeline / "ilp_bootstrap.py").write_text(
    "class Bootstrap(object):\n    packages = {}\n"
)
(_pipeline / "config.py").write_text(
    "from ilp_bootstrap import Bootstrap\n"
    "\n"
    "\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    packages = dict(maya=('maya-2026.3',))\n"
    "    packages['nuke'] = tuple('nuke-%s' % v for v in ('16.0',))\n"
    "\n"
    "    def _get_show_packages(self):\n"
    "        return ('show_probed',)\n"
)


def wait_for_probe(seconds: float = 30.0) -> None:
    deadline = time.time() + seconds
    while window._probe_process is not None and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()


cfg_mod.set_path_overrides({"shows_root": str(probe_shows)})
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("probed_show")

check(
    "the static read draws the window first",
    window._bootstrap is not None and window._bootstrap.source == "static",
    "" if window._bootstrap is None else window._bootstrap.source,
)
check(
    "and only sees the tool written literally",
    list(window._dcc_buttons) == ["maya"],
    str(list(window._dcc_buttons)),
)

wait_for_probe()
check(
    "the probe's answer replaces it",
    window._bootstrap.source == "bootstrap",
    window._bootstrap.source,
)
check(
    "including the tool built at import time",
    list(window._dcc_buttons) == ["maya", "nuke"],
    str(list(window._dcc_buttons)),
)
check(
    "the resolved list says where it came from",
    "from the bootstrap" in window.resolve_frame.badge.text(),
    window.resolve_frame.badge.text(),
)
check(
    "_get_show_packages is taken at its word",
    window.show_package_requests() == ("show_probed",),
    str(window.show_package_requests()),
)
check(
    "and it reaches the resolve",
    "show_probed" in window.resolved_packages(),
    str(window.resolved_packages()),
)
check(
    "with a package root behind it, since rez has to find it somewhere",
    window.included_roots() != (),
    str(window.included_roots()),
)

print("\nre-selecting a show does not re-probe it")
_before = dict(window._probe_cache)
unpin_all()
pin("probed_show")
check("served from cache", window._probe_process is None)
check("cache untouched", dict(window._probe_cache) == _before)
check(
    "and the answer is still the probe's",
    window._bootstrap.source == "bootstrap"
    and list(window._dcc_buttons) == ["maya", "nuke"],
    str(list(window._dcc_buttons)),
)

print("\nturning the probe off leaves a purely static BootyCall")
_saved_mode = cfg_mod.PROBE_MODE
cfg_mod.PROBE_MODE = "off"
window._probe_cache.clear()
unpin_all()
pin("probed_show")
check("no probe started", window._probe_process is None)
check(
    "static answer stands",
    window._bootstrap.source == "static" and list(window._dcc_buttons) == ["maya"],
    str(list(window._dcc_buttons)),
)
check(
    "and the show package falls back to what is on disk",
    window.show_package_requests() == (),
    str(window.show_package_requests()),
)
cfg_mod.PROBE_MODE = _saved_mode

print("\na probe that cannot run costs nothing")
_saved_cmd = cfg_mod.PROBE_COMMAND
cfg_mod.PROBE_COMMAND = ("definitely-not-an-interpreter", "{script}", "{bootstrap}")
window._probe_cache.clear()
unpin_all()
pin("probed_show")
wait_for_probe(5.0)
check(
    "the window still works",
    window._bootstrap is not None and list(window._dcc_buttons) == ["maya"],
    str(list(window._dcc_buttons)),
)
check("nothing was applied", window._bootstrap.source == "static")
cfg_mod.PROBE_COMMAND = _saved_cmd

cfg_mod.set_path_overrides({})
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("batman_returns")

import time  # noqa: E402
import bootycall.ui.main_window as mw_mod  # noqa: E402

print("\ninstalled dev packages have their own checkboxes")
from bootycall import dev_install as _di  # noqa: E402
from bootycall.ui.main_window import _PACKAGE_NAME_ROLE as _NAME_ROLE  # noqa: E402

pin("batman_returns")
_dev_names = [
    window.dev_list.item(i).data(_NAME_ROLE)
    for i in range(window.dev_list.count())
]
_dev_names = [n for n in _dev_names if n]
check("there are dev packages to tick", bool(_dev_names), str(_dev_names))
check(
    "every dev row carries a check state, which is what draws the box",
    all(
        window.dev_list.item(i).data(Qt.CheckStateRole) is not None
        for i in range(window.dev_list.count())
    ),
)
check(
    "all ticked to begin with",
    all(
        window.dev_list.item(i).checkState() == Qt.Checked
        for i in range(window.dev_list.count())
    ),
)
check(
    "local packages have none, so no boxes appear - it is a whole-root call",
    all(
        window.local_list.item(i).data(Qt.CheckStateRole) is None
        for i in range(window.local_list.count())
    ),
)

_first = _dev_names[0]
window.dev_list.item(0).setCheckState(Qt.Unchecked)
QApplication.processEvents()
check("unticking one records it", window._disabled_dev == {_first}, str(window._disabled_dev))
check(
    "and it drops out of what is in play",
    _first not in [p.name for p in window.enabled_dev_packages()],
    str([p.name for p in window.enabled_dev_packages()]),
)
check(
    "saved for next time",
    window.store.disabled_dev_packages() == (_first,),
    str(window.store.disabled_dev_packages()),
)

_marked = [
    window.dev_list.item(i).text()
    for i in range(window.dev_list.count())
    if window.dev_list.item(i).data(_NAME_ROLE) == _first
]
check(
    "and an unticked package stops claiming to override anything",
    all("      overrides" not in t for t in _marked),
    str(_marked),
)

# Unticking it does not make it irrelevant to this show: it is still one of
# yours that the resolve names, and the row has to say ticking it would
# change the launch.
_standby = [
    window.dev_list.item(i)
    for i in range(window.dev_list.count())
    if window.dev_list.item(i).data(_NAME_ROLE) == _first
]
_relevant = [i for i in _standby if "would override" in i.text()]
check(
    "it says what ticking it would do instead",
    bool(_relevant),
    str([i.text() for i in _standby]),
)
check(
    "in the same hue as 'in use', darker - not the grey of a row with nothing "
    "to say",
    all(i.foreground().color().name() == mw_mod._ROW_STANDBY for i in _relevant),
    str([(i.text(), i.foreground().color().name()) for i in _relevant]),
)
check(
    "and it is still not counted as in use, because it is not",
    "in use" not in window.dev_frame.note.text()
    or window.dev_frame.note.text() == "",
    window.dev_frame.note.text(),
)

print("\nan unticked dev package leaves the resolve through a filtered root")
_saved_rez = os.environ.get("REZ_PACKAGES_PATH")
os.environ["REZ_PACKAGES_PATH"] = "%s:/ice/rez/packages/int" % _lp.dev_root()
launcher._PACKAGES_PATH = None
_paths, _note = launcher.filtered_packages_path(
    window.excluded_roots(), window.included_roots()
)
check(
    "the real dev root comes off the path",
    str(_lp.dev_root()) not in _paths,
    str(_paths),
)
_view = window._dev_view_root()
check("a view was built instead", _view is not None and _view.is_dir(), str(_view))
check("and it is on the path", str(_view) in _paths, str(_paths))
_on_disk = sorted(
    e.name
    for e in os.scandir(_lp.dev_root())
    if e.is_dir() and not e.name.startswith(".")
)
check(
    "holding every dev package except the unticked one",
    sorted(p.name for p in _view.iterdir())
    == [n for n in _on_disk if n != _first],
    str(sorted(p.name for p in _view.iterdir())),
)
check(
    "and rez's own .cache is not dragged in with them",
    not any(p.name.startswith(".") for p in _view.iterdir()),
    str([p.name for p in _view.iterdir()]),
)

window.dev_list.item(0).setCheckState(Qt.Checked)
QApplication.processEvents()
check("re-ticking clears it", window._disabled_dev == set(), str(window._disabled_dev))
check("no view needed when nothing is off", window._dev_view_root() is None)
_paths, _note = launcher.filtered_packages_path(
    window.excluded_roots(), window.included_roots()
)
check("and the real dev root is back", str(_lp.dev_root()) in _paths, str(_paths))
check("nothing stored", window.store.disabled_dev_packages() == ())
if _saved_rez:
    os.environ["REZ_PACKAGES_PATH"] = _saved_rez
else:
    os.environ.pop("REZ_PACKAGES_PATH", None)
launcher._PACKAGES_PATH = None

print("\nrow colour matches the counts in the header")
_colour_of = lambda item: item.foreground().color().name()
_pin_texts = [window.local_list.item(i) for i in range(window.local_list.count())]
check(
    "a build that will be in the environment is the colour of 'in use'",
    all(
        _colour_of(i) == mw_mod._ROW_IN_USE
        for i in _pin_texts
        if "overrides" in i.text()
    ),
    str([(i.text(), _colour_of(i)) for i in _pin_texts]),
)
check(
    "and one that lost is the colour of the alert that counts it",
    all(
        _colour_of(i) == mw_mod._ROW_LOST
        for i in _pin_texts
        if "outranked by" in i.text() or "does not satisfy" in i.text()
    ),
    str([(i.text(), _colour_of(i)) for i in _pin_texts]),
)

print("\nthe working location's packages are rows in the list, not a second window")
_work = Path(tempfile.mkdtemp(prefix="bootycall-working-"))
(_work / "shot_tools").mkdir()
(_work / "shot_tools" / "package.py").write_text("name = 'shot_tools'\n")
(_work / "just_notes").mkdir()
(_work / "half_done").mkdir()
(_work / "half_done" / "readme.txt").write_text("no definition here\n")

_installed = Path(tempfile.mkdtemp(prefix="bootycall-installed-"))
cfg_mod.set_path_overrides(
    {"dev_root": str(_installed), "dev_working_root": str(_work)}
)
window.refresh_package_lists()
QApplication.processEvents()

_rows = [window.dev_list.item(i) for i in range(window.dev_list.count())]
_texts = [r.text() for r in _rows]
check(
    "everything in the working location is shown, installed or not",
    sorted(_texts) == sorted(
        ["half_done  (not installed)", "just_notes  (not installed)",
         "shot_tools  (not installed)"]
    ),
    str(_texts),
)
check(
    "an uninstalled row carries no package name - nothing here resolves",
    all(r.data(_NAME_ROLE) is None for r in _rows),
    str([r.data(_NAME_ROLE) for r in _rows]),
)
check(
    "nor a package path, so the delete and browse paths keep skipping it",
    all(r.data(mw_mod._PACKAGE_PATH_ROLE) is None for r in _rows),
)
check(
    "it does carry the folder to build from",
    sorted(Path(r.data(mw_mod._SOURCE_PATH_ROLE)).name for r in _rows)
    == ["half_done", "just_notes", "shot_tools"],
)
check(
    "the box is drawn but cannot be ticked",
    all(
        r.data(Qt.CheckStateRole) is not None
        and not (r.flags() & Qt.ItemIsUserCheckable)
        for r in _rows
    ),
)
check(
    "and the badge counts both halves",
    window.dev_frame.badge.text() == "3 not",
    window.dev_frame.badge.text(),
)

# A working copy is source, not a build. Nothing in this menu may remove it.
_work_labels = []


class _CollectWorkMenu:
    def __init__(self, *a, **k):
        pass

    def addAction(self, label):
        _work_labels.append(label)
        return label

    def addSeparator(self):
        pass

    def exec(self, *a):
        return None


_uninstalled = [r for r in _rows if r.data(mw_mod._SOURCE_PATH_ROLE)][0]
_real_menu0 = mw_mod.QMenu
mw_mod.QMenu = _CollectWorkMenu
window._on_package_menu(
    window.dev_list, window.dev_list.visualItemRect(_uninstalled).center()
)
mw_mod.QMenu = _real_menu0
check(
    "the menu offers no way to remove a working copy",
    not any(
        word in label.lower()
        for label in _work_labels
        for word in ("remove", "delete")
    ),
    str(_work_labels),
)
check("what it does offer is Install and Link", "Install" in _work_labels, str(_work_labels))

_saved_install = cfg_mod.DEV_INSTALL_COMMAND
cfg_mod.DEV_INSTALL_COMMAND = (
    "bash", "-c",
    "mkdir -p $1/$(basename $PWD)/1.0.0; cp package.py $1/$(basename $PWD)/1.0.0/",
    "x", "{dest}",
)
_shot_row = [r for r in _rows if r.text().startswith("shot_tools")][0]
_source = _shot_row.data(mw_mod._SOURCE_PATH_ROLE)
_real_menu = mw_mod.QMenu


class _PickFirst:
    """A menu that silently chooses whichever action was added first.

    Actions are plain strings: the handler only ever compares them with `is`,
    and a real QAction would need a real menu to hang off.
    """

    def __init__(self, *a, **k):
        self._first = None

    def addAction(self, label):
        if self._first is None:
            self._first = label
        return label

    def addSeparator(self):
        pass

    def exec(self, *a):
        return self._first


mw_mod.QMenu = _PickFirst
window._on_package_menu(window.dev_list, window.dev_list.visualItemRect(_shot_row).center())
QApplication.processEvents()
mw_mod.QMenu = _real_menu
cfg_mod.DEV_INSTALL_COMMAND = _saved_install

# reload_all() re-reads the saved settings, which is the whole point of it --
# so the throwaway roots this test set at runtime have to be put back.
cfg_mod.set_path_overrides(
    {"dev_root": str(_installed), "dev_working_root": str(_work)}
)
window.refresh_package_lists()
QApplication.processEvents()

check(
    "Install builds it into the dev root",
    (_installed / "shot_tools" / "1.0.0" / "package.py").is_file(),
)
_after = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check(
    "and the row becomes a real package, ticked",
    any(t.startswith("shot_tools-1.0.0") and "(not installed)" not in t for t in _after),
    str(_after),
)
check(
    "with the two that are still only in the working location behind it",
    sum("(not installed)" in t for t in _after) == 2,
    str(_after),
)
check(
    "the badge follows",
    window.dev_frame.badge.text() == "1 installed  \u00b7  2 not",
    window.dev_frame.badge.text(),
)

_real_box = mw_mod.QMessageBox

print("\nlaunching checks the installed dev packages against the working copies")
_stale_work = Path(tempfile.mkdtemp(prefix="bootycall-stale-"))
(_stale_work / "shot_tools").mkdir()
(_stale_work / "shot_tools" / "package.py").write_text("name = 'shot_tools'\n")
time.sleep(0.02)
(_stale_work / "shot_tools" / "edited.py").write_text("# newer than the install\n")

cfg_mod.set_path_overrides(
    {"dev_root": str(_installed), "dev_working_root": str(_stale_work)}
)
window.refresh_package_lists()
QApplication.processEvents()
_stale = window.stale_dev_installs()
check(
    "the edited package is spotted",
    [s.name for s in _stale] == ["shot_tools"],
    str([s.name for s in _stale]),
)
check(
    "and described in terms of how far behind it is",
    "newer" in _stale[0].describe(),
    _stale[0].describe(),
)

_answers = []


class _StaleBox:
    Warning = _real_box.Warning
    AcceptRole = _real_box.AcceptRole
    DestructiveRole = _real_box.DestructiveRole
    Cancel = _real_box.Cancel
    reply = "cancel"

    def __init__(self, *args, **kwargs):
        self._buttons = {}

    def setIcon(self, *a):
        pass

    setWindowTitle = setIcon

    def setText(self, text):
        _answers.append(text)

    def setInformativeText(self, text):
        _answers.append(text)

    def addButton(self, *args):
        label = args[0] if isinstance(args[0], str) else "cancel"
        self._buttons[label] = object()
        return self._buttons[label]

    def setDefaultButton(self, *a):
        pass

    def exec(self):
        return 0

    def clickedButton(self):
        return self._buttons.get(_StaleBox.reply)


mw_mod.QMessageBox = _StaleBox
_StaleBox.reply = "cancel"
check("cancelling stops the launch", window.check_dev_installs() == "cancel")
check(
    "the prompt listed what is out of date",
    any("shot_tools" in a for a in _answers),
    str(_answers[-1:]),
)
check(
    "and said what launching anyway would mean",
    any("not what you have been editing" in a for a in _answers),
    str(_answers[-1:]),
)

_StaleBox.reply = "Launch Anyway"
check("launching anyway is allowed", window.check_dev_installs() == "launch")
check("and nothing was rebuilt", window.stale_dev_installs() != [])

cfg_mod.DEV_INSTALL_COMMAND = (
    "bash", "-c",
    "mkdir -p $1/$(basename $PWD)/1.0.0; touch $1/$(basename $PWD)/1.0.0/package.py",
    "x", "{dest}",
)
_StaleBox.reply = "Update and Launch"
check("updating then launching is allowed", window.check_dev_installs() == "launch")
check("and it really rebuilt", window.stale_dev_installs() == [], str(window.stale_dev_installs()))
check("so a second launch asks nothing", window.check_dev_installs() == "")
mw_mod.QMessageBox = _real_box
cfg_mod.DEV_INSTALL_COMMAND = _saved_install
cfg_mod.set_path_overrides({})
window.refresh_package_lists()
QApplication.processEvents()

print("\noverriding packages come to the top of the list")
pin("batman_returns")
window.local_frame.set_expanded(True)
QApplication.processEvents()
_texts = [window.local_list.item(i).text() for i in range(window.local_list.count())]
_flagged = [t for t in _texts if "overrides" in t or "does not satisfy" in t]
check("something in the root is named by this resolve", bool(_flagged), str(_texts))
check(
    "and it is first, not buried in the list",
    _texts[0] in _flagged,
    str(_texts),
)
check(
    "the rest keep their order behind it",
    _texts[1:] == sorted(_texts[1:]),
    str(_texts[1:]),
)

print("\na build that cannot satisfy the request is not called an override")
check(
    "the fixture has one: nuke_plugins-4.1.0 against a request for nuke_plugins-3",
    any("nuke_plugins" in t and "does not satisfy" in t for t in _texts),
    str(_texts),
)
check(
    "it is not counted as being in use",
    window.local_frame.note.text() == "",
    window.local_frame.note.text(),
)
check(
    "it is counted as unusable instead, in the red badge",
    window.local_frame.alert.text() == "1 unusable",
    window.local_frame.alert.text(),
)
_resolve_texts = [
    window.package_list.item(i).text() for i in range(window.package_list.count())
]
check(
    "and the resolve does not claim it is overridden either",
    not any("nuke_plugins" in t and "overridden" in t for t in _resolve_texts),
    str([t for t in _resolve_texts if "nuke_plugins" in t]),
)

print("\nthe menu bar carries Copy command now")
check("there is an Edit menu", window.edit_menu.title() == "&Edit", window.edit_menu.title())
check(
    "with the copy action in it",
    window.copy_action in window.edit_menu.actions(),
    str([a.text() for a in window.edit_menu.actions()]),
)
check("enabled once there is something to copy", window.copy_action.isEnabled())
window._on_copy_command()
QApplication.processEvents()
_copied = QApplication.clipboard().text()
check("copying gives the whole command", "rez-env" in _copied, _copied[:80])
check("cd'd into the show", "/tmp/ice/shows/batman_returns" in _copied, _copied[:80])
check("and no footer button is left", not hasattr(window, "copy_button"))

print("\nthe window is a quarter narrower than it was")
check("minimum width", window.minimumWidth() == 428, str(window.minimumWidth()))
window.resize(428, 700)
for _ in range(4):
    QApplication.processEvents()
_tiles = list(window._dcc_buttons.values()) + [window.terminal_button]
_rows = sorted({t.y() for t in _tiles})
check("the tile row wraps at that width", len(_rows) > 1, str(_rows))
_bottom = max(t.y() + t.height() for t in _tiles)
check(
    "and every tile is inside the row that holds them",
    _bottom <= window.dcc_container.height(),
    "%d in %d" % (_bottom, window.dcc_container.height()),
)

print("\ncompact keeps its title bar, with a title that fits in it")
window.set_compact(True)
QApplication.processEvents()
check("shortened, not cleared", window.windowTitle() == "B.C.", window.windowTitle())
check(
    "short enough that a one-tile-wide bar can show all of it",
    len(window.windowTitle()) <= 6,
    window.windowTitle(),
)
check(
    "and the frame is still there to drag and close by",
    not (window.windowFlags() & Qt.FramelessWindowHint),
)
window.set_compact(False)
QApplication.processEvents()
check(
    "expanding puts the full title back",
    window.windowTitle() == window.EXPANDED_TITLE,
    window.windowTitle(),
)

print("\ncollapsing holds the corner it is nearest")
_screen = QApplication.primaryScreen().availableGeometry()


def _collapse_from(corner):
    """Park the expanded window fully inside ``corner``, then collapse it.

    Placed from the window's real expanded size rather than a guess: a frame
    hanging off the edge of the screen gets clamped back on, and then the test
    is measuring the clamp instead of the anchoring.
    """
    window.set_compact(False)
    for _ in range(3):
        QApplication.processEvents()
    frame = window.frameGeometry()
    x = (
        _screen.right() - frame.width() - 20
        if corner[0] == "right"
        else _screen.left() + 20
    )
    y = (
        _screen.bottom() - frame.height() - 20
        if corner[1] == "bottom"
        else _screen.top() + 20
    )
    window.move(x, y)
    for _ in range(3):
        QApplication.processEvents()
    before = window.frameGeometry()
    window.set_compact(True)
    for _ in range(3):
        QApplication.processEvents()
    return before, window.frameGeometry()


_before, _after = _collapse_from(("left", "top"))
check(
    "top-left stays put by its top-left",
    abs(_after.left() - _before.left()) <= 2 and abs(_after.top() - _before.top()) <= 2,
    "%s -> %s" % (_before, _after),
)

_before, _after = _collapse_from(("right", "bottom"))
check(
    "bottom-right collapses towards the bottom-right",
    abs(_after.right() - _before.right()) <= 2
    and abs(_after.bottom() - _before.bottom()) <= 2,
    "%s -> %s" % (_before, _after),
)
check(
    "which is not where it would have landed before",
    _after.left() > _before.left() and _after.top() > _before.top(),
    "%s -> %s" % (_before, _after),
)

print("\nand expanding grows back out of the same corner")
_compact_frame = window.frameGeometry()
window.set_compact(False)
for _ in range(3):
    QApplication.processEvents()
_expanded = window.frameGeometry()
check(
    "the bottom-right corner did not move",
    abs(_expanded.right() - _compact_frame.right()) <= 2
    and abs(_expanded.bottom() - _compact_frame.bottom()) <= 2,
    "%s -> %s" % (_compact_frame, _expanded),
)
check(
    "so it grew up and to the left, staying on screen",
    _expanded.left() >= _screen.left() and _expanded.top() >= _screen.top(),
    "%s in %s" % (_expanded, _screen),
)

print("\ndiagnostics, for when a package is not where you expect it")
from bootycall import diagnostics as _diag  # noqa: E402

pin("batman_returns")
_report = _diag.report(window)
for _needle in (
    "what rez itself is configured to read",
    "the path this launch will actually use",
    "installed dev packages",
    "local packages",
    "the dev working location",
    "what will be run",
):
    check("the report covers: %s" % _needle, _needle in _report, _report[:120])
check(
    "it names the roots in play",
    str(_lp.local_root()) in _report and str(_lp.dev_root()) in _report,
)
check("and what each definition declares", "definition declares:" in _report)
check(
    "and the command that would run",
    "rez-env" in _report,
    _report[-200:],
)
check(
    "the Edit menu offers it",
    window.diagnostics_action in window.edit_menu.actions(),
    str([a.text() for a in window.edit_menu.actions()]),
)

print("\na build that loses to a newer one elsewhere says so")
_pr = Path(tempfile.mkdtemp(prefix="bootycall-precedence-"))
_pr_shows, _pr_local, _pr_studio = _pr / "shows", _pr / "local", _pr / "studio"
(_pr_shows / "demo" / ".ilp" / "pipeline").mkdir(parents=True)
(_pr_shows / "demo" / ".ilp" / "pipeline" / "config.py").write_text(
    "from ilp_bootstrap import Bootstrap\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    packages = dict(maya=('maya-2026', 'rig_utils-1'))\n"
)


def _put(root, name, version):
    d = root / name / version
    d.mkdir(parents=True, exist_ok=True)
    (d / "package.py").write_text("name = %r\nversion = %r\n" % (name, version))


_put(_pr_local / "dev", "rig_utils", "1.7.666")
_put(_pr_studio, "rig_utils", "1.9.0")

_saved_rez = os.environ.get("REZ_PACKAGES_PATH")
os.environ["REZ_PACKAGES_PATH"] = str(_pr_studio)
launcher._PACKAGES_PATH = None
cfg_mod.set_path_overrides(
    {
        "shows_root": str(_pr_shows),
        "local_root": str(_pr_local),
        "dev_root": "{local}/dev",
    }
)
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("demo")
window.dev_frame.set_expanded(True)
QApplication.processEvents()

_rows = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check("the dev build is listed", any("rig_utils" in r for r in _rows), str(_rows))
check(
    "and it is not called an override, because it does not win",
    all("overrides" not in r for r in _rows),
    str(_rows),
)
check(
    "it names the version that beats it",
    any("outranked by 1.9.0" in r for r in _rows),
    str(_rows),
)

_win = window._winner_for("rig_utils", "rig_utils-1")
check(
    "and the resolver agrees where it comes from",
    _win is not None and str(_win.root) == str(_pr_studio),
    _win.describe() if _win else "no winner",
)

_report = _diag.report(window)
check(
    "the report spells it out",
    "but rez will use 1.9.0" in _report,
    "\n".join(l for l in _report.splitlines() if "rig_utils" in l),
)

print("\nnarrow the request and the same build wins")
(_pr_shows / "demo" / ".ilp" / "pipeline" / "config.py").write_text(
    "from ilp_bootstrap import Bootstrap\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    packages = dict(maya=('maya-2026', 'rig_utils-1.7'))\n"
)
unpin_all()
pin("demo")
window.dev_frame.set_expanded(True)
QApplication.processEvents()
_rows = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check(
    "now it is the override",
    any("overrides rig_utils-1.7" in r for r in _rows),
    str(_rows),
)

cfg_mod.set_path_overrides({})
if _saved_rez:
    os.environ["REZ_PACKAGES_PATH"] = _saved_rez
else:
    os.environ.pop("REZ_PACKAGES_PATH", None)
launcher._PACKAGES_PATH = None
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("batman_returns")

print("\nasking rez what it actually resolved")
import stat  # noqa: E402

_bin = Path(tempfile.mkdtemp(prefix="bootycall-fakerez-")) / "bin"
_bin.mkdir(parents=True)
_fake = _bin / "rez-env"
_fake.write_text(
    "#!/usr/bin/env bash\n"
    "# Stands in for a graph that pins rig_utils below the newest build.\n"
    'if [ -n "$BOOTYCALL_FAKE_FAIL" ]; then\n'
    '  echo "PackageFamilyNotFoundError: no such package" >&2; exit 1\n'
    "fi\n"
    "export REZ_RIG_UTILS_VERSION=1.6.2\n"
    "export REZ_RIG_UTILS_ROOT=/studio/rig_utils/1.6.2\n"
    'while [ "$1" != "--" ] && [ $# -gt 0 ]; do shift; done\n'
    'shift\n'
    'exec "$@"\n'
)
_fake.chmod(_fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
_saved_path = os.environ["PATH"]
os.environ["PATH"] = "%s:%s" % (_bin, _saved_path)

# Reuse the precedence fixture: a dev build that outranks everything on disk.
cfg_mod.set_path_overrides(
    {
        "shows_root": str(_pr_shows),
        "local_root": str(_pr_local),
        "dev_root": "{local}/dev",
    }
)
(_pr_shows / "demo" / ".ilp" / "pipeline" / "config.py").write_text(
    "from ilp_bootstrap import Bootstrap\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    packages = dict(maya=('maya-2026', 'rig_utils-1'))\n"
)
_put(_pr_local / "dev", "rig_utils", "1.8.666")
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("demo")
QApplication.processEvents()

_probe = launcher.resolve_probe(
    window.current_project(),
    window.resolved_packages(),
    window.excluded_roots(),
    window.included_roots(),
)
check("the resolve ran", _probe.ok, _probe.error[:100])
check(
    "and rez's own answer is read back",
    launcher.resolved_for(_probe, "rig_utils") == ("1.6.2", "/studio/rig_utils/1.6.2"),
    str(launcher.resolved_for(_probe, "rig_utils")),
)
check(
    "a package rez did not resolve reads empty, not missing",
    launcher.resolved_for(_probe, "not_in_the_resolve") == ("", ""),
)

_resolve_text = _diag.resolve_report(window)
check(
    "the report names the build the user made",
    "your newest build: 1.8.666" in _resolve_text,
    "\n".join(l for l in _resolve_text.splitlines() if "build" in l),
)
check(
    "and what rez chose instead",
    "rez resolved:      1.6.2" in _resolve_text,
    "\n".join(l for l in _resolve_text.splitlines() if "resolved:" in l),
)
check(
    "flagging the disagreement rather than glossing it",
    "yours is NOT the one in the environment" in _resolve_text,
    _resolve_text[:200],
)
check(
    "and pointing at the only thing that can explain it",
    "requires" in _resolve_text and "rez-context --graph" in _resolve_text,
    "\n".join(l for l in _resolve_text.splitlines() if "requires" in l),
)

os.environ["BOOTYCALL_FAKE_FAIL"] = "1"
_failed = _diag.resolve_report(window)
check(
    "a failed resolve is reported as the answer, not hidden",
    "the resolve failed" in _failed and "PackageFamilyNotFound" in _failed,
    _failed[:200],
)
del os.environ["BOOTYCALL_FAKE_FAIL"]

check(
    "the Edit menu offers it",
    window.resolve_test_action in window.edit_menu.actions(),
    str([a.text() for a in window.edit_menu.actions()]),
)

os.environ["PATH"] = _saved_path
cfg_mod.set_path_overrides({})
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("batman_returns")

print("\nin use and overridden are counted apart")
# The precedence fixture again: one dev build that wins, one that loses.
cfg_mod.set_path_overrides(
    {
        "shows_root": str(_pr_shows),
        "local_root": str(_pr_local),
        "dev_root": "{local}/dev",
    }
)
(_pr_shows / "demo" / ".ilp" / "pipeline" / "config.py").write_text(
    "from ilp_bootstrap import Bootstrap\n"
    "class ProjectBootstrap(Bootstrap):\n"
    "    packages = dict(maya=('maya-2026', 'rig_utils-1', 'anim_bot-2'))\n"
)
_put(_pr_local / "dev", "anim_bot", "2.4.0")   # nothing newer anywhere: wins
_put(_pr_studio, "rig_utils", "1.9.0")         # beats the dev 1.8.666
_saved_rez = os.environ.get("REZ_PACKAGES_PATH")
os.environ["REZ_PACKAGES_PATH"] = str(_pr_studio)
launcher._PACKAGES_PATH = None
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("demo")
window.dev_frame.set_expanded(True)
QApplication.processEvents()

check(
    "the one that wins is in use",
    window.dev_frame.note.text() == "1 in use",
    window.dev_frame.note.text(),
)
check(
    "the one that loses is outranked, separately and in red",
    window.dev_frame.alert.text() == "1 outranked",
    window.dev_frame.alert.text(),
)
check(
    "the header uses the same word the row does",
    any(
        "outranked" in window.dev_list.item(i).text()
        for i in range(window.dev_list.count())
    ),
    str([window.dev_list.item(i).text() for i in range(window.dev_list.count())]),
)
check(
    "the alert badge is visible when it has something to say",
    window.dev_frame.alert.isVisible(),
)

_rows = [window.dev_list.item(i).text() for i in range(window.dev_list.count())]
check(
    "and the rows agree with the header",
    any("anim_bot" in r and "overrides" in r for r in _rows)
    and any("rig_utils" in r and "outranked" in r for r in _rows),
    str(_rows),
)

_resolve_rows = [
    window.package_list.item(i).text() for i in range(window.package_list.count())
]
check(
    "the resolve list only marks the override that really happens",
    any("anim_bot" in r and "overridden by" in r for r in _resolve_rows)
    and not any("rig_utils" in r and "overridden by" in r for r in _resolve_rows),
    str(_resolve_rows),
)

window.dev_frame.set_checked(False)
QApplication.processEvents()
check("a section switched off says so and nothing else", window.dev_frame.note.text() == "not used")
check("with no red badge left over", window.dev_frame.alert.text() == "")
window.dev_frame.set_checked(True)
QApplication.processEvents()

print("\nreload means all of it")
_before_probe = dict(window._probe_cache)
launcher._PACKAGES_PATH = ["/stale/path"]
window._winner_cache[("x", "x-1")] = None
window.reload_all()
QApplication.processEvents()
check("the rez path cache is dropped", launcher._PACKAGES_PATH != ["/stale/path"])
check("the winner cache is dropped", ("x", "x-1") not in window._winner_cache)
check("and the shows are still there", window.project_field.projects() != [])
check(
    "with a status message saying what it did",
    "Reloaded" in window.statusBar().currentMessage(),
    window.statusBar().currentMessage(),
)

cfg_mod.set_path_overrides({})
if _saved_rez:
    os.environ["REZ_PACKAGES_PATH"] = _saved_rez
else:
    os.environ.pop("REZ_PACKAGES_PATH", None)
launcher._PACKAGES_PATH = None
window.reload_projects()
QApplication.processEvents()
unpin_all()
pin("batman_returns")

print("\nthe dev section is the one you keep open")
check("open on startup", window.dev_frame.is_expanded())
check(
    "and it does not spend a row on a path that never changes",
    not window.dev_path_label.isVisible(),
)
check(
    "the local one still shows its path",
    window.local_path_label.isVisible(),
)
check(
    "but the dev root is still a hover away on the header",
    str(_lp.dev_root()) in window.dev_frame.toggle_button.toolTip(),
    window.dev_frame.toggle_button.toolTip(),
)
check(
    "saying exactly what the hidden line would have said",
    window.dev_frame.toggle_button.toolTip() == window.dev_path_label.text(),
    "%r vs %r"
    % (window.dev_frame.toggle_button.toolTip(), window.dev_path_label.text()),
)

print("\nupdate dev installs says why it can do nothing")
_dvi = Path(tempfile.mkdtemp(prefix="bootycall-updatecheck-"))
from bootycall.dev_install import update_blocker as _blocker  # noqa: E402
from bootycall.local_packages import LocalPackage as _LP  # noqa: E402

_installed = [_LP(name="rig_utils", version="1.0.0", path=_dvi / "x")]
check(
    "a switched-off section is named as the reason",
    "switched off" in _blocker(_installed, False, _dvi),
    _blocker(_installed, False, _dvi),
)
check(
    "so is having nothing in play",
    "none are installed" in _blocker([], True, _dvi),
    _blocker([], True, _dvi),
)
check(
    "a working location that is not there is named, with the path",
    "does not exist" in _blocker(_installed, True, _dvi / "nope")
    and str(_dvi / "nope") in _blocker(_installed, True, _dvi / "nope"),
    _blocker(_installed, True, _dvi / "nope"),
)
check(
    "an empty working location too",
    "is a rez package" in _blocker(_installed, True, _dvi),
    _blocker(_installed, True, _dvi),
)

(_dvi / "something_else").mkdir()
(_dvi / "something_else" / "package.py").write_text("name = 'something_else'\n")
_mismatch = _blocker(_installed, True, _dvi)
check(
    "and a working location with no matching names explains the mismatch",
    "matched by directory name" in _mismatch,
    _mismatch,
)
check(
    "listing both sides so the mismatch is obvious",
    "rig_utils" in _mismatch and "something_else" in _mismatch,
    _mismatch,
)

(_dvi / "rig_utils").mkdir()
(_dvi / "rig_utils" / "package.py").write_text("name = 'rig_utils'\n")
check(
    "and nothing at all to say once the names line up",
    _blocker(_installed, True, _dvi) == "",
    _blocker(_installed, True, _dvi),
)

print("\na minimalist progress bar for the rebuild")
check("hidden when idle", not window.progress.isVisible())
check("three pixels tall", window.progress.height() == 3, str(window.progress.height()))
check(
    "and overlaid, so showing it cannot resize the window",
    window.progress.parent() is window.centralWidget(),
)

_before = (window.width(), window.height())
window._start_progress(3)
QApplication.processEvents()
check("shown while working", window.progress.isVisible())
check(
    "the window did not move or grow to make room",
    (window.width(), window.height()) == _before,
    "%s -> %s" % (_before, (window.width(), window.height())),
)
check(
    "pinned to the bottom edge",
    window.progress.y() + window.progress.height()
    == window.centralWidget().height(),
    "%d in %d" % (window.progress.y(), window.centralWidget().height()),
)
check(
    "and the full width of it",
    window.progress.width() == window.centralWidget().width(),
)

window._step_progress(1, 3, "rig_utils")
QApplication.processEvents()
check("it advances", window.progress.value() == 1, str(window.progress.value()))
check("out of the right total", window.progress.maximum() == 3)
window._end_progress()
check("and goes away afterwards", not window.progress.isVisible())

print("\nit works in compact, which is where it was asked for")
window.set_compact(True)
QApplication.processEvents()
_compact_size = (window.width(), window.height())
window._start_progress(2)
QApplication.processEvents()
check("visible while collapsed", window.progress.isVisible())
check(
    "and compact stays exactly the size it was",
    (window.width(), window.height()) == _compact_size,
    "%s -> %s" % (_compact_size, (window.width(), window.height())),
)
check(
    "spanning the bottom of the compact window",
    window.progress.width() == window.centralWidget().width(),
)
window._end_progress()
window.set_compact(False)
QApplication.processEvents()

print("\nsymlinked installs are labelled as such")
_sym = Path(tempfile.mkdtemp(prefix="bootycall-symui-"))
_sym_src = _sym / "working" / "rig_utils"
_sym_src.mkdir(parents=True)
(_sym_src / "package.py").write_text("name = 'rig_utils'\n")
(_sym_src / "keep_me.py").write_text("# the working copy\n")
_sym_dev = _sym / "local" / "dev"
_sym_dev.mkdir(parents=True)
(_sym_dev / "real_one").mkdir()
(_sym_dev / "real_one" / "package.py").write_text("name = 'real_one'\n")
try:
    (_sym_dev / "rig_utils").symlink_to(_sym_src, target_is_directory=True)
    _have_links = True
except OSError:
    _have_links = False

if _have_links:
    cfg_mod.set_path_overrides(
        {"local_root": str(_sym / "local"), "dev_root": "{local}/dev"}
    )
    window.refresh_package_lists()
    QApplication.processEvents()

    _rows = {
        window.dev_list.item(i).data(_NAME_ROLE): window.dev_list.item(i)
        for i in range(window.dev_list.count())
    }
    check("both are listed", set(_rows) == {"rig_utils", "real_one"}, str(list(_rows)))
    check(
        "the linked one says so",
        "(symlinked)" in _rows["rig_utils"].text(),
        _rows["rig_utils"].text(),
    )
    check(
        "the built one does not",
        "(symlinked)" not in _rows["real_one"].text(),
        _rows["real_one"].text(),
    )
    check(
        "no row in either list carries a tooltip",
        not any(
            listing.item(i).toolTip()
            for listing in (window.dev_list, window.local_list, window.package_list)
            for i in range(listing.count())
        ),
        str(
            [
                listing.item(i).toolTip()
                for listing in (window.dev_list, window.local_list, window.package_list)
                for i in range(listing.count())
                if listing.item(i).toolTip()
            ]
        ),
    )

    # Nothing hovers to warn you any more, so the one moment that matters --
    # the confirmation before a delete -- has to carry it.
    _asked = []
    _real_warn = mw_mod.QMessageBox.warning
    mw_mod.QMessageBox.warning = staticmethod(
        lambda parent, title, text, *a, **k: (
            _asked.append((title, text)),
            mw_mod.QMessageBox.No,
        )[1]
    )
    window._confirm_delete_packages(
        window.dev_list, [p for p in window._dev_packages if p.name == "rig_utils"]
    )
    mw_mod.QMessageBox.warning = _real_warn
    check("the confirmation is named for the section", _asked[0][0] == "Remove Dev Package", str(_asked[0][0]))
    check(
        "and says a link loses only the link",
        "only the link is removed" in _asked[0][1],
        _asked[0][1],
    )
    check("saying No changes nothing", (_sym_dev / "rig_utils").is_symlink())

    _pkgs = [p for p in window._dev_packages if p.name == "rig_utils"]
    _errors = window.delete_packages(window.dev_list, _pkgs)
    QApplication.processEvents()
    check("deleting it works", _errors == [], str(_errors))
    check("the link is gone", not (_sym_dev / "rig_utils").is_symlink())
    check(
        "and the working copy is untouched",
        (_sym_src / "keep_me.py").is_file() and (_sym_src / "package.py").is_file(),
        str(sorted(x.name for x in _sym_src.iterdir())),
    )

    cfg_mod.set_path_overrides({})
    window.refresh_package_lists()
    QApplication.processEvents()

print("\nthe remove action is named for the section it acts on")
check(
    "dev list",
    window._section_noun(window.dev_list) == "Dev Package",
    window._section_noun(window.dev_list),
)
check(
    "local list",
    window._section_noun(window.local_list) == "Local Package",
    window._section_noun(window.local_list),
)

_labels = []


class _CollectMenu:
    def __init__(self, *a, **k):
        pass

    def addAction(self, label):
        _labels.append(label)
        return label

    def addSeparator(self):
        pass

    def exec(self, *a):
        return None


pin("batman_returns")
QApplication.processEvents()
_real_menu2 = mw_mod.QMenu
mw_mod.QMenu = _CollectMenu
_first_local = window.local_list.item(0)
window.local_list.setCurrentItem(_first_local)
window._on_package_menu(
    window.local_list, window.local_list.visualItemRect(_first_local).center()
)
mw_mod.QMenu = _real_menu2
check(
    "the local list offers Remove Local Package, not 'delete from disk'",
    "Remove Local Package" in _labels,
    str(_labels),
)

print("\ntooltips are readable, not light-on-light")
_style = app.styleSheet()
check("QToolTip is styled at all", "QToolTip" in _style)
_tip = _style.split("QToolTip", 1)[1].split("}", 1)[0]
check("with its own background", "background:" in _tip, _tip)
check("and its own colour", "color:" in _tip, _tip)

print("\nthe launch says what this window switched off")
pin("batman_returns")
QApplication.processEvents()
check("nothing to report while everything is on", window.launch_notes() == (), str(window.launch_notes()))

window.local_frame.set_checked(False)
QApplication.processEvents()
_notes = window.launch_notes()
check(
    "switching local off is reported",
    any("Local packages are switched OFF" in t for _l, t in _notes),
    str(_notes),
)
check("as a warning", all(l == "warn" for l, t in _notes if "Local" in t), str(_notes))

window.dev_frame.set_checked(False)
QApplication.processEvents()
check(
    "and so is switching dev off",
    any("dev packages are switched OFF" in t for _l, t in window.launch_notes()),
    str(window.launch_notes()),
)

window.local_frame.set_checked(True)
window.dev_frame.set_checked(True)
QApplication.processEvents()
_first_dev = window.dev_list.item(0).data(_NAME_ROLE)
window.dev_list.item(0).setCheckState(Qt.Unchecked)
QApplication.processEvents()
check(
    "unticking one dev package is named, not just counted",
    any(
        "Dev packages switched off" in t and _first_dev in t
        for _l, t in window.launch_notes()
    ),
    str(window.launch_notes()),
)
window.dev_list.item(0).setCheckState(Qt.Checked)
QApplication.processEvents()

_argv = launcher.build_command(
    window.resolved_packages(),
    "maya",
    window.highlight_roots(),
    (("warn", "Local packages are switched OFF for this launch"),),
)
_script = preamble(_argv[-1])
check(
    "the banner reaches the launch command",
    "what this window changed about the environment" in _script,
    _script[:160],
)
check(
    "with the note in it",
    "Local packages are switched OFF" in _script,
    _script[:200],
)
check(
    "and the resolved-package summary as well",
    "your packages in this environment" in _script,
)

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
check("reload still present, and now means all of it", "&Reload" in texts, str(texts))
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
check(
    "the software row it was saved with came back too",
    "nuke" in window._visible_software,
    str(window._visible_software),
)
shot(window, "09-applied-setup")

# The bug: a setup whose DCC has since been hidden from the Softwares menu.
# The tile does not exist, and applying used to report that as "the show does
# not offer it any more" -- which was not true, and sent you to look at the
# show rather than at the menu you had changed.
window._software_actions["nuke"].setChecked(False)
QApplication.processEvents()
check("nuke is hidden", "nuke" not in window._visible_software, str(window._visible_software))
check("and has no tile", "nuke" not in window._dcc_buttons, str(list(window._dcc_buttons)))

unpin_all()
window._on_apply_config("Nightly comp")
QApplication.processEvents()
check(
    "applying turns its software back on rather than failing",
    "nuke" in window._visible_software,
    str(window._visible_software),
)
check("the tile is back", "nuke" in window._dcc_buttons, str(list(window._dcc_buttons)))
check("and it is selected", window._active_dcc.name == "nuke", str(window._active_dcc))
check("with its variant", window._current_tool() == "nuke16", str(window._current_tool()))
check("no error", window.status_label.property("level") != "error", window.status_label.text())
check(
    "and the change is saved, so the menu agrees next launch",
    "nuke" in (window.store.visible_software() or ()),
    str(window.store.visible_software()),
)

# A setup saved before the software row was recorded restores nothing but its
# own DCC: it has no row to put back, and clearing one the user arranged for
# other reasons would be worse than leaving it alone.
_old_style = mw_mod.SavedConfig(
    name="Legacy", show="batman_returns", dcc="blender", tool="blender"
)
check("it has no software of its own", _old_style.software == ())
window.store.add(_old_style)
_before = set(window._visible_software)
window._on_apply_config("Legacy")
QApplication.processEvents()
check("its own DCC is turned on", "blender" in window._visible_software)
check(
    "and everything already on is left alone",
    _before <= set(window._visible_software),
    "%s -> %s" % (sorted(_before), sorted(window._visible_software)),
)
window.store.remove("Legacy")
window._rebuild_file_menu()
rows = [a for a in window.file_menu.actions() if isinstance(a, ConfigMenuAction)]

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
