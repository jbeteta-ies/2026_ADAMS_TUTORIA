"""Synthetic end-to-end evidence for Issue #102.

These tests deliberately use an injected local-model double.  They never start
Ollama, open a socket, download a model, or access a remote service.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from adams_tutoria.domain import Course, Edition, Enrollment, Student, TutorAction
from adams_tutoria.generation import (
    DraftGenerationRequest,
    DraftGenerationService,
    GenerationStatus,
    HttpResponse,
    OllamaConfig,
    OllamaGenerator,
    PromptContext,
    PromptRequest,
)
from adams_tutoria.persistence.database import initialize_database
from adams_tutoria.persistence.repositories import (
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    GenerationRepository,
    StudentRepository,
    TutorActionRepository,
)


def _enrollments(path: Path) -> tuple[Enrollment, Enrollment]:
    initialize_database(path)
    course = Course(uuid4(), "Synthetic issue 102 course", "SYN-102")
    edition = Edition(uuid4(), course, "Synthetic edition", "edition-102")
    first = Student(uuid4(), "Synthetic Student 001", "student001@example.invalid", "s-001")
    second = Student(uuid4(), "Synthetic Student 002", "student002@example.invalid", "s-002")
    enrollments = (
        Enrollment(uuid4(), first, edition, "enrollment-001"),
        Enrollment(uuid4(), second, edition, "enrollment-002"),
    )
    CourseRepository(path).save(course)
    EditionRepository(path).save(edition)
    for student in (first, second):
        StudentRepository(path).save(student)
    for enrollment in enrollments:
        EnrollmentRepository(path).save(enrollment)
    return enrollments


class SyntheticGenerator:
    model_name = "synthetic-model"

    def __init__(self) -> None:
        self.payloads: list[Mapping[str, Any]] = []

    def generate(self, payload: Mapping[str, Any]) -> str:
        self.payloads.append(payload)
        if len(self.payloads) == 2:
            raise RuntimeError("synthetic transport failure")
        return "Synthetic draft for human review"


def _request(enrollment: Enrollment, reason: str) -> DraftGenerationRequest:
    return DraftGenerationRequest(
        enrollment,
        " progress_follow_up ",
        reason,
        PromptRequest(
            PromptContext(progress_percentage="42", pending_evaluations=1),
            "progress_follow_up",
            "supportive",
        ),
    )


def test_local_generation_flow_is_isolated_minimized_and_manual(tmp_path: Path) -> None:
    path = tmp_path / "issue-102.sqlite3"
    first, second = _enrollments(path)
    generator = SyntheticGenerator()
    repository = GenerationRepository(path)
    service = DraftGenerationService(
        generator, repository, lambda: datetime(2026, 9, 1, tzinfo=UTC)
    )

    result = service.generate(
        [_request(first, "low progress"), _request(second, "synthetic failure")]
    )

    assert len(result.records) == 1
    assert result.records[0].enrollment_id == first.id
    assert len(result.failures) == 1
    assert result.failures[0].enrollment_id == second.id
    assert result.failures[0].error_code == "RuntimeError"
    assert "student_email" not in str(generator.payloads[0])
    assert "Synthetic Student" not in str(generator.payloads[0])

    record = repository.get(result.records[0].id)
    assert record is not None
    repository.transition(record.id, GenerationStatus.REVIEWED, datetime(2026, 9, 2, tzinfo=UTC))
    repository.transition(
        record.id,
        GenerationStatus.EDITED,
        datetime(2026, 9, 3, tzinfo=UTC),
        "Edited synthetic draft",
    )
    repository.transition(record.id, GenerationStatus.COPIED, datetime(2026, 9, 4, tzinfo=UTC))
    repository.transition(record.id, GenerationStatus.SENT, datetime(2026, 9, 5, tzinfo=UTC))
    assert repository.get(record.id).status is GenerationStatus.SENT  # type: ignore[union-attr]


def test_ollama_contract_uses_only_injected_transport(tmp_path: Path) -> None:
    """The adapter contract is tested without Ollama or network access."""
    calls: list[tuple[str, bytes, float]] = []

    def post(url: str, body: bytes, timeout_seconds: float) -> HttpResponse:
        calls.append((url, body, timeout_seconds))
        return HttpResponse(200, b'{"response":"Synthetic local response"}')

    class Transport:
        def post(self, url: str, body: bytes, timeout_seconds: float) -> HttpResponse:
            return post(url, body, timeout_seconds)

    del tmp_path  # This test has no filesystem side effect; keep fixtures uniform.
    result = OllamaGenerator(OllamaConfig("synthetic-model"), Transport()).generate(
        {"communication_type": "follow_up", "reason": "synthetic reason"}
    )

    assert result == "Synthetic local response"
    assert calls[0][0] == "http://localhost:11434/api/generate"
    assert b'"stream":false' in calls[0][1]
    assert calls[0][2] == 30.0


def test_mock_generation_records_effective_model_and_never_delivers(tmp_path: Path) -> None:
    first, _ = _enrollments(tmp_path / "model-trace.sqlite3")
    transport = type(
        "Transport",
        (),
        {
            "post": lambda self, url, body, timeout_seconds: HttpResponse(
                200, b'{"model":"synthetic-effective","response":"Draft for review"}'
            )
        },
    )()
    generator = OllamaGenerator(OllamaConfig("synthetic-configured"), transport)
    repository = GenerationRepository(tmp_path / "model-trace.sqlite3")
    result = DraftGenerationService(generator, repository).generate(
        [_request(first, "synthetic reason")]
    )

    assert result.records[0].model_name == "synthetic-effective"
    assert result.records[0].status is GenerationStatus.GENERATED
    assert not hasattr(generator, "send")
    assert not (tmp_path / "model-trace.sqlite3").read_bytes().find(b"SMTP") >= 0


def test_human_review_copy_discard_and_action_audit_are_local_only(tmp_path: Path) -> None:
    path = tmp_path / "human-controls.sqlite3"
    first, second = _enrollments(path)
    repository = GenerationRepository(path)
    generator = SyntheticGenerator()
    service = DraftGenerationService(generator, repository)
    generated = service.generate([_request(first, "synthetic review")]).records[0]

    repository.transition(
        generated.id, GenerationStatus.REVIEWED, datetime(2026, 10, 2, tzinfo=UTC)
    )
    repository.transition(
        generated.id,
        GenerationStatus.EDITED,
        datetime(2026, 10, 3, tzinfo=UTC),
        "Edited synthetic draft",
    )
    repository.transition(generated.id, GenerationStatus.COPIED, datetime(2026, 10, 4, tzinfo=UTC))
    copied = repository.get(generated.id)
    assert copied is not None and copied.status is GenerationStatus.COPIED

    discarded = (
        DraftGenerationService(SyntheticGenerator(), repository)
        .generate([_request(second, "synthetic discard")])
        .records[0]
    )
    repository.transition(
        discarded.id, GenerationStatus.DISCARDED, datetime(2026, 10, 2, tzinfo=UTC)
    )
    assert repository.get(discarded.id).status is GenerationStatus.DISCARDED  # type: ignore[union-attr]

    actions = TutorActionRepository(path)
    action = TutorAction(uuid4(), first.id, datetime(2026, 10, 4, tzinfo=UTC), "Revisar borrador")
    actions.save(action)
    assert actions.list_for_enrollment(first.id) == (action,)
    assert repository.history(generated.id)[-1].to_status is GenerationStatus.COPIED
