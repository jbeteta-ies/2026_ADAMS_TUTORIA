"""Application-facing orchestration for local spreadsheet imports.

The module is intentionally independent from Streamlit.  It accepts normalized
contracts produced by the existing adapters and delegates preview/application
to :class:`ImportReviewService`; it never stores a source file or raw rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from adams_tutoria.domain import (
    ImportBatch,
    ImportBatchStatus,
    ImportChangeType,
    ImportSourceType,
)
from adams_tutoria.excel_contract import EvaluationRecord, ProgressRecord
from adams_tutoria.import_contract import ImportCandidate, ImportResult
from adams_tutoria.import_review import (
    ConfirmationRequest,
    ConfirmationResult,
    ImportPreview,
    ImportReviewService,
)
from adams_tutoria.tabular_import import TabularImportConfig, TabularRow, read_tabular

BLOCKING_CHANGE_TYPES = frozenset(
    {ImportChangeType.REJECTED, ImportChangeType.CONFLICT, ImportChangeType.ERROR}
)


@dataclass(frozen=True, slots=True)
class PreparedImport:
    """Safe result of reading and adapting one local XLSX source."""

    batch: ImportBatch
    preview: ImportPreview
    rejected_rows: int
    warnings: int

    @property
    def blocked(self) -> bool:
        return self.rejected_rows > 0 or any(
            change.change_type in BLOCKING_CHANGE_TYPES for change in self.preview.changes
        )


class ImportOperationService:
    """Coordinate source reading, adaptation, preview and total confirmation."""

    def __init__(
        self, database_path: str | Path, review: ImportReviewService | None = None
    ) -> None:
        self.database_path = database_path
        self.review = review or ImportReviewService(database_path)

    @staticmethod
    def read_xlsx(
        path: str | Path, *, config: TabularImportConfig | None = None
    ) -> ImportResult[TabularRow]:
        """Read only XLSX input at this operation boundary."""
        if Path(path).suffix.lower() != ".xlsx":
            raise ValueError("the local operation accepts only .xlsx files")
        return read_tabular(path, config=config)

    def preview(
        self,
        source_name: str,
        *,
        candidates: Iterable[ImportCandidate] = (),
        progress: Iterable[ProgressRecord] = (),
        evaluations: Iterable[EvaluationRecord] = (),
        rejected_rows: int = 0,
        warnings: int = 0,
        context: str | None = None,
        source_fingerprint: str | None = None,
        created_at: datetime,
    ) -> PreparedImport:
        """Create a safe preview; no file or input row is retained."""
        candidates, progress, evaluations = tuple(candidates), tuple(progress), tuple(evaluations)
        total = len(candidates) + len(progress) + len(evaluations) + rejected_rows
        batch = ImportBatch(
            uuid4(),
            ImportSourceType.EXCEL,
            _safe_source_name(source_name),
            created_at,
            ImportBatchStatus.CONFIRMED,
            context=context,
            source_fingerprint=source_fingerprint,
            total_count=total,
            accepted_count=total - rejected_rows,
            rejected_count=rejected_rows,
            warning_count=warnings,
        )
        preview = self.review.preview(
            batch,
            candidates=candidates,
            progress=progress,
            evaluations=evaluations,
            created_at=created_at,
        )
        return PreparedImport(batch, preview, rejected_rows, warnings)

    def confirm(
        self,
        prepared: PreparedImport,
        *,
        operator_reference: str | None,
        timestamp: datetime,
        idempotency_key: str,
    ) -> ConfirmationResult:
        """Apply only after an explicit, all-record confirmation."""
        if prepared.blocked:
            raise ValueError("confirmation is blocked while rejected, conflict or error rows exist")
        return self.review.confirm(
            ConfirmationRequest(
                prepared.preview.preview_id,
                prepared.preview.digest,
                "all",
                timestamp,
                idempotency_key,
                operator_reference,
            )
        )


def fingerprint_file(path: str | Path) -> str:
    """Return a digest without retaining the source content."""
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source_name(name: str) -> str:
    """Avoid persisting local paths or user-provided names as provenance."""
    return "local-xlsx"
