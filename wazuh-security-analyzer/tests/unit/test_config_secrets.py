import yaml

from app.core.config import AppConfig, ConfigManager, deep_merge, strip_secret_like_keys
from app.core.secrets import MemorySecretStore, SecretStore


def test_default_config_file_is_valid():
    from app.core import paths
    data = yaml.safe_load(paths.default_config_path().read_text())
    cfg = AppConfig.model_validate(data)
    assert cfg.network.mode == "offline" and cfg.ai.provider == "none"
    assert cfg.risk_thresholds.critical == 80


def test_user_overrides_and_secret_keys_ignored(tmp_path):
    default = tmp_path / "default.yaml"
    default.write_text(yaml.safe_dump({"network": {"mode": "offline", "timeout_seconds": 15}}))
    user = tmp_path / "user.yaml"
    user.write_text(yaml.safe_dump({"network": {"mode": "online"}, "ai": {"api_key": "LEAK", "max_tokens": 999}}))
    cm = ConfigManager(user, default)
    assert cm.config.network.mode == "online" and cm.config.network.timeout_seconds == 15
    assert cm.config.ai.max_tokens == 999
    cm.save()
    assert "LEAK" not in user.read_text()


def test_invalid_user_config_falls_back(tmp_path):
    user = tmp_path / "user.yaml"
    user.write_text("risk_thresholds: {critical: 10, high: 50}\n")
    cm = ConfigManager(user, tmp_path / "missing.yaml")
    assert cm.config.risk_thresholds.critical == 80


def test_corrupt_yaml_ignored(tmp_path):
    user = tmp_path / "user.yaml"
    user.write_text("::: not yaml [")
    assert ConfigManager(user, tmp_path / "missing.yaml").config.network.mode == "offline"


def test_helpers():
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}}) == {"a": {"b": 3, "c": 2}}
    assert strip_secret_like_keys({"password": 1, "x": {"token": 2, "max_tokens": 3}}) == {"x": {"max_tokens": 3}}


def test_memory_secret_store(monkeypatch):
    s = MemorySecretStore()
    assert s.get("virustotal_api_key") is None
    assert s.set("virustotal_api_key", "abc") is False  # not persisted
    assert s.get("virustotal_api_key") == "abc" and s.has("virustotal_api_key")
    s.delete("virustotal_api_key")
    monkeypatch.setenv("WSA_OTX_API_KEY", "from-env")
    assert s.get("otx_api_key") == "from-env"


def test_secret_store_without_keyring_backend():
    s = SecretStore(use_keyring=False)
    assert not s.persistent
    s.set("openai_api_key", "k")
    assert s.get("openai_api_key") == "k"
