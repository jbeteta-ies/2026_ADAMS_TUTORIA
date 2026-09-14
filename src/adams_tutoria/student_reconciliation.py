"""Application boundary for importing the internal student spreadsheet contract.

The Excel contract deliberately stops at ``StudentRecord``.  This module is
the small orchestration layer that supplies the manually selected edition and
hands normalized candidates to the existing auditable lifecycle.  It does not
parse source files, resolve by descriptive fields, or create editions.
"""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from uuid import UUID

from adams_tutoria.domain import ImportBatch
from adams_tutoria.enrollment_lifecycle import EnrollmentLifecycleService, LifecycleResult
from adams_tutoria.excel_contract import StudentRecord
from adams_tutoria.import_contract import (
    EditionEvidence,
    EnrollmentEvidence,
    ImportCandidate,
    ImportEntity,
    Provenance,
    ResolutionReference,
    StudentEvidence,
)


class StudentReconciliationService:
    """Reconcile normalized student records with one existing edition.

    ``edition_reference`` is an application-owned reference (normally the
    UUID of an edition).  The lifecycle validates it in the same transaction
    that applies the changes, so a missing edition cannot be created as a
    side-effect.
    """

    def __init__(self, path: Path) -> None:
        self._lifecycle = EnrollmentLifecycleService(path)

    def apply_records(
        self,
        batch: ImportBatch,
        records: Iterable[StudentRecord],
        edition_reference: UUID | str,
        occurred_at: datetime,
    ) -> LifecycleResult:
        """Convert #73 records to enrollment candidates and apply them.

        Records without the stable composite identity are rejected by the
        contract-to-candidate boundary rather than matched by name or email.
        Callers should use the adapter's ``ImportResult.rejected`` diagnostics
        for malformed source rows before invoking this method.
        """

        candidates = (
            self._candidate(record, edition_reference, number)
            for number, record in enumerate(records, 1)
        )
        return self._lifecycle.apply(batch, candidates, occurred_at)

    def apply_candidates(
        self,
        batch: ImportBatch,
        candidates: Iterable[ImportCandidate],
        occurred_at: datetime,
    ) -> LifecycleResult:
        """Apply already normalized student/enrollment candidates.

        Student-only candidates are associated with the batch's existing
        edition scope.  Enrollment candidates are passed through unchanged,
        preserving the established lifecycle semantics.
        """

        normalized = (self._associate_student(candidate, batch) for candidate in candidates)
        return self._lifecycle.apply(batch, normalized, occurred_at)

    @staticmethod
    def _candidate(
        record: StudentRecord, edition_reference: UUID | str, row_number: int
    ) -> ImportCandidate:
        if record.identity is None:
            raise ValueError("stable external student identity is required")
        student = StudentEvidence(
            name=record.name,
            email=record.email,
            external_identity=record.identity,
        )
        provenance = record.provenance or Provenance("normalized-students", "contract", row_number)
        return ImportCandidate(
            entity=ImportEntity.ENROLLMENT,
            provenance=provenance,
            enrollment=EnrollmentEvidence(
                enrollment_reference=ResolutionReference(record.identity.source_student_id),
                student=student,
                edition=EditionEvidence(ResolutionReference(edition_reference)),
            ),
            action=record.action,
            group=record.group,
        )

    @staticmethod
    def _associate_student(candidate: ImportCandidate, batch: ImportBatch) -> ImportCandidate:
        if candidate.entity is not ImportEntity.STUDENT:
            return candidate
        if not batch.scope_reference:
            raise ValueError("student candidates require an existing edition scope")
        if candidate.student is None or candidate.student.external_identity is None:
            return candidate
        identity = candidate.student.external_identity
        return ImportCandidate(
            entity=ImportEntity.ENROLLMENT,
            provenance=candidate.provenance,
            enrollment=EnrollmentEvidence(
                enrollment_reference=ResolutionReference(identity.source_student_id),
                student=candidate.student,
                edition=EditionEvidence(ResolutionReference(batch.scope_reference)),
            ),
            values=candidate.values,
            action=candidate.action,
            group=candidate.group,
        )
