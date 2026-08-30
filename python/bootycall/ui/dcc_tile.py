"""
A DCC tile: icon, software name, and the chosen variant beneath it.

QToolButton draws one run of text in one colour, so the variant line is painted
on afterwards. The alternative -- a composite widget faking a button -- costs
the real hover, checked and disabled states that the style already gives us.

Right-clicking a tile picks the variant, which is why there is no variant
dropdown anywhere: the choice belongs to the thing it describes.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QToolButton

#: Height reserved below the button's own text for the variant line. The
#: stylesheet pads the tile by the same amount so nothing overlaps.
SUBTITLE_HEIGHT = 14


class DccTile(QToolButton):
    """One software tile. Left-click selects it, right-click picks the variant."""

    variantMenuRequested = Signal(object, object)  # (tile, QPoint)

    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dccButton")
        self.dcc_name = name
        self._subtitle = ""
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda point: self.variantMenuRequested.emit(self, point)
        )

    # -- subtitle ----------------------------------------------------------

    def set_interactive(self, enabled: bool) -> None:
        """Turn clicking on or off without greying the tile out.

        Compact mode shows the selected tile as a label. Disabling it would
        grey the icon and read as "this software is unavailable", which is the
        opposite of what it means.
        """
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not enabled)
        self.setFocusPolicy(Qt.StrongFocus if enabled else Qt.NoFocus)

    def subtitle(self) -> str:
        return self._subtitle

    def set_subtitle(self, text: str) -> None:
        if text == self._subtitle:
            return
        self._subtitle = text
        self.update()

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._subtitle:
            return

        painter = QPainter(self)
        font = QFont(self.font())
        font.setPointSizeF(max(6.5, self.font().pointSizeF() - 1.5))
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#a0b6cd" if self.isEnabled() else "#507296"))

        area = QRect(
            4,
            self.height() - SUBTITLE_HEIGHT - 6,
            self.width() - 8,
            SUBTITLE_HEIGHT,
        )
        metrics = painter.fontMetrics()
        text = metrics.elidedText(self._subtitle, Qt.ElideRight, area.width())
        painter.drawText(area, Qt.AlignHCenter | Qt.AlignVCenter, text)
        painter.end()
