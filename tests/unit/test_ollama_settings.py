from pathlib import Path

from adams_tutoria.generation import (
    GenerationConfigurationError,
    HttpResponse,
    InvalidEndpointError,
)
from adams_tutoria.ollama import OllamaDiscovery, OllamaSettings, OllamaSettingsRepository


class Transport:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        return HttpResponse(self.status, self.body)


def test_settings_defaults_and_sqlite_round_trip(tmp_path):
    repository = OllamaSettingsRepository(tmp_path / "settings.sqlite3")
    assert repository.get() == OllamaSettings()
    saved = OllamaSettings("synthetic-model", "http://127.0.0.1:11434", 0.7, 100, 10)
    repository.save(saved)
    assert repository.get() == saved


def test_settings_reject_remote_and_unknown_values():
    import pytest

    with pytest.raises(InvalidEndpointError):
        OllamaSettings(endpoint="https://remote.example")
    with pytest.raises(GenerationConfigurationError):
        OllamaSettings.from_mapping({"future": True})


def test_discovery_normalizes_minimal_model_metadata():
    discovery = OllamaDiscovery(
        OllamaSettings(),
        Transport(b'{"models":[{"name":"synthetic-model","size":123,"digest":"abc"}]}'),
    )
    assert discovery.list_models()[0].name == "synthetic-model"


def test_discovery_supports_empty_local_model_list_without_fallback():
    discovery = OllamaDiscovery(OllamaSettings(), Transport(b'{"models":[]}'))
    assert discovery.list_models() == ()


def test_selected_missing_model_is_detectable_without_silent_fallback(tmp_path: Path):
    repository = OllamaSettingsRepository(tmp_path / "restart.sqlite3")
    repository.save(OllamaSettings("persisted-model"))
    restarted = OllamaSettingsRepository(tmp_path / "restart.sqlite3")
    available = tuple(
        model.name
        for model in OllamaDiscovery(
            restarted.get(), Transport(b'{"models":[{"name":"other-model"}]}')
        ).list_models()
    )
    assert restarted.get().model == "persisted-model"
    assert restarted.get().model not in available
