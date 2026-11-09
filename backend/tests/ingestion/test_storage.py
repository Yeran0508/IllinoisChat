import uuid

import pytest
from app.ingestion.storage import LocalDocumentStorage


def test_local_storage_round_trip_and_delete(tmp_path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    version_id = uuid.uuid4()

    key = storage.put(version_id, "../notes.md", b"course notes")

    assert key == f"{version_id}/notes.md"
    assert storage.read(key) == b"course notes"

    storage.delete(key)
    assert not (tmp_path / key).exists()


def test_local_storage_rejects_escaping_key(tmp_path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(ValueError, match="escapes"):
        storage.read("../../secret.txt")
