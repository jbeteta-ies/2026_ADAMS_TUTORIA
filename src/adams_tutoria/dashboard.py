"""Initial Streamlit shell for the local ADAMS Tutoria dashboard.

This module deliberately contains only synthetic catalog data. Persistence,
imports, ADAMS integrations, and operational data belong to future Issues.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import streamlit as st

from adams_tutoria.attention import (
    AttentionConfig,
    PriorityThresholds,
    prioritize_attention,
)
from adams_tutoria.config import default_config
from adams_tutoria.content_search import MarkdownIndex
from adams_tutoria.demo_profile import demo_profile
from adams_tutoria.demo_summary import demo_edition_id, demo_enrollment_summaries
from adams_tutoria.domain import (
    CommunicationStatus,
    ContentSource,
    ContentSourceType,
    Course,
    TutorAction,
)
from adams_tutoria.message_templates import MessageContext, render_message
from adams_tutoria.persistence.database import database_path, initialize_database
from adams_tutoria.persistence.repositories import (
    CommunicationRecordRepository,
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    StudentRepository,
    TutorActionRepository,
)
from adams_tutoria.question_assistant import QuestionAssistant
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
        _render_question_assistant(course)
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
                _render_student_profile(detail.row.enrollment_id)
        else:
            st.info("No hay matrículas que coincidan con los filtros.")


def _assistant_course(option: CourseOption) -> Course:
    """Build a synthetic course reference for the dashboard demo."""
    content_root = Path(__file__).with_name("demo_question_content") / option.id
    return Course(
        uuid5(UUID("00000000-0000-0000-0000-000000000029"), option.id),
        option.name,
        code=option.code,
        content_source=ContentSource(ContentSourceType.LOCAL_PATH, str(content_root)),
    )


def _render_question_assistant(option: CourseOption) -> None:
    """Render a local, human-reviewed question-answer draft."""
    st.subheader("Asistente de apoyo para dudas")
    st.caption("Borrador sintético basado solo en el contenido del curso seleccionado.")
    question = st.text_input("Duda", key="question_assistant_input")
    if st.button("Preparar borrador", key="question_assistant_submit"):
        if not question.strip():
            st.warning("Escribe una duda antes de preparar el borrador.")
            return
        index = MarkdownIndex()
        selected_course = _assistant_course(option)
        index.index_course(selected_course)
        draft = QuestionAssistant(index).draft(selected_course, question)
        st.text_area("Borrador (revisión manual)", draft.text, height=180)
        st.write("**Referencias**")
        for reference in draft.references:
            st.caption(f"{reference.path} · {reference.module}/{reference.document}")
            st.code(reference.fragment)


def _render_student_profile(enrollment_id) -> None:
    """Render the detail view using one enrollment as its only scope."""
    config = default_config()
    path = database_path(config)
    initialize_database(path)
    actions_repository = TutorActionRepository(path)
    communications_repository = CommunicationRecordRepository(path)
    try:
        profile = demo_profile(enrollment_id, actions_repository.list_for_enrollment(enrollment_id))
    except StopIteration:
        st.info("La ficha sintética no está disponible para esta matrícula.")
        return
    CourseRepository(path).save(profile.enrollment.edition.course)
    EditionRepository(path).save(profile.enrollment.edition)
    StudentRepository(path).save(profile.enrollment.student)
    EnrollmentRepository(path).save(profile.enrollment)
    for communication in profile.communications:
        if communications_repository.get(communication.id) is None:
            communications_repository.save(communication)
    profile = demo_profile(enrollment_id, actions_repository.list_for_enrollment(enrollment_id))
    st.subheader("Ficha de alumno")
    st.caption(f"Matrícula: {profile.enrollment.id}")
    st.write(
        {
            "Alumno": profile.enrollment.student.full_name,
            "Correo": profile.enrollment.student.email,
            "Progreso": profile.summary.progress.percentage,
            "Evaluaciones pendientes": profile.summary.evaluations.pending,
        }
    )
    st.write("**Evaluaciones**", [evaluation.target_id for evaluation in profile.evaluations])
    st.write(
        "**Alertas y seguimiento**",
        [reason.explanation for reason in profile.summary.follow_up.reasons],
    )
    st.write(
        "**Historial de progreso**",
        [
            {
                "captured_at": snapshot.captured_at.isoformat(),
                "progress": snapshot.progress_percentage,
            }
            for snapshot in profile.snapshots
        ],
    )
    if profile.communications:
        _render_communications(profile, communications_repository)
    st.write("**Acciones del tutor**", [action.action for action in profile.actions])
    with st.form(f"tutor-action-{enrollment_id}"):
        action = st.text_input("Nueva acción del tutor")
        note = st.text_area("Nota de la acción")
        if st.form_submit_button("Registrar acción"):
            if action.strip():
                actions_repository.save(
                    TutorAction(
                        id=uuid4(),
                        enrollment_id=enrollment_id,
                        occurred_at=datetime.now(UTC),
                        action=action.strip(),
                        note=note.strip(),
                    )
                )
                st.success("Acción registrada en el historial local de tutoría.")
                st.rerun()
            else:
                st.warning("Escribe una acción antes de registrar.")


def _render_communications(profile, repository: CommunicationRecordRepository) -> None:
    """Show approved messages and record only explicit manual tutor actions."""
    communications = repository.list_for_enrollment(profile.enrollment.id)
    st.subheader("Comunicaciones")
    if not communications:
        st.info("No hay comunicaciones sugeridas.")
        return
    for communication in communications:
        st.markdown(
            f"**{communication.communication_type}** · estado: `{communication.status.value}`"
        )
        st.caption(f"Motivo: {communication.reason}")
        if communication.status is CommunicationStatus.SUGGESTED:
            if st.button("Aprobar mensaje para revisión", key=f"approve-{communication.id}"):
                repository.transition(
                    communication.id, CommunicationStatus.APPROVED, datetime.now(UTC)
                )
                st.rerun()
            st.info("Aprueba la sugerencia para mostrar el mensaje completo.")
            continue
        if communication.status in (CommunicationStatus.APPROVED, CommunicationStatus.COPIED):
            message = render_message(
                communication.communication_type,
                MessageContext(
                    name=profile.enrollment.student.full_name,
                    course=profile.enrollment.edition.course.name,
                    edition=profile.enrollment.edition.label,
                    context=communication.reason,
                ),
            )
            st.text_area(
                "Mensaje completo (selección manual)",
                value=message,
                height=160,
                key=f"message-{communication.id}",
                disabled=True,
            )
            st.download_button(
                "Descargar mensaje para copiar manualmente",
                data=message,
                file_name=f"mensaje-{communication.id}.txt",
                mime="text/plain",
                key=f"download-{communication.id}",
            )
            if communication.status is CommunicationStatus.APPROVED and st.button(
                "Registrar COPIED (ya copié el mensaje)", key=f"copied-{communication.id}"
            ):
                repository.transition(
                    communication.id, CommunicationStatus.COPIED, datetime.now(UTC)
                )
                st.rerun()
            if communication.status is CommunicationStatus.COPIED and st.button(
                "Registrar SENT (ya lo envié manualmente en ADAMS)",
                key=f"sent-{communication.id}",
            ):
                repository.transition(communication.id, CommunicationStatus.SENT, datetime.now(UTC))
                st.rerun()
        elif communication.status is CommunicationStatus.SENT:
            st.success("SENT registrado tras confirmación manual del tutor en ADAMS.")


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
