from __future__ import annotations

from pathlib import Path

import pytest

from adams_tutoria import adams_login_cli
from adams_tutoria.adams_login import AdamsLoginSettings, LoginResult


def test_cli_loads_dotenv_only_when_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ADAMS_USERNAME=dotenv-user\nADAMS_PASSWORD=dotenv-password\n"
        "ADAMS_LOGIN_URL=https://example.invalid/login\n",
        encoding="utf-8",
    )
    captured: list[AdamsLoginSettings] = []

    def fake_login(settings: AdamsLoginSettings) -> LoginResult:
        captured.append(settings)
        return LoginResult("success", "secret detail must not be printed")

    monkeypatch.setattr(adams_login_cli, "login_with_playwright", fake_login)
    assert adams_login_cli.main() == 0
    assert captured[0].username == "dotenv-user"
    assert capsys.readouterr().out == "success\n"


def test_environment_precedes_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ADAMS_USERNAME=dotenv-user\nADAMS_PASSWORD=dotenv-password\n"
        "ADAMS_LOGIN_URL=https://dotenv.invalid/login\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ADAMS_USERNAME", "environment-user")
    monkeypatch.setenv("ADAMS_PASSWORD", "environment-password")
    monkeypatch.setenv("ADAMS_LOGIN_URL", "https://environment.invalid/login")
    captured: list[AdamsLoginSettings] = []
    monkeypatch.setattr(
        adams_login_cli,
        "login_with_playwright",
        lambda settings: captured.append(settings) or LoginResult("failed", "secret"),
    )

    adams_login_cli.main()
    assert captured[0].username == "environment-user"
    assert captured[0].login_url == "https://environment.invalid/login"


@pytest.mark.parametrize("status", ("success", "failed", "blocked"))
def test_cli_prints_only_allowed_status(
    monkeypatch: pytest.MonkeyPatch, capsys, status: str
) -> None:
    monkeypatch.setattr(
        adams_login_cli,
        "login_with_playwright",
        lambda settings: LoginResult(status, "password=synthetic-secret"),
    )
    monkeypatch.setenv("ADAMS_USERNAME", "synthetic-user")
    monkeypatch.setenv("ADAMS_PASSWORD", "synthetic-password")
    monkeypatch.setenv("ADAMS_LOGIN_URL", "https://example.invalid/login")

    assert adams_login_cli.main() == 0
    assert capsys.readouterr().out == f"{status}\n"


def test_cli_converts_configuration_and_browser_errors_to_failed(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(adams_login_cli, "login_with_playwright", lambda settings: 1 / 0)
    assert adams_login_cli.main() == 0
    assert capsys.readouterr().out == "failed\n"
