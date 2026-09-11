from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.content_search import ContentIndexError, MarkdownIndex
from adams_tutoria.domain import ContentSource, ContentSourceType, Course


def make_course(
    root: Path, source_type: ContentSourceType = ContentSourceType.LOCAL_PATH
) -> Course:
    return Course(uuid4(), "Curso sintético", content_source=ContentSource(source_type, str(root)))


def test_search_identifies_module_document_and_fragment(tmp_path: Path) -> None:
    (tmp_path / "modulo-a").mkdir()
    (tmp_path / "modulo-a" / "intro.md").write_text(
        "# Introducción\n\nLa gestión de riesgos requiere revisión.", encoding="utf-8"
    )
    selected = make_course(tmp_path)
    index = MarkdownIndex()
    assert index.index_course(selected) == 1
    results = index.search(selected, "GESTION de RIESGOS")
    assert [(result.module, result.document) for result in results] == [("modulo-a", "intro")]
    assert "gestión de riesgos" in results[0].fragment


def test_normalization_and_order_are_deterministic(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text("Árbol y módulo", encoding="utf-8")
    (tmp_path / "a.md").write_text("Árbol y módulo", encoding="utf-8")
    selected = make_course(tmp_path, ContentSourceType.REPOSITORY)
    index = MarkdownIndex()
    index.index_course(selected)
    assert [result.path for result in index.search(selected, "arbol modulo")] == ["a.md", "b.md"]


def test_subpath_and_course_isolation(tmp_path: Path) -> None:
    (tmp_path / "safe").mkdir()
    (tmp_path / "safe" / "lesson.md").write_text("Contenido compartido", encoding="utf-8")
    first = Course(
        uuid4(),
        "Primero",
        content_source=ContentSource(ContentSourceType.LOCAL_PATH, str(tmp_path), "safe"),
    )
    second = make_course(tmp_path / "other")
    index = MarkdownIndex()
    index.index_course(first)
    assert index.search(first, "compartido")[0].path == "lesson.md"
    with pytest.raises(ContentIndexError, match="not been indexed"):
        index.search(second, "compartido")


def test_controlled_errors(tmp_path: Path) -> None:
    index = MarkdownIndex()
    selected = make_course(tmp_path / "missing")
    with pytest.raises(ContentIndexError, match="accessible local directory"):
        index.index_course(selected)
    with pytest.raises(ContentIndexError, match="at least one term"):
        index.search(selected, "   ")
