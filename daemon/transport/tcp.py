"""
TCP transport for testing via ADB forward.

Setup on laptop before running the daemon:
    adb forward tcp:7654 tcp:7654

The Android app listens on port 7654 in debug mode.
"""
import socket
from typing import Optional
from .base import Transport


class TcpTransport(Transport):
    def __init__(self, host: str = "127.0.0.1", port: int = 7654,
                 read_timeout: float = 1.0) -> None:
        self.host         = host
        self.port         = port
        self.read_timeout = read_timeout
        self._sock: Optional[socket.socket] = None
        self._connected   = False

    def connect(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.read_timeout)
            s.connect((self.host, self.port))
            self._sock      = s
            self._connected = True
            return True
        except Exception as exc:
            self._connected = False
            return False

    def read(self, size: int) -> Optional[bytes]:
        if not self._sock:
            return None
        try:
            data = self._sock.recv(size)
            if not data:
                self._connected = False
                return None
            return data
        except socket.timeout:
            return b""
        except Exception:
            self._connected = False
            return None

    def write(self, data: bytes) -> bool:
        if not self._sock:
            return False
        try:
            self._sock.sendall(data)
            return True
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def name(self) -> str:
        return f"TCP {self.host}:{self.port}"
