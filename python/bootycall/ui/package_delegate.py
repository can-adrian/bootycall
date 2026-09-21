"""Row painting for the package lists.

Every row in these lists is several things at once: a package, where its
source lives, and what this window has worked out about it. Written as one
string -- ``rig_utils-1.12.1  (alembic)  overrides rig_utils-1`` -- the reader
has to parse it to see which part is which, and nothing lines up with the row
above, so a list of twenty builds is twenty separate acts of reading.

So a row that carries :data:`CELLS_ROLE` is drawn in columns: name, version,
the folder it came from, and what this window has to say about it. The columns
are measured once across the whole list, so they line up down it, and the
folder column is capped rather than allowed to push the last column off the
edge. Anything in brackets is italic -- ``(in use)``, ``(overridden)``,
``(live)`` -- because those are the window talking, not the package.

A row with no cells is drawn the old way, as one string with its bracketed
asides italicised. That is what the resolve and local lists still use.

It paints only the text. The checkbox, the selection background and the focus
rectangle are still drawn by the style, because reimplementing those is how a
list stops looking like the rest of the application.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

#: Splits on a bracketed group, keeping it. Non-greedy and newline-free so an
#: unclosed bracket cannot swallow the rest of the row.
_BRACKETED = re.compile(r"(\([^()\n]*\))")

#: A row's cells: ``(name, version, folder, status)``. Any of them may be
#: empty, and an empty one still holds its column open, which is the point.
#: Deliberately far from the roles the window itself hands out, so the two
#: blocks cannot grow into each other.
CELLS_ROLE = Qt.UserRole + 21

#: Set on a row that has no checkbox but sits among rows that do. Qt draws
#: such a row's text further left, so without this it would stick out to the
#: left of every row beside it -- which is the opposite of lining up.
INDENT_ROLE = Qt.UserRole + 20

#: Space between columns.
_GUTTER = 14

#: The most of the row the folder column may take. A worktree named after a
#: JIRA ticket and a description should elide rather than shove the column
#: that says whether the package is in the environment off the edge.
_FOLDER_SHARE = 0.34


def runs(text: str) -> list[tuple[str, bool]]:
    """``text`` split into ``(fragment, italic)`` pairs."""
    return [
        (part, bool(part) and part.startswith("(") and part.endswith(")"))
        for part in _BRACKETED.split(text)
        if part
    ]


def indent_for(opt, style, widget) -> int:
    """How far to shift a row that has no checkbox, so its text lines up.

    Asked of the style rather than guessed: the same option with a checkbox
    added says where the text *would* start if this row had one, and the
    difference is exactly the width the style reserves for it. A number picked
    by eye here would be right until someone changed the stylesheet.
    """
    plain = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
    boxed = QStyleOptionViewItem(opt)
    boxed.features |= QStyleOptionViewItem.HasCheckIndicator
    boxed.checkState = Qt.Unchecked
    shift = (
        style.subElementRect(QStyle.SE_ItemViewItemText, boxed, widget).left()
        - plain.left()
    )
    return max(shift, 0)


def column_widths(widget, font=None) -> tuple[int, int, int]:
    """Widest name, version and folder in ``widget``, in pixels.

    Measured across every row rather than per row, because a column that is
    only as wide as the row it is in is not a column.
    """
    metrics = QFontMetrics(font if font is not None else widget.font())
    widest = [0, 0, 0]
    for row in range(widget.count()):
        cells = widget.item(row).data(CELLS_ROLE)
        if not cells:
            continue
        for column in range(3):
            text = cells[column] if column < len(cells) else ""
            if text:
                widest[column] = max(widest[column], metrics.horizontalAdvance(text))
    return tuple(widest)  # type: ignore[return-value]


class PackageItemDelegate(QStyledItemDelegate):
    """Draws package rows in columns, with the window's asides in italic."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._columns: tuple[int, int, int] | None = None

    def invalidate_columns(self) -> None:
        """Forget the measured column widths.

        Called when the list is rebuilt. The status column is rewritten far
        more often than that, but it is the last one and nothing lines up
        behind it, so it costs no remeasuring.
        """
        self._columns = None

    def _widths(self, widget, font) -> tuple[int, int, int]:
        if self._columns is None:
            self._columns = column_widths(widget, font)
        return self._columns

    # -- painting ----------------------------------------------------------

    def paint(self, painter, option, index) -> None:  # noqa: N802 - Qt's name
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        cells = index.data(CELLS_ROLE)
        indented = bool(index.data(INDENT_ROLE))
        parts = runs(opt.text)
        if not cells and len(parts) < 2 and not indented:
            # Nothing to set apart and nothing to line up. Hand it back to Qt
            # rather than repainting it slightly differently by hand.
            super().paint(painter, option, index)
            return

        # Let the style draw everything except the text: checkbox, selection,
        # hover, focus rectangle.
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)

        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
        if rect.isEmpty():
            return
        if indented:
            rect.setLeft(rect.left() + indent_for(opt, style, widget))
            if rect.isEmpty():
                return

        painter.save()
        painter.setClipRect(rect)
        painter.setPen(self._colour(opt, index))
        if cells and widget is not None:
            self._paint_cells(painter, opt, rect, widget, list(cells))
        else:
            self._paint_runs(painter, opt, rect, parts, float(rect.left()))
        painter.restore()

    @staticmethod
    def _colour(opt, index) -> QColor:
        colour = opt.palette.text().color()
        if opt.state & QStyle.State_Selected:
            return opt.palette.highlightedText().color()
        given = index.data(Qt.ForegroundRole)
        if isinstance(given, QColor):
            return given
        if given is not None and hasattr(given, "color"):
            return given.color()
        return colour

    def _paint_cells(self, painter, opt, rect, widget, cells) -> None:
        """One column at a time, each starting where every other row's does."""
        while len(cells) < 4:
            cells.append("")
        name_w, version_w, folder_w = self._widths(widget, opt.font)
        folder_w = min(folder_w, int(rect.width() * _FOLDER_SHARE))

        x = float(rect.left())
        right = float(rect.right()) + 1.0
        for column, text in enumerate(cells):
            if x >= right:
                break
            if column == 3:
                # The last column takes whatever is left: nothing lines up
                # behind it, so capping it would only elide for the sake of it.
                self._paint_runs(painter, opt, rect, runs(text), x)
                break
            width = (name_w, version_w, folder_w)[column]
            if text:
                self._draw(painter, opt, rect, text, x, min(width, right - x))
            # The column holds its place even when this row's cell is empty --
            # that is the difference between a column and a gap.
            x += width + _GUTTER

    def _paint_runs(self, painter, opt, rect, parts, x: float) -> None:
        """Fragments end to end, brackets italic, from ``x``."""
        right = float(rect.right()) + 1.0
        for fragment, italic in parts:
            if x >= right:
                break
            x += self._draw(
                painter, opt, rect, fragment, x, right - x, italic=italic
            )

    @staticmethod
    def _draw(painter, opt, rect, text, x: float, room: float, italic=False) -> float:
        """Draw ``text`` at ``x``. Returns how much width it actually took."""
        font = opt.font
        font.setItalic(italic)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        shown = text
        if metrics.horizontalAdvance(text) > room:
            # Elide the fragment that runs out of room rather than the whole
            # line: the package name is at the front and is the part worth
            # keeping.
            shown = metrics.elidedText(text, Qt.ElideRight, int(max(room, 0)))
        painter.drawText(
            QRectF(x, rect.top(), max(room, 0.0), rect.height()),
            int(Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine),
            shown,
        )
        return metrics.horizontalAdvance(shown)
