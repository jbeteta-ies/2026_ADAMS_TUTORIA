from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.content_search import MarkdownIndex
from adams_tutoria.domain import ContentSource, ContentSourceType, Course
from adams_tutoria.question_assistant import QuestionAssistant


def course(root: Path, name: str = "Curso sintético") -> Course:
    return Course(
        uuid4(), name, content_source=ContentSource(ContentSourceType.LOCAL_PATH, str(root))
    )


def test_draft_is_deterministic_and_traceable(tmp_path: Path) -> None:
    (tmp_path / "unidad").mkdir()
    (tmp_path / "unidad" / "guia.md").write_text(
        "La revisión del resultado es obligatoria.", encoding="utf-8"
    )
    selected = course(tmp_path)
    index = MarkdownIndex()
    index.index_course(selected)

    first = QuestionAssistant(index).draft(selected, "¿Es obligatoria la revisión?")
    second = QuestionAssistant(index).draft(selected, "¿Es obligatoria la revisión?")

    assert first == second
    assert first.course_id == selected.id
    assert first.references[0].path == "unidad/guia.md"
    assert "revisión del resultado" in first.text


def test_draft_does_not_cross_course_boundaries(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / "a.md").write_text("Contenido del curso primero", encoding="utf-8")
    (second_root / "b.md").write_text("Contenido del curso segundo", encoding="utf-8")
    first, second = course(first_root, "Primero"), course(second_root, "Segundo")
    index = MarkdownIndex()
    index.index_course(first)
    index.index_course(second)

    draft = QuestionAssistant(index).draft(first, "contenido curso")

    assert all(reference.path != "b.md" for reference in draft.references)
    with pytest.raises(ValueError, match="question must not be blank"):
        QuestionAssistant(index).draft(first, "   ")


def test_draft_without_matches_is_explicit(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("Tema sintético", encoding="utf-8")
    selected = course(tmp_path)
    index = MarkdownIndex()
    index.index_course(selected)

    draft = QuestionAssistant(index).draft(selected, "evaluación inexistente")

    assert draft.references == ()
    assert "No se ha encontrado" in draft.text
