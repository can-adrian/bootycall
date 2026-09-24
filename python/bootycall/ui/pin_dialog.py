"""
Pin a show's bootstrap to the versions a resolve actually produced.

The dialog's whole job is to be readable before anything is written. It lists
every request the bootstrap names -- not only the ones about to change --
because a list of just the changes cannot be read for what it is leaving
alone, and "what did it *not* pin?" is the question you ask at four o'clock
on a Friday.

Two things it will not do without being told twice: write a version that only
exists in your own package root, and overwrite the show's own file. The first
produces a bootstrap that resolves on your machine and nowhere else. The
second is fine, and is why the original is copied beside it first.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from .. import pinning
from .package_delegate import PackageItemDelegate
from .style import ROW_IN_USE, ROW_LOST, ROW_PLAIN, ROW_QUIET

#: label -> how many version components to keep. Nothing here writes rez's
#: ``==`` form: a prefix range at full depth is the syntax the file already
#: uses, and putting a form into a production bootstrap that nobody here has
#: watched rez read is the kind of guess this tool exists to avoid.
DEPTHS: tuple[tuple[str, int], ...] = (
    ("Exactly what resolved", 0),
    ("Patch version  (1.7.8)", 3),
    ("Feature version  (1.7)", 2),
)


class PinBootstrapDialog(QDialog):
    """Choose how tightly to pin, and where the result goes."""

    def __init__(
        self,
        parent,
        bootstrap,
        resolved: dict,
        own_roots: tuple = (),
        tool: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pin bootstrap")
        self.setModal(True)
        self.setMinimumWidth(620)

        self._bootstrap = bootstrap
        self._resolved = resolved
        self._own_roots = tuple(own_roots)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        heading = QLabel("Pin %s" % Path(bootstrap.path).name)
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)

        subtitle = QLabel(
            "Rewrites the requests this file already names, to the versions "
            "rez resolved%s. Nothing else in the file changes."
            % (" for %s" % tool if tool else "")
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        picker = QHBoxLayout()
        picker.setSpacing(8)
        caption = QLabel("Pin to")
        caption.setObjectName("hint")
        picker.addWidget(caption)
        self.depth_box = QComboBox()
        for label, depth in DEPTHS:
            self.depth_box.addItem(label, depth)
        self.depth_box.currentIndexChanged.connect(self._refresh)
        picker.addWidget(self.depth_box)
        picker.addStretch(1)
        layout.addLayout(picker)

        self.listing = QListWidget()
        self.listing.setItemDelegate(PackageItemDelegate(self.listing))
        self.listing.setMinimumHeight(220)
        layout.addWidget(self.listing, 1)

        self.own_box = QCheckBox(
            "Also pin versions that only exist in my own packages"
        )
        self.own_box.setToolTip(
            "Those versions may exist nowhere else. A bootstrap pinned to one "
            "resolves on this machine and fails for the farm and everyone "
            "else on the show."
        )
        self.own_box.toggled.connect(self._refresh)
        layout.addWidget(self.own_box)

        self.copy_button = QRadioButton("Save a copy...")
        self.copy_button.setChecked(True)
        self.overwrite_button = QRadioButton(
            "Overwrite this file, keeping a dated backup beside it"
        )
        layout.addWidget(self.copy_button)
        layout.addWidget(self.overwrite_button)

        self.summary = QLabel("")
        self.summary.setObjectName("hint")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.write_button = QPushButton("Write")
        self.write_button.setObjectName("launchButton")
        self.write_button.setDefault(True)
        self.write_button.clicked.connect(self.accept)
        footer.addWidget(self.write_button)
        layout.addLayout(footer)

        self._refresh()
        self.adjustSize()

    # -- what the dialog decided ------------------------------------------

    def depth(self) -> int:
        return int(self.depth_box.currentData() or 0)

    def allow_own(self) -> bool:
        return self.own_box.isChecked()

    def overwrite(self) -> bool:
        return self.overwrite_button.isChecked()

    def pins(self) -> list:
        """The plan as the dialog currently shows it."""
        return pinning.plan(
            self._bootstrap,
            self._resolved,
            depth=self.depth(),
            own_roots=() if self.allow_own() else self._own_roots,
        )

    # -- drawing -----------------------------------------------------------

    def _refresh(self) -> None:
        pins = self.pins()
        # Counted with the refusal on whatever the checkbox says, so the
        # warning does not disappear the moment you agree to ignore it.
        own = len(
            [
                p
                for p in pinning.plan(
                    self._bootstrap,
                    self._resolved,
                    depth=self.depth(),
                    own_roots=self._own_roots,
                )
                if p.blocked.startswith("only in your")
            ]
        )
        self.listing.clear()

        changing = 0
        for pin in pins:
            if pin.changes:
                changing += 1
                text = "%s  →  %s" % (pin.request, pin.pinned)
                colour = ROW_IN_USE
            elif pin.blocked.startswith("only in your"):
                text = "%s  (%s, %s)" % (pin.request, pin.version, pin.blocked)
                colour = ROW_LOST
            elif pin.blocked:
                text = "%s  (%s)" % (pin.request, pin.blocked)
                colour = ROW_QUIET
            else:
                text = "%s  (already this specific)" % pin.request
                colour = ROW_PLAIN
            item = QListWidgetItem(text)
            item.setForeground(QColor(colour))
            item.setFlags(Qt.ItemIsEnabled)
            self.listing.addItem(item)

        # Counting the ones left alone as loudly as the ones being changed:
        # this dialog is read to find out what it is *not* going to do.
        parts = ["%d of %d requests would change" % (changing, len(pins))]
        if own:
            parts.append(
                "%d can only come from your own packages and %s"
                % (own, "will be written" if self.allow_own() else "will not be")
            )
        self.summary.setText(".  ".join(parts) + ".")
        self.own_box.setVisible(bool(own))
        self.write_button.setEnabled(changing > 0)
