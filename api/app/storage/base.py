from abc import ABC, abstractmethod
from typing import BinaryIO


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, content: bytes | BinaryIO) -> str:
        """Persist content and return the stored object key."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Read the object bytes for a key."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the object if it exists."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether the object exists."""
