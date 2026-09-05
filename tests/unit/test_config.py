"""Tests for the standard-library configuration layer."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from adams_tutoria.config import AppConfig, default_config, load_config


def test_default_config_uses_expected_data_paths(tmp_path: Path) -> None:
    config = default_config(base_dir=tmp_path)

    assert config == AppConfig(
        base_dir=tmp_path,
        data_root=tmp_path / "data",
        private_data_dir=tmp_path / "data" / "private",
        local_data_dir=tmp_path / "data" / "local",
    )
    assert not tmp_path.joinpath("data").exists()


def test_config_is_frozen(tmp_path: Path) -> None:
    config = default_config(base_dir=tmp_path)

    with pytest.raises(FrozenInstanceError):
        config.base_dir = tmp_path / "other"  # type: ignore[misc]


def test_empty_environment_applies_no_overrides(tmp_path: Path) -> None:
    assert load_config(environ={}, base_dir=tmp_path) == default_config(base_dir=tmp_path)


def test_environment_overrides_and_data_root_precedence(tmp_path: Path) -> None:
    config = load_config(
        environ={
            "ADAMS_TUTORIA_DATA_ROOT": "workspace",
            "ADAMS_TUTORIA_PRIVATE_DATA_DIR": "secure",
        },
        base_dir=tmp_path,
    )

    assert config.data_root == tmp_path / "workspace"
    assert config.private_data_dir == tmp_path / "secure"
    assert config.local_data_dir == tmp_path / "workspace" / "local"


def test_environment_is_read_at_call_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADAMS_TUTORIA_DATA_ROOT", "first")
    first = load_config(base_dir=tmp_path)
    monkeypatch.setenv("ADAMS_TUTORIA_DATA_ROOT", "second")
    second = load_config(base_dir=tmp_path)

    assert first.data_root == tmp_path / "first"
    assert second.data_root == tmp_path / "second"


def test_relative_paths_do_not_resolve_or_touch_the_filesystem(tmp_path: Path) -> None:
    config = load_config(
        environ={"ADAMS_TUTORIA_DATA_ROOT": "relative/../data"},
        base_dir=tmp_path,
    )

    assert config.data_root == tmp_path / "relative" / ".." / "data"
