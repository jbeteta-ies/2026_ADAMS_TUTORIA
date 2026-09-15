"""Small Streamlit shell for the local import operation.

This module owns presentation only.  It deliberately does not define ADAMS
headers or parsing rules; callers provide a prepared operation built with the
approved source adapter and contracts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from adams_tutoria.import_operation import ImportOperationService, PreparedImport

IMPORT_TYPES = ("Alumnos y matrículas", "Progreso", "Evaluaciones")


def render_import_operation(
    service: ImportOperationService,
    prepared: PreparedImport | None = None,
) -> PreparedImport | None:
    """Render one local XLSX operation and an explicit total confirmation."""
    st.title("Importación local")
    st.caption("Solo XLSX · sin conexión remota · revisión total antes de aplicar")
    import_type = st.selectbox("Tipo de importación", IMPORT_TYPES)
    uploaded = st.file_uploader("Archivo XLSX", type=["xlsx"], key="import_xlsx")
    st.info(
        f"Tipo seleccionado: {import_type}. La aplicación no presupone columnas ADAMS; "
        "la adaptación se realiza mediante los contratos existentes."
    )
    if uploaded is None:
        _render_history(service)
        return prepared
    st.write({"archivo": "local-xlsx", "tamaño": uploaded.size})
    st.warning(
        "La revisión requiere una adaptación explícita del archivo al contrato. "
        "No se generan cursos ni ediciones automáticamente."
    )
    _render_history(service)
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
                idempotency_key=f"ui-{prepared.preview.preview_id}",
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


def _render_preview(prepared: PreparedImport) -> None:
    preview = prepared.preview
    st.subheader("Preview")
    st.write(
        {
            "cambios": len(preview.changes),
            "rechazadas": prepared.rejected_rows,
            "advertencias": prepared.warnings,
        }
    )
    st.dataframe(
        [
            {
                "entidad": c.entity,
                "resultado": c.change_type.value,
                "fila": c.source_row_number,
                "código": c.diagnostic_code,
            }
            for c in preview.changes
        ],
        hide_index=True,
        use_container_width=True,
    )


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
    service = ImportOperationService("data/local/adams_tutoria.sqlite3")
    render_import_operation(service)


if __name__ == "__main__":
    main()
