"""Static, synthetic checks for the Supervisor OpenCode harness."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
SUPERVISOR = ROOT / ".opencode" / "agents" / "supervisor.md"


def supervisor_text() -> str:
    return SUPERVISOR.read_text(encoding="utf-8")


def test_supervisor_identity_and_oauth_boundary() -> None:
    text = supervisor_text()
    assert "mode: primary" in text
    assert "model: openai/gpt-5.6-luna" in text
    assert "OpenAI OAuth" in text
    assert "OPENAI_API_KEY" in text  # explicit prohibition, not configuration


def test_only_approved_native_task_targets_are_allowed() -> None:
    text = supervisor_text()
    assert "native `task` delegation" in text
    assert "action: subagent" in text
    assert 'resource: "*"\n    effect: deny' in text
    for agent in ("planner", "implementer", "validator", "reviewer", "github-manager"):
        assert f"resource: {agent}" in text
    assert "custom tool" in text.lower()
    assert "child session" in text.lower()


def test_supervisor_cannot_edit_or_use_shell() -> None:
    text = supervisor_text()
    assert 'action: edit\n    resource: "*"\n    effect: deny' in text
    assert 'action: bash\n    resource: "*"\n    effect: deny' in text
    assert 'action: shell\n    resource: "*"\n    effect: deny' in text
    assert "Do not use shell commands" in text


def test_gates_and_limits_are_explicit() -> None:
    text = supervisor_text()
    for phrase in ("PLAN APPROVED", "PR APPROVED"):
        assert phrase in text
    for limit in (
        "PLAN_MAX_ITERATIONS = 3",
        "REVIEW_MAX_ITERATIONS = 3",
        "GLOBAL_TRANSITION_LIMIT = 12",
    ):
        assert limit in text
    assert "Never auto-advance" in text
    assert "material deviation" in text.lower()


def test_workflow_routes_and_manual_limitations_are_documented() -> None:
    text = supervisor_text().lower()
    for route in (
        "planner",
        "implementer",
        "validator",
        "reviewer",
        "github-manager",
        "correction",
        "replanning",
        "conversational protocol",
        "manual workflow",
    ):
        assert route in text
