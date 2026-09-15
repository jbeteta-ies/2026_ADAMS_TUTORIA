from datetime import UTC, datetime
from pathlib import Path

from adams_tutoria.import_operation import ImportOperationService
from adams_tutoria.import_pipeline import InMemoryImportAdapter, dataset_from
from adams_tutoria.persistence.database import initialize_database


def test_synthetic_non_excel_adapter_reaches_common_preview(tmp_path: Path) -> None:
    service = ImportOperationService(tmp_path / "synthetic.sqlite3")
    initialize_database(tmp_path / "synthetic.sqlite3")
    prepared = service.prepare(
        InMemoryImportAdapter(dataset_from()),
        "synthetic-memory",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert prepared.batch.source_name == "local-source"
    assert prepared.preview.changes == ()
