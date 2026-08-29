"""Dark stylesheet, sized for a facility workstation."""

STYLESHEET = """
QWidget {
    background: #1b1d21;
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
    color: #7c828d;
    font-size: 12px;
}
QLabel#tagline {
    color: #7c828d;
    font-size: 12px;
    font-style: italic;
}
QLabel#sectionLabel {
    color: #8b929e;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}
QLabel#statusLabel {
    color: #7c828d;
    font-size: 12px;
    padding: 2px 0;
}
QLabel#statusLabel[level="error"] { color: #e06c75; }
QLabel#statusLabel[level="ok"]    { color: #7fbf7f; }

QFrame#showField {
    background: #23262b;
    border: 1px solid #33373e;
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
    background: #23262b;
    border: 1px solid #33373e;
    border-radius: 5px;
    padding: 5px 9px;
}
QLineEdit#filterField:focus { border-color: #4a90d9; }

QListView {
    background: #23262b;
    border: 1px solid #33373e;
    border-radius: 6px;
    outline: none;
    padding: 4px;
}
QListView::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListView::item:selected { background: #34455c; color: #ffffff; }
QListView::item:hover:!selected { background: #2b2f36; }

QComboBox {
    background: #23262b;
    border: 1px solid #33373e;
    border-radius: 5px;
    padding: 6px 10px;
    min-width: 160px;
}
QComboBox:focus, QComboBox:hover { border-color: #4a90d9; }
/* Left ::drop-down unstyled on purpose: styling it suppresses Fusion's
   built-in arrow, and there is no image to replace it with. */
QComboBox QAbstractItemView {
    background: #23262b;
    border: 1px solid #3a3f47;
    selection-background-color: #34455c;
    outline: none;
}

QPushButton {
    background: #2b2f36;
    border: 1px solid #3a3f47;
    border-radius: 5px;
    padding: 8px 16px;
    color: #d7dae0;
}
QPushButton:hover:!disabled  { background: #333841; border-color: #4a5058; }
QPushButton:pressed:!disabled { background: #262a31; }
QPushButton:disabled { color: #575c65; border-color: #2c3037; }

QPushButton#launchButton {
    background: #3f6fa8;
    border: 1px solid #4a90d9;
    color: #ffffff;
    font-weight: 600;
    padding: 9px 22px;
}
QPushButton#launchButton:hover:!disabled  { background: #4a80c0; }
QPushButton#launchButton:pressed:!disabled { background: #365e8f; }
QPushButton#launchButton:disabled { background: #2b2f36; color: #575c65; }
QPushButton#launchButton[compact="true"] { padding: 8px 10px; }

QToolButton#dccButton {
    background: #23262b;
    border: 1px solid #33373e;
    border-radius: 8px;
    /* Extra bottom padding reserves the strip DccTile paints its variant line
       into; the icon and name sit above it. */
    padding: 12px 10px 26px 10px;
    color: #b9bec7;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#dccButton:hover   { background: #2b2f36; border-color: #4a5058; }
QToolButton#dccButton:checked { background: #2c333d; color: #ffffff; }

/* Terminal and Favourites: same shape as a DCC tile, but dashed so it reads as
   an action rather than one of the show's software choices. */
QToolButton#actionTile {
    background: transparent;
    border: 1px dashed #3a3f47;
    border-radius: 8px;
    /* Matches the DCC tile, subtitle strip included, so the row lines up even
       though this tile has no variant line of its own. */
    padding: 12px 10px 26px 10px;
    color: #949aa4;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#actionTile:hover:!disabled {
    background: #23262b;
    border-color: #5a616b;
    color: #ffffff;
}
QToolButton#actionTile:pressed:!disabled { background: #1e2126; }
QToolButton#actionTile:disabled { color: #4d525a; border-color: #2c3037; }

QWidget#showChip {
    background: #2b2f36;
    border: 1px solid #3a3f47;
    /* Exactly half of chips.CHIP_HEIGHT, so the ends are true semicircles. */
    border-radius: 12px;
}
QWidget#showChip[hover="true"]    { border-color: #4a5058; }
QWidget#showChip[selected="true"] { background: #2f4a68; border-color: #4a90d9; }
QWidget#showChip:focus            { border-color: #4a90d9; }

QLabel#showChipLabel { background: transparent; color: #b9bec7; font-size: 12px; }
QLabel#showChipLabel[hover="true"]    { color: #e4e8ee; }
QLabel#showChipLabel[selected="true"] { color: #ffffff; font-weight: 600; }

QToolButton#showChipRemove {
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #767c86;
    font-size: 11px;
    padding: 0;
}
QToolButton#showChipRemove[hover="true"]    { color: #b0b7c1; }
QToolButton#showChipRemove[selected="true"] { color: #c9dcf2; }
QToolButton#showChipRemove:hover  { background: #a8564f; color: #ffffff; }
QToolButton#showChipRemove:pressed { background: #8e4640; }

QToolButton#compactButton {
    background: #2b2f36;
    border: 1px solid #3a3f47;
    border-radius: 5px;
}
QToolButton#compactButton:hover   { background: #333841; border-color: #4a5058; }
QToolButton#compactButton:pressed { background: #262a31; }

QToolButton#moreButton {
    background: #23262b;
    border: 1px solid #33373e;
    border-radius: 15px;
    color: #949aa4;
    font-size: 15px;
    font-weight: 700;
    padding-bottom: 3px;
}
QToolButton#moreButton:hover   { background: #2b2f36; border-color: #5a616b; color: #ffffff; }
QToolButton#moreButton:pressed { background: #1e2126; }

QPushButton#dangerButton { color: #d99e9e; }
QPushButton#dangerButton:hover:!disabled {
    background: #4a2c2c; border-color: #a8564f; color: #ffffff;
}

QListWidget#favoritesList::item { padding: 8px 10px; }

QWidget#collapsibleHeader {
    background: #202328;
    border: 1px solid #2c3037;
    border-radius: 5px;
}
QWidget#collapsibleHeader:hover { border-color: #3d434c; }

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

QLabel#collapsibleBadge { color: #767c86; font-size: 11px; background: transparent; }
QLabel#collapsibleNote {
    color: #767c86;
    font-size: 11px;
    background: transparent;
    padding: 1px 6px;
    border-radius: 3px;
}
QLabel#collapsibleNote[level="warn"]  { color: #e0a23c; background: rgba(224, 162, 60, 0.15); }
QLabel#collapsibleNote[level="error"] { color: #e06c75; background: rgba(224, 108, 117, 0.15); }

QWidget#collapsibleContent { background: transparent; }

QGroupBox {
    border: 1px solid #2c3037;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #8b929e;
    font-size: 11px;
    font-weight: 600;
}

QSplitter::handle { background: #2c3037; }
QSplitter::handle:horizontal { width: 3px; }

QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #3a3f47; border-radius: 5px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: #4a5058; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QStatusBar { background: #16181b; color: #7c828d; }
QStatusBar::item { border: none; }

QMenuBar { background: #16181b; }
QMenuBar::item { padding: 5px 10px; background: transparent; }
QMenuBar::item:selected { background: #2b2f36; }

QMenu {
    background: #23262b;
    border: 1px solid #3a3f47;
    padding: 5px 0;
}
QMenu::item { padding: 6px 26px; }
QMenu::item:selected { background: #34455c; }
QMenu::item:disabled { color: #6b717b; }
QMenu::separator { height: 1px; background: #33373e; margin: 5px 8px; }

/* Saved-setup rows are QWidgetActions, so they need their own hover state --
   QMenu::item:selected does not reach inside a widget action. */
QWidget#configItem { background: transparent; }
QWidget#configItem[hover="true"] { background: #34455c; }

QLabel#configItemLabel { background: transparent; color: #d7dae0; }
QLabel#configItemLabel[hover="true"] { color: #ffffff; }
QLabel#configItemDetail { background: transparent; color: #767c86; font-size: 11px; }
QLabel#configItemDetail[hover="true"] { color: #b9c4d2; }

QToolButton#configRemoveButton {
    background: transparent;
    border: none;
    border-radius: 9px;
    color: #767c86;
    font-size: 12px;
    padding: 0;
}
QToolButton#configRemoveButton[hover="true"] { color: #c3cad4; }
QToolButton#configRemoveButton:hover {
    background: #a8564f;
    color: #ffffff;
}
QToolButton#configRemoveButton:pressed { background: #8e4640; }
"""
