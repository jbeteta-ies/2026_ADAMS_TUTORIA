from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.domain import ImportChangeType, ImportSourceType
from adams_tutoria.import_operation import ImportOperationService, PreparedImport
from adams_tutoria.import_review import ImportPreview, PreviewChange
from adams_tutoria.persistence.database import initialize_database


def test_operation_accepts_only_xlsx_at_ui_boundary(tmp_path: Path) -> None:
    service = ImportOperationService(tmp_path / "synthetic.sqlite3")
    with pytest.raises(ValueError, match="only .xlsx"):
        service.read_xlsx(tmp_path / "synthetic.csv")


@pytest.mark.parametrize(
    ("adapter_kind", "expected"),
    [("xlsx", ImportSourceType.EXCEL), ("csv", ImportSourceType.CSV)],
)
def test_adapter_format_maps_to_persisted_source_type(
    tmp_path: Path, adapter_kind: str, expected: ImportSourceType
) -> None:
    database_path = tmp_path / "synthetic.sqlite3"
    service = ImportOperationService(database_path)
    initialize_database(database_path)
    prepared = service.preview(
        "synthetic-source",
        source_kind=adapter_kind,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert prepared.batch.source_type is expected


def test_blocking_preview_cannot_be_confirmed(tmp_path: Path) -> None:
    service = ImportOperationService(tmp_path / "synthetic.sqlite3")
    preview = ImportPreview(
        uuid4(),
        "digest",
        "state",
        datetime(2026, 1, 1, tzinfo=UTC),
        (PreviewChange("student", ImportChangeType.REJECTED),),
    )
    prepared = PreparedImport(
        preview=preview,
        batch=None,
        rejected_rows=0,
        warnings=0,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="blocked"):
        service.confirm(
            prepared,
            operator_reference=None,
            timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            idempotency_key="synthetic",
        )


def test_import_ui_is_local_xlsx_only_and_exposes_three_types() -> None:
    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).parents[2] / "src/adams_tutoria/import_ui.py"
    app = AppTest.from_file(app_path).run()

    assert not app.exception
    assert app.file_uploader[0].label == "Fuente local"
    assert app.selectbox[0].options == ["Alumnos y matrículas", "Progreso", "Evaluaciones"]
