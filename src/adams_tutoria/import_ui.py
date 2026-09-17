"""Small Streamlit shell for the local import operation.

This module owns presentation only.  It deliberately does not define ADAMS
headers or parsing rules; callers provide a prepared operation built with the
approved source adapter and contracts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from adams_tutoria.domain import ImportChangeType
from adams_tutoria.import_operation import ImportOperationService, PreparedImport
from adams_tutoria.import_review import ImportPreview

IMPORT_TYPES = ("Alumnos y matrículas", "Progreso", "Evaluaciones")


def render_import_operation(
    service: ImportOperationService,
    prepared: PreparedImport | None = None,
) -> PreparedImport | None:
    """Render one local XLSX operation and an explicit total confirmation."""
    st.title("Importación local")
    st.caption("Fuente local · sin conexión remota · revisión total antes de aplicar")
    import_type = st.selectbox("Tipo de importación", IMPORT_TYPES)
    edition_id = _render_edition_selection(service)
    uploaded = st.file_uploader("Fuente local", type=["xlsx"], key="import_source")
    st.info(
        f"Tipo seleccionado: {import_type}. La aplicación no presupone columnas ADAMS; "
        "la adaptación se realiza mediante los contratos existentes."
    )
    if uploaded is None:
        _render_history(service)
        return prepared
    st.write({"fuente": "local", "tamaño": uploaded.size})
    st.warning(
        "La revisión requiere una adaptación explícita del archivo al contrato. "
        "No se generan cursos ni ediciones automáticamente."
    )
    _render_history(service)
    if prepared is None and import_type == "Alumnos y matrículas":
        try:
            prepared = service.prepare_snapshot_xlsx(
                uploaded, edition_id=edition_id, created_at=datetime.now(UTC)
            )
        except Exception as error:
            st.error(f"No se pudo preparar el snapshot: {type(error).__name__}")
            return None
    if prepared is None:
        st.caption("La UI presenta el punto de operación; el adaptador entrega el PreparedImport.")
        return None
    _render_preview(prepared)
    if prepared.blocked:
        st.error("No se puede confirmar: existen filas rechazadas, conflictos o errores.")
        return prepared
    confirmed = st.checkbox("He revisado todos los cambios y confirmo aplicar el lote completo")
    if confirmed and st.button("Aplicar importación completa", type="primary"):
        try:
            result = service.confirm(
                prepared,
                operator_reference="local-operator",
                timestamp=datetime.now(UTC),
                idempotency_key=f"snapshot-{prepared.batch.source_fingerprint}-{edition_id}",
            )
        except Exception as error:
            st.error(f"No se pudo confirmar la importación: {type(error).__name__}")
        else:
            st.success(
                "Importación aplicada." if result.applied else "La importación no se aplicó."
            )
            if result.error:
                st.error("La operación fue revertida por un error transaccional.")
    return prepared


def _render_edition_selection(service: ImportOperationService) -> str:
    """Persist the operator's existing course/edition selection in session state."""
    try:
        from adams_tutoria.persistence.database import connection

        with connection(Path(service.database_path)) as db:
            rows = db.execute(
                "SELECT e.id, c.name || ' · ' || e.label AS label "
                "FROM edition e JOIN course c ON c.id=e.course_id ORDER BY c.name, e.label"
            ).fetchall()
    except Exception:
        rows = []
    if not rows:
        st.warning("Debe existir al menos una edición antes de importar un snapshot.")
        return ""
    options = {row["id"]: row["label"] for row in rows}
    selected = st.selectbox(
        "Curso y edición existente",
        list(options),
        format_func=lambda value: options[value],
        key="snapshot_edition_id",
    )
    return selected


def _render_preview(prepared: PreparedImport) -> None:
    preview = prepared.preview
    st.subheader("Preview")
    st.write(
        {
            "altas": _count_operations(preview, "created"),
            "cambios de nombre": _count_name_changes(preview),
            "bajas lógicas": _count_operations(preview, "absent"),
            "reactivaciones": _count_operations(preview, "reactivated"),
            "sin cambios": _count_operations(preview, "unchanged"),
            "conflictos": _count_types(preview, ImportChangeType.CONFLICT),
            "rechazadas": prepared.rejected_rows,
            "errores": _count_types(preview, ImportChangeType.ERROR),
            "advertencias": prepared.warnings,
        }
    )
    st.dataframe(
        [
            {
                "entidad": c.entity,
                "resultado": c.change_type.value,
                "operación": _operation_label(c.operation),
                "fila": c.source_row_number,
                "código": c.diagnostic_code,
            }
            for c in preview.changes
        ],
        hide_index=True,
        use_container_width=True,
    )


def _count_operations(preview: ImportPreview, operation: str, *, entity: str | None = None) -> int:
    changes = preview.changes
    return sum(
        1
        for change in changes
        if change.operation == operation and (entity is None or change.entity == entity)
    )


def _count_name_changes(preview: ImportPreview) -> int:
    """Count snapshot name changes emitted for either affected entity type.

    The lifecycle records a snapshot rename on the student and returns the
    resulting enrollment operation in the preview.  Both representations are
    valid for the UI counter; the enrollment is not a different operation.
    """
    return sum(
        1
        for change in preview.changes
        if change.operation == "modified" and change.entity in {"student", "enrollment"}
    )


def _count_types(preview: ImportPreview, change_type: ImportChangeType) -> int:
    return sum(1 for change in preview.changes if change.change_type == change_type)


def _operation_label(operation: str | None) -> str:
    return {
        "created": "alta",
        "modified": "cambio",
        "absent": "baja lógica",
        "reactivated": "reactivación",
        "unchanged": "sin cambios",
        "conflict": "conflicto",
        "rejected": "rechazo",
        "error": "error",
    }.get(operation or "", operation or "desconocido")


def _render_history(service: ImportOperationService) -> None:
    """Show only safe import metadata; never raw rows or source paths."""
    try:
        from adams_tutoria.persistence.database import connection

        with connection(Path(service.database_path)) as db:
            rows = db.execute(
                "SELECT source_type, status, total_count, accepted_count, rejected_count, "
                "warning_count, error_count, started_at "
                "FROM import_batch ORDER BY started_at DESC LIMIT 20"
            ).fetchall()
    except Exception:
        rows = []
    st.subheader("Historial reciente")
    st.dataframe([dict(row) for row in rows], hide_index=True, use_container_width=True)


def main() -> None:
    database = Path("data/local/adams_tutoria.sqlite3")
    from adams_tutoria.persistence.database import initialize_database

    initialize_database(database)
    service = ImportOperationService(database)
    render_import_operation(service)


if __name__ == "__main__":
    main()
