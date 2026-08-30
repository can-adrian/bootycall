"""Dark stylesheet, sized for a facility workstation."""

STYLESHEET = """
QWidget {
    background: #0c1927;
    color: #d7dae0;
    font-family: "Inter", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 13px;
}

QLabel#title {
    font-size: 38px;
    font-weight: 600;
    /* The softer amber used by the "in use" / override badges, not the
       saturated Houdini tile orange. */
    color: #e0a23c;
}
/* Dialog headings stay at the old size; only the app logo grew. */
QLabel#dialogTitle {
    font-size: 20px;
    font-weight: 600;
    color: #f2f4f8;
}

QLabel#subtitle, QLabel#hint {
    color: #90a8c2;
    font-size: 12px;
}
QLabel#tagline {
    color: #90a8c2;
    font-size: 12px;
    font-style: italic;
}
QLabel#sectionLabel {
    color: #9db3ca;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}
QLabel#statusLabel {
    color: #90a8c2;
    font-size: 12px;
    padding: 2px 0;
}
QLabel#statusLabel[level="error"] { color: #e06c75; }
QLabel#statusLabel[level="ok"]    { color: #7fbf7f; }

QFrame#showField {
    background: #0e1c2b;
    border: 1px solid #152232;
    border-radius: 8px;
}
QFrame#showField[focused="true"] { border-color: #4a90d9; }

QLineEdit#showFieldEdit {
    background: transparent;
    border: none;
    padding: 4px 4px;
    font-size: 14px;
    selection-background-color: #3f6fa8;
}
/* The validity tint lands on the text, not a border -- the border belongs to
   the box the chips share. */
QLineEdit#showFieldEdit[state="ok"]  { color: #8fce8f; }
QLineEdit#showFieldEdit[state="bad"] { color: #d99e9e; }

QLineEdit#filterField {
    background: #0e1c2b;
    border: 1px solid #152232;
    border-radius: 5px;
    padding: 5px 9px;
}
QLineEdit#filterField:focus { border-color: #4a90d9; }

QListView {
    background: #0e1c2b;
    border: 1px solid #152232;
    border-radius: 6px;
    outline: none;
    padding: 4px;
}
QListView::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListView::item:selected { background: #12263e; color: #ffffff; }
QListView::item:hover:!selected { background: #111f30; }

QComboBox {
    background: #0e1c2b;
    border: 1px solid #152232;
    border-radius: 5px;
    padding: 6px 10px;
    min-width: 160px;
}
QComboBox:focus, QComboBox:hover { border-color: #4a90d9; }
/* Left ::drop-down unstyled on purpose: styling it suppresses Fusion's
   built-in arrow, and there is no image to replace it with. */
QComboBox QAbstractItemView {
    background: #0e1c2b;
    border: 1px solid #182637;
    selection-background-color: #12263e;
    outline: none;
}

QPushButton {
    background: #111f30;
    border: 1px solid #182637;
    border-radius: 5px;
    padding: 8px 16px;
    color: #d7dae0;
}
QPushButton:hover:!disabled  { background: #152334; border-color: #1e2c3c; }
QPushButton:pressed:!disabled { background: #0f1d2e; }
QPushButton:disabled { color: #23303f; border-color: #112030; }

QPushButton#launchButton {
    background: #3f6fa8;
    border: 1px solid #4a90d9;
    color: #ffffff;
    font-weight: 600;
    padding: 9px 22px;
}
QPushButton#launchButton:hover:!disabled  { background: #4a80c0; }
QPushButton#launchButton:pressed:!disabled { background: #365e8f; }
QPushButton#launchButton:disabled { background: #111f30; color: #23303f; }
QPushButton#launchButton[compact="true"] { padding: 8px 10px; }

QToolButton#dccButton {
    background: #0e1c2b;
    border: 1px solid #152232;
    border-radius: 8px;
    /* Extra bottom padding reserves the strip DccTile paints its variant line
       into; the icon and name sit above it. */
    padding: 12px 10px 26px 10px;
    color: #b9bec7;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#dccButton:hover   { background: #111f30; border-color: #1e2c3c; }
QToolButton#dccButton:checked { background: #112134; color: #ffffff; }

/* Terminal and Favourites: same shape as a DCC tile, but dashed so it reads as
   an action rather than one of the show's software choices. */
QToolButton#actionTile {
    background: transparent;
    border: 1px dashed #182637;
    border-radius: 8px;
    /* Matches the DCC tile, subtitle strip included, so the row lines up even
       though this tile has no variant line of its own. */
    padding: 12px 10px 26px 10px;
    color: #a6bad0;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#actionTile:hover:!disabled {
    background: #0e1c2b;
    border-color: #243040;
    color: #ffffff;
}
QToolButton#actionTile:pressed:!disabled { background: #0a1521; }
QToolButton#actionTile:disabled { color: #1f2d3d; border-color: #112030; }

QWidget#showChip {
    background: #111f30;
    border: 1px solid #182637;
    /* Exactly half of chips.CHIP_HEIGHT, so the ends are true semicircles. */
    border-radius: 12px;
}
QWidget#showChip[hover="true"]    { border-color: #1e2c3c; }
QWidget#showChip[selected="true"] { background: #2f4a68; border-color: #4a90d9; }
QWidget#showChip:focus            { border-color: #4a90d9; }

QLabel#showChipLabel { background: transparent; color: #b9bec7; font-size: 12px; }
QLabel#showChipLabel[hover="true"]    { color: #e4e8ee; }
QLabel#showChipLabel[selected="true"] { color: #ffffff; font-weight: 600; }

QToolButton#showChipRemove {
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #8ba3bd;
    font-size: 11px;
    padding: 0;
}
QToolButton#showChipRemove[hover="true"]    { color: #b0b7c1; }
QToolButton#showChipRemove[selected="true"] { color: #c9dcf2; }
QToolButton#showChipRemove:hover  { background: #a8564f; color: #ffffff; }
QToolButton#showChipRemove:pressed { background: #8e4640; }

QToolButton#compactButton {
    background: #111f30;
    border: 1px solid #182637;
    border-radius: 5px;
}
QToolButton#compactButton:hover   { background: #152334; border-color: #1e2c3c; }
QToolButton#compactButton:pressed { background: #0f1d2e; }

QToolButton#moreButton {
    background: #0e1c2b;
    border: 1px solid #152232;
    border-radius: 15px;
    color: #a6bad0;
    font-size: 15px;
    font-weight: 700;
    padding-bottom: 3px;
}
QToolButton#moreButton:hover   { background: #111f30; border-color: #243040; color: #ffffff; }
QToolButton#moreButton:pressed { background: #0a1521; }

QPushButton#dangerButton { color: #d99e9e; }
QPushButton#dangerButton:hover:!disabled {
    background: #4a2c2c; border-color: #a8564f; color: #ffffff;
}

QListWidget#favoritesList::item { padding: 8px 10px; }

QWidget#collapsibleHeader {
    background: #0b1724;
    border: 1px solid #112030;
    border-radius: 5px;
}
QWidget#collapsibleHeader:hover { border-color: #192739; }

QToolButton#collapsibleToggle {
    background: transparent;
    border: none;
    padding: 2px 4px;
    color: #b9bec7;
    font-size: 12px;
    font-weight: 600;
}
QToolButton#collapsibleToggle:hover   { color: #ffffff; }
QToolButton#collapsibleToggle:checked { color: #eef1f5; }

QCheckBox#collapsibleCheck { background: transparent; spacing: 0; }
QCheckBox#collapsibleCheck::indicator { width: 14px; height: 14px; }

QLabel#collapsibleBadge { color: #8ba3bd; font-size: 11px; background: transparent; }
QLabel#collapsibleNote {
    color: #8ba3bd;
    font-size: 11px;
    background: transparent;
    padding: 1px 6px;
    border-radius: 3px;
}
QLabel#collapsibleNote[level="warn"]  { color: #e0a23c; background: rgba(224, 162, 60, 0.15); }
QLabel#collapsibleNote[level="error"] { color: #e06c75; background: rgba(224, 108, 117, 0.15); }

/* Always red: it only ever says how many of your packages lost. */
QLabel#collapsibleAlert {
    color: #e06c75;
    background: rgba(224, 108, 117, 0.15);
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 3px;
}

QWidget#collapsibleContent { background: transparent; }

QGroupBox {
    border: 1px solid #112030;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #9db3ca;
    font-size: 11px;
    font-weight: 600;
}

QSplitter::handle { background: #112030; }
QSplitter::handle:horizontal { width: 3px; }

QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #182637; border-radius: 5px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: #1e2c3c; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QStatusBar { background: #09131e; color: #90a8c2; }
QStatusBar::item { border: none; }

QMenuBar { background: #09131e; }
QMenuBar::item { padding: 5px 10px; background: transparent; }
QMenuBar::item:selected { background: #111f30; }

QMenu {
    background: #0e1c2b;
    border: 1px solid #182637;
    padding: 5px 0;
}
QMenu::item { padding: 6px 26px; }
QMenu::item:selected { background: #12263e; }
QMenu::item:disabled { color: #2a3644; }
QMenu::separator { height: 1px; background: #152232; margin: 5px 8px; }

/* Saved-setup rows are QWidgetActions, so they need their own hover state --
   QMenu::item:selected does not reach inside a widget action. */
QWidget#configItem { background: transparent; }
QWidget#configItem[hover="true"] { background: #12263e; }

QLabel#configItemLabel { background: transparent; color: #d7dae0; }
QLabel#configItemLabel[hover="true"] { color: #ffffff; }
QLabel#configItemDetail { background: transparent; color: #8ba3bd; font-size: 11px; }
QLabel#configItemDetail[hover="true"] { color: #b9c4d2; }

QToolButton#configRemoveButton {
    background: transparent;
    border: none;
    border-radius: 9px;
    color: #8ba3bd;
    font-size: 12px;
    padding: 0;
}
QToolButton#configRemoveButton[hover="true"] { color: #c3cad4; }
QToolButton#configRemoveButton:hover {
    background: #a8564f;
    color: #ffffff;
}
QToolButton#configRemoveButton:pressed { background: #8e4640; }

/* The update bar: three pixels along the bottom edge, no text, no border.
   It is there to say "still going", and nothing else. */
QProgressBar#microProgress {
    background: transparent;
    border: none;
}
QProgressBar#microProgress::chunk { background: #e0a23c; }
"""
