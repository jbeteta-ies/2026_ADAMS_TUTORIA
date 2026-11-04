"""Contract and privacy tests for synthetic response diagnostics."""

from __future__ import annotations

import json
from math import inf, nan
from os import utime
from time import time

from adams_tutoria.config import SiteConfig
from adams_tutoria.response_metadata import (
    ExpectedResultMatch,
    ResponseMetadata,
    ResponsePhase,
    ResponseResult,
    validate_response_metadata,
)
from adams_tutoria.site_logging import SiteLogWriter


def metadata(**changes: object) -> dict[str, object]:
    value = ResponseMetadata(
        step="step-1",
        phase=ResponsePhase.NAVIGATION,
        method="GET",
        status_code=200,
        expected_result_match=ExpectedResultMatch.YES,
        redirected=False,
        duration=0.25,
        result=ResponseResult.OK,
    ).as_dict()
    value.update(changes)
    return value


def writer(tmp_path) -> SiteLogWriter:
    return SiteLogWriter(
        SiteConfig(
            "synthetic-site",
            "SYNTHETIC",
            "https://example.invalid/login",
            "https://example.invalid/target",
            "synthetic-user",
            "synthetic-password",
            log_file=tmp_path / "site.log",
        )
    )


def test_contract_allows_only_safe_fields_and_values() -> None:
    assert validate_response_metadata(metadata())
    for field, value in (("method", "DELETE"), ("phase", "other"), ("result", "oops")):
        assert not validate_response_metadata(metadata(**{field: value}))
    assert not validate_response_metadata(metadata(unknown="not allowed"))
    assert not validate_response_metadata(metadata(duration=-0.01))
    for invalid in (True, nan, inf, -inf, 86_400.1):
        assert not validate_response_metadata(metadata(duration=invalid))
    for invalid in (True, 99, 600):
        assert not validate_response_metadata(metadata(status_code=invalid))
    assert not validate_response_metadata(metadata(step="https://example.invalid/?token=synthetic"))
    for invalid in ("step-1-extra", "step-1-abcdef123456", "step-one", "step-0"):
        assert not validate_response_metadata(metadata(step=invalid))


def test_writer_rejects_unknown_metadata_and_preserves_historical_writer_contract(tmp_path) -> None:
    safe_writer = writer(tmp_path)
    assert not safe_writer.write(
        action="navigation", result="success", response_metadata=metadata(body="forbidden")
    )

    calls: list[dict[str, object]] = []

    class HistoricalWriter:
        def write(self, *, action: str, result: str, category=None, message=None) -> bool:
            calls.append(
                {"action": action, "result": result, "category": category, "message": message}
            )
            return True

    historical = HistoricalWriter()
    # This is the compatibility shape used by monitoring's injected writer path.
    arguments = {"action": "navigation", "result": "success", "response_metadata": metadata()}
    try:
        historical.write(**arguments)
    except TypeError:
        arguments.pop("response_metadata")
        assert historical.write(**arguments)
    assert calls


def test_writer_serializes_metadata_without_sensitive_response_material(tmp_path) -> None:
    safe_writer = writer(tmp_path)
    forbidden = (
        "<html>synthetic body</html>",
        "Authorization: Bearer synthetic-token",
        "Cookie: synthetic-cookie",
        "synthetic-user@example.invalid",
        "https://example.invalid/private?token=synthetic",
    )
    assert safe_writer.write(action="navigation", result="success", response_metadata=metadata())
    text = (tmp_path / "site.log").read_text(encoding="utf-8")
    record = json.loads(text)
    assert set(record["response_metadata"]) == {
        "step",
        "phase",
        "method",
        "status_code",
        "expected_result_match",
        "redirected",
        "duration",
        "result",
    }
    assert all(value not in text for value in forbidden)


def test_writer_rotates_and_retains_only_recent_sidecars(tmp_path) -> None:
    configured = SiteConfig(
        "rotation-site",
        "SYNTHETIC",
        "https://example.invalid/login",
        "https://example.invalid/target",
        "synthetic-user",
        "synthetic-password",
        log_file=tmp_path / "site.log",
    )
    safe_writer = SiteLogWriter(configured, max_bytes=100, backup_count=2, retention_days=1)
    for _ in range(12):
        assert safe_writer.write(action="navigation", result="success")
    sidecar = tmp_path / "site.log.1"
    assert sidecar.exists()
    old_sidecar = tmp_path / "site.log.legacy"
    old_sidecar.write_text("synthetic legacy log", encoding="utf-8")
    old_time = time() - 3 * 24 * 60 * 60
    utime(old_sidecar, (old_time, old_time))
    assert safe_writer.write(action="navigation", result="success")
    assert not old_sidecar.exists()
    assert (tmp_path / "site.log").exists()
