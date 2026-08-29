"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .single_instance import SingleInstance
from .ui.main_window import MainWindow, apply_style


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, False)
    app = QApplication(argv)
    app.setApplicationName("BootyCall")
    app.setOrganizationName("ILP")
    # Fusion so the stylesheet lands the same way on every workstation,
    # regardless of the desktop's native Qt theme.
    app.setStyle("Fusion")
    apply_style(app)

    # One per user. A second launch raises the first rather than opening a
    # rival window with its own idea of the saved state.
    instance = SingleInstance()
    if not instance.is_primary():
        instance.notify_primary()
        print("BootyCall is already running; raised the existing window.")
        return 0

    window = MainWindow()
    instance.activated.connect(window.raise_to_front)
    window.show()
    try:
        return app.exec()
    finally:
        instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
