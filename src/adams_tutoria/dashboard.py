"""Initial Streamlit shell for the local ADAMS Tutoria dashboard.

This module deliberately contains only synthetic catalog data. Persistence,
imports, ADAMS integrations, and operational data belong to future Issues.
"""

from dataclasses import dataclass
from decimal import Decimal

import streamlit as st

from adams_tutoria.attention import (
    AttentionConfig,
    PriorityThresholds,
    prioritize_attention,
)
from adams_tutoria.demo_summary import demo_edition_id, demo_enrollment_summaries
from adams_tutoria.student_tracking import (
    filter_tracking_rows,
    prepare_tracking_rows,
    select_tracking_detail,
    sort_tracking_rows,
)
from adams_tutoria.summary import summarize_edition


@dataclass(frozen=True)
class CourseOption:
    """Synthetic course option with a stable identifier."""

    id: str
    name: str
    code: str


@dataclass(frozen=True)
class EditionOption:
    """Synthetic edition option with a stable identifier and course link."""

    id: str
    course_id: str
    label: str


COURSES: tuple[CourseOption, ...] = (
    CourseOption("course-demo-alpha", "Curso de demostración Alpha", "DEMO-A"),
    CourseOption("course-demo-beta", "Curso de demostración Beta", "DEMO-B"),
)

EDITIONS: tuple[EditionOption, ...] = (
    EditionOption("edition-alpha-2026-1", "course-demo-alpha", "Edición 2026 · 1ª convocatoria"),
    EditionOption("edition-alpha-2026-2", "course-demo-alpha", "Edición 2026 · 2ª convocatoria"),
    EditionOption("edition-beta-2026-1", "course-demo-beta", "Edición 2026 · 1ª convocatoria"),
)


def editions_for_course(course_id: str) -> tuple[EditionOption, ...]:
    """Return synthetic editions belonging to *course_id*."""

    return tuple(edition for edition in EDITIONS if edition.course_id == course_id)


def _option_label(option: CourseOption | EditionOption) -> str:
    """Build a stable, human-readable selector label."""

    if isinstance(option, CourseOption):
        return f"{option.code} — {option.name}"
    return option.label


def _initial_selection() -> None:
    """Initialize only the dashboard selection state."""

    st.session_state.setdefault("course_id", COURSES[0].id)
    initial_editions = editions_for_course(st.session_state["course_id"])
    st.session_state.setdefault("edition_id", initial_editions[0].id)


def _render_selection() -> tuple[CourseOption, EditionOption]:
    """Render independent course/edition selectors and return their values."""

    course_ids = [course.id for course in COURSES]
    current_course_id = st.session_state["course_id"]
    if current_course_id not in course_ids:
        current_course_id = course_ids[0]
    selected_course_id = st.sidebar.selectbox(
        "Curso",
        course_ids,
        index=course_ids.index(current_course_id),
        format_func=lambda course_id: _option_label(
            next(course for course in COURSES if course.id == course_id)
        ),
        key="course_id",
    )
    selected_editions = editions_for_course(selected_course_id)
    edition_ids = [edition.id for edition in selected_editions]
    current_edition_id = st.session_state.get("edition_id")
    if current_edition_id not in edition_ids:
        current_edition_id = edition_ids[0]
        st.session_state["edition_id"] = current_edition_id
    selected_edition_id = st.sidebar.selectbox(
        "Edición",
        edition_ids,
        index=edition_ids.index(current_edition_id),
        format_func=lambda edition_id: _option_label(
            next(edition for edition in selected_editions if edition.id == edition_id)
        ),
        key="edition_id",
    )
    course = next(course for course in COURSES if course.id == selected_course_id)
    edition = next(edition for edition in selected_editions if edition.id == selected_edition_id)
    return course, edition


def _render_page(course: CourseOption, edition: EditionOption, page: str) -> None:
    """Render a placeholder page without loading operational data."""

    if page == "Inicio":
        st.title("Dashboard de tutoría")
        st.write("Shell inicial del dashboard local.")
        st.info(
            "Los datos mostrados son sintéticos. "
            "Las fuentes operativas se añadirán en futuras Issues."
        )
    elif page == "Curso":
        st.title("Curso")
        st.subheader(course.name)
        st.caption(f"ID estable: {course.id}")
        st.info("Placeholder: aquí se mostrarán futuros indicadores del curso.")
    else:
        st.title("Edición")
        st.subheader(edition.label)
        st.caption(f"ID estable: {edition.id} · Curso: {course.id}")
        metrics = summarize_edition(
            demo_edition_id(edition.id), demo_enrollment_summaries(edition.id)
        )
        columns = st.columns(6)
        for column, label, value in zip(
            columns,
            (
                "Total",
                "No iniciados",
                "Inactivos",
                "Evaluaciones pendientes",
                "Finalizados",
                "Requieren atención",
            ),
            (
                metrics.total,
                metrics.not_started,
                metrics.inactive,
                metrics.pending_evaluations,
                metrics.completed,
                metrics.needs_attention,
            ),
            strict=True,
        ):
            column.metric(label, value)

        summaries = demo_enrollment_summaries(edition.id)
        attention = prioritize_attention(
            summaries,
            AttentionConfig(
                {
                    "progress_unknown": Decimal("3"),
                    "not_started": Decimal("2"),
                    "inactive": Decimal("2"),
                    "pending_evaluations": Decimal("1"),
                    "completed": Decimal("0"),
                },
                PriorityThresholds(Decimal("1"), Decimal("2"), Decimal("3")),
            ),
            edition_id=demo_edition_id(edition.id),
        )
        rows = prepare_tracking_rows(summaries, attention, demo_edition_id(edition.id))
        st.subheader("Seguimiento de matrículas")
        status_options = ["Todos"] + sorted({row.status for row in rows})
        selected_status = st.selectbox("Estado", status_options, key="tracking_status")
        alert_filter = st.selectbox(
            "Alerta", ("Todas", "Con alerta", "Sin alerta"), key="tracking_alert"
        )
        sort_options = {
            "Prioridad": "priority",
            "Estado": "status",
            "Progreso": "progress",
            "Última actividad": "last_activity",
            "Evaluaciones pendientes": "pending_evaluations",
        }
        selected_sort = st.selectbox("Ordenar por", tuple(sort_options), key="tracking_sort")
        descending = st.checkbox("Orden descendente", key="tracking_descending")
        visible_rows = filter_tracking_rows(
            rows,
            status=None if selected_status == "Todos" else selected_status,
            alert=None if alert_filter == "Todas" else alert_filter == "Con alerta",
        )
        visible_rows = sort_tracking_rows(
            visible_rows, sort_by=sort_options[selected_sort], descending=descending
        )
        table = [
            {
                "Matrícula": str(row.enrollment_id),
                "Estado": row.status,
                "Progreso": None if row.progress is None else f"{row.progress}%",
                "Alerta": "Sí" if row.alert else "No",
                "Prioridad": None if row.priority is None else row.priority.value,
                "Razón": row.reason,
                "Última actividad": row.last_activity,
                "Evaluaciones pendientes": row.pending_evaluations,
            }
            for row in visible_rows
        ]
        st.dataframe(table, use_container_width=True, hide_index=True)
        if visible_rows:
            selected_enrollment = st.selectbox(
                "Matrícula",
                [row.enrollment_id for row in visible_rows],
                format_func=str,
                key="tracking_enrollment",
            )
            detail = select_tracking_detail(summaries, visible_rows, selected_enrollment)
            if detail is not None:
                st.caption(f"Detalle de {detail.row.enrollment_id}")
                st.write(
                    {
                        "Estado": detail.row.status,
                        "Progreso": detail.row.progress,
                        "Última actividad": detail.row.last_activity,
                        "Evaluaciones pendientes": detail.summary.evaluations.pending,
                        "Razones": detail.row.reason,
                    }
                )
        else:
            st.info("No hay matrículas que coincidan con los filtros.")


def main() -> None:
    """Run the Streamlit dashboard shell."""

    st.set_page_config(page_title="ADAMS Tutoria", page_icon="📚", layout="wide")
    _initial_selection()
    st.sidebar.title("Navegación")
    page = st.sidebar.radio("Sección", ("Inicio", "Curso", "Edición"))
    course, edition = _render_selection()
    _render_page(course, edition, page)


if __name__ == "__main__":
    main()
