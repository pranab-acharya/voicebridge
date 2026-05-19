from abc import ABC, abstractmethod
from typing import Optional


class Transport(ABC):
    """Abstract bidirectional byte stream."""

    @abstractmethod
    def connect(self) -> bool:
        """Attempt connection; return True on success."""

    @abstractmethod
    def read(self, size: int) -> Optional[bytes]:
        """
        Read up to `size` bytes.
        Returns b'' on timeout, None on disconnect/error.
        """

    @abstractmethod
    def write(self, data: bytes) -> bool:
        """Write data; return False on error."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection cleanly."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @property
    def name(self) -> str:
        return type(self).__name__
