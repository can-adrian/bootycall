"""Row painting for the package lists.

Every row in these lists is several things at once: a package, where its
source lives, and what this window has worked out about it --
``rig_utils  1.12.1  alembic    (in use)``.

Qt's default item painting draws all of that in one weight, so the reader has
to parse the string to see which part is which. This delegate italicises
anything in brackets, which is exactly the set of asides -- ``(in use)``,
``(overridden)``, ``(live)``, ``(symlinked)`` -- and leaves the package itself
upright.

It also shifts rows marked with :data:`INDENT_ROLE`. Those are the ones with
no checkbox, which Qt draws further left than the rows that have one; without
the shift they would stick out to the left of everything beside them.

The parts run left to right with the spacing the text itself carries. Column
alignment was tried and read worse: a version column pushed out by one long
name leaves every other row with a gap in the middle of it, and the eye ends
up following the whitespace rather than the packages.

It paints only the text. The checkbox, the selection background and the focus
rectangle are still drawn by the style, because reimplementing those is how a
list stops looking like the rest of the application.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

#: Splits on a bracketed group, keeping it. Non-greedy and newline-free so an
#: unclosed bracket cannot swallow the rest of the row.
_BRACKETED = re.compile(r"(\([^()\n]*\))")

#: A row's parts: ``(name, version, folder, status)``. Not used for painting
#: -- the row's own text is what gets drawn -- but it is what lets the window
#: rewrite the status without parsing its way back through the rest.
#: Deliberately far from the roles the window itself hands out, so the two
#: blocks cannot grow into each other.
CELLS_ROLE = Qt.UserRole + 21

#: Set on a row that has no checkbox but sits among rows that do.
INDENT_ROLE = Qt.UserRole + 20


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


class PackageItemDelegate(QStyledItemDelegate):
    """Draws package rows with the window's asides in italic."""

    def paint(self, painter, option, index) -> None:  # noqa: N802 - Qt's name
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        indented = bool(index.data(INDENT_ROLE))
        parts = runs(opt.text)
        if len(parts) < 2 and not indented:
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
        x = float(rect.left())
        right = float(rect.right()) + 1.0
        for fragment, italic in parts:
            if x >= right:
                break
            x += self._draw(
                painter, opt, rect, fragment, x, right - x, italic=italic
            )
        painter.restore()

    @staticmethod
    def _colour(opt, index) -> QColor:
        if opt.state & QStyle.State_Selected:
            return opt.palette.highlightedText().color()
        given = index.data(Qt.ForegroundRole)
        if isinstance(given, QColor):
            return given
        if given is not None and hasattr(given, "color"):
            return given.color()
        return opt.palette.text().color()

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
