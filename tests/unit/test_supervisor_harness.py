"""Static, synthetic checks for the Supervisor OpenCode harness."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
SUPERVISOR = ROOT / ".opencode" / "agents" / "supervisor.md"


def supervisor_text() -> str:
    return SUPERVISOR.read_text(encoding="utf-8")


def normalized_supervisor_text() -> str:
    """Fold case and Markdown whitespace without removing required wording."""
    return " ".join(supervisor_text().casefold().split())


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
    ):
        assert limit in text
    assert "Never auto-advance" in text
    assert "material deviation" in text.lower()


def test_review_counter_counts_only_completed_correction_cycles() -> None:
    text = normalized_supervisor_text()
    assert "review_iteration: 0/3" in text
    assert "initial implementer → validator → reviewer sequence" in text
    assert "request changes" in text
    assert "counts only completed corrective" in text
    assert "does not increment" in text
    assert "keep the current value" in text
    assert "increment it once only after the complete" in text
    assert "never increment once per agent" in text
    assert "replanning" in text
    assert "does not increment `review_iteration`" in text
    assert "starting correction and every intermediate delegation" in text
    assert "previous corrective cycle completed at `2/3`" in text
    assert "remains at `2/3`" in text
    assert "becomes `3/3` only after" in text


def test_workflow_counters_are_isolated_and_plan_counter_is_explicit() -> None:
    text = supervisor_text()
    assert "At the start of every new workflow" in text
    assert "Do not inherit either" in text
    assert "Increment `PLAN_ITERATION` only when requesting a new iteration" in text
    assert "Stop at the review limit of `3/3`" in text


def test_no_global_transition_counter_is_used() -> None:
    text = supervisor_text()
    assert "GLOBAL_TRANSITION_LIMIT" not in text
    assert "GLOBAL_TRANSITIONS" not in text


def test_request_changes_does_not_increment_before_corrective_route() -> None:
    text = normalized_supervisor_text()
    request_changes = text.index(
        "if validator or reviewer returns the explicit result `request changes`"
    )
    starts_route = text.index("start the corrective route without changing `review_iteration`")
    increments_after = text.index(
        "when that complete corrective implementer → validator → reviewer"
    )
    assert request_changes < starts_route < increments_after
    assert "a new `request changes` by itself never increments the counter" in text
    assert "counter must not change" in text
    assert "intermediate delegation in the route is in progress" in text


def test_github_manager_preparation_precedes_gate_two_and_final_workflow_follows() -> None:
    text = normalized_supervisor_text()
    preparation = text.index("**pr preparation**")
    gate_two_request = text.index("request the exact human message **pr approved**")
    final_workflow = text.index("**final workflow**")

    assert preparation < gate_two_request < final_workflow
    for requirement in (
        "commit the validated changes",
        "push the issue branch",
        "create or update the pr",
        "include the final validator report and reviewer result",
        "verify that the published pr exactly matches the validated and reviewed state",
    ):
        assert requirement in text
    for forbidden_before_gate in (
        "must not merge",
        "close the issue",
        "delete branches",
        "perform cleanup",
    ):
        assert text.index(forbidden_before_gate) < final_workflow
    for final_requirement in (
        "verify the pr and checks",
        "merge",
        "confirm issue closure when applicable",
        "delete the branches",
        "synchronize `main`",
        "perform cleanup",
    ):
        assert final_requirement in text[final_workflow:]
    assert "no final-workflow action may be delegated before `pr approved`" in text


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
