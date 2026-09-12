"""Integration coverage for the synthetic main tutoring flow.

The flow deliberately stays local: a temporary SQLite database and a synthetic
CSV are the only inputs.  No adapter in this suite contacts ADAMS or the
operational database.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from adams_tutoria.attention import AttentionConfig, PriorityThresholds, prioritize_attention
from adams_tutoria.communication_recommendations import (
    RecommendationConfig,
    RepetitionPolicy,
    recommend_communications,
)
from adams_tutoria.domain import (
    CommunicationRecord,
    CommunicationStatus,
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationStatus,
    EvaluationTargetType,
    ProgressSnapshot,
    Student,
)
from adams_tutoria.follow_up import FollowUpRules, assess_follow_up
from adams_tutoria.import_contract import RejectionCode
from adams_tutoria.message_templates import MessageContext
from adams_tutoria.persistence.database import initialize_database
from adams_tutoria.persistence.repositories import (
    CommunicationHistoryAdapter,
    CommunicationRecordRepository,
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    EvaluationRepository,
    ProgressSnapshotRepository,
    StudentRepository,
)
from adams_tutoria.student_tracking import prepare_tracking_rows
from adams_tutoria.summary import summarize_edition, summarize_enrollment
from adams_tutoria.tabular_import import TabularImportConfig, read_tabular

AS_OF = datetime(2026, 3, 1, 12, tzinfo=UTC)
RULES = FollowUpRules(
    not_started_max_progress=Decimal("5"),
    inactivity_after=timedelta(days=14),
    completion_min_progress=Decimal("90"),
)
ATTENTION = AttentionConfig(
    {
        "progress_unknown": Decimal("3"),
        "not_started": Decimal("2"),
        "inactive": Decimal("2"),
        "pending_evaluations": Decimal("1"),
    },
    PriorityThresholds(Decimal("1"), Decimal("2"), Decimal("3")),
)
RECOMMENDATIONS = RecommendationConfig(
    {"inactive": "inactivity_reminder", "pending_evaluations": "pending_evaluation_reminder"},
    RepetitionPolicy(max_occurrences=1),
)


def _read_synthetic_rows(path: Path) -> tuple[dict[str, object], ...]:
    path.write_text(
        "student_id,student_name,student_email,progress,pending_evaluations\n"
        "student-001,Alumno sintético 001,alumno-001@example.invalid,10,1\n"
        "student-002,Alumno sintético 002,alumno-002@example.invalid,95,0\n",
        encoding="utf-8",
    )
    result = read_tabular(
        path,
        config=TabularImportConfig(
            required_columns=("student_id", "progress", "pending_evaluations"),
            required_non_empty_columns=("student_name",),
        ),
    )
    assert not result.rejected, result.rejected
    return result.accepted


def _graph(
    row: dict[str, object], edition: Edition, index: int
) -> tuple[Student, Enrollment, ProgressSnapshot, Evaluation]:
    student_id = UUID(int=100 + index)
    enrollment_id = UUID(int=200 + index)
    snapshot_id = UUID(int=300 + index)
    evaluation_id = UUID(int=400 + index)
    student = Student(
        student_id, str(row["student_name"]), str(row["student_email"]), str(row["student_id"])
    )
    enrollment = Enrollment(enrollment_id, student, edition, f"enrollment-{index}")
    captured_at = AS_OF - (timedelta(days=30) if index == 1 else timedelta(days=1))
    snapshot = ProgressSnapshot(
        snapshot_id, enrollment, captured_at, Decimal(str(row["progress"])), f"snapshot-{index}"
    )
    pending = int(str(row["pending_evaluations"]))
    evaluation = Evaluation(
        evaluation_id,
        enrollment,
        EvaluationTargetType.ACTIVITY,
        f"activity-{index}",
        EvaluationStatus.PENDING if pending else EvaluationStatus.COMPLETED,
        external_id=f"evaluation-{index}",
    )
    return student, enrollment, snapshot, evaluation


def test_synthetic_import_persistence_rules_dashboard_and_communications(tmp_path: Path) -> None:
    """Exercise the main flow end to end with fixed IDs and timestamps."""
    rows = _read_synthetic_rows(tmp_path / "synthetic-main-flow.csv")
    database = tmp_path / "integration.sqlite3"
    initialize_database(database)
    course = Course(UUID(int=10), "Curso sintético", "SYN-001")
    edition = Edition(UUID(int=11), course, "Edición sintética", "edition-001", date(2026, 1, 1))

    enrollments: list[Enrollment] = []
    snapshots: list[ProgressSnapshot] = []
    evaluations: list[Evaluation] = []
    for index, row in enumerate(rows, start=1):
        student, enrollment, snapshot, evaluation = _graph(row, edition, index)
        CourseRepository(database).save(course)
        EditionRepository(database).save(edition)
        StudentRepository(database).save(student)
        EnrollmentRepository(database).save(enrollment)
        ProgressSnapshotRepository(database).save(snapshot)
        EvaluationRepository(database).save(evaluation)
        enrollments.append(enrollment)
        snapshots.append(snapshot)
        evaluations.append(evaluation)

    recovered = tuple(EnrollmentRepository(database).get(item.id) for item in enrollments)
    assert recovered == tuple(enrollments)
    recovered_snapshots = tuple(
        ProgressSnapshotRepository(database).list_for_enrollment(item.id) for item in enrollments
    )
    assert recovered_snapshots == ((snapshots[0],), (snapshots[1],))

    summaries = tuple(
        summarize_enrollment(
            enrollment,
            ProgressSnapshotRepository(database).list_for_enrollment(enrollment.id),
            EvaluationRepository(database).list_for_enrollment(enrollment.id),
            assess_follow_up(
                enrollment,
                ProgressSnapshotRepository(database).list_for_enrollment(enrollment.id),
                EvaluationRepository(database).list_for_enrollment(enrollment.id),
                RULES,
                as_of=AS_OF,
            ),
            as_of=AS_OF,
        )
        for enrollment in enrollments
    )
    assert {reason.code for reason in summaries[0].follow_up.reasons} == {
        "inactive",
        "pending_evaluations",
    }
    assert any(reason.code == "completed" for reason in summaries[1].follow_up.reasons)
    assert summarize_edition(edition.id, (*summaries, summaries[0])).total == 2

    cases = prioritize_attention(summaries, ATTENTION, edition_id=edition.id)
    rows_for_dashboard = prepare_tracking_rows((*summaries, summaries[0]), cases, edition.id)
    assert len(rows_for_dashboard) == 2
    assert rows_for_dashboard[0].status == "inactive"
    assert rows_for_dashboard[0].alert is True
    assert rows_for_dashboard[1].status == "completed"
    assert rows_for_dashboard[1].alert is False

    contexts = {
        (summaries[0].enrollment_id, edition.id): MessageContext(
            "Alumno sintético 001", course.name, edition.label, "contexto sintético"
        )
    }
    recommendations = recommend_communications(
        (*summaries, summaries[0]),
        (*cases, cases[0]),
        (),
        RECOMMENDATIONS,
        as_of=AS_OF,
        message_contexts=contexts,
    )
    assert len(recommendations) == 2
    assert len({item.recommendation_id for item in recommendations}) == len(recommendations)
    assert {item.trigger for item in recommendations} == {"inactive", "pending_evaluations"}
    assert all(
        item.rendered_message and "Alumno sintético 001" in item.rendered_message
        for item in recommendations
    )

    communication_repository = CommunicationRecordRepository(database)
    for index, recommendation in enumerate(recommendations, start=1):
        communication_repository.save(
            CommunicationRecord(
                UUID(int=500 + index),
                enrollments[0],
                recommendation.communication_type,
                recommendation.reason,
                AS_OF,
                CommunicationStatus.SUGGESTED,
                deduplication_key=recommendation.recommendation_id,
                recommendation_id=recommendation.recommendation_id,
                trigger=recommendation.trigger,
                edition_id=edition.id,
            )
        )
    history = CommunicationHistoryAdapter(communication_repository, edition_id=edition.id)
    assert len(tuple(history)) == 2
    assert (
        recommend_communications(
            summaries, cases, history, RECOMMENDATIONS, as_of=AS_OF, message_contexts=contexts
        )
        == ()
    )

    repeat = recommend_communications(
        tuple(reversed(summaries)),
        tuple(reversed(cases)),
        (),
        RECOMMENDATIONS,
        as_of=AS_OF,
        message_contexts=contexts,
    )
    assert repeat == recommendations


def test_import_diagnostic_is_safe_and_reproducible(tmp_path: Path) -> None:
    source = tmp_path / "synthetic-invalid.csv"
    source.write_text("student_id,student_name,progress\nstudent-001,,10\n", encoding="utf-8")
    result = read_tabular(
        source,
        config=TabularImportConfig(required_non_empty_columns=("student_name",)),
    )
    assert not result.accepted
    assert len(result.rejected) == 1
    diagnostic = result.rejected[0]
    assert diagnostic.code is RejectionCode.MISSING_EVIDENCE
    assert diagnostic.provenance.source_name == source.name
    assert diagnostic.provenance.row_number == 1
    assert diagnostic.fields == ("student_name",)
    assert "student-001" not in diagnostic.message
    assert (
        read_tabular(
            source, config=TabularImportConfig(required_non_empty_columns=("student_name",))
        )
        == result
    )
