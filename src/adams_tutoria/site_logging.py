"""Bounded, privacy-safe local logging for one monitored site."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from logging import LogRecord
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from adams_tutoria.config import SiteConfig

_MAX_BYTES: Final = 1_048_576
_BACKUP_COUNT: Final = 3
_RETENTION_DAYS: Final = 30
_ACTIONS: Final = frozenset({"startup", "login", "navigation", "reload"})
_CATEGORIES: Final = frozenset(
    {"config", "authentication", "navigation", "timeout", "blocked", "logging"}
)
_MESSAGES: Final = frozenset(
    {
        "Startup no disponible.",
        "Login no confirmado.",
        "Navegación no confirmada.",
        "Operación agotó el tiempo.",
        "Intervención humana requerida.",
        "Registro local no disponible.",
    }
)


def _safe_label(value: str) -> str:
    """Keep configured labels single-line and bounded without logging secrets."""
    return "".join(character if character.isprintable() else "?" for character in value)[:128]


class SiteLogWriter:
    """Write only fixed-schema operational events to a site's local file.

    The writer owns a handler for exactly one site.  It never receives browser
    responses, credentials, or exception text, and write failures are returned
    to the caller rather than escaping into the monitor loop.
    """

    def __init__(
        self,
        site: SiteConfig,
        *,
        max_bytes: int = _MAX_BYTES,
        backup_count: int = _BACKUP_COUNT,
        retention_days: int = _RETENTION_DAYS,
    ) -> None:
        if max_bytes < 1 or backup_count < 0 or retention_days < 1:
            raise ValueError("logging limits must be positive")
        self._site = site
        self._path = site.log_file
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._retention_days = retention_days

    @property
    def path(self) -> Path:
        return self._path

    def write(
        self,
        *,
        action: str,
        result: str,
        category: str | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> bool:
        """Persist one safe event, returning ``False`` if local logging failed."""
        if action not in _ACTIONS or result not in {"success", "error"}:
            return False
        if result == "error" and category is None:
            category = "logging"
        if result == "error" and message is None:
            message = "Registro local no disponible."
        if result == "error" and (category not in _CATEGORIES or message not in _MESSAGES):
            return False
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "site_id": _safe_label(self._site.id),
            "provider": _safe_label(self._site.provider),
            "action": action,
            "result": result,
        }
        if result == "error":
            assert category is not None and message is not None
            record["category"] = category
            record["message"] = message
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                self._path,
                maxBytes=self._max_bytes,
                backupCount=self._backup_count,
                encoding="utf-8",
            )
            try:
                handler.emit(_json_record(record))
            finally:
                handler.close()
            self._prune_old_files()
        except Exception:
            # Logging is diagnostic only and must never escape into monitoring.
            return False
        return True

    def _prune_old_files(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        candidates = [self._path, *self._path.parent.glob(f"{self._path.name}.*")]
        for candidate in candidates:
            try:
                modified = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
                if modified < cutoff:
                    candidate.unlink()
            except OSError:
                # Retention is best effort and must never affect monitoring.
                continue


def _json_record(record: dict[str, str]) -> LogRecord:
    """Return a logging record compatible with ``Handler.emit``."""
    message = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    return logging.LogRecord("adams_tutoria.site", logging.INFO, __file__, 0, message, (), None)


__all__ = ["SiteLogWriter"]
