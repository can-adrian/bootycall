"""Row painting for the package lists.

Every row in these lists is two things at once: a package, and what this window
has worked out about it. ``nuke_utils-4.10.0      outranked by 4.11.0`` is a
name followed by a finding, and ``rig_utils-1.8.666  (symlinked)`` is a name
followed by a fact about the install.

Qt's default item painting draws all of that in one weight, so the reader has
to parse the string to see which half is which. This delegate italicises
anything in brackets, which is exactly the set of asides -- ``(symlinked)``,
``(not installed)``, ``(older build)``, ``(show package)`` -- and leaves the
package itself upright.

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


def runs(text: str) -> list[tuple[str, bool]]:
    """``text`` split into ``(fragment, italic)`` pairs."""
    return [
        (part, bool(part) and part.startswith("(") and part.endswith(")"))
        for part in _BRACKETED.split(text)
        if part
    ]


class PackageItemDelegate(QStyledItemDelegate):
    """Draws package rows with their bracketed asides in italic."""

    def paint(self, painter, option, index) -> None:  # noqa: N802 - Qt's name
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        parts = runs(text)
        if len(parts) < 2:
            # Nothing to set apart. Hand it back to Qt rather than repainting
            # it slightly differently by hand.
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

        colour = opt.palette.text().color()
        if opt.state & QStyle.State_Selected:
            colour = opt.palette.highlightedText().color()
        else:
            given = index.data(Qt.ForegroundRole)
            if isinstance(given, QColor):
                colour = given
            elif given is not None and hasattr(given, "color"):
                colour = given.color()

        painter.save()
        painter.setClipRect(rect)
        painter.setPen(colour)
        font = opt.font
        x = float(rect.left())
        right = float(rect.right()) + 1.0
        for fragment, italic in parts:
            if x >= right:
                break
            font.setItalic(italic)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            remaining = right - x
            shown = fragment
            if metrics.horizontalAdvance(fragment) > remaining:
                # Elide the fragment that runs out of room rather than the
                # whole line: the package name is at the front and is the part
                # worth keeping.
                shown = metrics.elidedText(fragment, Qt.ElideRight, int(remaining))
            painter.drawText(
                QRectF(x, rect.top(), remaining, rect.height()),
                int(Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine),
                shown,
            )
            x += metrics.horizontalAdvance(shown)
        painter.restore()
