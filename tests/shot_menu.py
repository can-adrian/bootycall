"""Render the File menu on its own -- menus are separate windows, so the
main-window grab in smoke_ui.py can't capture them."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BOOTYCALL_SHOWS_ROOT", "/tmp/ice/shows")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from bootycall.configs import ConfigStore, SavedConfig  # noqa: E402
from bootycall.ui.main_window import MainWindow, apply_style  # noqa: E402

OUT = Path("/home/claude/bootycall/shots")
OUT.mkdir(exist_ok=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
apply_style(app)

store = ConfigStore(Path(tempfile.mkdtemp(prefix="bootycall-menu-")) / "configs.json")
store.add(SavedConfig("Nightly comp", "batman_returns", "nuke", "nuke16"))
store.add(SavedConfig("FX lookdev", "dune_pt3", "houdini", "houdinifx"))
store.add(SavedConfig("Anim dailies", "combat_2", "maya", "maya"))
store.add(SavedConfig("Ziva sim", "ORCA_ep01", "maya", "maya_ziva"))

window = MainWindow(store=store)
window.show()
window.reload_projects()
window.project_field.setText("batman_returns")
QApplication.processEvents()

window._rebuild_file_menu()
menu = window.file_menu
menu.popup(window.mapToGlobal(window.rect().topLeft()))
QApplication.processEvents()

# Hover the second row so the highlight and its X are visible in the shot.
rows = [a for a in menu.actions() if hasattr(a, "item")]
rows[1].item._set_hover(True)
QApplication.processEvents()

menu.grab().save(str(OUT / "10-file-menu.png"))
print("wrote %s  (%dx%d)" % (OUT / "10-file-menu.png", menu.width(), menu.height()))
menu.close()

# Settings dialog, on its own.
from bootycall.ui.settings_dialog import SettingsDialog  # noqa: E402

dialog = SettingsDialog(window)
dialog.resize(620, 520)
dialog.show()
for _ in range(3):
    QApplication.processEvents()
dialog.grab().save(str(OUT / "18-settings.png"))
print("wrote %s" % (OUT / "18-settings.png"))
dialog.close()

# The package context menu, built the same way the right-click handler builds it.
from PySide6.QtWidgets import QMenu  # noqa: E402

pkg_menu = QMenu(window)
pkg_menu.addAction("Browse folder")
pkg_menu.addAction("Copy path")
pkg_menu.addSeparator()
pkg_menu.addAction("Delete from disk")
pkg_menu.popup(window.mapToGlobal(window.rect().topLeft()))
for _ in range(3):
    QApplication.processEvents()
pkg_menu.grab().save(str(OUT / "19-package-menu.png"))
print("wrote %s" % (OUT / "19-package-menu.png"))
pkg_menu.close()

# The variant menu, as _on_variant_menu builds it for Houdini Core.
window.project_field.setText("batman_returns")
QTest_key = None
window.chip_bar.add("batman_returns")
for _ in range(3):
    QApplication.processEvents()

var_menu = QMenu(window)
for label in ("Houdini Core   (21.0)", "Houdini + RenderMan   (21.0 \u00b7 RenderMan)", "Houdini (dev)   (21.0 \u00b7 dev)"):
    act = var_menu.addAction(label)
    act.setCheckable(True)
act = var_menu.actions()[0]
act.setChecked(True)
var_menu.popup(window.mapToGlobal(window.rect().topLeft()))
for _ in range(3):
    QApplication.processEvents()
var_menu.grab().save(str(OUT / "20-variant-menu.png"))
print("wrote %s" % (OUT / "20-variant-menu.png"))
var_menu.close()

# The Launch button's right-click menu.
from bootycall import dev_install  # noqa: E402

launch_menu = QMenu(window)
launch_menu.addAction("Launch")
launch_menu.addAction(dev_install.MENU_LABEL)
launch_menu.popup(window.mapToGlobal(window.rect().topLeft()))
for _ in range(3):
    QApplication.processEvents()
launch_menu.grab().save(str(OUT / "22-launch-menu.png"))
print("wrote %s" % (OUT / "22-launch-menu.png"))
launch_menu.close()
