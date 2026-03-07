"""Unit tests for the persistence layer."""

import json
from unittest.mock import patch

from kage.core.models import Session
from kage.persistence.config import KageConfig
from kage.persistence.session import SessionStorage


class TestSessionStorageSave:
    """SessionStorage.save creates files atomically."""

    async def test_save_creates_file(self, tmp_path):
        """Saving a session creates the JSON file."""
        storage = SessionStorage(storage_dir=tmp_path)
        session = Session(name="test-session")
        path = await storage.save(session)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "test-session"

    async def test_save_updates_index(self, tmp_path):
        """Saving a session updates the index file."""
        storage = SessionStorage(storage_dir=tmp_path)
        session = Session(name="indexed")
        await storage.save(session)
        index_path = tmp_path / "index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text())
        assert session.id in index["sessions"]

    async def test_save_overwrite(self, tmp_path):
        """Saving the same session twice overwrites cleanly."""
        storage = SessionStorage(storage_dir=tmp_path)
        session = Session(name="v1")
        await storage.save(session)
        session.name = "v2"
        await storage.save(session)
        path = storage._get_session_path(session.id)
        data = json.loads(path.read_text())
        assert data["name"] == "v2"


class TestSessionStorageLoad:
    """SessionStorage.load reads sessions and handles errors."""

    async def test_load_existing(self, tmp_path):
        """Loading a saved session returns the same data."""
        storage = SessionStorage(storage_dir=tmp_path)
        session = Session(name="roundtrip")
        await storage.save(session)
        loaded = await storage.load(session.id)
        assert loaded is not None
        assert loaded.name == "roundtrip"
        assert loaded.id == session.id

    async def test_load_missing_returns_none(self, tmp_path):
        """Loading a non-existent session returns None."""
        storage = SessionStorage(storage_dir=tmp_path)
        assert await storage.load("does-not-exist") is None

    async def test_load_corrupt_json_returns_none(self, tmp_path):
        """Corrupt JSON file returns None instead of crashing."""
        storage = SessionStorage(storage_dir=tmp_path)
        bad_path = tmp_path / "corrupt.json"
        bad_path.write_text("{not valid json!!!")
        # Manually write a file with a known session id pattern
        session_path = tmp_path / "bad-session.json"
        session_path.write_text("NOT JSON AT ALL")
        result = await storage.load("bad-session")
        assert result is None


class TestSessionStorageDelete:
    """SessionStorage.delete removes sessions."""

    async def test_delete_existing(self, tmp_path):
        """Deleting a session removes its file."""
        storage = SessionStorage(storage_dir=tmp_path)
        session = Session(name="to-delete")
        await storage.save(session)
        assert await storage.delete(session.id) is True
        assert not storage._get_session_path(session.id).exists()

    async def test_delete_nonexistent(self, tmp_path):
        """Deleting a nonexistent session returns False."""
        storage = SessionStorage(storage_dir=tmp_path)
        assert await storage.delete("nope") is False


class TestKageConfigLoad:
    """KageConfig.load handles corrupt YAML gracefully."""

    def test_load_defaults(self, tmp_path):
        """Loading with no file returns defaults."""
        config_path = tmp_path / "config.yaml"
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = KageConfig.load()
        assert cfg.llm.provider == "ollama"
        assert cfg.security.safe_mode is True

    def test_load_corrupt_yaml(self, tmp_path):
        """Corrupt YAML returns defaults instead of crashing."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(": : : [invalid yaml\n\t\x00")
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = KageConfig.load()
        assert cfg.llm.provider == "ollama"

    def test_load_valid_yaml(self, tmp_path):
        """Valid YAML is loaded correctly."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("llm:\n  provider: openai\n  model: gpt-4\n")
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = KageConfig.load()
        assert cfg.llm.provider == "openai"
        assert cfg.llm.model == "gpt-4"


class TestKageConfigAsyncLoadSave:
    """KageConfig async load/save."""

    async def test_aload(self, tmp_path):
        """aload returns a KageConfig instance."""
        config_path = tmp_path / "config.yaml"
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = await KageConfig.aload()
        assert isinstance(cfg, KageConfig)

    async def test_asave(self, tmp_path):
        """asave persists config to disk."""
        config_path = tmp_path / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = KageConfig()
            await cfg.asave()
        assert config_path.exists()
