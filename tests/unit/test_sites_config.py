"""Synthetic tests for the local multi-site YAML configuration contract."""

from pathlib import Path

import pytest

from adams_tutoria.config import SiteConfigError, load_sites_config


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_multiple_sites_and_defaults(tmp_path: Path) -> None:
    config = load_sites_config(
        _write(
            tmp_path,
            """
schema_version: 1
sites:
  - id: alpha
    provider: ADAMS
    login_url: https://example.invalid/login
    target_url: https://example.invalid/target
    username: synthetic-user
    password: synthetic-password
  - id: beta
    provider: BETA
    login_url: https://example.invalid/b
    target_url: https://example.invalid/t
    username: another-user
    password: another-password
    timezone: Europe/Madrid
""",
        )
    )
    assert tuple(site.id for site in config.sites) == ("alpha", "beta")
    assert config.sites[0].interval_seconds == 300
    assert config.sites[0].timezone == "UTC"


@pytest.mark.parametrize(
    "fragment",
    [
        "schema_version: true\nsites: []",
        "schema_version: 2\nsites: []",
        """schema_version: 1
sites:
  - id: same
    provider: A
    login_url: https://example.invalid/a
    target_url: https://example.invalid/a
    username: u
    password: p
  - id: same
    provider: B
    login_url: https://example.invalid/b
    target_url: https://example.invalid/b
    username: u
    password: p""",
        """schema_version: 1
sites:
  - id: x
    provider: A
    login_url: https://user:secret@example.invalid/a
    target_url: https://example.invalid/a
    username: u
    password: secret""",
    ],
)
def test_rejects_invalid_contract(tmp_path: Path, fragment: str) -> None:
    with pytest.raises(SiteConfigError) as error:
        load_sites_config(_write(tmp_path, fragment))
    assert "synthetic-password" not in str(error.value)


def test_unknown_fields_and_unsafe_paths_are_rejected_without_password(tmp_path: Path) -> None:
    text = """
schema_version: 1
sites:
  - id: alpha
    provider: ADAMS
    login_url: https://example.invalid/login
    target_url: https://example.invalid/target
    username: synthetic-user
    password: do-not-leak-this
    unexpected: value
    log_file: ../secret.log
"""
    with pytest.raises(SiteConfigError) as error:
        load_sites_config(_write(tmp_path, text))
    assert "do-not-leak-this" not in str(error.value)


@pytest.mark.parametrize(
    "field, value",
    [
        ("login_url", "https://[2001:db8::1"),
        ("target_url", "https://[2001:db8:::1]/target"),
        ("login_url", "https://example.invalid:bad-port/login"),
    ],
)
def test_malformed_urls_are_site_config_errors_without_sensitive_values(
    tmp_path: Path, field: str, value: str
) -> None:
    text = f"""
schema_version: 1
sites:
  - id: alpha
    provider: ADAMS
    login_url: https://example.invalid/login
    target_url: https://example.invalid/target
    username: synthetic-user
    password: synthetic-url-password
    {field}: {value}
"""
    with pytest.raises(SiteConfigError) as error:
        load_sites_config(_write(tmp_path, text))
    assert "synthetic-url-password" not in str(error.value)


@pytest.mark.parametrize("field", ["start_date", "end_date"])
def test_invalid_yaml_dates_are_site_config_errors_without_sensitive_values(
    tmp_path: Path, field: str
) -> None:
    text = f"""
schema_version: 1
sites:
  - id: alpha
    provider: ADAMS
    login_url: https://example.invalid/login
    target_url: https://example.invalid/target
    username: synthetic-user
    password: synthetic-date-password
    {field}: 2026-99-99
"""
    with pytest.raises(SiteConfigError) as error:
        load_sites_config(_write(tmp_path, text))
    assert "synthetic-date-password" not in str(error.value)


@pytest.mark.parametrize(
    "date_values",
    [
        'start_date: "2026-01-01"\n    end_date: "2026-12-31"',
        "start_date: 2026-01-01\n    end_date: 2026-12-31",
    ],
)
def test_accepts_quoted_and_unquoted_iso_dates(tmp_path: Path, date_values: str) -> None:
    config = load_sites_config(
        _write(
            tmp_path,
            f"""
schema_version: 1
sites:
  - id: alpha
    provider: ADAMS
    login_url: https://example.invalid/login
    target_url: https://example.invalid/target
    username: synthetic-user
    password: synthetic-date-password
    {date_values}
""",
        )
    )
    assert config.sites[0].start_date.isoformat() == "2026-01-01"
    assert config.sites[0].end_date.isoformat() == "2026-12-31"
