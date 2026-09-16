"""Small, dependency-free configuration layer for the application.

This module only describes paths.  It deliberately does not create directories,
read files, or initialize a database.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


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
