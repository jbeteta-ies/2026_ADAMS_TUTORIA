"""Application-facing orchestration for source-independent imports.

The module is intentionally independent from Streamlit.  It accepts normalized
contracts produced by the existing adapters and delegates preview/application
to :class:`ImportReviewService`; it never stores a source file or raw rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID, uuid4

from adams_tutoria.domain import (
    ImportBatch,
    ImportBatchStatus,
    ImportChangeType,
    ImportSourceType,
)
from adams_tutoria.excel_contract import (
    EnrollmentSnapshotAdapter,
    EnrollmentSnapshotRecord,
    EvaluationRecord,
    ProgressRecord,
)
from adams_tutoria.import_contract import ImportCandidate, ImportResult
from adams_tutoria.import_pipeline import ImportDatasetAdapter
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
    """Safe result of adapting one source and generating its preview."""

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
        path: str | Path | BinaryIO, *, config: TabularImportConfig | None = None
    ) -> ImportResult[TabularRow]:
        """Read only XLSX input at this operation boundary."""
        suffix = Path(path).suffix.lower() if isinstance(path, (str, Path)) else ".xlsx"
        if suffix != ".xlsx":
            raise ValueError("the local operation accepts only .xlsx files")
        return read_tabular(path, config=config)

    def prepare(
        self,
        adapter: ImportDatasetAdapter,
        source_name: str,
        *,
        context: str | None = None,
        source_fingerprint: str | None = None,
        created_at: datetime,
    ) -> PreparedImport:
        """Run an adapter through the common pipeline up to preview."""
        result = adapter.load()
        if len(result.accepted) != 1:
            raise ValueError("an adapter must return exactly one normalized dataset")
        item = result.accepted[0]
        return self.preview(
            source_name,
            source_kind="other",
            candidates=item.candidates,
            progress=item.progress,
            evaluations=item.evaluations,
            rejected_rows=len(result.rejected),
            warnings=len(result.warnings),
            context=context,
            source_fingerprint=source_fingerprint,
            created_at=created_at,
        )

    def prepare_snapshot_xlsx(
        self, path: str | Path | BinaryIO, *, edition_id: str, created_at: datetime
    ) -> PreparedImport:
        """Adapt a complete XLSX snapshot for an already selected edition."""
        source = _uploaded_bytes(path)
        result = self.read_xlsx(source)
        adapted = EnrollmentSnapshotAdapter(source_name="local-snapshot").adapt(result.accepted)
        records: tuple[EnrollmentSnapshotRecord, ...] = adapted.accepted
        from adams_tutoria.enrollment_snapshot import EnrollmentSnapshotService

        candidates = EnrollmentSnapshotService(self.database_path).candidates(
            records, UUID(edition_id)
        )
        return self.preview(
            "local-snapshot",
            candidates=candidates,
            rejected_rows=len(result.rejected) + len(adapted.rejected),
            context=edition_id,
            source_kind="xlsx",
            source_fingerprint=fingerprint_file(source),
            created_at=created_at,
            scope_type="full",
            scope_reference=edition_id,
        )

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
        source_kind: str = "other",
        created_at: datetime,
        scope_type: str = "partial",
        scope_reference: str | None = None,
    ) -> PreparedImport:
        """Create a safe preview; no file or input row is retained."""
        candidates, progress, evaluations = tuple(candidates), tuple(progress), tuple(evaluations)
        total = len(candidates) + len(progress) + len(evaluations) + rejected_rows
        batch = ImportBatch(
            uuid4(),
            _source_type(source_kind),
            _safe_source_name(source_name, source_kind),
            created_at,
            ImportBatchStatus.CONFIRMED,
            context=context,
            source_fingerprint=source_fingerprint,
            total_count=total,
            accepted_count=total - rejected_rows,
            rejected_count=rejected_rows,
            warning_count=warnings,
            scope_type=scope_type,
            scope_reference=scope_reference,
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


def fingerprint_file(path: str | Path | BinaryIO) -> str:
    """Return a digest without retaining the source content."""
    digest = sha256()
    if isinstance(path, (str, Path)):
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    else:
        position = path.tell()
        path.seek(0)
        for chunk in iter(lambda: path.read(1024 * 1024), b""):
            digest.update(chunk)
        path.seek(position)
    return digest.hexdigest()


def _uploaded_bytes(source: str | Path | BinaryIO) -> str | Path | BinaryIO:
    """Normalize Streamlit's UploadedFile without retaining an uploaded file."""
    if isinstance(source, (str, Path)):
        return source
    if hasattr(source, "getvalue"):
        getvalue = cast(Any, source).getvalue
        return BytesIO(getvalue())
    return source


def _source_type(kind: str) -> ImportSourceType:
    # ``xlsx`` is the adapter's format label, while the persisted domain
    # vocabulary calls that source type ``excel``.  Keep that translation at
    # the application boundary instead of exposing adapter-specific labels in
    # persistence.
    if kind == "xlsx":
        return ImportSourceType.EXCEL
    try:
        return ImportSourceType(kind)
    except ValueError:
        return ImportSourceType.OTHER


def _safe_source_name(name: str, source_kind: str) -> str:
    """Avoid persisting local paths or user-provided names as provenance."""
    return f"local-{source_kind}" if source_kind in {"xlsx", "csv"} else "local-source"
