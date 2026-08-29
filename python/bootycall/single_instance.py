"""
One BootyCall per user.

A second launch should not open a second window -- it should bring the running
one forward, which is what people mean when they click the icon again.

Implemented with QLocalServer/QLocalSocket rather than a lock file: the socket
tells us not just *that* another instance exists but lets us talk to it, and the
OS cleans it up when the process dies. A lock file left behind by a crash needs
its own staleness dance; a stale socket is detected by failing to connect to it
and removed.

The key includes the user name so two people on the same host do not block each
other.
"""

from __future__ import annotations

import getpass
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

#: Milliseconds to wait when probing for a running instance. Local sockets
#: answer immediately or not at all.
_CONNECT_TIMEOUT = 300


def default_key() -> str:
    """Socket name, scoped to the user."""
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - getuser() raises bare KeyError on some hosts
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    return "bootycall-%s" % user


class SingleInstance(QObject):
    """Holds the lock, or knows who does.

    ``is_primary()`` is True in the first process. In any later one it is
    False, and :meth:`notify_primary` asks the running instance to show itself.
    """

    activated = Signal()

    def __init__(self, key: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.key = key or default_key()
        self._server: QLocalServer | None = None
        self._primary = False
        self._claim()

    # -- claiming ----------------------------------------------------------

    def _claim(self) -> None:
        if self._probe_existing():
            return

        server = QLocalServer(self)
        # A crash leaves the socket file behind; nothing answered the probe
        # above, so it is stale and safe to clear.
        QLocalServer.removeServer(self.key)
        if not server.listen(self.key):
            # Could not listen and nothing is answering: fall back to running
            # anyway rather than refusing to start at all.
            server.deleteLater()
            return

        server.newConnection.connect(self._on_new_connection)
        self._server = server
        self._primary = True

    def _probe_existing(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        connected = socket.waitForConnected(_CONNECT_TIMEOUT)
        socket.abort()
        return connected

    # -- state -------------------------------------------------------------

    def is_primary(self) -> bool:
        return self._primary

    #: Payload that means "show yourself". A bare connection is how a starting
    #: instance *probes* for a running one, and must not count as a request --
    #: otherwise merely checking whether BootyCall is running would raise it.
    SHOW = b"show"

    def notify_primary(self) -> bool:
        """Ask the running instance to come forward. True if it heard us."""
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(_CONNECT_TIMEOUT):
            return False
        socket.write(self.SHOW)
        socket.flush()
        socket.waitForBytesWritten(_CONNECT_TIMEOUT)
        socket.disconnectFromServer()
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            QLocalServer.removeServer(self.key)
            self._server = None
        self._primary = False

    # -- incoming ----------------------------------------------------------

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        connection = self._server.nextPendingConnection()
        if connection is None:
            return

        def _read() -> None:
            if self.SHOW in bytes(connection.readAll()):
                self.activated.emit()

        connection.readyRead.connect(_read)
        connection.disconnected.connect(connection.deleteLater)
