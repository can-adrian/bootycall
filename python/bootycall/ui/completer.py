"""
Project autocomplete field.

A single-line edit backed by a substring-matching completer over the shows
listing. Typing ``bat`` matches ``combat_2`` as well as ``batman``; the popup
opens on focus and on the Down key so the field doubles as a browser for people
who don't remember the exact show code.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QCompleter, QLineEdit

from ..discovery import Project

_PATH_ROLE = Qt.UserRole + 1


class ProjectLineEdit(QLineEdit):
    """Autocomplete field for shows under the shows root."""

    projectChanged = Signal(object)  # Project or None
    projectActivated = Signal(object)  # Project, on Enter / popup click

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._compact = False
        self._count = 0
        self.setClearButtonEnabled(True)
        self.setObjectName("projectField")

        self._projects: dict[str, Project] = {}
        self._current: Project | None = None

        self._model = QStandardItemModel(self)

        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setMaxVisibleItems(14)
        self._completer.activated[str].connect(self._on_completer_activated)
        self.setCompleter(self._completer)

        self.textChanged.connect(self._on_text_changed)
        self.returnPressed.connect(self._on_return_pressed)

    # -- population --------------------------------------------------------

    def set_projects(self, projects: list[Project]) -> None:
        """Replace the completion list."""
        self._projects = {p.name: p for p in projects}
        self._model.clear()
        for project in projects:
            item = QStandardItem(project.name)
            item.setData(str(project.path), _PATH_ROLE)
            item.setToolTip(str(project.path))
            self._model.appendRow(item)
        self._count = len(projects)
        self._apply_placeholder()
        self._revalidate()

    def projects(self) -> list[Project]:
        return list(self._projects.values())

    def set_compact_placeholder(self, compact: bool) -> None:
        """Drop the prompt once chips are sharing the field with it."""
        if compact == self._compact:
            return
        self._compact = compact
        self._apply_placeholder()

    def _apply_placeholder(self) -> None:
        if not self._count:
            self.setPlaceholderText("No shows found")
        elif self._compact:
            # Nothing. The prompt exists to tell you what an empty field is
            # for; once there are chips in it, the chips say that, and the
            # words are just something else to read past.
            self.setPlaceholderText("")
        else:
            self.setPlaceholderText(
                "Type a show name and press Enter to pin it  (%d available)"
                % self._count
            )

    # -- current selection -------------------------------------------------

    def current_project(self) -> Project | None:
        return self._current

    def set_current_project(self, project: Project | str | None) -> None:
        name = project.name if isinstance(project, Project) else (project or "")
        self.setText(name)

    # -- behaviour ---------------------------------------------------------

    # No popup on focus: the window focuses this field on startup so you can
    # type straight away, and a list unfurling over the UI unasked reads as a
    # glitch. Clicking it or pressing Down still opens it.

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if not self.text():
            self._show_all()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Down and not self._completer.popup().isVisible():
            self._show_all() if not self.text() else self._completer.complete()
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self._take_completion():
            return

        super().keyPressEvent(event)

    def _take_completion(self) -> bool:
        """Enter with the list open takes the highlighted row, or the first.

        QCompleter only acts on Enter when a row is *current*, and typing does
        not make one current -- you have to press Down first. So typing ``bat``,
        seeing ``batman_returns`` at the top of the list and pressing Enter did
        nothing at all: no chip, and the text left sitting in the field. The
        row you are looking at is the one you meant.

        Handled here rather than through ``activated`` so the popup is shut
        before anything else runs. QCompleter writes the chosen text into the
        field *after* its own signal, which is why the click path below has to
        defer around it; hiding the popup first means there is no such write to
        work around, and the chip appears on the keystroke.
        """
        popup = self._completer.popup()
        if not popup.isVisible() or not self._completer.completionCount():
            return False

        index = popup.currentIndex()
        self._completer.setCurrentRow(index.row() if index.isValid() else 0)
        name = self._completer.currentCompletion()
        project = self._projects.get(name)
        if project is None:
            return False

        popup.hide()
        self.setText(name)
        self._revalidate()
        self.projectActivated.emit(project)
        return True

    def _show_all(self) -> None:
        if self._model.rowCount():
            self._completer.setCompletionPrefix("")
            self._completer.complete()

    def reset(self) -> None:
        """Empty the field and forget what was being completed.

        ``clear()`` alone leaves the popup open over the window, still listing
        the show you just pinned, and leaves the completion prefix behind it --
        so the next press of Down offered a list filtered by text that was no
        longer there. The field looked empty and behaved as though it was not.
        """
        self.clear()
        self._completer.popup().hide()
        self._completer.setCompletionPrefix("")

    # -- state -------------------------------------------------------------

    def _on_text_changed(self, _text: str) -> None:
        self._revalidate()

    def _on_completer_activated(self, text: str) -> None:
        """A row was clicked. (Enter is handled in :meth:`_take_completion`.)"""
        self.setText(text)
        self._revalidate()
        project = self._current
        if project is None:
            return
        # Deferred by one turn: QCompleter writes the chosen text into the line
        # edit through its own connection *after* this slot returns, so pinning
        # here would be immediately undone by that write. The popup is closed
        # in the same turn as the pin, so a click leaves nothing behind.
        self._completer.popup().hide()
        QTimer.singleShot(0, lambda: self.projectActivated.emit(project))

    def _on_return_pressed(self) -> None:
        # Reached only with the list closed: an open one is taken by
        # _take_completion before Qt gets this far.
        #
        # Enter on an exact-but-unselected match should still count.
        if self._current is None:
            match = self._unique_match(self.text())
            if match is not None:
                self.setText(match.name)
        if self._current is not None:
            self.projectActivated.emit(self._current)

    def _unique_match(self, text: str) -> Project | None:
        text = text.strip().lower()
        if not text:
            return None
        hits = [p for name, p in self._projects.items() if text in name.lower()]
        return hits[0] if len(hits) == 1 else None

    def _revalidate(self) -> None:
        project = self._projects.get(self.text().strip())
        state = "empty" if not self.text().strip() else ("ok" if project else "bad")
        if self.property("state") != state:
            self.setProperty("state", state)
            self.style().unpolish(self)
            self.style().polish(self)
        if project is not self._current:
            self._current = project
            self.projectChanged.emit(project)
