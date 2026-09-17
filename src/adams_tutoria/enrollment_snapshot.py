"""Complete, edition-scoped student/enrollment snapshot import."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from uuid import UUID

from adams_tutoria.domain import ImportBatch
from adams_tutoria.enrollment_lifecycle import EnrollmentLifecycleService, LifecycleResult
from adams_tutoria.excel_contract import EnrollmentSnapshotRecord
from adams_tutoria.import_contract import (
    EditionEvidence,
    EnrollmentEvidence,
    ExternalStudentIdentity,
    ImportCandidate,
    ImportEntity,
    ResolutionReference,
    StudentEvidence,
)


class EnrollmentSnapshotService:
    """Turn snapshot rows into full-scope candidates for the existing lifecycle."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def candidates(
        self, records: Iterable[EnrollmentSnapshotRecord], edition_id: UUID
    ) -> tuple[ImportCandidate, ...]:
        return tuple(
            ImportCandidate(
                ImportEntity.ENROLLMENT,
                record.provenance,
                enrollment=EnrollmentEvidence(
                    enrollment_reference=ResolutionReference(record.dni),
                    student=StudentEvidence(
                        name=record.full_name,
                        external_identity=ExternalStudentIdentity("dni", "global", record.dni),
                    ),
                    edition=EditionEvidence(ResolutionReference(edition_id)),
                ),
                action="snapshot",
            )
            for record in records
        )

    def apply(
        self,
        batch: ImportBatch,
        records: Iterable[EnrollmentSnapshotRecord],
        edition_id: UUID,
        occurred_at: datetime,
    ) -> LifecycleResult:
        if batch.scope_type != "full" or batch.scope_reference != str(edition_id):
            raise ValueError("snapshot batch must be full and scoped to the selected edition")
        return EnrollmentLifecycleService(self.path).apply(
            batch, self.candidates(records, edition_id), occurred_at
        )
