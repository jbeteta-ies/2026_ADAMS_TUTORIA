"""Local, in-memory indexing and searching of course Markdown content."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from adams_tutoria.domain import ContentSourceType, Course


class ContentIndexError(ValueError):
    """A safe, expected error while loading local course content."""


@dataclass(frozen=True)
class SearchResult:
    """A matching fragment and its course-content location."""

    course_id: UUID
    module: str
    document: str
    path: str
    fragment: str
    score: int


@dataclass(frozen=True)
class _Document:
    course_id: UUID
    module: str
    document: str
    path: str
    text: str
    normalized: str


_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SPACE_RE.sub(" ", without_marks.casefold()).strip()


def _terms(query: str) -> tuple[str, ...]:
    terms = tuple(dict.fromkeys(_WORD_RE.findall(_normalize(query))))
    if not terms:
        raise ContentIndexError("search query must contain at least one term")
    return terms


class MarkdownIndex:
    """An in-memory index isolated by course identity."""

    def __init__(self) -> None:
        self._documents: dict[UUID, tuple[_Document, ...]] = {}

    def index_course(self, course: Course) -> int:
        """Read all Markdown files from an existing local course source."""
        source = course.content_source
        if source is None:
            raise ContentIndexError("course has no content source")
        if source.source_type not in (ContentSourceType.LOCAL_PATH, ContentSourceType.REPOSITORY):
            raise ContentIndexError("unsupported content source")
        root = Path(source.location).expanduser()
        if source.subpath is not None:
            root /= source.subpath
        root = root.resolve()
        if not root.is_dir():
            raise ContentIndexError("content source is not an accessible local directory")

        documents: list[_Document] = []
        for path in sorted(root.rglob("*.md"), key=lambda item: item.as_posix().casefold()):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise ContentIndexError("could not read a Markdown document") from error
            relative = path.relative_to(root)
            documents.append(
                _Document(
                    course_id=course.id,
                    module=relative.parts[0] if len(relative.parts) > 1 else "root",
                    document=path.stem,
                    path=relative.as_posix(),
                    text=text,
                    normalized=_normalize(text),
                )
            )
        self._documents[course.id] = tuple(documents)
        return len(documents)

    def search(self, course: Course, query: str, *, limit: int = 10) -> list[SearchResult]:
        """Return deterministic matching fragments for an indexed course."""
        if limit < 1:
            raise ContentIndexError("limit must be positive")
        terms = _terms(query)
        documents = self._documents.get(course.id)
        if documents is None:
            raise ContentIndexError("course has not been indexed")
        matches: list[tuple[int, _Document]] = []
        for document in documents:
            score = sum(document.normalized.count(term) for term in terms)
            if score and all(term in document.normalized for term in terms):
                matches.append((score, document))
        matches.sort(key=lambda item: (-item[0], item[1].path.casefold(), item[1].path))
        return [self._result(document, terms, score) for score, document in matches[:limit]]

    @staticmethod
    def _result(document: _Document, terms: tuple[str, ...], score: int) -> SearchResult:
        lines = document.text.splitlines() or [document.text]
        matching = [
            line.strip() for line in lines if all(term in _normalize(line) for term in terms)
        ]
        fragment = (
            matching[0]
            if matching
            else next(
                (line.strip() for line in lines if any(term in _normalize(line) for term in terms)),
                document.text.strip(),
            )
        )
        return SearchResult(
            document.course_id, document.module, document.document, document.path, fragment, score
        )
