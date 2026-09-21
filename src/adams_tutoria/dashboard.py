"""Operational, read-only dashboard over the local persistence contracts."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import streamlit as st

from adams_tutoria.attention import (
    AttentionConfig,
    PriorityThresholds,
    prioritize_attention,
)
from adams_tutoria.communication_recommendations import (
    EditionPolicyContext,
    RecommendationConfig,
    recommend_communications,
)
from adams_tutoria.config import AppConfig, load_config
from adams_tutoria.domain import (
    CommunicationStatus,
    TutorAction,
)
from adams_tutoria.follow_up import FollowUpRules, assess_follow_up
from adams_tutoria.generation import (
    DraftGenerationRequest,
    DraftGenerationService,
    GenerationRecord,
    GenerationStatus,
    HttpTransport,
    OllamaConfig,
    OllamaGenerator,
    PromptContext,
    PromptRequest,
    UrllibTransport,
    build_model_payload,
)
from adams_tutoria.message_templates import MessageContext, render_message
from adams_tutoria.ollama import (
    OllamaDiscovery,
    OllamaDiscoveryTransport,
    OllamaSettings,
    OllamaSettingsRepository,
)
from adams_tutoria.persistence.catalog import Catalog
from adams_tutoria.persistence.database import database_path, initialize_database
from adams_tutoria.persistence.repositories import (
    CommunicationHistoryAdapter,
    CommunicationRecordRepository,
    ContentProgressSnapshotRepository,
    EditionRepository,
    EnrollmentRepository,
    EvaluationRepository,
    GenerationRepository,
    ProgressSnapshotRepository,
    TutorActionRepository,
)
from adams_tutoria.student_tracking import (
    filter_tracking_rows,
    prepare_tracking_rows,
    select_tracking_detail,
    sort_tracking_rows,
)
from adams_tutoria.summary import summarize_edition, summarize_enrollment


@dataclass(frozen=True)
class CourseOption:
    """Persisted course option used only for presentation."""

    id: str
    name: str
    code: str


@dataclass(frozen=True)
class EditionOption:
    """Persisted edition option used only for presentation."""

    id: str
    course_id: str
    label: str


# Kept as empty compatibility symbols: operational selectors never use them.
COURSES: tuple[CourseOption, ...] = ()
EDITIONS: tuple[EditionOption, ...] = ()


def editions_for_course(course_id: str) -> tuple[EditionOption, ...]:
    """Return persisted editions for a course; never return demo data."""
    return _editions(course_id)


def _catalog(config: AppConfig | None = None) -> tuple[CourseOption, ...]:
    path = database_path(config or load_config())
    initialize_database(path)
    return tuple(
        CourseOption(str(course.id), course.name, course.code or str(course.id))
        for course in Catalog(path).list_courses()
    )


def _editions(course_id: str, config: AppConfig | None = None) -> tuple[EditionOption, ...]:
    path = database_path(config or load_config())
    return tuple(
        EditionOption(str(edition.id), str(edition.course.id), edition.label)
        for edition in Catalog(path).list_editions(UUID(course_id))
    )


def _option_label(option: CourseOption | EditionOption) -> str:
    """Build a stable, human-readable selector label."""

    if isinstance(option, CourseOption):
        return f"{option.code} — {option.name}"
    return option.label


def _initial_selection(config: AppConfig) -> None:
    """Initialize only the dashboard selection state."""

    courses = _catalog(config)
    if not courses:
        return
    st.session_state.setdefault("course_id", courses[0].id)
    initial_editions = _editions(st.session_state["course_id"], config)
    if initial_editions:
        st.session_state.setdefault("edition_id", initial_editions[0].id)


def _render_selection(config: AppConfig) -> tuple[CourseOption | None, EditionOption | None]:
    """Render independent course/edition selectors and return their values."""

    courses = _catalog(config)
    if not courses:
        st.sidebar.info("No hay cursos persistidos.")
        return None, None
    course_ids = [course.id for course in courses]
    current_course_id = st.session_state["course_id"]
    if current_course_id not in course_ids:
        current_course_id = course_ids[0]
    selected_course_id = st.sidebar.selectbox(
        "Curso",
        course_ids,
        index=course_ids.index(current_course_id),
        format_func=lambda course_id: _option_label(
            next(course for course in courses if course.id == course_id)
        ),
        key="course_id",
    )
    selected_editions = _editions(selected_course_id, config)
    if not selected_editions:
        st.sidebar.info("El curso no tiene ediciones persistidas.")
        return next(course for course in courses if course.id == selected_course_id), None
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
    course = next(course for course in courses if course.id == selected_course_id)
    edition = next(edition for edition in selected_editions if edition.id == selected_edition_id)
    return course, edition


def _operational_summaries(edition_id: UUID, config: AppConfig):
    path = database_path(config)
    edition = EditionRepository(path).get(edition_id)
    if edition is None:
        return (), (), ()
    now = datetime.now(UTC)
    rules = FollowUpRules(Decimal("0"), timedelta(days=7), Decimal("80"))
    enrollments = EnrollmentRepository(path).list_for_edition(edition_id)
    progress = ProgressSnapshotRepository(path)
    content_progress = ContentProgressSnapshotRepository(path)
    evaluations = EvaluationRepository(path)
    summaries = tuple(
        summarize_enrollment(
            enrollment,
            progress.list_for_enrollment(enrollment.id),
            evaluations.list_for_enrollment(enrollment.id),
            assess_follow_up(
                enrollment,
                progress.list_for_enrollment(enrollment.id),
                evaluations.list_for_enrollment(enrollment.id),
                rules,
                as_of=now,
            ),
            as_of=now,
        )
        for enrollment in enrollments
    )
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
        edition_id=edition_id,
    )
    recommendation_diagnostics: list = []
    recommendations = recommend_communications(
        summaries,
        attention,
        CommunicationHistoryAdapter(CommunicationRecordRepository(path), edition_id=edition_id),
        RecommendationConfig(
            {
                "not_started": "invitation_to_start",
                "inactive": "inactivity_reminder",
                "pending_evaluations": "pending_evaluation_reminder",
                "passed_evaluation": "passed_evaluation_congratulation",
                "failed_evaluation": "insufficient_result_encouragement",
                "completed": "completion_congratulation",
            }
        ),
        as_of=now,
        edition_contexts={
            edition_id: EditionPolicyContext(
                edition_id, edition.start_date, edition.end_date, edition.active
            )
        },
        diagnostics=recommendation_diagnostics,
    )
    progress_values = [
        snapshot
        for enrollment in enrollments
        for snapshot in progress.list_for_enrollment(enrollment.id)
    ]
    content_values = [
        item
        for enrollment in enrollments
        for item in content_progress.list_current_for_enrollment(enrollment.id)
    ]
    evaluation_values = [
        evaluation
        for enrollment in enrollments
        for evaluation in evaluations.list_for_enrollment(enrollment.id)
    ]
    coverage = {
        "matrículas": len(enrollments),
        "con progreso": len({item.enrollment.id for item in progress_values}),
        "con evaluaciones": len({item.enrollment.id for item in evaluation_values}),
        "con progreso por contenido": len({item.enrollment.id for item in content_values}),
        "filas de progreso por contenido": len(content_values),
        "último progreso": max((item.captured_at for item in progress_values), default=None),
        "última evaluación": max(
            (item.completed_at for item in evaluation_values if item.completed_at is not None),
            default=None,
        ),
    }
    return (
        summaries,
        attention,
        (
            edition,
            now,
            recommendations,
            recommendation_diagnostics,
            coverage,
            content_values,
        ),
    )


def _render_page(
    course: CourseOption, edition: EditionOption, page: str, config: AppConfig
) -> None:
    """Render persisted operational data without mutating domain records."""

    if page == "Settings":
        _render_settings()
    elif page == "Inicio":
        st.title("Dashboard de tutoría")
        st.write(
            "Consulta de datos locales persistidos. Las acciones de envío siguen siendo manuales."
        )
    elif page == "Curso":
        st.title("Curso")
        st.subheader(course.name)
        st.caption(f"ID estable: {course.id}")
        st.info("Selecciona una edición para consultar el seguimiento operativo.")
    else:
        st.title("Edición")
        st.subheader(edition.label)
        st.caption(f"ID estable: {edition.id} · Curso: {course.id}")
        try:
            summaries, attention, metadata = _operational_summaries(UUID(edition.id), config)
        except Exception as exc:
            st.error(f"No se pudo leer la persistencia local ({type(exc).__name__}).")
            return
        if not metadata:
            st.warning("La edición no está disponible en la persistencia local.")
            return
        metrics = summarize_edition(UUID(edition.id), summaries)
        persisted_edition = metadata[0]
        coverage = metadata[4]
        st.subheader("Contexto de la edición")
        st.write(
            {
                "Estado": "Activa" if persisted_edition.active else "Archivada",
                "Inicio": persisted_edition.start_date or "No disponible",
                "Fin": persisted_edition.end_date or "No disponible",
                "Matrículas": coverage["matrículas"],
                "Matrículas con progreso": coverage["con progreso"],
                "Matrículas con evaluaciones": coverage["con evaluaciones"],
                "Matrículas con progreso por contenido": coverage["con progreso por contenido"],
                "Filas de progreso por contenido": coverage["filas de progreso por contenido"],
                "Último progreso": coverage["último progreso"] or "No disponible",
                "Última evaluación": coverage["última evaluación"] or "No disponible",
            }
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

        rows = prepare_tracking_rows(summaries, attention, UUID(edition.id))
        recommendations = metadata[2]
        st.subheader("Recomendaciones de comunicación")
        if recommendations:
            st.dataframe(
                [
                    {
                        "Prioridad": item.priority.value,
                        "Tipo": item.communication_type,
                        "Estado": item.status.value,
                        "Razón": item.reason,
                        "Matrícula": str(item.enrollment_id),
                        "Contexto temporal": item.temporal_context,
                    }
                    for item in recommendations
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No hay recomendaciones aplicables con los datos disponibles.")
        st.subheader("Progreso por contenido")
        content_values = metadata[5]
        if content_values:
            st.dataframe(
                [
                    {
                        "Matrícula": str(item.enrollment.id),
                        "Contenido": item.node.title,
                        "Progreso": f"{item.progress_percentage}%",
                        "Actualizado": item.captured_at.isoformat(),
                    }
                    for item in content_values
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No hay progreso por contenido disponible.")
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
        _render_draft_review(edition, summaries, visible_rows, metadata[2], config)
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
                _render_student_profile(detail.row.enrollment_id, UUID(edition.id), config)
        else:
            st.info("No hay matrículas que coincidan con los filtros.")


def _generation_repository(config: AppConfig) -> GenerationRepository:
    """Return the existing local draft repository used by the dashboard."""
    path = database_path(config)
    initialize_database(path)
    return GenerationRepository(path, config.generation_text_dir)


def _dashboard_request(
    summary,
    communication_type: str,
    tutor_text: str,
    config: AppConfig | None = None,
    recommendation_reason: str | None = None,
) -> DraftGenerationRequest:
    """Build one explicit request without selecting a recipient or recommendation."""
    reasons = tuple(reason.explanation for reason in summary.follow_up.reasons)
    if not reasons:
        raise ValueError("La matrícula no tiene un motivo autorizado para generar un borrador.")
    reason = recommendation_reason or " · ".join(reasons)
    prompt = PromptRequest(
        PromptContext.from_summary(summary, recommendation_reason=reason),
        communication_type,
        "neutral",
        tutor_text or None,
    )
    enrollment = EnrollmentRepository(database_path(config or load_config())).get(
        summary.enrollment_id
    )
    if enrollment is None:
        raise ValueError("La matrícula persistida ya no está disponible.")
    return DraftGenerationRequest(enrollment, communication_type, reason, prompt)


def _ollama_transport() -> object:
    """Return a test-injected transport, or the real local-only transport."""
    injected = st.session_state.get("_ollama_transport")
    return injected if injected is not None else UrllibTransport()


def _local_dashboard_generator(config: AppConfig) -> OllamaGenerator:
    """Create the explicitly invoked local-only generator; it never sends messages."""
    settings = OllamaSettingsRepository(database_path(config)).get()
    if not settings.model:
        raise ValueError("Selecciona un modelo Ollama en Settings antes de generar.")
    return OllamaGenerator(
        OllamaConfig(
            settings.model,
            settings.endpoint,
            settings.timeout_seconds,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        ),
        cast("HttpTransport", _ollama_transport()),
    )


def _render_settings() -> None:
    """Render local-only Ollama settings; discovery is injected in tests/runtime."""
    st.title("Settings")
    config = load_config()
    repository = OllamaSettingsRepository(database_path(config))
    current = repository.get()
    st.caption(
        "Solo se aceptan servicios Ollama en localhost; no se guardan credenciales ni prompts."
    )
    endpoint = st.text_input("Endpoint local", current.endpoint, key="ollama-endpoint")
    temperature = st.number_input("Temperature", 0.0, 2.0, current.temperature, 0.1)
    max_tokens = st.number_input("Límite de tokens", 1, 16_000, current.max_tokens)
    timeout = st.number_input("Timeout (segundos)", 1.0, 300.0, current.timeout_seconds, 1.0)
    if st.button("Listar modelos locales", key="ollama-list"):
        try:
            settings = OllamaSettings(current.model, endpoint, temperature, max_tokens, timeout)
            models = OllamaDiscovery(
                settings, cast(OllamaDiscoveryTransport, _ollama_transport())
            ).list_models()
            st.session_state["ollama-models"] = tuple(model.name for model in models)
            st.session_state["ollama-discovery-attempted"] = True
        except Exception as exc:
            st.error(f"No se pudieron listar los modelos: {type(exc).__name__}")
    models = st.session_state.get("ollama-models", ())
    if st.session_state.get("ollama-discovery-attempted"):
        if current.model and current.model not in models:
            st.error(
                f"El modelo persistido «{current.model}» no está disponible. "
                "Selecciona otro explícitamente."
            )
        elif not current.model:
            st.warning("No hay modelo persistido. Selecciona un modelo antes de generar.")
    selected = st.selectbox(
        "Modelo",
        ("", *models),
        index=(models.index(current.model) + 1 if current.model in models else 0),
    )
    if st.button("Guardar configuración", key="ollama-save"):
        try:
            repository.save(OllamaSettings(selected, endpoint, temperature, max_tokens, timeout))
            st.success("Configuración guardada localmente.")
        except Exception as exc:
            st.error(f"Configuración rechazada: {type(exc).__name__}")


def settings_to_config(settings: OllamaSettings) -> OllamaConfig:
    """Adapt settings to the existing local HTTP transport contract."""
    return OllamaConfig(settings.model or "discovery", settings.endpoint, settings.timeout_seconds)


def _record_key(edition_id: str, enrollment_id) -> str:
    return f"draft:{edition_id}:{enrollment_id}"


def _render_draft_review(
    edition: EditionOption, summaries, rows, recommendations, config: AppConfig
) -> None:
    """Render independent draft generation and human review controls."""
    st.subheader("Borradores asistidos (revisión humana)")
    st.warning(
        "IA local: el borrador se genera en el equipo y nunca se envía automáticamente. "
        "Revisa y copia manualmente en ADAMS si corresponde."
    )
    summary_by_id = {summary.enrollment_id: summary for summary in summaries}
    recommendation_by_id = {item.enrollment_id: item for item in recommendations}
    authorized_ids = set(recommendation_by_id)
    options = tuple(row.enrollment_id for row in rows if row.enrollment_id in authorized_ids)
    selected = st.multiselect(
        "Selecciona matrículas para generar borradores independientes",
        options,
        format_func=str,
        key=f"draft-selection:{edition.id}",
    )
    communication_type = ""
    tutor_text = st.text_area(
        "Nota opcional del tutor (no sustituye las reglas de privacidad)",
        key=f"draft-note:{edition.id}",
    )
    if selected:
        st.subheader("Vista previa del payload minimizado")
        st.caption("Se mostrará este resumen allowlisted antes de solicitar cualquier generación.")
        for enrollment_id in selected:
            summary = summary_by_id[enrollment_id]
            recommendation = recommendation_by_id[enrollment_id]
            communication_type = recommendation.communication_type
            reason = recommendation.reason
            payload = build_model_payload(
                communication_type,
                reason,
                {
                    "progress_summary": (
                        "sin dato"
                        if summary.progress.percentage is None
                        else f"{summary.progress.percentage}%"
                    ),
                },
            )
            st.json({"matrícula": str(enrollment_id), "payload": payload})
    if st.button("Generar borradores seleccionados", key=f"draft-generate:{edition.id}"):
        try:
            repository = _generation_repository(config)
            service = DraftGenerationService(_local_dashboard_generator(config), repository)
        except Exception as exc:
            st.error(f"No se pudo preparar la generación ({type(exc).__name__}).")
            return
        for enrollment_id in selected:
            try:
                request = _dashboard_request(
                    summary_by_id[enrollment_id],
                    recommendation_by_id[enrollment_id].communication_type,
                    tutor_text,
                    config,
                    recommendation_by_id[enrollment_id].reason,
                )
                request = DraftGenerationRequest(
                    request.enrollment,
                    request.communication_type,
                    recommendation_by_id[enrollment_id].reason,
                    PromptRequest(
                        request.prompt.context,
                        recommendation_by_id[enrollment_id].communication_type,
                        request.prompt.tone,
                        request.prompt.tutor_text,
                    ),
                )
                result = service.generate([request])
                if result.records:
                    st.session_state[_record_key(edition.id, enrollment_id)] = str(
                        result.records[0].id
                    )
                else:
                    st.error(f"No se generó borrador para {enrollment_id}.")
            except Exception as exc:
                st.error(f"Falló solo la matrícula {enrollment_id}: {exc}")
        st.rerun()

    try:
        repository = _generation_repository(config)
    except Exception as exc:
        st.error(f"No se pudo leer el historial de borradores ({type(exc).__name__}).")
        return
    for enrollment_id in selected:
        record_id = st.session_state.get(_record_key(edition.id, enrollment_id))
        if record_id is None:
            continue
        record = repository.get(UUID(record_id))
        if record is not None:
            _render_one_draft(
                edition,
                enrollment_id,
                record,
                summary_by_id[enrollment_id],
                repository,
                config,
            )


def _render_one_draft(
    edition, enrollment_id, record: GenerationRecord, summary, repository, config: AppConfig
) -> None:
    """Render controls for exactly one record, scoped by edition and enrollment."""
    key = _record_key(edition.id, enrollment_id)
    st.markdown(f"### Matrícula {enrollment_id}")
    st.caption(f"Motivo: {record.reason}")
    st.caption(
        "Datos usados: contexto minimizado de seguimiento y evaluaciones; "
        "sin contacto ni IDs externos."
    )
    edited = st.text_area("Borrador", value=record.draft_text, key=f"draft-text:{key}", height=180)
    if record.status not in (
        GenerationStatus.COPIED,
        GenerationStatus.SENT,
        GenerationStatus.DISCARDED,
    ):
        if st.button("Guardar edición", key=f"draft-edit:{key}"):
            repository.transition(record.id, GenerationStatus.EDITED, datetime.now(UTC), edited)
            st.rerun()
        if st.button("Marcar revisado", key=f"draft-review:{key}"):
            repository.transition(record.id, GenerationStatus.REVIEWED, datetime.now(UTC))
            st.rerun()
        if st.button("Regenerar este borrador", key=f"draft-regenerate:{key}"):
            try:
                repository.transition(record.id, GenerationStatus.DISCARDED, datetime.now(UTC))
                request = _dashboard_request(
                    summary, record.communication_type, "", config, record.reason
                )
                result = DraftGenerationService(
                    _local_dashboard_generator(config), repository
                ).generate([request])
                if result.records:
                    st.session_state[key] = str(result.records[0].id)
                else:
                    st.error(f"No se pudo regenerar {enrollment_id}.")
            except Exception as exc:
                st.error(f"Regeneración fallida solo para {enrollment_id}: {exc}")
            st.rerun()
        if st.button("Descartar", key=f"draft-discard:{key}"):
            repository.transition(record.id, GenerationStatus.DISCARDED, datetime.now(UTC))
            st.rerun()
    if record.status in (
        GenerationStatus.REVIEWED,
        GenerationStatus.EDITED,
        GenerationStatus.COPIED,
    ):
        st.download_button(
            "Copiar manualmente (descargar texto)",
            record.draft_text,
            file_name=f"borrador-{enrollment_id}.txt",
            mime="text/plain",
            key=f"draft-copy:{key}",
        )
        if record.status is not GenerationStatus.COPIED and st.button(
            "Registrar COPIED (ya copié manualmente)", key=f"draft-copied:{key}"
        ):
            repository.transition(record.id, GenerationStatus.COPIED, datetime.now(UTC))
            st.rerun()
    if record.status is GenerationStatus.COPIED and st.button(
        "Registrar SENT (solo confirmé envío manual)", key=f"draft-sent:{key}"
    ):
        repository.transition(record.id, GenerationStatus.SENT, datetime.now(UTC))
        st.rerun()
    if record.status is GenerationStatus.SENT:
        st.success("SENT registrado únicamente tras una acción manual externa del tutor.")
    if record.status is GenerationStatus.DISCARDED:
        st.info("Borrador descartado; no se muestra como mensaje activo.")


def _render_student_profile(enrollment_id, edition_id: UUID, config: AppConfig) -> None:
    """Render the detail view using one enrollment as its only scope."""
    path = database_path(config)
    initialize_database(path)
    actions_repository = TutorActionRepository(path)
    communications_repository = CommunicationRecordRepository(path)
    enrollment = EnrollmentRepository(path).get(enrollment_id)
    if enrollment is None or enrollment.edition.id != edition_id:
        st.info("La ficha operativa no está disponible para esta matrícula.")
        return
    progress = ProgressSnapshotRepository(path).list_for_enrollment(enrollment_id)
    evaluations = EvaluationRepository(path).list_for_enrollment(enrollment_id)
    content_progress = ContentProgressSnapshotRepository(path).list_current_for_enrollment(
        enrollment_id
    )
    now = datetime.now(UTC)
    follow_up = assess_follow_up(
        enrollment,
        progress,
        evaluations,
        FollowUpRules(Decimal("0"), timedelta(days=7), Decimal("80")),
        as_of=now,
    )
    summary = summarize_enrollment(enrollment, progress, evaluations, follow_up, as_of=now)
    st.subheader("Ficha de alumno")
    st.caption(f"Matrícula: {enrollment.id}")
    st.write(
        {
            "Alumno": enrollment.student.full_name,
            "Progreso": summary.progress.percentage,
            "Evaluaciones pendientes": summary.evaluations.pending,
            "Filas de progreso por contenido": len(content_progress),
        }
    )
    st.write("**Evaluaciones**", [evaluation.target_id for evaluation in evaluations])
    st.write(
        "**Alertas y seguimiento**",
        [reason.explanation for reason in summary.follow_up.reasons],
    )
    st.write(
        "**Historial de progreso**",
        [
            {
                "captured_at": snapshot.captured_at.isoformat(),
                "progress": snapshot.progress_percentage,
            }
            for snapshot in progress
        ],
    )
    st.write(
        "**Progreso por contenido**",
        [
            {
                "content": item.node.title,
                "progress": item.progress_percentage,
                "imported_at": item.captured_at.isoformat(),
            }
            for item in content_progress
        ]
        or "No disponible",
    )
    communications = communications_repository.list_for_enrollment(enrollment_id, edition_id)
    if communications:
        _render_communications(enrollment, communications, communications_repository)
    st.write(
        "**Acciones del tutor**",
        [action.action for action in actions_repository.list_for_enrollment(enrollment_id)],
    )
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


def _render_communications(
    enrollment, communications, repository: CommunicationRecordRepository
) -> None:
    """Show approved messages and record only explicit manual tutor actions."""
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
                    name=enrollment.student.full_name,
                    course=enrollment.edition.course.name,
                    edition=enrollment.edition.label,
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
    config = load_config()
    _initial_selection(config)
    st.sidebar.title("Navegación")
    page = st.sidebar.radio("Sección", ("Inicio", "Curso", "Edición", "Settings"))
    if page == "Settings":
        _render_settings()
        return
    course, edition = _render_selection(config)
    if course is None or edition is None:
        st.info("No hay un curso y una edición persistidos disponibles.")
        return
    _render_page(course, edition, page, config)


if __name__ == "__main__":
    main()
