"""BootyCall main window."""

from __future__ import annotations

import os
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QProcess, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, config, dev_install, launcher, platform_hints, probe
from ..configs import ConfigStore, SavedConfig
from ..discovery import (
    Project,
    ProjectsUnavailable,
    apply_probe,
    available_dccs,
    list_projects,
    find_show_package,
    load_bootstrap,
    newest_variant,
    show_package_roots,
    variant_version,
)
from ..local_packages import (
    LocalPackage,
    LocalPackagesUnavailable,
    current_user,
    definition_mismatch,
    delete_package,
    dev_root,
    dev_working_root,
    list_local_packages,
    local_root,
    resolves_to,
    shadowed_requests,
)
from ..parser import Bootstrap
from .chips import ShowChipBar
from .collapsible import CollapsibleFrame
from .config_menu import ConfigMenuAction
from .dcc_tile import DccTile
from .favorites_window import FavoritesWindow
from .flow_layout import FlowLayout
from .install_dialog import InstallPackageDialog
from .settings_dialog import SettingsDialog
from .style import STYLESHEET


#: Width of a software tile, and therefore the width compact mode aims for --
#: the whole collapsed window should be no wider than one icon plus padding.
#: Floor for a tile's width. Tiles are sized to the widest label in the row and
#: then all set to that one size, so the row reads as a set of equals rather
#: than a ragged line -- but a row of nothing but short names should still not
#: collapse to something you have to aim at.
DCC_TILE_MIN_WIDTH = 84

#: Item roles on the local/dev package rows.
_PACKAGE_NAME_ROLE = Qt.UserRole
_PACKAGE_PATH_ROLE = Qt.UserRole + 1

#: Shown under the logo in quotes, one at random per launch. Stored unquoted so
#: the list stays the source of truth for the text itself.
TAGLINES: tuple[str, ...] = (
    "Yesterdays Technology. Today.",
    "Now, where did I put that New Pipeline?",
    "Because, Fuck You, That's Why.",
    "Pull yourself up by your Bootstrap.",
    "If your Grandma had wheels, She would be a Bicycle",
)


def _chevrons(up: bool, size: int = 16) -> QPixmap:
    """Two stacked chevrons, drawn rather than shipped as an asset file."""
    scale = 3
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#c3cad4"))
    pen.setWidth(int(1.6 * scale))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)

    span = size * scale
    inset = span * 0.24
    width = span - inset * 2
    for index in (0, 1):
        top = span * (0.26 if index == 0 else 0.54)
        rise = span * 0.20
        if up:
            painter.drawPolyline(
                [
                    QPointF(inset, top + rise),
                    QPointF(inset + width / 2, top),
                    QPointF(inset + width, top + rise),
                ]
            )
        else:
            painter.drawPolyline(
                [
                    QPointF(inset, top),
                    QPointF(inset + width / 2, top + rise),
                    QPointF(inset + width, top),
                ]
            )
    painter.end()
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def random_tagline() -> str:
    """One tagline, curly-quoted for display."""
    return "\u201c%s\u201d" % random.choice(TAGLINES)


def _badge(letter: str, color: str, size: int = 26) -> QPixmap:
    """A small rounded colour chip with a letter, used as the DCC icon."""
    scale = 3  # draw big, scale down: cheap antialiasing
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(
        pixmap.rect(), 7 * scale, 7 * scale
    )
    font = painter.font()
    # Two- and three-character labels ("HC", "FX", ">_") need to come down a
    # size or they overflow the chip.
    shrink = {1: 0.50, 2: 0.36}.get(len(letter), 0.30)
    font.setPointSizeF(size * scale * shrink)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#15171a"))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, letter)
    painter.end()
    return pixmap.scaled(
        size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )


def _winner_is_ours(winner, packages) -> bool:
    """Did the build that wins come from this section's own list?

    Resolved through symlinks rather than compared as strings: when some dev
    packages are switched off the path carries a *view* of the dev root made of
    links, so the root that wins is not spelled the same as the root the list
    was scanned from -- but it points at the same directory.
    """
    if winner is None:
        return False
    target = Path(winner.root) / winner.name
    if winner.version:
        target = target / winner.version

    for package in packages:
        if package.name != winner.name or package.version != winner.version:
            continue
        try:
            if Path(package.path).resolve() == target.resolve():
                return True
        except OSError:
            pass
        if str(package.path) == str(target):
            return True
    return False


class MainWindow(QMainWindow):
    def __init__(self, store: ConfigStore | None = None) -> None:
        super().__init__()
        self.EXPANDED_TITLE = "BootyCall %s" % __version__
        #: Short enough that a title bar the width of one tile can show all
        #: of it. An elided title reads like a fault; an abbreviation does
        #: not.
        self.COMPACT_TITLE = "B.C."
        self.setWindowTitle(self.EXPANDED_TITLE)
        self.resize(705, 680)
        # 428 rather than 570: the window has to be parkable beside a DCC,
        # and everything in it either wraps or elides at this width.
        self.setMinimumSize(428, 560)

        self._bootstrap: Bootstrap | None = None
        self._dcc_buttons: dict[str, DccTile] = {}
        self._dcc_variants: dict[str, tuple[str, ...]] = {}
        self._dcc_variant: dict[str, str] = {}
        self._preferred_dcc: str | None = None
        self._active_dcc: config.Dcc | None = None
        self._compact = False
        self._expanded_size = None
        self._expanded_minimum = None
        self._local_packages: list[LocalPackage] = []
        self._dev_packages: list[LocalPackage] = []
        self._projects_by_name: dict[str, Project] = {}
        self._favorites_window: FavoritesWindow | None = None
        #: The running bootstrap probe, if any. One at a time: flicking through
        #: shows must not leave a queue of imports running behind you.
        self._probe_process: QProcess | None = None
        self._probe_project: Project | None = None
        #: (bootstrap path, mtime) -> ProbeResult. Keyed on mtime so editing a
        #: bootstrap re-probes it, and re-selecting a show does not.
        self._probe_cache: dict[tuple[str, float], probe.ProbeResult] = {}
        #: The one width every tile in the row is set to. Recomputed
        #: whenever the row changes, since the labels in it change with it.
        self._tile_width = DCC_TILE_MIN_WIDTH
        #: (name, request) -> which root wins it. Cleared on every refresh,
        #: since it is a directory scan of every root on the path.
        self._winner_cache: dict = {}
        self.store = store if store is not None else ConfigStore()
        # Before anything reads a path: the stored settings are the outermost
        # layer, and reload_projects() fires as soon as the window is up.
        config.set_path_overrides(self.store.path_overrides())
        self._dcc_variant.update(self.store.variants())
        self._use_local = self.store.use_local()
        self._use_dev = self.store.use_dev()
        #: Installed dev packages switched off by name. Only the off ones
        #: are held, so a newly installed package is in play by default.
        self._disabled_dev: set[str] = set(self.store.disabled_dev_packages())
        self._preferred_dcc = self.store.selected_dcc()
        self._restore_compact = self.store.compact()
        stored = self.store.visible_software()
        self._visible_software: list[str] = list(
            config.DEFAULT_VISIBLE_SOFTWARE if stored is None else stored
        )

        self._build_ui()
        self._build_menu()
        if self.store.load_error:
            self.statusBar().showMessage(self.store.load_error, 10000)
        QTimer.singleShot(0, self.reload_projects)
        if self._restore_compact:
            # After the first listing, so the chip and tile it keeps exist.
            QTimer.singleShot(0, lambda: self.set_compact(True))

    # -- construction ------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        self.EXPANDED_MARGINS = (22, 20, 22, 16)
        self.COMPACT_MARGINS = (10, 8, 10, 8)
        root.setContentsMargins(*self.EXPANDED_MARGINS)
        root.setSpacing(14)

        # Header ----------------------------------------------------------
        title = QLabel("BootyCall")
        title.setObjectName("title")
        self.title_label = title
        self.tagline = QLabel(random_tagline())
        self.tagline.setObjectName("tagline")
        subtitle = self.tagline
        root.addWidget(title)
        root.addWidget(subtitle)

        # Project picker --------------------------------------------------
        root.addSpacing(2)

        # One bordered box holding the pinned chips and the entry. The entry
        # no longer *is* the selection -- it only pins; the selected chip is
        # what the rest of the window describes.
        self.chip_bar = ShowChipBar()
        self.project_field = self.chip_bar.line_edit
        self.project_field.projectActivated.connect(self._on_show_entered)
        self.chip_bar.selectionChanged.connect(self._on_chip_selected)
        self.chip_bar.chipsChanged.connect(self._persist_pinned_shows)
        root.addWidget(self.chip_bar)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.header_separator = self._separator()
        root.addWidget(self.header_separator)

        # DCC row ---------------------------------------------------------
        dcc_container = QWidget()
        self.dcc_container = dcc_container
        self.dcc_row = FlowLayout(dcc_container, margin=0, spacing=10)
        # A FlowLayout answers heightForWidth, but a QVBoxLayout only asks when
        # the child widget's size policy says it should. Without this the
        # container keeps one row's height and the tiles that wrapped onto a
        # second row are simply cut off -- which is what a narrow window does.
        _policy = dcc_container.sizePolicy()
        _policy.setHeightForWidth(True)
        dcc_container.setSizePolicy(_policy)
        self.dcc_group = QButtonGroup(self)
        self.dcc_group.setExclusive(True)
        self.dcc_group.buttonClicked.connect(self._on_dcc_clicked)

        self.dcc_placeholder = QLabel("Select a show to see what it provides.")
        self.dcc_placeholder.setObjectName("hint")
        self.dcc_row.addWidget(self.dcc_placeholder)

        # Terminal and Favourites sit in the same row but outside the exclusive
        # group: they are actions, not part of the show's software list, and
        # they stay available whatever is selected.
        self.terminal_button = QToolButton()
        self.terminal_button.setObjectName("actionTile")
        self.terminal_button.setText("Terminal")
        self.terminal_button.setIcon(_badge(">_", "#6c7a89"))
        self.terminal_button.setIconSize(QSize(26, 26))
        self.terminal_button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.terminal_button.setMinimumWidth(DCC_TILE_MIN_WIDTH)
        self.terminal_button.setToolTip(
            "Open a shell resolved against the selected package set"
        )
        self.terminal_button.setEnabled(False)
        self.terminal_button.clicked.connect(self._on_open_terminal)
        self.dcc_row.addWidget(self.terminal_button)

        root.addWidget(dcc_container)

        root.addSpacing(4)

        # Resolved packages (collapsed by default) -------------------------
        # No checkbox: there is nothing to launch without the resolve, so an
        # always-on control was only ever a greyed-out thing to wonder about.
        self.resolve_frame = CollapsibleFrame("Resolved packages", expanded=False)
        self.resolve_frame.toggled.connect(self._on_frame_toggled)
        self.package_list = QListWidget()
        self.package_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.package_list.setAlternatingRowColors(False)
        self.package_list.setMinimumHeight(120)
        self.package_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.resolve_frame.add_widget(self.package_list, 1)
        root.addWidget(self.resolve_frame)
        self._resolve_index = root.count() - 1

        # Local packages (collapsed by default) ----------------------------
        (
            self.local_frame,
            self.local_path_label,
            self.local_list,
        ) = self._build_package_section("Local packages")
        self.local_frame.set_checked(self._use_local)
        root.addWidget(self.local_frame)
        self._local_index = root.count() - 1

        # Installed dev packages (collapsed by default) --------------------
        (
            self.dev_frame,
            self.dev_path_label,
            self.dev_list,
        ) = self._build_package_section(
            "Installed Dev Packages", expanded=True, show_path=False
        )
        self.dev_list.itemChanged.connect(self._on_dev_item_changed)
        self.dev_frame.set_checked(self._use_dev)
        root.addWidget(self.dev_frame)
        self._dev_index = root.count() - 1

        root.addStretch(0)
        self._spacer_index = root.count() - 1
        self._root_layout = root

        # Footer ----------------------------------------------------------
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self._footer = footer
        # Copy command lives on the Edit menu now. It is a thing you reach for
        # when something has gone wrong and you want to paste the resolve into
        # a shell -- worth having, not worth a permanent button in the footer.
        footer.addStretch(1)
        self._footer_lead_spacer = footer.itemAt(footer.count() - 1)

        self.compact_button = QToolButton()
        self.compact_button.setObjectName("compactButton")
        self.compact_button.setIcon(_chevrons(up=True))
        self.compact_button.setIconSize(QSize(16, 16))
        self.compact_button.setFixedSize(34, 34)
        self.compact_button.setToolTip("Collapse to a compact launcher (Ctrl+M)")
        self.compact_button.clicked.connect(self.toggle_compact)
        footer.addWidget(self.compact_button)

        self.launch_button = QPushButton("Launch")
        self.launch_button.setObjectName("launchButton")
        self.launch_button.setEnabled(False)
        self.launch_button.setDefault(True)
        # Not connected directly: clicked emits its checked state, which would
        # arrive as _on_launch's first argument and quietly skip the dev
        # check the day someone makes this button checkable.
        self.launch_button.clicked.connect(lambda: self._on_launch())
        self.launch_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.launch_button.customContextMenuRequested.connect(self._on_launch_menu)
        footer.addWidget(self.launch_button)
        root.addLayout(footer)

        self.setCentralWidget(central)

        # A three-pixel strip along the bottom edge, parented to the central
        # widget rather than placed in the layout: in a layout it would grow
        # the window when it appeared, and compact mode is sized to the pixel.
        # Overlaid, it costs nothing until there is something to say.
        self.progress = QProgressBar(central)
        self.progress.setObjectName("microProgress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        self.statusBar().showMessage(config.shows_root())
        self._apply_frame_stretch()

    def _build_package_section(
        self, title: str, expanded: bool = False, show_path: bool = True
    ) -> tuple[CollapsibleFrame, QLabel, QListWidget]:
        """One package section: checkbox, header, optional root path, list."""
        frame = CollapsibleFrame(
            title, expanded=expanded, checkable=True, checked=True
        )
        frame.toggled.connect(self._on_package_frame_toggled)
        frame.check_box.setToolTip(
            "Use these packages. Unchecked, their root is taken off the "
            "rez packages path for anything BootyCall launches."
        )
        frame.checkChanged.connect(self._on_package_use_changed)

        path_label = QLabel("")
        path_label.setObjectName("hint")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # A section that stays open pays for that line every time you look at
        # it, and the path does not change. Where it is hidden the same text
        # goes on the header's tooltip, so nothing is lost -- it just stops
        # taking a row of the window to say something you already know.
        path_label.setVisible(show_path)
        frame.add_widget(path_label)

        listing = QListWidget()
        listing.setSelectionMode(QListWidget.ExtendedSelection)
        listing.setMinimumHeight(100)
        listing.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        listing.setContextMenuPolicy(Qt.CustomContextMenu)
        listing.customContextMenuRequested.connect(
            lambda point, lst=listing: self._on_package_menu(lst, point)
        )
        frame.add_widget(listing, 1)
        return frame, path_label, listing

    def _build_menu(self) -> None:
        self.file_menu = self.menuBar().addMenu("&File")
        # Rebuilt on open so the list always reflects the store, including
        # edits made by another BootyCall window.
        self.file_menu.aboutToShow.connect(self._rebuild_file_menu)

        self.save_action = QAction("&Save current setup...", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self._on_save_config)
        self.addAction(self.save_action)  # keep Ctrl+S live without the menu open

        self.favorites_action = QAction("&Favourites...", self)
        self.favorites_action.setShortcut(QKeySequence("Ctrl+B"))
        self.favorites_action.triggered.connect(self.show_favorites)
        self.addAction(self.favorites_action)

        self.terminal_action = QAction("Open &terminal", self)
        self.terminal_action.setShortcut(QKeySequence("Ctrl+T"))
        self.terminal_action.triggered.connect(self._on_open_terminal)
        self.addAction(self.terminal_action)

        self.reload_action = QAction("&Reload", self)
        self.reload_action.setShortcut(QKeySequence.Refresh)
        self.reload_action.setToolTip(
            "Re-read everything: shows, the selected show's bootstrap, your "
            "package roots, and rez's packages path."
        )
        self.reload_action.triggered.connect(self.reload_all)
        self.addAction(self.reload_action)

        self.focus_action = QAction("&Find show", self)
        self.focus_action.setShortcut(QKeySequence.Find)
        self.focus_action.triggered.connect(self._focus_project_field)
        self.addAction(self.focus_action)

        self.compact_action = QAction("&Compact mode", self)
        self.compact_action.setShortcut(QKeySequence("Ctrl+M"))
        self.compact_action.setCheckable(True)
        self.compact_action.triggered.connect(self.set_compact)
        self.addAction(self.compact_action)

        self.settings_action = QAction("&Settings...", self)
        self.settings_action.setShortcut(QKeySequence.Preferences)
        self.settings_action.setMenuRole(QAction.PreferencesRole)
        self.settings_action.triggered.connect(self.show_settings)
        self.addAction(self.settings_action)

        self.copy_action = QAction("&Copy launch command", self)
        self.copy_action.setShortcut(QKeySequence.Copy)
        self.copy_action.setEnabled(False)
        self.copy_action.triggered.connect(self._on_copy_command)
        self.addAction(self.copy_action)

        self.diagnostics_action = QAction("&Diagnostics...", self)
        self.diagnostics_action.setToolTip(
            "Why is my package not in the environment? Everything that decides "
            "that, in one report."
        )
        self.diagnostics_action.triggered.connect(self.show_diagnostics)
        self.addAction(self.diagnostics_action)

        self.resolve_test_action = QAction("&Test resolve with rez...", self)
        self.resolve_test_action.setToolTip(
            "Run the real resolve and report what rez chose. Everything else "
            "BootyCall says about which package wins is a prediction; this is "
            "the measurement."
        )
        self.resolve_test_action.triggered.connect(self.run_resolve_test)
        self.addAction(self.resolve_test_action)

        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.Quit)
        self.quit_action.triggered.connect(self.close)

        self._config_actions: list[ConfigMenuAction] = []
        self._rebuild_file_menu()
        self._build_software_menu()

    def _build_software_menu(self) -> None:
        """Checkboxes for which DCCs get a tile.

        The registry knows about seven; four are shown out of the box. The rest
        are real but rarely wanted, and a row of nine tiles buries the ones
        people actually reach for -- so they live behind a toggle rather than
        being dropped from the registry.
        """
        # A top-level Settings entry as well as the File one: paths are the
        # thing people go looking for, and burying them under File hides them.
        self.edit_menu = self.menuBar().addMenu("&Edit")
        self.edit_menu.addAction(self.copy_action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.diagnostics_action)
        self.edit_menu.addAction(self.resolve_test_action)

        self.software_menu = self.menuBar().addMenu("&Softwares")
        self._software_actions: dict[str, QAction] = {}

        for dcc in config.DCCS:
            action = QAction(dcc.label, self)
            action.setCheckable(True)
            action.setChecked(dcc.name in self._visible_software)
            action.toggled.connect(
                lambda checked, name=dcc.name: self._on_software_toggled(
                    name, checked
                )
            )
            self.software_menu.addAction(action)
            self._software_actions[dcc.name] = action

        self.software_menu.addSeparator()
        reset = QAction("Reset to defaults", self)
        reset.triggered.connect(self._on_reset_software)
        self.software_menu.addAction(reset)

    def _on_software_toggled(self, name: str, checked: bool) -> None:
        if checked and name not in self._visible_software:
            # Keep registry order rather than click order, so the row does not
            # reshuffle depending on what you turned on first.
            order = [d.name for d in config.DCCS]
            self._visible_software.append(name)
            self._visible_software.sort(key=order.index)
        elif not checked and name in self._visible_software:
            self._visible_software.remove(name)

        error = self.store.set_visible_software(self._visible_software)
        if error:
            self.statusBar().showMessage(error, 8000)
        self._reapply_software()

    def _on_reset_software(self) -> None:
        self._visible_software = list(config.DEFAULT_VISIBLE_SOFTWARE)
        self.store.set_visible_software(None)
        for dcc_name, action in self._software_actions.items():
            action.blockSignals(True)
            action.setChecked(dcc_name in self._visible_software)
            action.blockSignals(False)
        self._reapply_software()

    def _reapply_software(self) -> None:
        """Redraw the software row for the current show."""
        project = self.current_project()
        if project is None:
            return
        self._on_project_changed(project)

    # -- saved setups ------------------------------------------------------

    def _rebuild_file_menu(self) -> None:
        """Redraw the File menu from the store.

        Cheap enough to do on every open, which keeps this the single place
        that knows the menu's shape.
        """
        menu = self.file_menu
        menu.clear()
        self._config_actions = []

        menu.addAction(self.save_action)
        menu.addAction(self.favorites_action)
        menu.addAction(self.terminal_action)
        menu.addSeparator()

        header = QAction("Saved setups", self)
        header.setEnabled(False)
        menu.addAction(header)

        if not len(self.store):
            empty = QAction("   Nothing saved yet", self)
            empty.setEnabled(False)
            menu.addAction(empty)
        else:
            for saved in self.store.configs():
                action = ConfigMenuAction(saved, menu)
                action.applied.connect(self._on_apply_config)
                action.removed.connect(self._on_remove_config)
                menu.addAction(action)
                self._config_actions.append(action)

        menu.addSeparator()
        menu.addAction(self.reload_action)
        menu.addAction(self.focus_action)
        menu.addAction(self.compact_action)
        menu.addSeparator()
        menu.addAction(self.settings_action)
        menu.addAction(self.quit_action)

    def _current_state(self) -> tuple[Project, config.Dcc, str] | None:
        """The (show, dcc, tool) triple a config is made of, if complete."""
        project = self.current_project()
        tool = self._current_tool()
        if project is None or self._active_dcc is None or tool is None:
            return None
        return project, self._active_dcc, tool

    def _on_save_config(self) -> None:
        state = self._current_state()
        if state is None:
            self.statusBar().showMessage(
                "Pick a show and a tool before saving a setup", 5000
            )
            return
        project, dcc, tool = state

        suggested = self.store.suggest_name(project.name, dcc.label_for(tool))
        name, accepted = QInputDialog.getText(
            self, "Save setup", "Name this setup:", text=suggested
        )
        name = name.strip()
        if not accepted or not name:
            return

        if self.store.get(name) is not None:
            reply = QMessageBox.question(
                self,
                "Replace setup",
                "A setup named '%s' already exists. Replace it?" % name,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        error = self.store.add(
            SavedConfig(name=name, show=project.name, dcc=dcc.name, tool=tool)
        )
        self._rebuild_file_menu()
        if self._favorites_window is not None:
            self._favorites_window.refresh()
        if error:
            QMessageBox.warning(self, "Setup not saved", error)
            return
        self.statusBar().showMessage("Saved setup '%s'" % name, 5000)

    def _on_remove_config(self, name: str) -> None:
        error = self.store.remove(name)
        # Drop just this row so the open menu keeps its place and several can
        # be cleared in one visit.
        for action in list(self._config_actions):
            if action.config.name != name:
                continue
            self.file_menu.removeAction(action)
            self._config_actions.remove(action)
            action.deleteLater()
            break

        if not self._config_actions and self.file_menu.isVisible():
            self.file_menu.close()

        if self._favorites_window is not None:
            self._favorites_window.refresh()
        if error:
            QMessageBox.warning(self, "Setup not removed", error)
            return
        self.statusBar().showMessage("Removed setup '%s'" % name, 5000)

    def _on_apply_config(self, name: str) -> None:
        saved = self.store.get(name)
        if saved is None:
            return

        if saved.show not in self._projects_by_name:
            self._set_status(
                "Setup '%s' points at show '%s', which is no longer in %s"
                % (name, saved.show, config.shows_root()),
                "error",
            )
            return

        # Loading a favourite pins its show if it is not pinned already: the
        # favourite is a stronger statement of intent than the chip row.
        self.chip_bar.add(saved.show)
        QApplication.processEvents()

        button = self._dcc_buttons.get(saved.dcc)
        if button is None:
            self._set_status(
                "Setup '%s': %s does not offer %s any more"
                % (name, saved.show, saved.dcc),
                "error",
            )
            return
        button.click()

        if saved.tool not in self._dcc_variants.get(saved.dcc, ()):
            self._set_status(
                "Setup '%s': '%s' is no longer defined for %s"
                % (name, saved.tool, saved.show),
                "error",
            )
            return
        self.set_variant(saved.dcc, saved.tool)
        self.statusBar().showMessage("Loaded setup '%s'" % name, 5000)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background: #2c3037; border: none;")
        return line

    def current_project(self) -> Project | None:
        """The show the window is describing: whichever chip is selected."""
        name = self.chip_bar.selected_name()
        if name is None:
            return None
        return self._projects_by_name.get(name)

    # -- pinned shows ------------------------------------------------------

    def _on_show_entered(self, project: Project) -> None:
        """Enter in the autocomplete field: pin the show and select it."""
        added = self.chip_bar.add(project.name)
        self.project_field.clear()
        self.project_field.setFocus()
        if not added:
            self.statusBar().showMessage(
                "%s is already pinned" % project.name, 4000
            )

    def _on_chip_selected(self, name: object) -> None:
        self.store.set_selected_show(name if isinstance(name, str) else None)
        self._on_project_changed(self.current_project())
        if self._compact:
            self._apply_compact_filter()

    def _persist_pinned_shows(self) -> None:
        error = self.store.set_pinned_shows(self.chip_bar.names())
        if error:
            self.statusBar().showMessage(error, 8000)

    def _restore_pinned_shows(self) -> None:
        """Re-pin what was there last time, dropping shows that have gone."""
        pinned = list(self.store.pinned_shows())
        if not pinned:
            self.chip_bar.set_names([], None)
            return

        alive = [n for n in pinned if n in self._projects_by_name]
        missing = [n for n in pinned if n not in self._projects_by_name]

        self.chip_bar.set_names(alive, self.store.selected_show())

        if missing:
            # Silently dropping a pin would look like the app lost it.
            self._persist_pinned_shows()
            self.statusBar().showMessage(
                "Unpinned %s - no longer in %s"
                % (", ".join(missing), config.shows_root()),
                10000,
            )

    # -- data --------------------------------------------------------------

    def reload_all(self) -> None:
        """Re-read everything the window is showing.

        "Reload shows" only re-listed the shows folder, which is the one thing
        that rarely changes while you are working. What does change is
        everything downstream of it: a bootstrap someone edited, a package you
        installed from a terminal, a rez config the site updated. Reloading one
        of those and not the others leaves a window that is half stale, which
        is worse than one that is wholly stale, because you cannot tell which
        half you are looking at.

        So all the caches go, in dependency order, and the window is rebuilt
        from disk.
        """
        # Asked once and remembered; a site that changed its config would
        # otherwise need BootyCall restarted to notice.
        launcher._PACKAGES_PATH = None
        # Keyed by bootstrap mtime, so an edited bootstrap re-probes anyway --
        # but a probe command that has since been fixed would not.
        self._probe_cache.clear()
        self._winner_cache.clear()
        # Settings may have been changed in another window sharing the file.
        self.store.load()
        config.set_path_overrides(self.store.path_overrides())

        self.reload_projects()
        self.refresh_package_lists()
        self.statusBar().showMessage(
            "Reloaded shows, bootstraps, package roots and the rez path", 6000
        )

    def reload_projects(self) -> None:
        self.refresh_package_lists()
        try:
            projects = list_projects()
        except ProjectsUnavailable as exc:
            self._projects_by_name = {}
            self.project_field.set_projects([])
            self.chip_bar.set_names([], None)
            self._set_status(str(exc), "error")
            return

        self._projects_by_name = {p.name: p for p in projects}
        self.project_field.set_projects(projects)
        self.statusBar().showMessage(
            "%s  -  %d shows" % (config.shows_root(), len(projects))
        )
        if not projects:
            self._set_status("No shows found in %s" % config.shows_root(), "error")
        else:
            self._set_status("")
        self._restore_pinned_shows()
        self._focus_project_field()

    def _focus_project_field(self) -> None:
        self.project_field.setFocus()
        self.project_field.selectAll()

    # -- reactions ---------------------------------------------------------

    def _on_project_changed(self, project: Project | None) -> None:
        self._clear_dccs()
        self._bootstrap = None
        self.package_list.clear()
        self.resolve_frame.set_badge("")
        self.resolve_frame.set_note("")
        self._refresh_override_marks()
        self._update_actions()

        if project is None:
            self._set_status("")
            return

        bootstrap, message = load_bootstrap(project)
        if bootstrap is None:
            self._set_status(message, "error")
            return

        self._bootstrap = bootstrap
        entries = available_dccs(bootstrap)
        if not entries:
            self._set_status(
                "%s  -  none of %s are configured for this show"
                % (message, " / ".join(d.label for d in config.DCCS)),
                "error",
            )
            return

        hidden = [d.label for d, _ in entries if d.name not in self._visible_software]
        shown = [e for e in entries if e[0].name in self._visible_software]

        if not shown:
            # Defined but switched off. Saying "not configured" here would be a
            # lie, and would send someone to edit the bootstrap for no reason.
            self._set_status(
                "%s  -  this show offers %s, all hidden. Turn them on in the "
                "Softwares menu." % (message, ", ".join(hidden)),
                "error",
            )
            return

        # Nothing to say when it worked: the tiles and the section badges are
        # the report. Only the failures below still speak up.
        self._set_status("")
        self._populate_dccs(entries)
        self._start_probe(project, bootstrap)

    # -- asking the bootstrap itself -----------------------------------------

    def _start_probe(self, project: Project, bootstrap: Bootstrap) -> None:
        """Ask the real bootstrap module what it resolves, in the background.

        The static read has already drawn the window by this point, which is
        the whole arrangement: you never wait for an interpreter to import rez
        before you can click anything, and if the probe comes back with
        something different, the window quietly corrects itself.
        """
        self._cancel_probe()
        if not config.probe_enabled():
            return

        path = bootstrap.path
        try:
            key = (str(path), os.path.getmtime(path))
        except OSError:
            return

        cached = self._probe_cache.get(key)
        if cached is not None:
            self._apply_probe(project, cached)
            return

        argv = probe.command(path)
        process = QProcess(self)
        process.setWorkingDirectory(str(project.path))
        process.setProgram(argv[0])
        process.setArguments(argv[1:])
        process.finished.connect(
            lambda _code, _status, k=key, p=project: self._on_probe_finished(k, p)
        )
        # A probe that cannot even start is the ordinary state at a site that
        # has not pointed BOOTYCALL_PROBE_COMMAND anywhere: nothing to report.
        process.errorOccurred.connect(lambda _err: self._cancel_probe())

        self._probe_process = process
        self._probe_project = project
        process.start()

    def _cancel_probe(self) -> None:
        process, self._probe_process = self._probe_process, None
        self._probe_project = None
        if process is None:
            return
        try:
            process.finished.disconnect()
            process.errorOccurred.disconnect()
            process.kill()
            # Brief, and only to stop Qt complaining that it was destroyed with
            # a child still running: the probe is a doomed import, not work.
            process.waitForFinished(200)
            process.deleteLater()
        except RuntimeError:
            pass  # already gone; nothing left to cancel

    def closeEvent(self, event) -> None:
        """Do not leave an import running behind a closed window."""
        self._cancel_probe()
        super().closeEvent(event)

    def _on_probe_finished(self, key: tuple[str, float], project: Project) -> None:
        process, self._probe_process = self._probe_process, None
        self._probe_project = None
        if process is None:
            return

        try:
            result = probe.parse_output(
                bytes(process.readAllStandardOutput()).decode("utf-8", "replace"),
                bytes(process.readAllStandardError()).decode("utf-8", "replace"),
            )
        except RuntimeError:
            # The window was torn down while the import was still running, so
            # the process went with it. Nothing to report to, either.
            return
        self._probe_cache[key] = result
        # Selection may have moved on while the import was running.
        current = self.current_project()
        if current is not None and current.name == project.name:
            self._apply_probe(project, result)

    def _apply_probe(self, project: Project, result: probe.ProbeResult) -> None:
        if self._bootstrap is None or not result.ok:
            return

        before = self._bootstrap.packages
        note = apply_probe(self._bootstrap, result)
        if set(before) != set(self._bootstrap.packages):
            # The set of tools changed, so the tiles are wrong. Rebuilding
            # keeps the selected software and variant: both live outside the
            # tiles precisely so a repopulate does not lose them.
            self._clear_dccs()
            self._populate_dccs(available_dccs(self._bootstrap))
        elif self._active_dcc is not None:
            tool = self._current_tool()
            if tool:
                self._show_packages(tool)
        if note:
            self._set_status(note, "warn")

    def _populate_dccs(self, entries: list[tuple[config.Dcc, tuple[str, ...]]]) -> None:
        for dcc, keys in entries:
            if dcc.name not in self._visible_software:
                continue
            self.dcc_placeholder.hide()
            button = DccTile(dcc.name)
            button.setCheckable(True)
            button.setText(dcc.label)
            button.setIcon(_badge(dcc.icon_text, dcc.accent))
            button.setIconSize(QSize(26, 26))
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setMinimumWidth(DCC_TILE_MIN_WIDTH)
            button.variantMenuRequested.connect(self._on_variant_menu)

            self._dcc_variants[dcc.name] = keys
            # Newest by default; a variant the user picked earlier for this DCC
            # only survives if this show still offers it.
            chosen = self._dcc_variant.get(dcc.name)
            if chosen not in keys:
                chosen = newest_variant(self._bootstrap, dcc, keys)
            self._dcc_variant[dcc.name] = chosen

            button.set_interactive(not self._compact)
            self._dcc_buttons[dcc.name] = button
            self._refresh_tile(dcc)
            self.dcc_group.addButton(button)
            # Before the Terminal and Favourites tiles, which stay last.
            self.dcc_row.insertWidget(self.dcc_row.count() - 2, button)

        self._equalise_tiles()

        shown = [(d, k) for d, k in entries if d.name in self._visible_software]
        if shown:
            # Stay on the software you were using where the new show offers it,
            # so flicking between shows does not keep dumping you back on the
            # first tile.
            chosen = next(
                (d for d, _k in shown if d.name == self._preferred_dcc),
                shown[0][0],
            )
            self._dcc_buttons[chosen.name].setChecked(True)
            self._activate_dcc(chosen)

    def _clear_dccs(self) -> None:
        for button in self._dcc_buttons.values():
            self.dcc_group.removeButton(button)
            self.dcc_row.removeWidget(button)
            # setParent(None) as well as deleteLater: taking a widget out of a
            # layout does not unmap it, so without this the old tiles keep
            # painting at their last geometry until the deferred delete runs,
            # and a show with fewer tiles shows the previous show's underneath.
            button.setParent(None)
            button.deleteLater()
        self._dcc_buttons.clear()
        self._dcc_variants.clear()
        self._active_dcc = None
        self.dcc_placeholder.show()
        self._equalise_tiles()

    def _fit_dcc_row(self) -> None:
        """Hold the tile row open to however many lines it actually wraps to.

        The size policy makes the parent layout *ask* for the wrapped height,
        but a QVBoxLayout will still squeeze a widget down to its minimum when
        something else in the column wants the room -- and this layout's
        minimum is one tile. The result is a second row of tiles laid out below
        the bottom edge of the container: present, positioned, and invisible.

        Pinning the minimum to the wrapped height is what stops that. It is
        recomputed on every resize because the number of lines is a function of
        the width.
        """
        container = getattr(self, "dcc_container", None)
        if container is None:
            return
        width = container.width()
        if width <= 0:
            return
        needed = self.dcc_row.heightForWidth(width)
        if needed > 0 and needed != container.minimumHeight():
            container.setMinimumHeight(needed)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_dcc_row()
        self._place_progress()

    def _place_progress(self) -> None:
        central = self.centralWidget()
        if central is None or not hasattr(self, "progress"):
            return
        self.progress.setGeometry(
            0, central.height() - self.progress.height(), central.width(), 3
        )
        self.progress.raise_()

    def _start_progress(self, total: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)
        self._place_progress()
        self.progress.show()
        QApplication.processEvents()

    def _step_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        if name and not self._compact:
            self.statusBar().showMessage(
                "Rebuilding %s  (%d of %d)" % (name, done + 1, total)
            )
        # A synchronous rez build blocks the loop; without this the bar is
        # painted once at the start and once at the end, which is the same as
        # not having one.
        QApplication.processEvents()

    def _end_progress(self) -> None:
        self.progress.hide()

    def _equalise_tiles(self) -> None:
        """Give every tile in the row the same size, set by the widest of them.

        Tiles size themselves to their own label, so a row of Houdini, HouFX,
        Maya and Terminal comes out as four different widths -- which reads as
        four different kinds of thing rather than one set to choose from.

        The size is measured rather than hardcoded: the labels are the things
        that decide it, and a number in the source would go stale the next time
        one of them is renamed. Terminal is measured with the rest, since it
        sits in the same row and looks wrong at any other width.
        """
        tiles = list(self._dcc_buttons.values()) + [self.terminal_button]

        # Released first, or last pass's fixed size is what gets measured.
        for tile in tiles:
            tile.setMinimumSize(0, 0)
            tile.setMaximumSize(16777215, 16777215)

        width = max([t.sizeHint().width() for t in tiles] + [DCC_TILE_MIN_WIDTH])
        height = max(t.sizeHint().height() for t in tiles)
        for tile in tiles:
            tile.setFixedSize(width, height)
        self._tile_width = width

        self.dcc_row.invalidate()
        self._fit_dcc_row()

    def _on_dcc_clicked(self, button: DccTile) -> None:
        dcc = config.dcc_by_name(button.dcc_name)
        if dcc is not None:
            self._preferred_dcc = dcc.name
            self._activate_dcc(dcc)

    def _activate_dcc(self, dcc: config.Dcc) -> None:
        self._active_dcc = dcc
        tool = self._dcc_variant.get(dcc.name)
        if tool:
            self._show_packages(tool)
        if self._compact:
            self._apply_compact_filter()
        self._update_actions()

    def _variant_subtitle(self, dcc: config.Dcc, key: str) -> str:
        """The grey line under a tile's name: the variant's version.

        Falls back to a short tag, and then to the variant label, because a
        version is only useful if the bootstrap actually names one -- and where
        two variants share a version the number alone would not say which is
        selected.
        """
        if self._bootstrap is None:
            return ""
        keys = self._dcc_variants.get(dcc.name, ())
        version = variant_version(
            self._bootstrap.packages.get(key, ()), dcc.version_package
        )
        tag = dcc.variant_tags.get(key, "")

        if version:
            others = [
                variant_version(
                    self._bootstrap.packages.get(k, ()), dcc.version_package
                )
                for k in keys
            ]
            if others.count(version) > 1 and tag:
                return "%s \u00b7 %s" % (version, tag)
            return version
        return tag or dcc.label_for(key)

    def _refresh_tile(self, dcc: config.Dcc) -> None:
        button = self._dcc_buttons.get(dcc.name)
        if button is None:
            return
        keys = self._dcc_variants.get(dcc.name, ())
        key = self._dcc_variant.get(dcc.name, "")
        button.set_subtitle(self._variant_subtitle(dcc, key))

        if len(keys) > 1:
            tip = "%s - %s\n\nRight-click for %d variants" % (
                dcc.label,
                dcc.label_for(key),
                len(keys),
            )
        else:
            tip = "%s - %s" % (dcc.label, dcc.label_for(key))
        button.setToolTip(tip)

    def _on_variant_menu(self, tile: DccTile, point) -> None:
        dcc = config.dcc_by_name(tile.dcc_name)
        if dcc is None:
            return
        keys = self._dcc_variants.get(dcc.name, ())
        if len(keys) < 2:
            return  # nothing to choose between

        current = self._dcc_variant.get(dcc.name)
        menu = QMenu(self)
        actions = {}
        for key in keys:
            version = self._variant_subtitle(dcc, key)
            label = dcc.label_for(key)
            if version and version not in label:
                label = "%s   (%s)" % (label, version)
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == current)
            actions[action] = key

        chosen = menu.exec(tile.mapToGlobal(point))
        if chosen in actions:
            self.set_variant(dcc.name, actions[chosen])

    def set_variant(self, dcc_name: str, key: str) -> None:
        """Choose a variant for one DCC, selecting that DCC as a side effect."""
        dcc = config.dcc_by_name(dcc_name)
        if dcc is None or key not in self._dcc_variants.get(dcc_name, ()):
            return
        self._dcc_variant[dcc_name] = key
        self._preferred_dcc = dcc_name
        self._refresh_tile(dcc)

        button = self._dcc_buttons.get(dcc_name)
        if button is not None and not button.isChecked():
            # Picking a variant is a statement about which tool you want, so it
            # selects the tile too rather than quietly editing a tile you are
            # not looking at.
            button.setChecked(True)
        self._activate_dcc(dcc)

    def _show_packages(self, key: str) -> None:
        self.package_list.clear()
        if self._bootstrap is None:
            self.resolve_frame.set_badge("")
            self.resolve_frame.set_note("")
            self._refresh_override_marks()
            return

        packages = self._bootstrap.packages.get(key, ())
        # A section that is switched off is not on the packages path for the
        # launch, so it cannot override anything and must not say it does.
        local_hits = (
            shadowed_requests(self._local_packages, packages)
            if self.local_frame.is_checked()
            else {}
        )
        # enabled_dev_packages() rather than all of them: a dev package you
        # unticked is not on the path for the launch, so it overrides nothing
        # and must not say it does.
        dev_hits = shadowed_requests(self.enabled_dev_packages(), packages)
        shadowed: dict[str, list[str]] = {}
        for shadow in local_hits.values():
            if self._override_takes_effect(shadow, self._local_packages):
                shadowed.setdefault(shadow.request, []).append("local")
        for shadow in dev_hits.values():
            if self._override_takes_effect(shadow, self.enabled_dev_packages()):
                shadowed.setdefault(shadow.request, []).append("dev")

        seen: set[str] = set()
        for request in packages:
            duplicate = request in seen
            seen.add(request)
            item = QListWidgetItem(request)
            tips = []
            if duplicate:
                item.setForeground(QColor("#90a8c2"))
                tips.append("Listed more than once in this package set")
            roots = shadowed.get(request)
            if roots:
                item.setText(
                    "%s      overridden by your %s build%s"
                    % (request, " and ".join(roots), "s" if len(roots) > 1 else "")
                )
                item.setForeground(QColor("#e0a23c"))
                tips.append(
                    "A package named '%s' exists in your %s root%s and takes "
                    "precedence over this request."
                    % (
                        request.split("-", 1)[0],
                        " and ".join(roots),
                        "s" if len(roots) > 1 else "",
                    )
                )
                if len(roots) > 1:
                    # Which of the two wins depends on REZ_PACKAGES_PATH order
                    # at your site, which BootyCall cannot see -- so say both
                    # rather than pick one and be wrong half the time.
                    tips.append(
                        "It is in both roots; which one wins depends on your "
                        "REZ_PACKAGES_PATH order."
                    )
            if tips:
                item.setToolTip("\n".join(tips))
            self.package_list.addItem(item)

        show_pkg = self.show_package()
        for name in self.show_package_requests():
            # Part of every resolve, so a list claiming to be the resolve has
            # to say so.
            item = QListWidgetItem("%s      (show package)" % name)
            item.setForeground(QColor("#8fce8f"))
            if show_pkg is not None and show_pkg.name == name:
                item.setToolTip(
                    "%s\nFound under %s, which is added to the packages path "
                    "for the launch." % (show_pkg.path, show_pkg.root)
                )
            else:
                item.setToolTip(
                    "The bootstrap adds this to every resolve. BootyCall could "
                    "not find it on disk, so every candidate package root is "
                    "added to the packages path for the launch."
                )
            self.package_list.addItem(item)

        duplicates = len(packages) - len(seen)
        badge = "%s  -  %d packages" % (key, len(packages))
        if duplicates:
            badge += "  (%d duplicate)" % duplicates
        if self._bootstrap.source == "bootstrap":
            # Worth the words: a list the module produced and a list read out
            # of the file are not the same claim, and only one of them can be
            # trusted about anything computed at import time.
            badge += "  · from the bootstrap"
        self.resolve_frame.set_badge(badge)
        self.resolve_frame.set_note(
            "%d overridden locally" % len(shadowed) if shadowed else "",
            "warn" if shadowed else "",
        )
        if self._active_dcc is not None:
            self._refresh_tile(self._active_dcc)
        self._refresh_override_marks()

    # -- local and dev packages --------------------------------------------

    def refresh_package_lists(self) -> None:
        """Rescan both per-user roots and repaint their sections."""
        self._local_packages = self._fill_package_section(
            frame=self.local_frame,
            path_label=self.local_path_label,
            listing=self.local_list,
            root=local_root(),
            exclude=None,
            empty_hint="No local packages yet - nothing here overrides your resolve.",
        )
        blocked = self.dev_list.blockSignals(True)
        self._dev_packages = self._fill_package_section(
            frame=self.dev_frame,
            path_label=self.dev_path_label,
            listing=self.dev_list,
            root=dev_root(),
            exclude=(),
            empty_hint="No dev packages installed - right-click here to install one.",
        )
        self.dev_list.blockSignals(blocked)

        # The resolve list marks overrides, so it has to be redrawn too.
        tool = self._current_tool()
        if tool and self._bootstrap is not None:
            self._show_packages(tool)
        else:
            self._refresh_override_marks()

    def _fill_package_section(
        self,
        frame: CollapsibleFrame,
        path_label: QLabel,
        listing: QListWidget,
        root,
        exclude,
        empty_hint: str,
    ) -> list[LocalPackage]:
        """Scan one root and paint its section. Returns what it found."""
        label = "%s   (user: %s)" % (root, current_user())
        if self._root_unknown_to_rez(root):
            # The single most confusing state this window can be in is showing
            # a package that never reaches a resolve. It cannot happen now --
            # BootyCall puts the root on the path itself -- but it is still
            # worth saying, because anything launched outside BootyCall will
            # not see these packages at all.
            label += "\n(not in your rez packages path - BootyCall adds it)"
        path_label.setText(label)
        # On the header too, so a section whose path line is hidden still has
        # the root and the warning a hover away.
        frame.toggle_button.setToolTip(label)

        error = ""
        try:
            packages = list_local_packages(root, exclude=exclude)
        except LocalPackagesUnavailable as exc:
            packages = []
            error = str(exc)

        listing.clear()

        if error:
            frame.set_badge("")
            frame.set_note("unreadable", "error")
            item = QListWidgetItem(error)
            item.setForeground(QColor("#e06c75"))
            listing.addItem(item)
        elif not root.exists():
            frame.set_badge("none")
            frame.set_note("")
            item = QListWidgetItem(empty_hint)
            item.setForeground(QColor("#90a8c2"))
            item.setToolTip("Expected at %s" % root)
            listing.addItem(item)
        elif not packages:
            frame.set_badge("none")
            frame.set_note("")
            item = QListWidgetItem(empty_hint)
            item.setForeground(QColor("#90a8c2"))
            listing.addItem(item)
        else:
            frame.set_badge("%d packages" % len(packages))
            # Only the dev list is tickable. Dev builds are the ones you flip
            # on and off while working; a local package is a whole-root
            # decision and a row of checkboxes there would only be clutter.
            tickable = listing is self.dev_list
            for package in packages:
                # Two spaces, not the six the override marks use: this belongs
                # to the package's name, not to what the resolve makes of it,
                # and must survive being remarked.
                display = package.request + (
                    "  (symlinked)" if package.is_symlink else ""
                )
                item = QListWidgetItem(display)
                item.setData(_PACKAGE_NAME_ROLE, package.name)
                item.setData(_PACKAGE_PATH_ROLE, str(package.path))
                tip = "%s\n%s" % (package.path, package.definition)
                if package.is_symlink:
                    tip += (
                        "\n\nA link to your working copy:\n  %s\nEdits there "
                        "are live in the next resolve, and deleting this "
                        "removes only the link." % package.link_target()
                    )

                # A package rez will skip is worth flagging before anything
                # else this list says about it: an override that rez never
                # sees is not an override, it is a puzzle.
                problem = definition_mismatch(package)
                if problem:
                    item.setText("%s      %s" % (display, problem))
                    item.setForeground(QColor("#e06c75"))
                    tip += "\n\n%s" % problem

                if tickable:
                    # Setting a check state is what puts a box on the row --
                    # ItemIsUserCheckable is already in Qt's default flags, so
                    # setting it would say nothing. A row with no check state
                    # is how the local list stays plain.
                    item.setCheckState(
                        Qt.Unchecked
                        if package.name in self._disabled_dev
                        else Qt.Checked
                    )
                    tip += (
                        "\n\nUnticked, this package is kept out of the resolve "
                        "and the studio one is used instead."
                    )
                item.setToolTip(tip)
                listing.addItem(item)

        return packages

    def _on_dev_item_changed(self, item: QListWidgetItem) -> None:
        """A dev package was ticked or unticked."""
        name = item.data(_PACKAGE_NAME_ROLE)
        if not name:
            return

        was_disabled = name in self._disabled_dev
        now_disabled = item.checkState() != Qt.Checked
        if was_disabled == now_disabled:
            return

        # By name, not by version: the checkbox says "use my build of this",
        # and having 1.0.0 on while 0.9.0 is off would resolve to whichever
        # rez picked anyway.
        if now_disabled:
            self._disabled_dev.add(name)
        else:
            self._disabled_dev.discard(name)

        self._sync_dev_checks()
        error = self.store.set_disabled_dev_packages(sorted(self._disabled_dev))
        if error:
            self.statusBar().showMessage(error, 8000)

        self._refresh_override_marks()
        tool = self._current_tool()
        if tool:
            self._show_packages(tool)

    def _sync_dev_checks(self) -> None:
        """Make every row of a name agree, without re-entering the handler."""
        blocked = self.dev_list.blockSignals(True)
        for row in range(self.dev_list.count()):
            item = self.dev_list.item(row)
            name = item.data(_PACKAGE_NAME_ROLE)
            if not name:
                continue
            item.setCheckState(
                Qt.Unchecked if name in self._disabled_dev else Qt.Checked
            )
        self.dev_list.blockSignals(blocked)

    def enabled_dev_packages(self) -> list[LocalPackage]:
        """The installed dev packages actually in play."""
        if not self.dev_frame.is_checked():
            return []
        return [p for p in self._dev_packages if p.name not in self._disabled_dev]

    # -- package context menu ----------------------------------------------

    def effective_packages_path(self) -> list[str]:
        """Every root this launch will read, in order."""
        paths, _note = launcher.filtered_packages_path(
            self.excluded_roots(), self.included_roots()
        )
        return paths or launcher.packages_path()

    def _winner_for(self, name: str, request: str):
        """Which root rez will take ``request`` from, cached for this refresh."""
        key = (name, request)
        if key in self._winner_cache:
            return self._winner_cache[key]
        winner = resolves_to(name, request, self.effective_packages_path())
        self._winner_cache[key] = winner
        return winner

    def _root_unknown_to_rez(self, root) -> bool:
        """Is ``root`` somewhere rez's own configuration never looks?"""
        known = {os.path.normpath(p) for p in launcher.packages_path()}
        if not known:
            return False  # cannot read the path: no claim either way
        return os.path.normpath(str(root)) not in known

    def _override_takes_effect(self, shadow, packages) -> bool:
        """Will this build of ours really be the one the resolve gets?

        The resolve list used to say "overridden by your local build" on the
        strength of a name match alone. It has to mean it: a request marked as
        overridden that resolves to the studio package is worse than no mark,
        because it is an answer that stops you looking.
        """
        if shadow.blocked:
            return False
        winner = self._winner_for(shadow.name, shadow.request)
        return winner is None or _winner_is_ours(winner, packages)

    def _section_for(self, listing: QListWidget):
        """The (packages, root, label) behind one of the two package lists."""
        if listing is self.dev_list:
            return self._dev_packages, dev_root(), "dev"
        return self._local_packages, local_root(), "local"

    def _packages_for_items(self, listing: QListWidget, items) -> list[LocalPackage]:
        packages, _root, _label = self._section_for(listing)
        by_path = {str(p.path): p for p in packages}
        found = []
        for item in items:
            package = by_path.get(item.data(_PACKAGE_PATH_ROLE) or "")
            if package is not None:
                found.append(package)
        return found

    def _on_package_menu(self, listing: QListWidget, point) -> None:
        clicked = listing.itemAt(point)
        is_dev = listing is self.dev_list

        if clicked is None or not clicked.data(_PACKAGE_PATH_ROLE):
            # Empty space, a placeholder, or an error row. On the dev list that
            # is exactly where someone with nothing installed yet will
            # right-click, so Install Package has to be reachable from there.
            if is_dev:
                menu = QMenu(self)
                install_action = menu.addAction("Install Package...")
                if menu.exec(listing.mapToGlobal(point)) is install_action:
                    self.show_install_dialog()
            return

        selected = [i for i in listing.selectedItems() if i.data(_PACKAGE_PATH_ROLE)]
        # Right-clicking outside the selection targets what was clicked, which
        # is what every other list in the world does.
        items = selected if clicked in selected else [clicked]
        packages = self._packages_for_items(listing, items)
        if not packages:
            return

        count = len(packages)
        menu = QMenu(self)
        install_action = menu.addAction("Install Package...") if is_dev else None
        if install_action is not None:
            menu.addSeparator()
        browse_action = menu.addAction(
            "Browse folder" if count == 1 else "Browse %d folders" % count
        )
        copy_action = menu.addAction(
            "Copy path" if count == 1 else "Copy %d paths" % count
        )
        menu.addSeparator()
        delete_action = menu.addAction(
            "Delete from disk"
            if count == 1
            else "Delete %d packages from disk" % count
        )

        chosen = menu.exec(listing.mapToGlobal(point))
        if install_action is not None and chosen is install_action:
            self.show_install_dialog()
        elif chosen is browse_action:
            self.browse_packages(packages)
        elif chosen is copy_action:
            QApplication.clipboard().setText(
                "\n".join(str(p.path) for p in packages)
            )
            self.statusBar().showMessage(
                "Copied %d path%s" % (count, "" if count == 1 else "s"), 4000
            )
        elif chosen is delete_action:
            self._confirm_delete_packages(listing, packages)

    def show_install_dialog(self) -> None:
        """Browse the working location and install one of its packages."""
        dialog = InstallPackageDialog(dev_working_root(), dev_root(), self)
        dialog.exec()
        if not dialog.installed:
            return

        self.refresh_package_lists()
        names = ", ".join(dict.fromkeys(dialog.installed))
        self.statusBar().showMessage("Installed %s" % names, 8000)

    def browse_packages(self, packages: list[LocalPackage]) -> list[str]:
        """Open each package folder in the desktop's file manager.

        Returns the failures. Opening a handful at once is the point -- you are
        usually comparing two builds -- but a dozen windows is not, so this
        stops at a sane number rather than carpeting the desktop.
        """
        limit = 5
        errors: list[str] = []
        for package in packages[:limit]:
            if not package.path.is_dir():
                errors.append("%s is no longer there" % package.path)
                continue
            if not QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(package.path))
            ):
                errors.append("no file manager would open %s" % package.path)

        if len(packages) > limit:
            errors.append(
                "opened the first %d of %d; the rest were skipped"
                % (limit, len(packages))
            )
        if errors:
            self.statusBar().showMessage(errors[0], 8000)
        else:
            self.statusBar().showMessage(
                "Opened %d folder%s"
                % (len(packages), "" if len(packages) == 1 else "s"),
                4000,
            )
        return errors

    def _confirm_delete_packages(
        self, listing: QListWidget, packages: list[LocalPackage]
    ) -> None:
        shown = [
            "%s%s" % (p.path, "   (link only)" if p.is_symlink else "")
            for p in packages[:8]
        ]
        if len(packages) > len(shown):
            shown.append("... and %d more" % (len(packages) - len(shown)))

        links = [p for p in packages if p.is_symlink]
        note = "This cannot be undone."
        if links:
            # The difference between removing a pointer and removing a day's
            # work, and worth saying before the button is pressed rather than
            # after.
            note = (
                "%d of these %s a link to a working copy: only the link is "
                "removed, and the files it points at are left alone.\n\n"
                "This cannot be undone."
                % (len(links), "is" if len(links) == 1 else "are")
            )

        reply = QMessageBox.warning(
            self,
            "Delete from disk",
            "Delete %d package%s?\n\n%s\n\n%s"
            % (
                len(packages),
                "" if len(packages) == 1 else "s",
                "\n".join(shown),
                note,
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,  # destructive: never the default
        )
        if reply != QMessageBox.Yes:
            return

        errors = self.delete_packages(listing, packages)
        if errors:
            QMessageBox.warning(
                self,
                "Not everything was deleted",
                "Deleted %d of %d.\n\n%s"
                % (len(packages) - len(errors), len(packages), "\n".join(errors)),
            )

    def delete_packages(
        self, listing: QListWidget, packages: list[LocalPackage]
    ) -> list[str]:
        """Delete without asking, and return the errors.

        Deliberately free of dialogs: the confirmation and the failure report
        both live in the caller, so this stays callable from a test without a
        modal blocking it.
        """
        _packages, root, label = self._section_for(listing)
        errors = [e for e in (delete_package(p, root) for p in packages) if e]

        self.refresh_package_lists()

        deleted = len(packages) - len(errors)
        if errors:
            self.statusBar().showMessage(errors[0], 8000)
        if deleted:
            self.statusBar().showMessage(
                "Deleted %d %s package%s"
                % (deleted, label, "" if deleted == 1 else "s"),
                6000,
            )
        return errors

    def _refresh_override_marks(self) -> None:
        """Flag packages in either root that shadow the current resolve."""
        self._winner_cache = {}
        tool = self._current_tool()
        requests = ()
        if self._bootstrap is not None and tool:
            requests = self._bootstrap.packages.get(tool, ())

        for listing, frame, packages in (
            (self.local_list, self.local_frame, self._local_packages),
            (self.dev_list, self.dev_frame, self.enabled_dev_packages()),
        ):
            overrides = (
                shadowed_requests(packages, requests)
                if frame.is_checked()
                else {}
            )

            # Each list is newest-first per name, and rez resolves the highest
            # version that satisfies the request, so only the first entry for a
            # given name actually wins. Marking all three of someone's
            # nuke_utils builds would say the opposite of what happens.
            marked: set[str] = set()
            for row in range(listing.count()):
                item = listing.item(row)
                name = item.data(_PACKAGE_NAME_ROLE)
                if not name:
                    continue
                shadow = overrides.get(name)
                base = item.text().split("      ")[0]
                first = shadow is not None and name not in marked
                if first:
                    marked.add(name)

                if shadow is not None and shadow.blocked and first:
                    # The resolve names this package, but this build cannot be
                    # the one it gets. Saying "overrides" here is how you end
                    # up staring at a package that is never in the environment.
                    item.setText(
                        "%s      does not satisfy %s" % (base, shadow.request)
                    )
                    item.setForeground(QColor("#e06c75"))
                    item.setToolTip(
                        "%s\nThe show asks for '%s', which this version cannot "
                        "satisfy - rez will use the studio build instead."
                        % (item.toolTip().split("\n")[0], shadow.request)
                    )
                elif shadow is not None and first:
                    winner = self._winner_for(name, shadow.request)
                    mine = winner is None or _winner_is_ours(winner, packages)

                    if not mine:
                        # The whole point of the list is to say what will be in
                        # the environment. A build that loses to a newer one
                        # elsewhere is not overriding anything, and calling it
                        # an override is how you spend an afternoon wondering
                        # why your change is not there.
                        item.setText(
                            "%s      outranked by %s"
                            % (base, winner.version or "another build")
                        )
                        item.setForeground(QColor("#90a8c2"))
                        item.setToolTip(
                            "%s\nThe show asks for '%s'. rez takes the highest "
                            "version satisfying that across every package path, "
                            "and that is %s in\n%s\n\nPath order only settles "
                            "ties between equal versions - being earlier does "
                            "not beat a higher version."
                            % (
                                item.toolTip().split("\n")[0],
                                shadow.request,
                                winner.version or "an unversioned build",
                                winner.root,
                            )
                        )
                    else:
                        item.setText("%s      overrides %s" % (base, shadow.request))
                        item.setForeground(QColor("#e0a23c"))
                        item.setToolTip(
                            "%s\nThe highest version of '%s' satisfying the "
                            "show's '%s' anywhere on the packages path, so this "
                            "is the one the resolve gets."
                            % (item.toolTip().split("\n")[0], name, shadow.request)
                        )
                elif shadow is not None:
                    item.setText("%s      (older build)" % base)
                    item.setForeground(QColor("#90a8c2"))
                else:
                    item.setText(base)
                    item.setForeground(QColor("#d7dae0"))

            self._float_overrides(listing, overrides)

            if not frame.is_checked():
                frame.set_note("not used", "")
                frame.set_alert("")
            elif packages:
                # Three facts, and they are not the same one. "In use" is a
                # build of yours the resolve will actually get. "Outranked" is
                # one that could have been used but lost to a higher version
                # elsewhere. "Unusable" is one that was never in the running,
                # because its version cannot satisfy the request at all.
                #
                # The words match the ones on the rows -- a header that says
                # "overridden" over a row that says "outranked by 1.9.0" makes
                # the reader stop and work out whether they mean the same
                # thing.
                in_use = 0
                outranked = 0
                unusable = 0
                for name, shadow in overrides.items():
                    if shadow.blocked:
                        unusable += 1
                        continue
                    winner = self._winner_for(name, shadow.request)
                    if winner is None or _winner_is_ours(winner, packages):
                        in_use += 1
                    else:
                        outranked += 1

                frame.set_note(
                    "%d in use" % in_use if in_use else "",
                    "warn" if in_use else "",
                )
                parts = []
                if outranked:
                    parts.append("%d outranked" % outranked)
                if unusable:
                    parts.append("%d unusable" % unusable)
                frame.set_alert("  \u00b7  ".join(parts))
            else:
                frame.set_alert("")

    def _float_overrides(self, listing: QListWidget, overrides: dict) -> None:
        """Lift the packages that override the resolve to the top of the list.

        These are the rows that change what you are about to launch. A root
        with thirty builds in it buries the two that matter halfway down, and
        scrolling to find out whether one of yours is in play defeats the point
        of showing the list at all.

        Every version of an overriding name moves, not just the winning one, so
        a name's builds stay together and the "(older build)" rows keep sitting
        under the one that beat them. Order within each group is untouched.
        """
        if not overrides or listing.count() < 2:
            return

        rows = [listing.item(row) for row in range(listing.count())]
        names = [item.data(_PACKAGE_NAME_ROLE) for item in rows]
        if not any(name in overrides for name in names if name):
            return

        # Stable partition: taking items out of a QListWidget renumbers the
        # rest, so the order is decided first and applied afterwards.
        wanted = [
            item
            for item, name in zip(rows, names)
            if name and name in overrides
        ]
        rest = [item for item in rows if item not in wanted]
        if [id(i) for i in wanted + rest] == [id(i) for i in rows]:
            return  # already in that order; reordering would only flicker

        blocked = listing.blockSignals(True)
        selected = {id(item) for item in listing.selectedItems()}
        for _ in range(listing.count()):
            listing.takeItem(0)
        for item in wanted + rest:
            listing.addItem(item)
            if id(item) in selected:
                item.setSelected(True)
        listing.blockSignals(blocked)

    def _on_frame_toggled(self, _expanded: bool) -> None:
        self._apply_frame_stretch()

    def excluded_roots(self) -> tuple[str, ...]:
        """Package roots to keep out of the resolve, per the checkboxes.

        The dev root also comes off when only *some* of its packages are
        wanted: what goes on the path instead is a filtered view of it, built
        by :func:`dev_install.selection_view`.
        """
        roots: list[str] = []
        if not self.local_frame.is_checked():
            roots.append(str(local_root()))
        if not self.dev_frame.is_checked():
            roots.append(str(dev_root()))
        elif self._dev_view_root() is not None:
            roots.append(str(dev_root()))
        return tuple(roots)

    def _dev_view_root(self):
        """The filtered dev root for this launch, or ``None`` for the real one.

        Only built when something is actually switched off, so the common case
        costs nothing and puts no extra directory on the path.
        """
        if not self.dev_frame.is_checked() or not self._disabled_dev:
            return None
        present = {p.name for p in self._dev_packages}
        off = sorted(self._disabled_dev & present)
        if not off:
            return None

        view, error = dev_install.selection_view(dev_root(), off)
        if error:
            self.statusBar().showMessage(error, 8000)
            return None
        return view

    def _on_package_use_changed(self, _checked: bool) -> None:
        self._use_local = self.local_frame.is_checked()
        self._use_dev = self.dev_frame.is_checked()
        error = self.store.set_package_use(self._use_local, self._use_dev)
        if error:
            self.statusBar().showMessage(error, 8000)

        # A section that is switched off cannot be overriding anything, so the
        # marking on both sides has to be redrawn, not just greyed.
        for frame, listing, on in (
            (self.local_frame, self.local_list, self._use_local),
            (self.dev_frame, self.dev_list, self._use_dev),
        ):
            listing.setEnabled(on)
        tool = self._current_tool()
        if tool and self._bootstrap is not None:
            self._show_packages(tool)
        else:
            self._refresh_override_marks()

        _kept, note = launcher.filtered_packages_path(
            self.excluded_roots(), self.included_roots()
        )
        if note:
            self.statusBar().showMessage(note, 10000)

    def _on_package_frame_toggled(self, expanded: bool) -> None:
        if expanded:
            # Cheap scandir, and it means the lists are never stale on open.
            self.refresh_package_lists()
        self._apply_frame_stretch()

    def _apply_frame_stretch(self) -> None:
        """Give vertical space only to sections that are open."""
        resolve_open = self.resolve_frame.is_expanded()
        local_open = self.local_frame.is_expanded()
        dev_open = self.dev_frame.is_expanded()
        self._root_layout.setStretch(self._resolve_index, 2 if resolve_open else 0)
        self._root_layout.setStretch(self._local_index, 1 if local_open else 0)
        self._root_layout.setStretch(self._dev_index, 1 if dev_open else 0)
        self._root_layout.setStretch(
            self._spacer_index,
            0 if (resolve_open or local_open or dev_open) else 1,
        )
        self._grow_to_fit()

    def _grow_to_fit(self, remaining_passes: int = 2) -> None:
        """Make room for a section that was just opened.

        Only ever grows: shrinking on collapse would undo a size the user chose
        deliberately. Opening both sections in a short window would otherwise
        squash both lists to a single row.

        Re-runs itself on the next event-loop turn because the resize only
        reaches the layout afterwards -- opening both sections at once needs
        more than one pass to settle.
        """
        central = self.centralWidget()
        if central is None or central.layout() is None:
            return
        # The layout's minimumSize is the only figure that respects the lists'
        # explicit setMinimumHeight; sizeHint and minimumSizeHint both ignore
        # it, and a QListWidget's own hint is far too small to be useful.
        central.layout().activate()
        deficit = central.layout().minimumSize().height() - central.height()
        if deficit <= 0:
            return
        wanted = self.height() + deficit
        screen = self.screen()
        if screen is not None:
            wanted = min(wanted, screen.availableGeometry().height() - 60)
        if wanted > self.height():
            self.resize(self.width(), wanted)
            if remaining_passes > 0:
                QTimer.singleShot(
                    0, lambda: self._grow_to_fit(remaining_passes - 1)
                )

    # -- actions -----------------------------------------------------------

    def _current_tool(self) -> str | None:
        if self._active_dcc is None:
            return None
        return self._dcc_variant.get(self._active_dcc.name) or None

    def _update_actions(self) -> None:
        ready = (
            self.current_project() is not None
            and self._bootstrap is not None
            and self._current_tool() is not None
        )
        self.launch_button.setEnabled(ready)
        self.copy_action.setEnabled(ready)
        self.save_action.setEnabled(ready)
        self.terminal_button.setEnabled(ready)

    def _on_copy_command(self) -> None:
        project = self.current_project()
        tool = self._current_tool()
        if project is None or tool is None or self._active_dcc is None:
            return
        preview = launcher.command_preview(
            project,
            self.resolved_packages(),
            self._active_dcc.run_command,
            self.highlight_roots(),
            self.launch_notes(),
        )
        QApplication.clipboard().setText(preview)
        self.statusBar().showMessage("Copied: %s" % preview, 5000)

    # -- resolving, launching, terminal -------------------------------------

    def resolved_packages(self) -> tuple[str, ...]:
        """The request list to resolve, for a launch or for a shell.

        The show's own ``show_<name>`` package is appended when the directory
        exists, because the bootstrap adds it to every resolve -- leaving it out
        would hand you an environment subtly unlike the one the show expects.
        """
        project = self.current_project()
        tool = self._current_tool()
        if project is None or self._bootstrap is None or tool is None:
            return ()
        packages = tuple(self._bootstrap.packages.get(tool, ()))
        return packages + self.show_package_requests()

    def show_package_requests(self) -> tuple[str, ...]:
        """The show packages appended to every resolve.

        When the probe ran, this is whatever ``_get_show_packages()`` returned
        -- the same call the pipeline makes, including the empty tuple, which
        is a real answer and not a failure. Otherwise BootyCall falls back to
        looking for the package on disk itself.
        """
        if self._bootstrap is not None and self._bootstrap.source == "bootstrap":
            return tuple(self._bootstrap.show_packages)
        show_pkg = self.show_package()
        return (show_pkg.name,) if show_pkg is not None else ()

    def show_package(self):
        """The selected show's own package, if it has one."""
        project = self.current_project()
        if project is None:
            return None
        return find_show_package(project)

    def included_roots(self) -> tuple[str, ...]:
        """Package roots the resolve needs that rez may not know about.

        A show package lives under the show, or under the user's own package
        directory. Requesting it without putting that root on the path would
        fail to resolve.

        When the probe named a show package BootyCall cannot find on disk, both
        candidate roots go on instead of neither: rez found it somewhere, and a
        root that turns out to hold nothing costs a resolve nothing.
        """
        extra: list[str] = list(self.package_roots_in_play())

        show_pkg = self.show_package()
        if show_pkg is not None:
            return tuple(extra) + (str(show_pkg.root),)

        project = self.current_project()
        if project is None or not self.show_package_requests():
            return tuple(extra)
        return tuple(extra) + tuple(
            str(root) for root in show_package_roots(project) if root.is_dir()
        )

    def dev_root_path(self):
        """The installed dev root, as the window understands it."""
        return dev_root()

    def local_root_path(self):
        return local_root()

    def dev_working_root_path(self):
        return dev_working_root()

    def run_resolve_test(self) -> None:
        """Run the real resolve and report what rez chose.

        Synchronous, with a wait cursor: a cold resolve of a Maya package set
        takes a while, and a diagnostic you started deliberately is one you are
        willing to wait for. Everything else in this window is a prediction;
        this is the one thing that measures.
        """
        from .. import diagnostics

        project = self.current_project()
        if project is None or not self.resolved_packages():
            self.statusBar().showMessage(
                "Pick a show and a tool first - there is nothing to resolve", 5000
            )
            return

        self.statusBar().showMessage("Resolving with rez - this can take a minute...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            text = diagnostics.resolve_report(self)
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().clearMessage()

        QApplication.clipboard().setText(text)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("What rez actually resolved")
        box.setText("Copied to the clipboard.")
        box.setInformativeText(
            "\n".join(
                line
                for line in text.splitlines()
                if line.strip().startswith(("***", ">>>"))
            )
            or "The resolve came back with nothing to flag."
        )
        box.setDetailedText(text)
        box.exec()

    def show_diagnostics(self) -> None:
        """Everything that decides whether a package reaches the environment."""
        from .. import diagnostics

        text = diagnostics.report(self)
        QApplication.clipboard().setText(text)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("BootyCall diagnostics")
        box.setText("Copied to the clipboard.")
        box.setInformativeText(
            "Everything that decides whether a package reaches the "
            "environment: what rez is configured to read, what this launch "
            "will use, what is on disk, and what each definition declares."
        )
        box.setDetailedText(text)
        box.exec()

    def package_roots_in_play(self) -> tuple[str, ...]:
        """The per-user roots this window says are in play, most specific first.

        BootyCall shows your local and dev packages and tells you which ones
        override the resolve. It used to leave putting them on
        ``REZ_PACKAGES_PATH`` to the site's rez config and simply assume the two
        agreed -- and when they did not, the package sat there in the list,
        marked as overriding, and never reached a single launch.

        So it stops assuming. Roots the site already lists are left exactly
        where they are (``filtered_packages_path`` drops duplicates), which
        means this changes nothing at a site that was already configured for it
        and fixes the one that was not.

        Dev before local because the dev root is nested inside the local one and
        is the more deliberate of the two: you install into it on purpose.
        """
        roots: list[str] = []

        if self.dev_frame.is_checked():
            view = self._dev_view_root()
            roots.append(str(view) if view is not None else str(dev_root()))
        if self.local_frame.is_checked():
            roots.append(str(local_root()))

        return tuple(r for r in roots if Path(r).is_dir())

    def highlight_roots(self) -> tuple[tuple[str, str], ...]:
        """Roots whose packages the launch should call out by name.

        rez marks its own configured local packages path green and ``(local)``
        in the context table; a dev root BootyCall added gets no mark, so a dev
        build sits in a forty-line table looking like everything else. These
        are the roots the launch says are yours.

        Most specific first, because the summary stops at the first match and
        the dev root lives inside the local one -- ordered the other way round,
        every dev package would be labelled "local".
        """
        roots: list[tuple[str, str]] = []
        if self.dev_frame.is_checked():
            view = self._dev_view_root()
            if view is not None:
                roots.append(("dev", str(view)))
            roots.append(("dev", str(dev_root())))
        if self.local_frame.is_checked():
            roots.append(("local", str(local_root())))
        return tuple(roots)

    def launch_notes(self) -> tuple[tuple[str, str], ...]:
        """What this window did to the environment that rez cannot report.

        rez prints what resolved. It has no idea you switched a package root
        off before launching -- that happened in a window it never saw -- and
        an artist who forgot they did it has no way to find out from inside the
        session. These are the things that are true because of BootyCall, said
        where the consequences turn up.
        """
        notes: list[tuple[str, str]] = []

        if not self.local_frame.is_checked():
            notes.append(
                ("warn", "Local packages are switched OFF for this launch")
            )
        if not self.dev_frame.is_checked():
            notes.append(
                ("warn", "Installed dev packages are switched OFF for this launch")
            )
        elif self._disabled_dev:
            present = sorted(
                {p.name for p in self._dev_packages} & self._disabled_dev
            )
            if present:
                notes.append(
                    (
                        "warn",
                        "Dev packages switched off: %s" % ", ".join(present),
                    )
                )

        missing = self.missing_from_rez_path()
        if missing:
            notes.append(
                (
                    "",
                    "Roots BootyCall added that rez is not configured to read: %s"
                    % ", ".join(missing),
                )
            )
        return tuple(notes)

    def missing_from_rez_path(self) -> tuple[str, ...]:
        """Roots in play that rez's own configuration does not list.

        Worth saying out loud once: it means the packages BootyCall is showing
        you are only in the resolve because BootyCall put them there, and
        anything launched by hand will not see them.
        """
        known = {os.path.normpath(p) for p in launcher.packages_path()}
        if not known:
            return ()
        return tuple(
            root
            for root in self.package_roots_in_play()
            if os.path.normpath(root) not in known
            # The filtered view is BootyCall's own construction; rez has no
            # reason to know about it and its absence is not news.
            and os.path.normpath(root) != os.path.normpath(str(dev_install.view_root()))
        )

    def _on_open_terminal(self) -> None:
        project = self.current_project()
        packages = self.resolved_packages()
        if project is None or not packages:
            self.statusBar().showMessage(
                "Pick a show and a tool first - the shell needs a package set", 5000
            )
            return
        try:
            launcher.open_terminal(
                project,
                packages,
                self.excluded_roots(),
                self.included_roots(),
                roots=self.highlight_roots(),
                notes=self.launch_notes(),
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Could not open a terminal",
                "%s\n\nCommand:\n%s"
                % (
                    exc,
                    launcher.terminal_preview(
                        project,
                        packages,
                        self.highlight_roots(),
                        self.launch_notes(),
                    ),
                ),
            )
            return
        self.statusBar().showMessage(
            "Opened a shell for %s (%d packages)" % (project.name, len(packages)),
            8000,
        )

    def raise_to_front(self) -> None:
        """Called when a second launch asks the running instance to show."""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # -- compact mode ------------------------------------------------------

    def is_compact(self) -> bool:
        return self._compact

    def toggle_compact(self) -> None:
        self.set_compact(not self._compact)

    def set_compact(self, compact: bool) -> None:
        """Collapse to show, software and Launch -- or restore.

        Everything else is hidden rather than removed, so the expanded window
        comes back exactly as it was, open sections and all.
        """
        compact = bool(compact)
        if compact == self._compact:
            return

        # Where the window is *now*, before anything below resizes it or
        # recreates the native window. Reading this later means measuring the
        # result of the collapse rather than the thing being collapsed.
        anchor = self._nearest_corner()
        before = self.frameGeometry()

        if compact:
            self._expanded_size = self.size()
            self._expanded_minimum = self.minimumSize()
        elif self._expanded_size is None:
            self._expanded_size = QSize(705, 680)
            self._expanded_minimum = QSize(570, 560)

        self._compact = compact
        self.compact_button.setIcon(_chevrons(up=not compact))
        self.compact_action.setChecked(compact)
        self.compact_button.setToolTip(
            "Back to the full window (Ctrl+M)"
            if compact
            else "Collapse to a compact launcher (Ctrl+M)"
        )

        for widget in (
            self.title_label,
            self.tagline,
            self.header_separator,
            self.resolve_frame,
            self.local_frame,
            self.dev_frame,
            self.terminal_button,
        ):
            widget.setVisible(not compact)
        self.menuBar().setVisible(not compact)
        self.statusBar().setVisible(not compact)
        # No title bar text: compact is a button, not a window you manage.
        self.setWindowTitle(self.COMPACT_TITLE if compact else self.EXPANDED_TITLE)
        if self.status_label.text():
            self.status_label.setVisible(not compact)

        # Buttons hug the left in compact, so the window can be as narrow as
        # the tile rather than as wide as a right-justified footer needs.
        # Collapse the leading spacer rather than zeroing its stretch factor:
        # a stretch spacer keeps an Expanding policy, and when every factor is
        # zero QBoxLayout still shares leftover space among expanding items --
        # so the spacer would eat the width the button is meant to take.
        self._footer_lead_spacer.changeSize(
            0,
            0,
            QSizePolicy.Fixed if compact else QSizePolicy.Expanding,
            QSizePolicy.Minimum,
        )
        self._footer.invalidate()
        self._footer.setSpacing(6 if compact else 10)

        # Compact: the button takes the width the chevron leaves, so its right
        # edge lands on the tile's. A trailing stretch would left-justify the
        # pair but leave a ragged gap under the tile instead.
        self.launch_button.setSizePolicy(
            QSizePolicy.Expanding if compact else QSizePolicy.Minimum,
            QSizePolicy.Fixed,
        )
        # Fusion gives buttons a generous minimum width of its own; without
        # overriding it the footer, not the tile, would set the window width
        # and the two right edges would miss each other by a few pixels.
        self.launch_button.setMinimumWidth(40 if compact else 0)

        # "Launch" plus its padding is wider than a tile on its own; "GO!" and
        # the tighter padding below fit beside the chevron inside one tile.
        self.launch_button.setText("GO!" if compact else "Launch")
        self.launch_button.setProperty("compact", compact)
        self.launch_button.style().unpolish(self.launch_button)
        self.launch_button.style().polish(self.launch_button)

        # Show codes are longer than a tile; elide rather than let one chip set
        # the width of the whole collapsed window.
        self.chip_bar.set_chip_max_width(
            self._tile_width - 12 if compact else None
        )
        self._root_layout.setContentsMargins(
            *(self.COMPACT_MARGINS if compact else self.EXPANDED_MARGINS)
        )
        self._root_layout.setSpacing(8 if compact else 14)

        self._apply_compact_filter()
        self._apply_window_hints()

        if compact:
            self.setMinimumSize(0, 0)
            self.adjustSize()
            self.resize(self.sizeHint())
        else:
            self.setMinimumSize(self._expanded_minimum)
            self.resize(self._expanded_size)

        self._keep_corner(before, anchor)

    def _nearest_corner(self) -> tuple[str, str]:
        """Which corner of the screen this window is sitting in.

        Returned as ``(horizontal, vertical)`` from the window's centre against
        the screen's, which is the reading that matches what people mean: a
        window mostly over on the right belongs to the right-hand corners even
        if its left edge is past the middle.
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return ("left", "top")
        available = screen.availableGeometry()
        centre = self.frameGeometry().center()
        return (
            "right" if centre.x() > available.center().x() else "left",
            "bottom" if centre.y() > available.center().y() else "top",
        )

    def _keep_corner(self, before, anchor: tuple[str, str]) -> None:
        """Resize about ``anchor`` rather than about the top-left.

        Qt grows and shrinks a window from its top-left, so collapsing a
        launcher parked in the bottom-right corner of the screen sends it
        skating up and to the left, away from where it was put. Holding the
        nearest corner still means the thing stays where you left it, and
        expanding grows back out of the same corner rather than off the screen.
        """
        horizontal, vertical = anchor
        after = self.frameGeometry()

        x = before.right() - after.width() + 1 if horizontal == "right" else before.left()
        y = (
            before.bottom() - after.height() + 1
            if vertical == "bottom"
            else before.top()
        )

        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            # Anchoring must not push the window off the edge it was anchored
            # to -- an expanded window that grows past the top of the screen has
            # a title bar you cannot reach.
            available = screen.availableGeometry()
            x = max(available.left(), min(x, available.right() - after.width() + 1))
            y = max(available.top(), min(y, available.bottom() - after.height() + 1))

        self.move(x, y)

    def _apply_window_hints(self) -> None:
        """Compact is a always-on-top, every-workspace launcher bar.

        Both hints are dropped when the window expands again: a full-size window
        that refuses to go behind anything is a nuisance, not a feature.
        """
        platform_hints.set_always_on_top(self, self._compact)
        note = platform_hints.set_visible_on_all_workspaces(self, self._compact)
        if self._compact and note:
            # Worth saying once, not worth blocking on.
            self.compact_button.setToolTip(
                "Back to the full window (Ctrl+M)\n\nNote: %s" % note
            )

    def _apply_compact_filter(self) -> None:
        """Show only the selected chip and tile while compact, as labels.

        Neither responds to clicks there: compact has room for one of each, so
        a control that can only ever select what is already selected is just a
        way to lose your place.
        """
        selected_show = self.chip_bar.selected_name()
        for chip in self.chip_bar._chips:
            chip.setVisible(not self._compact or chip.name == selected_show)
        self.chip_bar.set_interactive(not self._compact)
        self.chip_bar.line_edit.setVisible(not self._compact)

        active = self._active_dcc.name if self._active_dcc else None
        for name, button in self._dcc_buttons.items():
            button.setVisible(not self._compact or name == active)
            button.set_interactive(not self._compact)
        self.dcc_placeholder.setVisible(
            not self._compact and not self._dcc_buttons
        )

        # Both rows are FlowLayouts, which skip hidden widgets only when asked
        # to lay out again.
        self.chip_bar._row.invalidate()
        self.dcc_row.invalidate()
        if self._compact:
            self.adjustSize()

    # -- favourites --------------------------------------------------------

    def show_settings(self) -> None:
        """Edit the three roots, then re-read everything they feed."""
        dialog = SettingsDialog(self)
        if dialog.exec() != SettingsDialog.Accepted:
            return

        overrides = dialog.overrides()
        config.set_path_overrides(overrides)
        error = self.store.set_path_overrides(overrides)
        if error:
            self.statusBar().showMessage(error, 8000)

        # Everything downstream is derived from these paths, so re-read the lot
        # rather than trying to work out what changed.
        self.reload_projects()
        self.refresh_package_lists()
        self.statusBar().showMessage("Settings saved", 5000)

    def show_favorites(self) -> None:
        """Open (or raise) the favourites window."""
        if self._favorites_window is None:
            window = FavoritesWindow(self.store, self)
            window.favoriteChosen.connect(self._on_apply_config)
            window.storeChanged.connect(self._rebuild_file_menu)
            window.add_button.clicked.connect(self._on_add_current_favorite)
            self._favorites_window = window
        self._favorites_window.refresh()
        self._favorites_window.show()
        self._favorites_window.raise_()
        self._favorites_window.activateWindow()

    def _on_add_current_favorite(self) -> None:
        self._on_save_config()
        if self._favorites_window is not None:
            self._favorites_window.refresh()

    def _on_launch_menu(self, point) -> None:
        menu = QMenu(self)
        launch_action = menu.addAction("Launch")
        update_action = menu.addAction(dev_install.MENU_LABEL)
        update_action.setEnabled(self.launch_button.isEnabled())
        launch_action.setEnabled(self.launch_button.isEnabled())

        chosen = menu.exec(self.launch_button.mapToGlobal(point))
        if chosen is launch_action:
            self._on_launch()
        elif chosen is update_action:
            self._on_update_and_launch()

    def stale_dev_installs(self) -> list:
        """Installed dev packages older than the working copies they came from.

        Only the ones actually in play: warning about a package you have
        switched off, or a whole section you have switched off, is a warning
        about something that is not going to be in the environment anyway.
        """
        enabled = self.enabled_dev_packages()
        if not enabled:
            return []
        return dev_install.stale_installs(enabled, dev_working_root())

    def _update_dev_installs(self, stale) -> bool:
        """Re-install ``stale``. Returns whether everything worked."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage(
            "Rebuilding %d dev package%s..."
            % (len(stale), "" if len(stale) == 1 else "s")
        )
        self._start_progress(len(stale))
        try:
            updated, failures = dev_install.update_installs(
                stale, dev_root(), on_progress=self._step_progress
            )
        finally:
            self._end_progress()
            QApplication.restoreOverrideCursor()

        self.refresh_package_lists()
        if failures:
            QMessageBox.warning(
                self,
                "Some dev packages were not updated",
                "%s\n\n%s"
                % (
                    "Updated: " + ", ".join(updated) if updated else "Nothing updated.",
                    "\n".join(failures),
                ),
            )
            return False

        self.statusBar().showMessage(
            "Updated %s" % ", ".join(updated) if updated else "Nothing to update", 8000
        )
        return True

    def check_dev_installs(self) -> str:
        """Ask about stale dev installs before launching.

        Returns "launch", "cancel", or "" when there was nothing to ask about.

        The prompt exists because the failure it prevents is silent: you edit a
        package, launch, and spend twenty minutes wondering why your change is
        not there. It only appears when something is genuinely behind, so it
        stays a signal rather than another dialog to dismiss on autopilot.
        """
        stale = self.stale_dev_installs()
        if not stale:
            return ""

        listing = "\n".join("  %s" % item.describe() for item in stale)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Dev packages are out of date")
        box.setText(
            "%d installed dev package%s older than your working copies:"
            % (len(stale), " is" if len(stale) == 1 else "s are")
        )
        box.setInformativeText(
            "%s\n\nLaunching now uses what is installed, not what you have "
            "been editing." % listing
        )
        update = box.addButton("Update and Launch", QMessageBox.AcceptRole)
        launch = box.addButton("Launch Anyway", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(update)
        box.exec()

        clicked = box.clickedButton()
        if clicked is launch:
            return "launch"
        if clicked is not update:
            return "cancel"

        return "launch" if self._update_dev_installs(stale) else "cancel"

    def _on_update_and_launch(self) -> None:
        """The Launch menu's explicit version of the same thing."""
        project = self.current_project()
        tool = self._current_tool()
        if project is None or tool is None:
            return

        blocker = dev_install.update_blocker(
            self.enabled_dev_packages(),
            self.dev_frame.is_checked(),
            dev_working_root(),
        )
        if blocker:
            # You asked for this explicitly, so "nothing happened" is not an
            # answer. Every one of these reasons used to end as a five-second
            # status message followed by an ordinary launch, which is
            # indistinguishable from a menu item that does not work.
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Nothing to update")
            box.setText("Dev installs could not be updated.")
            box.setInformativeText(blocker)
            launch = box.addButton("Launch Anyway", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(launch)
            box.exec()
            if box.clickedButton() is not launch:
                return
            self._on_launch(checked_dev=True)
            return

        stale = self.stale_dev_installs()
        if not stale:
            self.statusBar().showMessage(
                "Every dev package in play is already up to date with %s"
                % dev_working_root(),
                8000,
            )
        elif not self._update_dev_installs(stale):
            # Deliberately does not fall through to a launch: that would look
            # like the update ran.
            return
        self._on_launch(checked_dev=True)

    def _on_launch(self, checked_dev: bool = False) -> None:
        project = self.current_project()
        tool = self._current_tool()
        if project is None or tool is None or self._active_dcc is None:
            return

        if not checked_dev and self.check_dev_installs() == "cancel":
            return

        packages = self.resolved_packages()
        command = self._active_dcc.run_command
        try:
            launcher.launch(
                project,
                packages,
                command,
                self.excluded_roots(),
                self.included_roots(),
                roots=self.highlight_roots(),
                notes=self.launch_notes(),
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Launch failed",
                "Could not start %s for %s:\n\n%s\n\nCommand:\n%s"
                % (
                    command,
                    project.name,
                    exc,
                    launcher.command_preview(project, packages, command),
                ),
            )
            return
        self.save_ui_state()
        self.statusBar().showMessage(
            "Launched %s (%s) for %s" % (command, tool, project.name), 8000
        )

    def save_ui_state(self) -> str:
        """Remember where you were: show, software, and every variant choice.

        Written on Launch rather than on every click -- launching is the moment
        that says "this is the setup I meant", and it keeps the config file off
        the write path of ordinary browsing.
        """
        project = self.current_project()
        error = self.store.save_ui_state(
            selected_show=project.name if project else None,
            selected_dcc=self._preferred_dcc,
            variants=self._dcc_variant,
            compact=self._compact,
        )
        if error:
            self.statusBar().showMessage(error, 8000)
        return error

    # -- helpers -----------------------------------------------------------

    def _set_status(self, text: str, level: str = "") -> None:
        self.status_label.setText(text)
        # Hidden when empty, or the now-usually-empty label leaves a gap under
        # the show field where the old green line used to be.
        self.status_label.setVisible(bool(text))
        self.status_label.setProperty("level", level)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


def apply_style(app: QApplication) -> None:
    app.setStyleSheet(STYLESHEET)
