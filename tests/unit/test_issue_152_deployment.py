"""Synthetic, offline checks for the Issue #152 deployment contract."""

from pathlib import Path

import yaml

from adams_tutoria.config import load_sites_config

ROOT = Path(__file__).parents[2]


def test_adams_template_preserves_validated_navigation_without_credentials(tmp_path: Path) -> None:
    template = ROOT / "config.adams.yaml.template"
    text = template.read_text(encoding="utf-8")
    assert "${ADAMS_USERNAME}" in text
    assert "${ADAMS_PASSWORD}" in text

    data = yaml.safe_load(text)
    site = data["sites"][0]
    site["username"] = "synthetic-user"
    site["password"] = "synthetic-password"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    configuration = load_sites_config(config_path)
    monitored = configuration.sites[0]
    assert monitored.id == "adams-site"
    assert monitored.start_time.isoformat(timespec="minutes") == "16:20"
    assert monitored.end_time.isoformat(timespec="minutes") == "20:40"
    assert monitored.navigation is not None
    assert [step.method for step in monitored.navigation.steps] == ["POST", "GET", "GET"]
    assert [step.url for step in monitored.navigation.steps] == [
        "https://www.formacion.cc/aula.php",
        "https://www.formacion.cc/tutorias.php?modoCarga=2",
        "https://www.formacion.cc/temario.php?modoCarga=1",
    ]


def test_generic_config_template_has_required_name_and_is_distinct_from_adams() -> None:
    generic = ROOT / "config.example.yaml"
    adams = ROOT / "config.adams.yaml.template"

    assert generic.is_file()
    assert not (ROOT / "config.yaml.example").exists()
    generic_text = generic.read_text(encoding="utf-8")
    adams_text = adams.read_text(encoding="utf-8")
    assert "example.invalid" in generic_text
    assert "${ADAMS_USERNAME}" not in generic_text
    assert "${ADAMS_PASSWORD}" not in generic_text
    assert "${ADAMS_USERNAME}" in adams_text
    assert "${ADAMS_PASSWORD}" in adams_text


def test_configuration_documentation_uses_unambiguous_template_names() -> None:
    files = [
        ROOT / "README.md",
        ROOT / "docs/declarative-navigation.md",
        ROOT / "docs/deployment-adams.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)

    assert "config.yaml.example" not in text
    assert "config.example.yaml" in text
    assert "config.adams.yaml.template" in text
    assert "config.yaml" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_adams_workflow_has_single_schedule_and_secret_safe_command() -> None:
    workflow = (ROOT / ".github/workflows/monitor-adams.yml").read_text(encoding="utf-8")
    assert workflow.count("cron:") == 1
    assert 'cron: "20 16 * * 1-5"' in workflow
    assert "timezone: Europe/Madrid" in workflow
    assert "group: adams-site" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "ADAMS_USERNAME" in workflow and "ADAMS_PASSWORD" in workflow
    assert "adams-monitor --config config.yaml --site adams-site --once-window" in workflow
    assert "retention-days: 7" in workflow
    config_position = workflow.index("Generate and validate effective ADAMS configuration")
    playwright_position = workflow.index("Install Chromium and Playwright dependencies")
    worker_position = workflow.index("Run the ADAMS worker")
    assert config_position < playwright_position < worker_position

    config_step = workflow[config_position:playwright_position]
    assert 'test -n "$ADAMS_USERNAME"' in config_step
    assert 'test -n "$ADAMS_PASSWORD"' in config_step
    assert "load_sites_config(output)" in config_step
    assert (
        'print("Effective ADAMS configuration validated without displaying secrets.")'
        in config_step
    )
    assert 'printf "%s\\n" "$ADAMS_USERNAME"' not in workflow
    assert 'printf "%s\\n" "$ADAMS_PASSWORD"' not in workflow
    assert "cat config.yaml" not in workflow
    assert "::add-mask::" not in workflow
    artifact_step = workflow.split("Upload ADAMS diagnostic logs", 1)[1].split(
        "Remove effective configuration", 1
    )[0]
    assert "config.yaml" not in artifact_step
