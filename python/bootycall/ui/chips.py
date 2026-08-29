"""
The show field: a token input holding pinned show chips plus a text entry.

Typing a show and pressing Enter pins it as a rounded chip *inside* the field,
the way a mail client tokenises recipients. The chips are the shortlist someone
actually works across -- the two or three shows they are on this week -- and
exactly one is selected at a time, because everything below the field (DCC,
variant, packages, launch) describes a single show.

The text entry is the last item in the same wrapping row, so it takes whatever
width the chips left and drops to a new line when they fill one.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyleOption,
    QToolButton,
    QWidget,
)

from .completer import ProjectLineEdit
from .flow_layout import FlowLayout


#: Chip height. The stylesheet's border-radius is half this, so the ends are
#: true semicircles rather than rounded corners.
CHIP_HEIGHT = 24


class ShowChip(QWidget):
    """One pinned show: click the body to select, click the ✕ to unpin."""

    clicked = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        self._name = name
        self._elide_width: int | None = None
        self.setObjectName("showChip")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setProperty("selected", False)

        # Fixed height so the corner radius can be exactly half of it: a
        # radius smaller than half draws a rounded rectangle, and how tall the
        # chip would otherwise be depends on the workstation's font.
        self.setFixedHeight(CHIP_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 0, 5, 0)
        layout.setSpacing(6)

        self.label = QLabel(name)
        self.label.setObjectName("showChipLabel")
        layout.addWidget(self.label)

        self.remove_button = QToolButton()
        self.remove_button.setObjectName("showChipRemove")
        self.remove_button.setText("✕")
        self.remove_button.setCursor(Qt.ArrowCursor)
        self.remove_button.setFixedSize(15, 15)
        self.remove_button.setFocusPolicy(Qt.NoFocus)
        self.remove_button.setToolTip("Unpin %s" % name)
        self.remove_button.clicked.connect(
            lambda: self.removeRequested.emit(self._name)
        )
        layout.addWidget(self.remove_button)

        self.setToolTip(name)

    @property
    def name(self) -> str:
        return self._name

    def set_interactive(self, enabled: bool) -> None:
        """Turn clicking on or off without changing how the chip looks.

        Compact mode shows the selected chip as a label, not a control, so it
        is made transparent to the mouse rather than disabled -- a greyed-out
        chip would read as "this show is unavailable". The ✕ goes away
        entirely, since a control you cannot use should not take up room.
        """
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not enabled)
        self.setFocusPolicy(Qt.TabFocus if enabled else Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self.remove_button.setVisible(enabled)
        self._apply_label()

    def set_elide_width(self, width: int | None) -> None:
        """Cap the chip's width, shortening the name to fit.

        Compact mode wants the whole window no wider than a software tile, and
        show codes are longer than that. The full name stays in the tooltip.
        """
        if width == self._elide_width:
            return
        self._elide_width = width
        self._apply_label()

    def _apply_label(self) -> None:
        if self._elide_width is None:
            self.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
            self.label.setText(self._name)
            return

        margins = self.layout().contentsMargins()
        chrome = margins.left() + margins.right()
        if not self.remove_button.isHidden():
            chrome += self.layout().spacing() + self.remove_button.width()
        available = max(24, self._elide_width - chrome)
        self.label.setText(
            self.label.fontMetrics().elidedText(
                self._name, Qt.ElideMiddle, available
            )
        )
        self.setMaximumWidth(self._elide_width)

    def is_selected(self) -> bool:
        return bool(self.property("selected"))

    def set_selected(self, selected: bool) -> None:
        if self.property("selected") == selected:
            return
        self._restyle("selected", selected)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        # A bare QWidget ignores stylesheet backgrounds unless it draws
        # PE_Widget itself.
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, option, painter, self)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.HoverEnter:
            self._restyle("hover", True)
        elif event.type() == QEvent.HoverLeave:
            self._restyle("hover", False)
        return super().event(event)

    def _restyle(self, prop: str, value: bool) -> None:
        self.setProperty(prop, value)
        for widget in (self, self.label, self.remove_button):
            widget.setProperty(prop, value)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()

    # -- interaction -------------------------------------------------------

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self._name)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self._name)
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.removeRequested.emit(self._name)
            return
        super().keyPressEvent(event)


class ShowChipBar(QFrame):
    """The show field: pinned chips and the text entry, in one bordered box.

    Named for what it manages rather than what it looks like; the main window
    talks to it as the chip collection, and it happens to own the entry too.
    """

    selectionChanged = Signal(object)  # show name, or None
    chipsChanged = Signal()  # pinned set changed -- persist it

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("showField")
        self.setFrameShape(QFrame.NoFrame)

        self._row = FlowLayout(self, margin=6, spacing=6)
        # Same reason as the DCC row: chips wrap, and a parent layout only asks
        # for the wrapped height when the size policy tells it to.
        _policy = self.sizePolicy()
        _policy.setHeightForWidth(True)
        self.setSizePolicy(_policy)

        self.line_edit = ProjectLineEdit()
        self.line_edit.setObjectName("showFieldEdit")
        self.line_edit.setMinimumWidth(170)
        self.line_edit.setFrame(False)
        self.line_edit.installEventFilter(self)
        self._row.addWidget(self.line_edit)
        # The entry, not "the last item": in compact mode it is hidden and the
        # last visible item is a chip, which should keep its own width.
        self._row._expand_widget = self.line_edit

        self._chips: list[ShowChip] = []
        self._selected: str | None = None
        self._chip_max_width: int | None = None
        self._interactive = True

    def set_chip_max_width(self, width: int | None) -> None:
        """Cap every chip's width, now and for chips added later."""
        self._chip_max_width = width
        for chip in self._chips:
            chip.set_elide_width(width)

    def set_interactive(self, enabled: bool) -> None:
        """Turn chip clicking on or off, now and for chips added later."""
        self._interactive = enabled
        for chip in self._chips:
            chip.set_interactive(enabled)

    # -- focus ring --------------------------------------------------------

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self.line_edit:
            if event.type() in (QEvent.FocusIn, QEvent.FocusOut):
                # The border belongs to the box, but focus lands on the entry.
                self.setProperty("focused", event.type() == QEvent.FocusIn)
                self.style().unpolish(self)
                self.style().polish(self)
            elif event.type() == QEvent.KeyPress:
                if (
                    event.key() == Qt.Key_Backspace
                    and not self.line_edit.text()
                    and self._chips
                ):
                    # Standard token-field behaviour: backspace on an empty
                    # entry eats the chip behind the cursor.
                    self.remove(self._chips[-1].name)
                    return True
        return super().eventFilter(watched, event)

    # -- queries -----------------------------------------------------------

    def names(self) -> list[str]:
        return [chip.name for chip in self._chips]

    def selected_name(self) -> str | None:
        return self._selected

    def chip(self, name: str) -> ShowChip | None:
        for chip in self._chips:
            if chip.name == name:
                return chip
        return None

    def __len__(self) -> int:
        return len(self._chips)

    # -- mutation ----------------------------------------------------------

    def add(self, name: str, select: bool = True) -> bool:
        """Pin ``name``. Returns True if it was new.

        Re-pinning an existing show selects it rather than duplicating it --
        hitting Enter twice on the same name should be idempotent, not an error.
        """
        existing = self.chip(name)
        if existing is not None:
            if select:
                self.select(name)
            return False

        chip = ShowChip(name)
        chip.set_elide_width(self._chip_max_width)
        chip.set_interactive(self._interactive)
        chip.clicked.connect(self.select)
        chip.removeRequested.connect(self.remove)
        self._chips.append(chip)
        # Before the entry, which stays last.
        self._row.insertWidget(self._row.count() - 1, chip)
        self._update_placeholder()

        if select:
            self.select(name)
        self.chipsChanged.emit()
        return True

    def remove(self, name: str) -> None:
        chip = self.chip(name)
        if chip is None:
            return
        index = self._chips.index(chip)
        was_selected = self._selected == name

        self._chips.remove(chip)
        self._row.removeWidget(chip)
        chip.setParent(None)
        chip.deleteLater()
        self._update_placeholder()

        if was_selected:
            # Land on the neighbour rather than dropping to nothing: removing
            # one of three shows should leave you working, not empty-handed.
            if self._chips:
                neighbour = self._chips[min(index, len(self._chips) - 1)]
                self._selected = None
                self.select(neighbour.name)
            else:
                self._selected = None
                self._sync_selection()
                self.selectionChanged.emit(None)

        self.chipsChanged.emit()

    def select(self, name: str | None) -> None:
        if name is not None and self.chip(name) is None:
            return
        if name == self._selected:
            return
        self._selected = name
        self._sync_selection()
        self.selectionChanged.emit(name)

    def clear(self) -> None:
        for chip in list(self._chips):
            self._chips.remove(chip)
            self._row.removeWidget(chip)
            chip.setParent(None)
            chip.deleteLater()
        self._selected = None
        self._update_placeholder()

    def set_names(self, names: list[str], selected: str | None = None) -> None:
        """Replace the whole set without emitting per-chip churn."""
        self.blockSignals(True)
        self.clear()
        for name in names:
            self.add(name, select=False)
        self.blockSignals(False)

        if selected in self.names():
            self._selected = None
            self.select(selected)
        elif self._chips:
            self._selected = None
            self.select(self._chips[0].name)
        else:
            self._selected = None
            self.selectionChanged.emit(None)

    # -- internals ---------------------------------------------------------

    def _sync_selection(self) -> None:
        for chip in self._chips:
            chip.set_selected(chip.name == self._selected)

    def _update_placeholder(self) -> None:
        """A prompt in an empty field, and none at all once it has chips."""
        self.line_edit.set_compact_placeholder(bool(self._chips))
