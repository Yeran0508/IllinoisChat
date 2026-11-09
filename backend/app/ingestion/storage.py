import os
import uuid
from contextlib import suppress
from pathlib import Path


class LocalDocumentStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put(self, version_id: uuid.UUID, source_name: str, content: bytes) -> str:
        safe_name = Path(source_name).name
        if not safe_name or safe_name in {".", ".."} or "\x00" in safe_name:
            raise ValueError("Invalid source filename")

        key = f"{version_id}/{safe_name}"
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.uploading")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return key

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def delete(self, key: str) -> None:
        target = self._resolve(key)
        target.unlink(missing_ok=True)
        with suppress(OSError):
            target.parent.rmdir()

    def _resolve(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Storage key escapes the configured root")
        return target
