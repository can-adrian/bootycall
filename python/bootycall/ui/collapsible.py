"""
Collapsible section.

A header row that toggles a content area. The header carries a badge on the
right so the section still reports what it holds while closed -- the point of
collapsing these is to get the noise out of the way, not to hide whether there
is anything worth opening.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleFrame(QWidget):
    """A titled section that expands and collapses."""

    toggled = Signal(bool)

    def __init__(self, title: str, expanded: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleFrame")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("collapsibleHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 5, 10, 5)
        header_layout.setSpacing(8)

        self.toggle_button = QToolButton()
        self.toggle_button.setObjectName("collapsibleToggle")
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.setFocusPolicy(Qt.TabFocus)
        self.toggle_button.clicked.connect(self.set_expanded)
        header_layout.addWidget(self.toggle_button)

        header_layout.addStretch(1)

        self.badge = QLabel("")
        self.badge.setObjectName("collapsibleBadge")
        header_layout.addWidget(self.badge)

        self.note = QLabel("")
        self.note.setObjectName("collapsibleNote")
        self.note.setVisible(False)
        header_layout.addWidget(self.note)

        outer.addWidget(header)

        self.content = QWidget()
        self.content.setObjectName("collapsibleContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 6, 0, 0)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)
        outer.addWidget(self.content)

        self._apply_size_policy(expanded)

    # -- state -------------------------------------------------------------

    def is_expanded(self) -> bool:
        return self.toggle_button.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        changed = expanded != self.content.isVisible()
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content.setVisible(expanded)
        self._apply_size_policy(expanded)
        if changed:
            self.toggled.emit(expanded)

    def toggle(self) -> None:
        self.set_expanded(not self.is_expanded())

    def _apply_size_policy(self, expanded: bool) -> None:
        # Collapsed sections must not hold on to vertical space, or two closed
        # frames leave a gap the size of the window.
        self.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Expanding if expanded else QSizePolicy.Fixed,
        )

    # -- header text -------------------------------------------------------

    def set_title(self, title: str) -> None:
        self.toggle_button.setText(title)

    def set_badge(self, text: str) -> None:
        """Right-hand count, e.g. ``29 packages``."""
        self.badge.setText(text)

    def set_note(self, text: str, level: str = "") -> None:
        """A highlighted note beside the badge, e.g. an override warning."""
        self.note.setText(text)
        self.note.setVisible(bool(text))
        if self.note.property("level") != level:
            self.note.setProperty("level", level)
            self.note.style().unpolish(self.note)
            self.note.style().polish(self.note)

    # -- content -----------------------------------------------------------

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.content_layout.addWidget(widget, stretch)
