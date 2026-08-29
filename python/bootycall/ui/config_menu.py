"""
Menu row for a saved setup.

A plain QAction can't carry a clickable control on its right-hand side, so each
saved setup is a QWidgetAction wrapping this widget: the name is the clickable
body, and the trailing X removes it without closing the menu, so several can be
cleared in one go.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QStyle,
    QStyleOption,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from ..configs import SavedConfig


class ConfigMenuItem(QWidget):
    """One saved setup: click the body to apply it, click the X to delete it."""

    applied = Signal(str)  # config name
    removed = Signal(str)  # config name

    def __init__(self, config: SavedConfig, parent=None) -> None:
        super().__init__(parent)
        self._name = config.name
        self.setObjectName("configItem")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(26)

        layout = QHBoxLayout(self)
        # Left margin lines the text up with the menu's other entries, which are
        # indented to leave room for checkmarks.
        layout.setContentsMargins(26, 2, 6, 2)
        layout.setSpacing(10)

        self.label = QLabel(config.name)
        self.label.setObjectName("configItemLabel")
        layout.addWidget(self.label)

        layout.addStretch(1)

        self.detail = QLabel(config.summary)
        self.detail.setObjectName("configItemDetail")
        layout.addWidget(self.detail)

        self.remove_button = QToolButton()
        self.remove_button.setObjectName("configRemoveButton")
        self.remove_button.setText("✕")  # ✕
        self.remove_button.setCursor(Qt.ArrowCursor)
        self.remove_button.setFixedSize(18, 18)
        self.remove_button.setToolTip("Remove '%s'" % config.name)
        self.remove_button.setFocusPolicy(Qt.NoFocus)
        self.remove_button.clicked.connect(self._on_remove)
        layout.addWidget(self.remove_button)

        self.setToolTip(
            "%s\nShow: %s\nTool: %s" % (config.name, config.show, config.tool)
        )

    @property
    def name(self) -> str:
        return self._name

    # -- hover highlight ---------------------------------------------------

    def paintEvent(self, event) -> None:
        # A bare QWidget ignores stylesheet backgrounds unless it draws
        # PE_Widget itself; without this the hover rule never shows.
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, option, painter, self)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.HoverEnter:
            self._set_hover(True)
        elif event.type() == QEvent.HoverLeave:
            self._set_hover(False)
        return super().event(event)

    def _set_hover(self, hovered: bool) -> None:
        if self.property("hover") == hovered:
            return
        self.setProperty("hover", hovered)
        for widget in (self, self.label, self.detail, self.remove_button):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    # -- interaction -------------------------------------------------------

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self._close_menu()
            self.applied.emit(self._name)
        super().mouseReleaseEvent(event)

    def _on_remove(self) -> None:
        # Menu stays open: removing several in a row is the common case.
        self.removed.emit(self._name)

    def _close_menu(self) -> None:
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, QMenu):
                widget.close()
                return
            widget = widget.parentWidget()


class ConfigMenuAction(QWidgetAction):
    """QWidgetAction wrapper so the row can live in a QMenu."""

    def __init__(self, config: SavedConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.item = ConfigMenuItem(config)
        self.applied = self.item.applied
        self.removed = self.item.removed
        self.setDefaultWidget(self.item)
