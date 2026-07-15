from pathlib import Path
from typing import BinaryIO

from app.storage.base import Storage


class LocalFolderStorage(Storage):
    def __init__(self, root: Path | str = Path("var/storage")) -> None:
        self.root = Path(root)

    def save(self, key: str, content: bytes | BinaryIO) -> str:
        target = self._path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            with target.open("wb") as file:
                while chunk := content.read(1024 * 1024):
                    file.write(chunk)

        return key

    def read(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def _path_for(self, key: str) -> Path:
        if not key or Path(key).is_absolute() or ".." in Path(key).parts:
            raise ValueError("storage key must be a relative path within storage root")

        return self.root / key
