"""
Install Package: pick a working copy, put it in the installed dev root.

A listing of the working location rather than a file chooser. A file chooser
would let you pick anything on the machine and then fail on most of it; this
shows the folders that are actually there and says, per row, whether each one
is a package rez could install. The ones that are not stay visible and greyed:
a browser that hides the folder you were looking for is worse than one that
tells you why it cannot use it.

Two ways out, because they are genuinely different things:

* **Install** builds the package into the dev root. What you want when you have
  finished a change.
* **Symlink** points the dev root at the working copy. What you want while you
  are still making them -- every edit is live, with no install step and no
  staleness to track.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .. import dev_install


class InstallPackageDialog(QDialog):
    """Browse the working location and install one of its packages."""

    def __init__(
        self,
        working_root: Path,
        dev_root: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Install Dev Package")
        self.setMinimumSize(520, 380)
        self.working_root = Path(working_root)
        self.dev_root = Path(dev_root)
        #: Names installed during this dialog, so the caller knows to refresh.
        self.installed: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.heading = QLabel("")
        self.heading.setObjectName("hint")
        self.heading.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)

        self.listing = QListWidget()
        self.listing.setObjectName("installList")
        self.listing.itemSelectionChanged.connect(self._update_actions)
        self.listing.itemDoubleClicked.connect(lambda _item: self._on_install())
        layout.addWidget(self.listing, 1)

        self.status = QLabel("")
        self.status.setObjectName("statusLabel")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.reload)
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)

        self.symlink_button = QPushButton("Symlink")
        self.symlink_button.setToolTip(
            "Point the dev root at the working copy instead of building it.\n"
            "Edits are live immediately - including broken ones."
        )
        self.symlink_button.clicked.connect(self._on_symlink)
        buttons.addWidget(self.symlink_button)

        self.install_button = QPushButton("Install")
        self.install_button.setObjectName("launchButton")
        self.install_button.setDefault(True)
        self.install_button.clicked.connect(self._on_install)
        buttons.addWidget(self.install_button)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.reload()

    # -- listing -----------------------------------------------------------

    def reload(self) -> None:
        self.listing.clear()
        packages = dev_install.list_working_packages(self.working_root)

        self.heading.setText(
            "Working location: %s\nInstalling into: %s"
            % (self.working_root, self.dev_root)
        )

        if not packages:
            self._set_status(
                "Nothing in %s. Set the Dev working location in Settings if "
                "your checkouts live somewhere else." % self.working_root,
                "warn",
            )
            self._update_actions()
            return

        for package in packages:
            item = QListWidgetItem(package.name)
            item.setData(Qt.UserRole, package)
            if package.is_package:
                item.setToolTip("%s\nDefinition: %s" % (package.path, package.definition))
            else:
                # Kept in the list, greyed and unselectable: seeing why the
                # folder cannot be used beats wondering where it went.
                item.setText("%s      %s" % (package.name, package.problem))
                item.setForeground(QColor("#6b7079"))
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                item.setToolTip("%s\n%s" % (package.path, package.problem))
            self.listing.addItem(item)

        usable = sum(1 for p in packages if p.is_package)
        self._set_status(
            "%d package%s here, of %d folder%s."
            % (usable, "" if usable == 1 else "s", len(packages),
               "" if len(packages) == 1 else "s")
        )
        self._update_actions()

    def selected(self):
        items = self.listing.selectedItems()
        if not items:
            return None
        package = items[0].data(Qt.UserRole)
        return package if package is not None and package.is_package else None

    def _update_actions(self) -> None:
        ready = self.selected() is not None
        self.install_button.setEnabled(ready)
        self.symlink_button.setEnabled(ready)

    def _set_status(self, text: str, level: str = "") -> None:
        self.status.setText(text)
        self.status.setProperty("level", level)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    # -- actions -----------------------------------------------------------

    def _on_install(self) -> None:
        package = self.selected()
        if package is None:
            return

        self._set_status("Building %s..." % package.name)
        self._set_busy(True)
        try:
            ok, output = dev_install.install(package.path, self.dev_root)
        finally:
            self._set_busy(False)

        if not ok:
            self._set_status("%s could not be installed." % package.name, "error")
            self._report_failure(package.name, output)
            return

        self.installed.append(package.name)
        self._set_status("Installed %s into %s." % (package.name, self.dev_root), "ok")

    def _on_symlink(self) -> None:
        package = self.selected()
        if package is None:
            return

        answer = QMessageBox.question(
            self,
            "Symlink %s" % package.name,
            "Link %s into your dev root instead of building it?\n\n"
            "Every edit you make in the working copy becomes live in the next "
            "resolve, with no install step - including a broken save. Nothing "
            "is built, so a package whose payload comes from its build will be "
            "incomplete, and BootyCall cannot tell you it is out of date, "
            "because it never can be."
            % package.name,
            QMessageBox.Cancel | QMessageBox.Ok,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Ok:
            return

        ok, output = dev_install.symlink(package.path, self.dev_root)
        if not ok:
            self._set_status("%s could not be linked." % package.name, "error")
            self._report_failure(package.name, output)
            return

        self.installed.append(package.name)
        self._set_status("Linked %s: %s" % (package.name, output), "ok")

    def _report_failure(self, name: str, output: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Could not install %s" % name)
        box.setText("%s was not installed." % name)
        # The reason goes in the visible part, not behind Show Details. A
        # dialog that says "it failed, click here to find out why" is a dialog
        # that gets dismissed.
        tail = [line for line in (output or "").strip().splitlines() if line.strip()]
        box.setInformativeText(
            (tail[-1][:400] if tail else "No output.")
            + "\n\nThe build's full output is below."
        )
        box.setDetailedText(output or "No output.")
        box.exec()

    def _set_busy(self, busy: bool) -> None:
        # A rez build is not fast and blocks this dialog while it runs; the
        # cursor is the only honest signal that something is happening.
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
        for widget in (self.install_button, self.symlink_button, self.refresh_button):
            widget.setEnabled(not busy)
        QApplication.processEvents()
