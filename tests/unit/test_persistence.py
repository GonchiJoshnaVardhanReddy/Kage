"""Unit tests for the persistence layer."""

import json
from unittest.mock import patch

from kage.core.models import Session
from kage.persistence.config import KageConfig
from kage.persistence.session import SessionStorage


class TestSessionStorageSave:
    async def test_save_creates_file(self, tmp_path):
        storage = SessionStorage(storage_dir=tmp_path)
        session = Session(name="test-session")
        path = await storage.save(session)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "test-session"


class TestKageConfigLoad:
    def test_load_defaults(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = KageConfig.load()
        assert cfg.llm.provider == "ollama"
        assert cfg.security.safe_mode is True

    def test_load_valid_yaml(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("llm:\n  provider: openai\n  model: gpt-4\n")
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = KageConfig.load()
        assert cfg.llm.provider == "openai"
        assert cfg.llm.model == "gpt-4"


class TestChatConfig:
    def test_slash_boost_defaults_present(self):
        cfg = KageConfig()
        boosts = cfg.chat.slash_suggestion_boosts
        assert boosts.pending_commands == 60
        assert boosts.pending_run == 55
        assert boosts.findings == 45

    def test_slash_boost_yaml_override(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "chat:\n"
            "  slash_suggestion_boosts:\n"
            "    pending_run: 120\n"
            "    status: 7\n",
            encoding="utf-8",
        )
        with patch.object(KageConfig, "get_config_path", return_value=config_path):
            cfg = KageConfig.load()
        assert cfg.chat.slash_suggestion_boosts.pending_run == 120
        assert cfg.chat.slash_suggestion_boosts.status == 7
