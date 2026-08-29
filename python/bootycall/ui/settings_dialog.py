"""
Settings: the three roots BootyCall reads.

Paths resolve in three layers -- the shipped constant, an environment variable,
then whatever is set here. This dialog writes the third layer, so a field left
blank means "use whatever the environment or the default says" rather than
"use an empty path".

Each row shows live feedback on whether the path exists, because a typo in a
network path is otherwise invisible until the section it feeds comes up empty.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..local_packages import current_user

#: key -> (label, what it feeds, whether it takes {user}/{local} placeholders)
FIELDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "shows_root",
        "Shows root",
        "Where BootyCall looks for shows and their bootstrap files. Feeds the "
        "show field and the Resolved packages section.",
        "",
    ),
    (
        "local_root",
        "Local packages",
        "Your per-user package root. {user} is substituted.",
        "{user}",
    ),
    (
        "dev_root",
        "Installed dev packages",
        "Where your installed dev packages land, and what rez resolves. "
        "{local} is the resolved local root, so leaving it as {local}/dev "
        "keeps the two together.",
        "{user}, {local}",
    ),
    (
        "dev_working_root",
        "Dev working location",
        "Where you edit dev packages, before installing them. Install Package "
        "browses this, and BootyCall compares it against your installed dev "
        "packages to tell you when one is out of date.",
        "{user}, {home}, {local}",
    ),
)


class _PathRow(QWidget):
    """One labelled path field with a Browse button and a live status line."""

    changed = Signal()

    def __init__(self, key: str, label: str, helptext: str, tokens: str, parent=None):
        super().__init__(parent)
        self.key = key

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        heading = QLabel(label)
        heading.setObjectName("sectionLabel")
        layout.addWidget(heading)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setObjectName("filterField")
        self.edit.setPlaceholderText(config.path_defaults()[key])
        self.edit.textChanged.connect(self._on_changed)
        row.addWidget(self.edit, 1)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._on_browse)
        row.addWidget(self.browse_button)
        layout.addLayout(row)

        note = helptext
        if tokens:
            note += "  Placeholders: %s" % tokens
        self.help_label = QLabel(note)
        self.help_label.setObjectName("hint")
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)

        self.status = QLabel("")
        self.status.setObjectName("statusLabel")
        layout.addWidget(self.status)

    # -- value -------------------------------------------------------------

    def value(self) -> str:
        return self.edit.text().strip()

    def set_value(self, value: str) -> None:
        self.edit.setText(value or "")

    def effective(self) -> str:
        """What this row resolves to, defaults and placeholders included.

        Every placeholder is offered to every row rather than a per-key list:
        a field that silently ignores {home} because of which row it is in is
        a rule nobody can see from the dialog.
        """
        raw = self.value() or config.path_defaults()[self.key]
        user = current_user()
        try:
            expanded = raw.format(
                user=user,
                home=os.path.expanduser("~"),
                local=config.local_root_template().format(user=user),
            )
        except (KeyError, IndexError):
            # An unknown placeholder is the user's typo to see, not ours to
            # swallow -- showing the raw text makes it obvious what happened.
            return raw
        return os.path.expanduser(expanded)

    # -- feedback ----------------------------------------------------------

    def refresh_status(self) -> None:
        resolved = self.effective()
        exists = Path(resolved).is_dir()
        using_default = not self.value()

        if exists:
            text = "%s  -  found" % resolved
            level = "ok"
        else:
            # Not an error: a dev root you have not made yet is normal, and the
            # sections say so themselves. Worth flagging, not worth blocking.
            text = "%s  -  does not exist yet" % resolved
            level = "error"
        if using_default:
            text += "   (default)"

        self.status.setText(text)
        if self.status.property("level") != level:
            self.status.setProperty("level", level)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

    def _on_changed(self) -> None:
        self.refresh_status()
        self.changed.emit()

    def _on_browse(self) -> None:
        start = self.effective()
        if not Path(start).is_dir():
            start = str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose a folder", start)
        if chosen:
            self.edit.setText(chosen)


class SettingsDialog(QDialog):
    """Edit the three roots. Applies on OK; Reset clears back to defaults."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(620, 520)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        heading = QLabel("Paths")
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)

        subtitle = QLabel(
            "Leave a field blank to use the default shown in grey. Changes apply "
            "when you press Save."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        overrides = config.path_overrides()
        self.rows: dict[str, _PathRow] = {}
        for key, label, helptext, tokens in FIELDS:
            row = _PathRow(key, label, helptext, tokens)
            row.set_value(overrides.get(key, ""))
            row.refresh_status()
            layout.addWidget(row)
            self.rows[key] = row

        layout.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.clicked.connect(self._on_reset)
        footer.addWidget(self.reset_button)
        footer.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("launchButton")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

    # -- results -----------------------------------------------------------

    def overrides(self) -> dict[str, str]:
        """Only the fields the user actually filled in."""
        return {
            key: row.value() for key, row in self.rows.items() if row.value()
        }

    def _on_reset(self) -> None:
        for row in self.rows.values():
            row.set_value("")
            row.refresh_status()
