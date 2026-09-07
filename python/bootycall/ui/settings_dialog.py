"""
Settings: the roots BootyCall reads.

Paths resolve in three layers -- the shipped constant, an environment variable,
then whatever is set here. This dialog writes the third layer, so a field left
blank means "use whatever the environment or the default says" rather than
"use an empty path".

The dialog is four rows and a panel. It used to carry, under every field, a
paragraph explaining it and a line reporting what the path resolved to -- so
four fields came with eight blocks of supporting text, all visible at once,
none of them about whatever you were actually typing in. The explanation is
worth having; having all four at all times is not.

So the panel at the bottom describes the field you are in, and says nothing
about the other three. And it reports a path only when the path is missing:
"found" on a path that is fine is a line you read once and then have to read
past forever.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .. import config
from ..local_packages import current_user

#: key -> (label, what it feeds, which placeholders it takes)
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
        "Your per-user package root.",
        "{user}",
    ),
    (
        "dev_root",
        "Dev packages",
        "Where your installed dev packages land, and what rez resolves. "
        "Leaving it as {local}/dev keeps the two together.",
        "{user}, {local}",
    ),
    (
        "dev_working_root",
        "Dev working location",
        "Where you edit dev packages, before installing them. The dev list "
        "reads this, and compares it against your installed packages to say "
        "when one is out of date.",
        "{user}, {home}, {local}",
    ),
)


def resolve(key: str, raw: str) -> str:
    """What a field resolves to, defaults and placeholders included.

    Every placeholder is offered to every row rather than a per-key list: a
    field that silently ignores ``{home}`` because of which row it is in is a
    rule nobody can see from the dialog.
    """
    text = raw.strip() or config.path_defaults()[key]
    user = current_user()
    try:
        expanded = text.format(
            user=user,
            home=os.path.expanduser("~"),
            local=config.local_root_template().format(user=user),
        )
    except (KeyError, IndexError):
        # An unknown placeholder is the user's typo to see, not ours to
        # swallow -- showing the raw text makes it obvious what happened.
        return text
    return os.path.expanduser(expanded)


class _PathField(QLineEdit):
    """A path field that says when it is entered."""

    entered = Signal()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.entered.emit()


class SettingsDialog(QDialog):
    """Edit the roots. Applies on Save; Reset clears back to defaults."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        heading = QLabel("Paths")
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)

        subtitle = QLabel("Leave a field blank to use the default shown in grey.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        # A grid, so the fields line up and the Browse column is one width
        # rather than four. In a per-row box layout the button was sized by
        # whatever space the row had left, which is how it ended up clipped.
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        overrides = config.path_overrides()
        self.rows: dict[str, _PathField] = {}
        self._help: dict[str, str] = {}

        for line, (key, label, helptext, tokens) in enumerate(FIELDS):
            caption = QLabel(label)
            caption.setObjectName("hint")
            grid.addWidget(caption, line, 0, Qt.AlignRight | Qt.AlignVCenter)

            edit = _PathField()
            edit.setObjectName("filterField")
            edit.setPlaceholderText(config.path_defaults()[key])
            edit.setText(overrides.get(key, ""))
            edit.textChanged.connect(
                lambda _text, k=key: self._on_changed(k)
            )
            edit.entered.connect(lambda k=key: self._describe(k))
            grid.addWidget(edit, line, 1)

            browse = QPushButton("Browse")
            # Both to the taller of the two hints. A fixed height taken from
            # the field alone is how the button ended up clipped: its own hint
            # is larger, because the stylesheet gives it more padding.
            tall = max(edit.sizeHint().height(), browse.sizeHint().height())
            browse.setFixedHeight(tall)
            edit.setFixedHeight(tall)
            browse.clicked.connect(lambda _checked, k=key: self._on_browse(k))
            grid.addWidget(browse, line, 2)

            self.rows[key] = edit
            self._help[key] = helptext + (
                "  Placeholders: %s" % tokens if tokens else ""
            )

        layout.addLayout(grid)
        layout.addStretch(1)

        # One panel, always the same height, so nothing below it moves as the
        # text in it changes.
        self.detail = QLabel("")
        self.detail.setObjectName("hint")
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(34)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.detail)

        self.problem = QLabel("")
        self.problem.setObjectName("statusLabel")
        self.problem.setProperty("level", "error")
        self.problem.setWordWrap(True)
        self.problem.setMinimumHeight(18)
        self.problem.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.problem)

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

        for key in self.rows:
            self._mark(key)
        self._describe(next(iter(self.rows)))
        self.adjustSize()

    # -- values ------------------------------------------------------------

    def value(self, key: str) -> str:
        return self.rows[key].text().strip()

    def effective(self, key: str) -> str:
        return resolve(key, self.rows[key].text())

    def overrides(self) -> dict[str, str]:
        """Only the fields the user actually filled in."""
        return {key: self.value(key) for key in self.rows if self.value(key)}

    def missing(self) -> list[str]:
        """Keys whose path is not a directory. Empty when everything is there."""
        return [k for k in self.rows if not Path(self.effective(k)).is_dir()]

    # -- feedback ----------------------------------------------------------

    def _describe(self, key: str) -> None:
        """Say what the field you are in is for, and only that field."""
        self._current = key
        label = dict((f[0], f[1]) for f in FIELDS)[key]
        self.detail.setText("%s — %s" % (label, self._help[key]))
        self._show_problem(key)

    def _show_problem(self, key: str) -> None:
        resolved = self.effective(key)
        if Path(resolved).is_dir():
            # Nothing to say. A path that is fine does not need a line about
            # being fine.
            self.problem.setText("")
        else:
            self.problem.setText("Not found: %s" % resolved)

    def _mark(self, key: str) -> None:
        """Tint a field whose path is missing, so it shows without clicking."""
        edit = self.rows[key]
        state = "" if Path(self.effective(key)).is_dir() else "bad"
        if edit.property("state") != state:
            edit.setProperty("state", state)
            edit.style().unpolish(edit)
            edit.style().polish(edit)

    def _on_changed(self, key: str) -> None:
        self._mark(key)
        if getattr(self, "_current", None) == key:
            self._show_problem(key)

    def _on_browse(self, key: str) -> None:
        start = self.effective(key)
        if not Path(start).is_dir():
            start = str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose a folder", start)
        if chosen:
            self.rows[key].setText(chosen)
            self._describe(key)

    def _on_reset(self) -> None:
        for key, edit in self.rows.items():
            edit.setText("")
            self._mark(key)
        self._describe(getattr(self, "_current", next(iter(self.rows))))
