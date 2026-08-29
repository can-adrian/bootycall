"""
Favourites window.

The File menu is fine for picking a saved setup, but it is a bad place to
*manage* one: menus close on every click, and a menu row has no room for
reorder or rename. This is the same store in a window you can leave open --
double-click to load, buttons to add, rename, reorder and remove.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
)

from ..configs import ConfigStore

_NAME_ROLE = Qt.UserRole + 1
_SUMMARY_ROLE = Qt.UserRole + 2


class _FavoriteDelegate(QStyledItemDelegate):
    """Two-line row: the name, then the show and tool in a quieter colour.

    A plain "name\\nsummary" item paints both lines identically, which makes the
    list read as one undifferentiated block.
    """

    ROW_HEIGHT = 48

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 - Qt API
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter, option, index) -> None:
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, widget)

        selected = bool(option.state & QStyle.State_Selected)
        rect = option.rect.adjusted(10, 6, -10, -6)

        name_font = QFont(option.font)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QColor("#ffffff" if selected else "#d7dae0"))
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width(), rect.height() // 2),
            Qt.AlignLeft | Qt.AlignVCenter,
            index.data(_NAME_ROLE) or "",
        )

        summary_font = QFont(option.font)
        summary_font.setPointSizeF(max(7.0, option.font.pointSizeF() - 1))
        painter.setFont(summary_font)
        painter.setPen(QColor("#b9c4d2" if selected else "#767c86"))
        painter.drawText(
            QRect(
                rect.left(),
                rect.top() + rect.height() // 2,
                rect.width(),
                rect.height() // 2,
            ),
            Qt.AlignLeft | Qt.AlignVCenter,
            index.data(_SUMMARY_ROLE) or "",
        )


class FavoritesWindow(QDialog):
    """Manage saved setups. Non-modal: it is meant to stay open beside the app."""

    favoriteChosen = Signal(str)  # config name
    storeChanged = Signal()

    def __init__(self, store: ConfigStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Favourites")
        self.setObjectName("favoritesWindow")
        self.setModal(False)
        self.resize(420, 440)
        self.setMinimumSize(360, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        heading = QLabel("Favourites")
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.subtitle)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setObjectName("favoritesList")
        self.list.setItemDelegate(_FavoriteDelegate(self.list))
        self.list.itemDoubleClicked.connect(self._on_open)
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        layout.addWidget(self.list, 1)

        # Edit row -----------------------------------------------------------
        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)

        self.add_button = QPushButton("Add current")
        self.add_button.setToolTip(
            "Save the main window's current show and tool as a favourite"
        )
        edit_row.addWidget(self.add_button)

        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self._on_rename)
        edit_row.addWidget(self.rename_button)

        self.up_button = QPushButton("Move up")
        self.up_button.clicked.connect(lambda: self._on_move(-1))
        edit_row.addWidget(self.up_button)

        self.down_button = QPushButton("Move down")
        self.down_button.clicked.connect(lambda: self._on_move(1))
        edit_row.addWidget(self.down_button)

        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("dangerButton")
        self.remove_button.clicked.connect(self._on_remove)
        edit_row.addWidget(self.remove_button)

        edit_row.addStretch(1)
        layout.addLayout(edit_row)

        # Footer -------------------------------------------------------------
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        footer.addWidget(self.close_button)
        self.open_button = QPushButton("Load")
        self.open_button.setObjectName("launchButton")
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self._on_open)
        footer.addWidget(self.open_button)
        layout.addLayout(footer)

        self.refresh()

    # -- population --------------------------------------------------------

    def refresh(self) -> None:
        """Redraw from the store, keeping the selection where possible."""
        selected = self.selected_name()
        self.list.clear()
        for saved in self.store.configs():
            item = QListWidgetItem()
            item.setData(_NAME_ROLE, saved.name)
            item.setData(_SUMMARY_ROLE, saved.summary)
            item.setToolTip(
                "Show: %s\nTool: %s\nSaved: %s"
                % (saved.show, saved.tool, saved.created or "unknown")
            )
            self.list.addItem(item)
            if saved.name == selected:
                self.list.setCurrentItem(item)

        count = len(self.store)
        if count:
            self.subtitle.setText(
                "%d saved. Double-click to load one into the main window."
                % count
            )
        else:
            self.subtitle.setText(
                "Nothing saved yet. Pick a show and a tool, then Add current."
            )
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self._update_buttons()

    def selected_name(self) -> str:
        item = self.list.currentItem()
        return item.data(_NAME_ROLE) if item is not None else ""

    def _update_buttons(self) -> None:
        has = bool(self.selected_name())
        row = self.list.currentRow()
        for button in (self.rename_button, self.remove_button, self.open_button):
            button.setEnabled(has)
        self.up_button.setEnabled(has and row > 0)
        self.down_button.setEnabled(has and 0 <= row < self.list.count() - 1)

    # -- actions -----------------------------------------------------------

    def _on_open(self, *_args) -> None:
        name = self.selected_name()
        if name:
            self.favoriteChosen.emit(name)

    def _on_rename(self) -> None:
        old = self.selected_name()
        if not old:
            return
        new, accepted = QInputDialog.getText(self, "Rename favourite", "New name:", text=old)
        if not accepted:
            return
        error = self.store.rename(old, new.strip())
        if error:
            QMessageBox.warning(self, "Not renamed", error)
            return
        self.refresh()
        self._select(new.strip())
        self.storeChanged.emit()

    def _on_move(self, delta: int) -> None:
        name = self.selected_name()
        if not name:
            return
        error = self.store.move(name, delta)
        if error:
            QMessageBox.warning(self, "Not moved", error)
            return
        self.refresh()
        self._select(name)
        self.storeChanged.emit()

    def _on_remove(self) -> None:
        name = self.selected_name()
        if not name:
            return
        reply = QMessageBox.question(
            self,
            "Remove favourite",
            "Remove '%s'?" % name,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        error = self.store.remove(name)
        if error:
            QMessageBox.warning(self, "Not removed", error)
            return
        self.refresh()
        self.storeChanged.emit()

    def _select(self, name: str) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(_NAME_ROLE) == name:
                self.list.setCurrentRow(row)
                return
