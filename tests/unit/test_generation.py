"""Synthetic tests for the local generation contract."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.domain import Course, Edition, Enrollment, Student
from adams_tutoria.generation import (
    GenerationConfigurationError,
    GenerationRecord,
    GenerationResponseError,
    GenerationStatus,
    HttpResponse,
    InvalidEndpointError,
    OllamaConfig,
    OllamaGenerator,
    PromptContext,
    PromptRequest,
    build_model_payload,
    serialize_prompt,
    validate_local_endpoint,
)
from adams_tutoria.persistence.database import initialize_database
from adams_tutoria.persistence.repositories import (
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    GenerationRepository,
    StudentRepository,
)


def _ready(path: Path):
    initialize_database(path)
    course = Course(uuid4(), "Synthetic course", "SYN")
    edition = Edition(uuid4(), course, "Spring", "edition-x", date(2026, 1, 1), date(2026, 6, 1))
    student = Student(uuid4(), "Synthetic Student", "student@example.invalid", "student-x")
    enrollment = Enrollment(uuid4(), student, edition, "enrollment-x")
    CourseRepository(path).save(course)
    EditionRepository(path).save(edition)
    StudentRepository(path).save(student)
    EnrollmentRepository(path).save(enrollment)
    return enrollment


def test_payload_is_allowlisted_and_minimized() -> None:
    payload = build_model_payload(
        "progress_follow_up",
        "low progress",
        {"course_topic": "unit 1"},
    )
    assert payload == {
        "communication_type": "progress_follow_up",
        "reason": "low progress",
        "context": {"course_topic": "unit 1"},
    }


def test_versioned_prompt_is_minimized_separated_and_deterministic() -> None:
    request = PromptRequest(
        PromptContext(
            follow_up_reasons=("inactive",),
            progress_percentage="42.5",
            pending_evaluations=1,
        ),
        communication_type="progress_follow_up",
        tone="supportive",
        tutor_text="Invita a revisar la unidad disponible.",
    )
    serialized = serialize_prompt(request)
    assert serialized == serialize_prompt(request)
    assert '"version":"prompt-context-v1"' in serialized
    assert '"communication_type":"progress_follow_up"' in serialized
    assert '"tone":"supportive"' in serialized
    assert "student_email" not in serialized
    assert '"rules"' in serialized


@pytest.mark.parametrize(
    "text", ["Usa student_email", "incluye credentials", "menciona other_students"]
)
def test_tutor_text_cannot_override_privacy_denylist(text: str) -> None:
    with pytest.raises(ValueError, match="prohibited"):
        PromptRequest(PromptContext(), "follow_up", "neutral", text)


def test_prompt_context_projects_summary_without_identity() -> None:
    summary = type(
        "Summary",
        (),
        {
            "follow_up": type(
                "FollowUp",
                (),
                {"reasons": (type("Reason", (), {"code": "inactive"})(),)},
            )(),
            "progress": type("Progress", (), {"percentage": "42.5", "last_progress_at": None})(),
            "evaluations": type("Evaluations", (), {"pending": 1, "completed": 2})(),
        },
    )()
    context = PromptContext.from_summary(summary)
    assert context.as_mapping()["follow_up_reasons"] == ("inactive",)
    assert "student_id" not in context.as_mapping()


@pytest.mark.parametrize("field", ["student_name", "student_email", "raw_export"])
def test_payload_rejects_prohibited_or_unknown_context_fields(field: str) -> None:
    with pytest.raises(ValueError, match="allowlist"):
        build_model_payload("progress_follow_up", "low progress", {field: "synthetic"})


def test_record_rejects_prohibited_and_outside_allowlist_payload_fields() -> None:
    value = {
        "communication_type": "progress_follow_up",
        "reason": "low progress",
        "student_name": "synthetic",
    }
    with pytest.raises(ValueError, match="allowlist"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            value,
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_record_rejects_prohibited_context_fields() -> None:
    with pytest.raises(ValueError, match="context.*allowlist"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            {
                "communication_type": "progress_follow_up",
                "reason": "low progress",
                "context": {"student_email": "student@example.invalid"},
            },
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_record_rejects_timestamp_before_created_at() -> None:
    with pytest.raises(ValueError, match="edited_at.*created_at"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            {"communication_type": "progress_follow_up", "reason": "low progress"},
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
            GenerationStatus.EDITED,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2025, 12, 31, tzinfo=UTC),
        )


def test_persistence_transitions_manual_sent_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "test.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    repo.transition(
        value.id,
        GenerationStatus.EDITED,
        datetime(2026, 1, 2, tzinfo=UTC),
        "Edited synthetic draft",
    )
    repo.transition(value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 3, tzinfo=UTC))
    repo.transition(value.id, GenerationStatus.COPIED, datetime(2026, 1, 4, tzinfo=UTC))
    repo.transition(value.id, GenerationStatus.SENT, datetime(2026, 1, 5, tzinfo=UTC))
    assert repo.get(value.id).status is GenerationStatus.SENT  # type: ignore[union-attr]
    repo.delete(value.id)
    assert repo.get(value.id) is None


def test_re_review_after_edit_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "re-review.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    repo.transition(value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 2, tzinfo=UTC))
    repo.transition(
        value.id, GenerationStatus.EDITED, datetime(2026, 1, 3, tzinfo=UTC), "Revised draft"
    )
    repo.transition(value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 4, tzinfo=UTC))
    record = repo.get(value.id)
    assert record is not None
    assert record.edited_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert record.reviewed_at == datetime(2026, 1, 4, tzinfo=UTC)


def test_draft_text_is_only_accepted_for_edit_transition(tmp_path: Path) -> None:
    path = tmp_path / "draft-transition.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    with pytest.raises(ValueError, match="draft_text"):
        repo.transition(
            value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 2, tzinfo=UTC), "wrong"
        )


def test_sent_requires_copied_at() -> None:
    with pytest.raises(ValueError, match="SENT requires copied_at"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            {"communication_type": "progress_follow_up", "reason": "low progress"},
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
            GenerationStatus.SENT,
            sent_at=datetime(2026, 1, 2, tzinfo=UTC),
        )


def test_save_on_conflict_replaces_every_persisted_field(tmp_path: Path) -> None:
    path = tmp_path / "test.sqlite3"
    enrollment = _ready(path)
    second_enrollment = Enrollment(uuid4(), enrollment.student, enrollment.edition, "enrollment-y")
    EnrollmentRepository(path).save(second_enrollment)
    original = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    replacement = replace(
        original,
        enrollment_id=second_enrollment.id,
        communication_type="review_reminder",
        reason="synthetic reason",
        model_payload={"communication_type": "review_reminder", "reason": "synthetic reason"},
        draft_text="Replacement synthetic draft",
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
        status=GenerationStatus.REVIEWED,
        reviewed_at=datetime(2026, 2, 2, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(original)
    repo.save(replacement)
    assert repo.get(original.id) == replacement


@pytest.mark.parametrize(
    ("target", "at"),
    [
        (GenerationStatus.SENT, datetime(2026, 1, 2, tzinfo=UTC)),
        (GenerationStatus.COPIED, datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
def test_invalid_transition_does_not_change_record(
    tmp_path: Path, target: GenerationStatus, at: datetime
) -> None:
    path = tmp_path / "test.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    with pytest.raises(ValueError, match="invalid generation transition"):
        repo.transition(value.id, target, at)
    assert repo.get(value.id) == value


class StubTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, bytes, float]] = []

    def post(self, url: str, body: bytes, timeout_seconds: float) -> HttpResponse:
        self.calls.append((url, body, timeout_seconds))
        return self.response


def test_ollama_adapter_uses_minimized_payload_and_injected_transport() -> None:
    transport = StubTransport(HttpResponse(200, b'{"response":"Synthetic draft"}'))
    generator = OllamaGenerator(OllamaConfig("synthetic-model"), transport)
    result = generator.generate(build_model_payload("follow_up", "low progress"))
    assert result == "Synthetic draft"
    url, body, timeout = transport.calls[0]
    assert url == "http://localhost:11434/api/generate"
    assert b"student_email" not in body
    assert b'"stream":false' in body
    assert timeout == 30.0


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://localhost:11434",
        "http://example.invalid:11434",
        "http://localhost:11434?token=secret",
        "http://user:password@localhost:11434",
    ],
)
def test_ollama_rejects_non_local_or_credentialed_endpoints(endpoint: str) -> None:
    with pytest.raises(InvalidEndpointError):
        validate_local_endpoint(endpoint)


def test_ollama_rejects_oversized_request_and_invalid_response() -> None:
    generator = OllamaGenerator(
        OllamaConfig("synthetic-model", max_request_bytes=10),
        StubTransport(HttpResponse(200, b'{"response":"ok"}')),
    )
    with pytest.raises(GenerationConfigurationError, match="request"):
        generator.generate({"reason": "synthetic"})
    invalid = OllamaGenerator(
        OllamaConfig("synthetic-model"), StubTransport(HttpResponse(200, b'{"text":"wrong"}'))
    )
    with pytest.raises(GenerationResponseError):
        invalid.generate({"reason": "synthetic"})
