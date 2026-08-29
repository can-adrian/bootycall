"""
Wrapping horizontal layout.

The software row holds seven DCCs plus a terminal and a favourites button, and
a show may add more. A QHBoxLayout would squash them all past legibility on a
narrow window, so the row wraps instead.

This is the standard Qt flow-layout pattern: lay items out left to right,
starting a new line whenever the next item would overflow.
"""

from __future__ import annotations

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy


class FlowLayout(QLayout):
    def __init__(
        self,
        parent=None,
        margin: int = 0,
        spacing: int = 8,
        expand_widget=None,
    ) -> None:
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        # The show field's text entry fills whatever width the chips left on
        # its line. Naming the widget rather than saying "the last one" matters
        # in compact mode, where the entry is hidden and the last visible item
        # is a chip, which should keep its own width.
        self._expand_widget = expand_widget
        self.setContentsMargins(QMargins(margin, margin, margin, margin))

    # -- QLayout plumbing --------------------------------------------------

    def addItem(self, item) -> None:  # noqa: N802 - Qt API
        self._items.append(item)

    def insertWidget(self, index: int, widget) -> None:  # noqa: N802 - Qt API
        """Add a widget at a position. QLayout has no insert of its own."""
        self.addWidget(widget)
        item = self._items.pop()
        self._items.insert(max(0, min(index, len(self._items))), item)
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt API
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - Qt API
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802 - Qt API
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt API
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt API
        size = QSize()
        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                # Hidden items must not hold the row open: in compact mode the
                # show field's entry is hidden, and its 170px minimum would
                # otherwise set the floor for the whole window.
                continue
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    # -- the actual flow ---------------------------------------------------

    def _layout(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        # Geometry is applied per line, not per item: a short item (the ⋯
        # button next to full-height tiles) can only be centred once the tallest
        # item on its line is known.
        line: list[tuple[object, QRect]] = []

        def flush() -> None:
            if not apply:
                return
            for entry, geometry in line:
                offset = (line_height - geometry.height()) // 2
                entry.setGeometry(geometry.translated(0, offset))

        visible = [
            i
            for i in self._items
            if i.widget() is None or not i.widget().isHidden()
        ]
        for item in visible:
            hint = item.sizeHint()
            expands = (
                self._expand_widget is not None
                and item.widget() is self._expand_widget
            )
            if expands:
                hint = QSize(max(hint.width(), item.minimumSize().width()), hint.height())
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > effective.right() and line_height > 0:
                flush()
                line = []
                x = effective.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            geometry = QRect(QPoint(x, y), hint)
            if expands:
                # Stretch to the right edge of the row.
                geometry.setRight(effective.right())
            line.append((item, geometry))
            x = next_x
            line_height = max(line_height, hint.height())

        flush()
        return y + line_height - rect.y() + margins.bottom()

    def spacing(self) -> int:
        return self._spacing

    def setSpacing(self, spacing: int) -> None:  # noqa: N802 - Qt API
        self._spacing = spacing
        self.invalidate()

    def clear(self) -> None:
        """Remove and delete every item's widget."""
        while self._items:
            item = self._items.pop()
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
