"""Small, dependency-free configuration layer for the application.

This module only describes paths.  It deliberately does not create directories,
read files, or initialize a database.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from adams_tutoria.declarative_navigation import (
    ExpectedResult,
    NavigationError,
    NavigationPlan,
    NavigationStep,
)


class SiteConfigError(ValueError):
    """Raised when the local sites YAML does not match the supported schema."""


_ROOT_FIELDS = frozenset({"schema_version", "sites"})
_SITE_FIELDS = frozenset(
    {
        "id",
        "provider",
        "login_url",
        "target_url",
        "navigation",
        "username",
        "password",
        "start_date",
        "end_date",
        "weekdays",
        "start_time",
        "end_time",
        "timezone",
        "interval_seconds",
        "timeout_seconds",
        "max_retries",
        "log_file",
    }
)
_WEEKDAY_NAMES = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
_WEEKDAYS = frozenset(_WEEKDAY_NAMES)


@dataclass(frozen=True)
class SiteConfig:
    """Validated, immutable configuration for one independently monitored site."""

    id: str
    provider: str
    login_url: str
    target_url: str | None
    username: str
    password: str
    start_date: date | None = None
    end_date: date | None = None
    weekdays: tuple[str, ...] = _WEEKDAY_NAMES
    start_time: time = time.min
    end_time: time = time(23, 59, 59)
    timezone: str = "UTC"
    interval_seconds: int = 300
    timeout_seconds: int = 30
    max_retries: int = 2
    log_file: Path = Path("data/local/logs/site.log")
    navigation: NavigationPlan | None = None


@dataclass(frozen=True)
class SitesConfig:
    """Validated application sites configuration. It performs no I/O beyond loading."""

    schema_version: int
    sites: tuple[SiteConfig, ...]


def _error(message: str) -> SiteConfigError:
    # Never include raw YAML or values: passwords must not appear in diagnostics.
    return SiteConfigError(message)


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(f"{context} must be a mapping")
    return value


def _text(data: Mapping[str, Any], name: str, *, required: bool = True) -> str | None:
    value = data.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{name} must be a non-empty string")
    return value.strip()


def _url(data: Mapping[str, Any], name: str) -> str:
    value = _text(data, name)
    assert value is not None
    try:
        parsed = urlparse(value)
        # Accessing hostname and port performs additional validation that
        # urlparse itself intentionally defers (notably malformed IPv6 and
        # invalid ports).
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError, UnicodeError) as exc:
        raise _error(f"{name} must be a valid HTTP(S) URL without credentials") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username
        or parsed.password
        or (port is None and parsed.netloc.endswith(":"))
        or any(character.isspace() for character in value)
    ):
        raise _error(f"{name} must be an HTTP(S) URL without credentials")
    return value


def _date(data: Mapping[str, Any], name: str) -> date | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{name} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise _error(f"{name} must use YYYY-MM-DD") from exc


def _time(data: Mapping[str, Any], name: str, default: time) -> time:
    value = _text(data, name, required=False)
    if value is None:
        return default
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise _error(f"{name} must use HH:MM[:SS]") from exc


def _safe_log_path(value: str, site_id: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise _error("log_file must be a relative path without '..'")
    if any(part in {".", "~"} for part in path.parts):
        raise _error("log_file contains an unsafe path component")
    return path


def _site(value: Any) -> SiteConfig:
    data = _mapping(value, "site")
    unknown = set(data) - _SITE_FIELDS
    if unknown:
        raise _error("site contains unknown fields")
    required = ("id", "provider", "login_url", "username", "password")
    for field in required:
        if field not in data:
            raise _error(f"site is missing required field {field}")
    site_id = _text(data, "id")
    provider = _text(data, "provider")
    username = _text(data, "username")
    password = _text(data, "password")
    assert (
        site_id is not None
        and provider is not None
        and username is not None
        and password is not None
    )
    start_date = _date(data, "start_date")
    end_date = _date(data, "end_date")
    if start_date and end_date and end_date < start_date:
        raise _error("end_date must not precede start_date")
    weekdays_value = data.get("weekdays")
    if weekdays_value is None:
        weekdays = _WEEKDAY_NAMES
    elif isinstance(weekdays_value, list) and all(isinstance(day, str) for day in weekdays_value):
        weekdays = tuple(day.upper() for day in weekdays_value)
        if (
            not weekdays
            or any(day not in _WEEKDAYS for day in weekdays)
            or len(set(weekdays)) != len(weekdays)
        ):
            raise _error("weekdays must contain unique weekday names")
    else:
        raise _error("weekdays must be a list of weekday names")
    interval = data.get("interval_seconds", 300)
    if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
        raise _error("interval_seconds must be a positive integer")
    timeout = data.get("timeout_seconds", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise _error("timeout_seconds must be a positive integer")
    retries = data.get("max_retries", 2)
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 5:
        raise _error("max_retries must be an integer between 0 and 5")
    timezone = _text(data, "timezone") if "timezone" in data else "UTC"
    assert timezone is not None
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(timezone)
    except (ValueError, KeyError) as exc:
        raise _error("timezone must be a valid IANA timezone") from exc
    start_time = _time(data, "start_time", time.min)
    end_time = _time(data, "end_time", time(23, 59, 59))
    if start_time == end_time:
        raise _error("start_time and end_time must differ")
    configured_log = data.get("log_file", f"data/local/logs/{site_id}.log")
    if not isinstance(configured_log, str):
        raise _error("log_file must be a relative path")
    log_file = _safe_log_path(configured_log, site_id)
    target_url = _url(data, "target_url") if "target_url" in data else None
    if target_url is not None and "navigation" in data:
        raise _error("site cannot define both target_url and navigation")
    navigation = _navigation(data.get("navigation")) if "navigation" in data else None
    if target_url is None and navigation is None:
        raise _error("site requires target_url or navigation")
    return SiteConfig(
        site_id,
        provider,
        _url(data, "login_url"),
        target_url,
        username,
        password,
        start_date,
        end_date,
        weekdays,
        start_time,
        end_time,
        timezone,
        interval,
        timeout,
        retries,
        log_file,
        navigation,
    )


def _navigation(value: Any) -> NavigationPlan:
    """Convert one site's YAML navigation mapping into the runtime contract."""
    try:
        data = _mapping(value, "navigation")
        if set(data) - {"version", "allowed_origin", "steps"}:
            raise _error("navigation contains unknown fields")
        version = _text(data, "version")
        allowed_origin = _url(data, "allowed_origin")
        assert version is not None
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            raise _error("navigation.steps must be a list")
        steps: list[NavigationStep] = []
        for raw in raw_steps:
            item = _mapping(raw, "navigation step")
            if set(item) - {
                "order",
                "method",
                "url",
                "params",
                "form_data",
                "timeout_seconds",
                "expected_result",
                "csrf_field",
                "read_only",
            }:
                raise _error("navigation step contains unknown fields")
            order = item.get("order")
            if isinstance(order, bool) or not isinstance(order, int):
                raise _error("navigation step order must be an integer")
            method = _text(item, "method")
            url = _url(item, "url")
            assert method is not None
            params = _string_mapping(item.get("params", {}), "navigation params")
            form_data = _string_mapping(item.get("form_data", {}), "navigation form_data")
            timeout = item.get("timeout_seconds", 30)
            if isinstance(timeout, bool) or not isinstance(timeout, int):
                raise _error("navigation timeout_seconds must be an integer")
            expected_data = _mapping(item.get("expected_result"), "expected_result")
            if set(expected_data) - {"status_code", "url_path", "text_marker"}:
                raise _error("expected_result contains unknown fields")
            status_code = expected_data.get("status_code")
            if status_code is not None and (
                isinstance(status_code, bool) or not isinstance(status_code, int)
            ):
                raise _error("expected_result.status_code must be an integer")
            expected = ExpectedResult(
                status_code=status_code,
                url_path=_optional_text(expected_data, "url_path"),
                text_marker=_optional_text(expected_data, "text_marker"),
            )
            read_only = item.get("read_only", False)
            if not isinstance(read_only, bool):
                raise _error("navigation step read_only must be a boolean")
            steps.append(
                NavigationStep(
                    order,
                    method,
                    url,
                    params,
                    form_data,
                    timeout,
                    expected,
                    _optional_text(item, "csrf_field"),
                    read_only,
                )
            )
        plan = NavigationPlan(version, tuple(steps), allowed_origin)
        from adams_tutoria.declarative_navigation import NavigationPlanValidator

        NavigationPlanValidator().validate(plan)
        return plan
    except NavigationError as exc:
        raise _error("navigation does not match its schema") from exc


def _optional_text(data: Mapping[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{name} must be a non-empty string")
    return value.strip()


def _string_mapping(value: Any, context: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise _error(f"{context} must be a mapping of text values")
    return dict(value)


def load_sites_config(path: Path) -> SitesConfig:
    """Load and validate a sites YAML file using PyYAML's non-executing safe loader."""
    try:
        with path.open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except (OSError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
        raise _error("unable to read valid YAML configuration") from exc
    try:
        data = _mapping(raw, "configuration")
        unknown = set(data) - _ROOT_FIELDS
        if unknown:
            raise _error("configuration contains unknown fields")
        schema_version = data.get("schema_version")
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise _error("schema_version must be an integer")
        if schema_version != 1:
            raise _error("schema_version must be 1")
        sites = data.get("sites")
        if not isinstance(sites, list) or not sites:
            raise _error("sites must be a non-empty list")
        parsed = tuple(_site(item) for item in sites)
        ids = [site.id for site in parsed]
        if len(ids) != len(set(ids)):
            raise _error("site ids must be unique")
        return SitesConfig(1, parsed)
    except SiteConfigError:
        raise
    except (AttributeError, KeyError, TypeError, UnicodeError, ValueError, OverflowError) as exc:
        # Do not expose parser/normalizer details or any raw YAML values.
        raise _error("configuration contains invalid values") from exc


@dataclass(frozen=True)
class AppConfig:
    """Application paths that are independent of business or domain settings."""

    base_dir: Path
    data_root: Path
    private_data_dir: Path
    local_data_dir: Path

    @property
    def generation_text_dir(self) -> Path:
        """Ignored operational directory containing UUID-named draft artifacts."""
        return self.local_data_dir / "generation-text"

    @property
    def generation_retention_days(self) -> int:
        """Initial deterministic retention policy for generation artifacts and audit."""
        return 30

    def generation_retention_cutoff(self, *, now: datetime | None = None) -> datetime:
        current = datetime.now(UTC) if now is None else now
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return current.astimezone(UTC) - timedelta(days=self.generation_retention_days)


def _path_value(value: str, *, base_dir: Path) -> Path:
    """Turn a configured path into a path relative to ``base_dir`` when needed."""

    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def default_config(*, base_dir: Path | None = None) -> AppConfig:
    """Return configuration using the standard local data directories.

    No environment variables are consulted by this function.  The default base
    directory is the process working directory; callers can provide one for
    deterministic use in tests or embedding applications.
    """

    root = Path.cwd() if base_dir is None else base_dir
    data_root = root / "data"
    return AppConfig(
        base_dir=root,
        data_root=data_root,
        private_data_dir=data_root / "private",
        local_data_dir=data_root / "local",
    )


def load_config(
    *,
    environ: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
) -> AppConfig:
    """Load defaults with optional ``ADAMS_TUTORIA_*`` path overrides.

    ``environ=None`` reads ``os.environ`` when this function is called.  Passing
    an empty mapping intentionally applies no overrides.  Relative override
    values are joined to ``base_dir`` and are not resolved or inspected.

    ``ADAMS_TUTORIA_DATA_ROOT`` changes the default location of both child
    directories.  A specific child override takes precedence over that derived
    value.  Supported variables are ``BASE_DIR``, ``DATA_ROOT``,
    ``PRIVATE_DATA_DIR``, and ``LOCAL_DATA_DIR``.
    """

    values = os.environ if environ is None else environ
    defaults = default_config(base_dir=base_dir)

    configured_base = values.get("ADAMS_TUTORIA_BASE_DIR")
    root = (
        defaults.base_dir
        if configured_base is None
        else _path_value(configured_base, base_dir=defaults.base_dir)
    )

    configured_data_root = values.get("ADAMS_TUTORIA_DATA_ROOT")
    data_root = (
        root / "data"
        if configured_data_root is None
        else _path_value(configured_data_root, base_dir=root)
    )

    configured_private = values.get("ADAMS_TUTORIA_PRIVATE_DATA_DIR")
    configured_local = values.get("ADAMS_TUTORIA_LOCAL_DATA_DIR")
    return AppConfig(
        base_dir=root,
        data_root=data_root,
        private_data_dir=(
            data_root / "private"
            if configured_private is None
            else _path_value(configured_private, base_dir=root)
        ),
        local_data_dir=(
            data_root / "local"
            if configured_local is None
            else _path_value(configured_local, base_dir=root)
        ),
    )
