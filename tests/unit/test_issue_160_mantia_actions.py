"""Offline contract tests for the Issue #160 Mantia deployment."""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
BASELINE = "0c89f717dc0938112b96557b8783a0fd6cea3e2d"


def _workflow(instance: str) -> tuple[Path, str, dict[str, object]]:
    path = ROOT / f".github/workflows/monitor-{instance}.yml"
    text = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    return path, text, parsed


def test_mantia_workflows_are_independent_manual_dispatch_jobs() -> None:
    for instance, start, end in (("mantia1", "14:30", "16:30"), ("mantia2", "20:30", "22:30")):
        _, text, workflow = _workflow(instance)
        # PyYAML's YAML 1.1 loader interprets the unquoted GitHub key `on` as
        # boolean True; accept that parser quirk while checking the contract.
        assert workflow.get("on", workflow.get(True)) == {"workflow_dispatch": None}
        assert "schedule:" not in text
        assert workflow["concurrency"] == {"group": instance, "cancel-in-progress": False}
        job = workflow["jobs"]["monitor"]
        assert job["timeout-minutes"] == 155
        assert "MANTIA_USERNAME: ${{ secrets.MANTIA_USERNAME }}" in text
        assert "MANTIA_PASSWORD: ${{ secrets.MANTIA_PASSWORD }}" in text
        assert f'id="{instance}"' in text
        assert f'start_time="{start}"' in text
        assert f'end_time="{end}"' in text
        assert "interval_seconds=60" in text
        assert f"--site {instance} --once-window" in text
        assert "playwright install --with-deps chromium" in text
        assert f"name: {instance}-monitor-logs-" in text
        assert "${{ github.run_id }}" in text
        assert f"{instance}-config.yaml" in text

        upload = next(step for step in job["steps"] if "upload-artifact" in step.get("uses", ""))
        artifact_path = upload["with"]["path"]
        assert artifact_path == f"data/local/logs/{instance}.log"
        assert f"{instance}-config.yaml" not in artifact_path

        cleanup = next(
            step
            for step in job["steps"]
            if step.get("name") == "Remove effective configuration and logs"
        )
        assert cleanup["if"] == "always()"
        cleanup_run = cleanup["run"]
        assert f"$RUNNER_TEMP/{instance}-config.yaml" in cleanup_run
        assert "data/local/logs" in cleanup_run

        generation = next(
            step
            for step in job["steps"]
            if step.get("name") == "Generate and validate effective Mantia configuration"
        )
        assert generation["env"] == {
            "MANTIA_USERNAME": "${{ secrets.MANTIA_USERNAME }}",
            "MANTIA_PASSWORD": "${{ secrets.MANTIA_PASSWORD }}",
        }
        assert "print(" in generation["run"]
        assert "MANTIA_PASSWORD" not in generation["run"].split("print(", 1)[1]


def test_mantia_contract_covers_all_new_files_and_preserves_adams() -> None:
    expected = {
        ".github/workflows/monitor-mantia1.yml",
        ".github/workflows/monitor-mantia2.yml",
        "docs/deployment-mantia.md",
        "tests/unit/test_issue_160_mantia_actions.py",
    }
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", BASELINE, "--"], cwd=ROOT, text=True
        ).splitlines()
    )
    untracked = set(
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True
        ).splitlines()
    )
    assert changed | untracked == expected
    assert not any(
        path.startswith(".github/workflows/monitor-adams") for path in changed | untracked
    )
    assert not any(
        path.startswith("src/adams_tutoria/adapters/adams") for path in changed | untracked
    )


def test_mantia_documentation_preserves_manual_handoff_and_safety_contract() -> None:
    text = (ROOT / "docs/deployment-mantia.md").read_text(encoding="utf-8")
    assert "No hay ningún `schedule` activo" in text
    assert "15 minutos" in text
    assert "cuatro páginas GET" in text
    assert "cron-job.org" in text
    assert "Authorization: Bearer <TOKEN>" in text
    assert "no se deben crear tareas" in text.lower()
    assert "ADAMS no forma parte" in text
