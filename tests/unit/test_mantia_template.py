"""Offline contract tests for the tracked Mantia configuration template."""

from pathlib import Path

import yaml

from adams_tutoria.config import load_sites_config

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / "config.mantia.yaml.template"


def test_mantia_template_loads_with_the_current_schema(tmp_path: Path) -> None:
    data = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    site = data["sites"][0]
    site["username"] = "synthetic-mantia-user"
    site["password"] = "synthetic-mantia-password"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    configuration = load_sites_config(config_path)

    assert configuration.schema_version == 1
    assert len(configuration.sites) == 1
    monitored = configuration.sites[0]
    assert monitored.id == "mantia1"
    assert monitored.provider == "MANTIA"
    assert monitored.start_time.isoformat(timespec="minutes") == "14:30"
    assert monitored.end_time.isoformat(timespec="minutes") == "16:30"
    assert monitored.log_file == Path("data/local/logs/mantia1.log")


def test_mantia_template_has_only_ordered_read_only_get_requests() -> None:
    data = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    site = data["sites"][0]
    steps = site["navigation"]["steps"]

    assert len(data["sites"]) == 1
    assert site["username"] == "${MANTIA_USERNAME}"
    assert site["password"] == "${MANTIA_PASSWORD}"
    assert [step["order"] for step in steps] == [1, 2, 3, 4]
    assert all(step["method"] == "GET" and step["read_only"] is True for step in steps)
    assert [step["url"] for step in steps] == [
        "https://betaformacion.mantia.es/my/",
        "https://betaformacion.mantia.es/course/view.php?id=56",
        "https://betaformacion.mantia.es/mod/forum/view.php?id=3834",
        "https://betaformacion.mantia.es/mod/scorm/view.php?id=3838",
    ]
    assert all(
        step["expected_result"] == {"status_code": 200, "url_path": expected_path}
        for step, expected_path in zip(
            steps,
            ("/my/", "/course/view.php", "/mod/forum/view.php", "/mod/scorm/view.php"),
            strict=True,
        )
    )


def test_mantia_template_contains_no_secret_or_dynamic_session_values() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "${MANTIA_USERNAME}" in text
    assert "${MANTIA_PASSWORD}" in text
    assert "token" not in text.lower()
    assert "cookie" not in text.lower()
    assert "session" not in text.lower()
    assert "2026-" not in text
