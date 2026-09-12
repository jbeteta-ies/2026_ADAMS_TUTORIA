"""Deterministic, local support for drafting answers to course questions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from adams_tutoria.content_search import ContentIndexError, MarkdownIndex, SearchResult
from adams_tutoria.domain import Course


@dataclass(frozen=True)
class AnswerReference:
    """A traceable course-content location used by a draft."""

    module: str
    document: str
    path: str
    fragment: str


@dataclass(frozen=True)
class AnswerDraft:
    """A human-reviewable answer draft; it is never sent automatically."""

    question: str
    course_id: UUID
    text: str
    references: tuple[AnswerReference, ...]


class QuestionAssistant:
    """Prepare a reproducible draft from one already indexed course."""

    def __init__(self, index: MarkdownIndex) -> None:
        self._index = index

    def draft(self, course: Course, question: str, *, limit: int = 3) -> AnswerDraft:
        """Return a deterministic draft based only on *course* Markdown.

        The assistant deliberately quotes matching fragments rather than
        inventing an explanation.  A caller must index the selected course
        explicitly, which keeps content from other courses out of the result.
        """

        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("question must not be blank")
        results = self._index.search(course, cleaned_question, limit=limit)
        references = tuple(self._reference(result) for result in results)
        if not references:
            text = (
                "No se ha encontrado contenido relevante en este curso. "
                "Revisa la duda y consulta manualmente el material."
            )
        else:
            text = "\n".join(
                [
                    "Borrador para revisión del tutor:",
                    f"Sobre «{cleaned_question}»: el contenido del curso indica:",
                    *[f"- {reference.fragment}" for reference in references],
                    "Verifica el contexto completo antes de compartir la respuesta.",
                ]
            )
        return AnswerDraft(cleaned_question, course.id, text, references)

    @staticmethod
    def _reference(result: SearchResult) -> AnswerReference:
        return AnswerReference(result.module, result.document, result.path, result.fragment)


__all__ = ["AnswerDraft", "AnswerReference", "ContentIndexError", "QuestionAssistant"]
