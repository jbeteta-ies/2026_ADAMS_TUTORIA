"""Transactional local catalog for courses and operational editions."""

from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

from adams_tutoria.domain import Course, Edition

from .database import connection, initialize_database
from .repositories import CourseRepository, EditionRepository


class Catalog:
    """Small SQLite application service; no ORM, remote calls, or raw imports."""

    def __init__(self, path: Path) -> None:
        self.path = path
        initialize_database(path)

    def create_course(
        self, name: str, code: str | None = None, description: str | None = None
    ) -> Course:
        candidate = Course(uuid4(), name, code, description)
        with connection(self.path) as db:
            rows = db.execute(
                "SELECT id FROM course WHERE (code = ? AND ? IS NOT NULL) OR "
                "(code IS NULL AND ? IS NULL AND name = ?)",
                (code, code, code, name),
            ).fetchall()
            if len(rows) > 1:
                raise ValueError("ambiguous duplicate course identity")
            if rows:
                return CourseRepository(self.path).get(UUID(rows[0]["id"]))  # type: ignore[return-value]
            db.execute(
                "INSERT INTO course(id,name,code,description) VALUES(?,?,?,?)",
                (str(candidate.id), name, code, description),
            )
        return candidate

    def get_course(self, course_id: UUID) -> Course | None:
        return CourseRepository(self.path).get(course_id)

    def update_course(self, course: Course, **changes: object) -> Course:
        allowed = {"name", "code", "description", "content_source", "active"}
        if set(changes) - allowed:
            raise ValueError("unsupported course metadata")
        updated = replace(course, **changes)  # type: ignore[arg-type]
        with connection(self.path) as db:
            if (
                updated.code is not None
                and db.execute(
                    "SELECT 1 FROM course WHERE code = ? AND id <> ?",
                    (updated.code, str(course.id)),
                ).fetchone()
            ):
                raise ValueError(f"course code conflict: {updated.code}")
            db.execute(
                "UPDATE course SET name=?, code=?, description=?, content_source_type=?, "
                "content_source_location=?, content_source_subpath=?, content_source_revision=? "
                "WHERE id=?",
                (
                    updated.name,
                    updated.code,
                    updated.description,
                    None
                    if updated.content_source is None
                    else updated.content_source.source_type.value,
                    None if updated.content_source is None else updated.content_source.location,
                    None if updated.content_source is None else updated.content_source.subpath,
                    None if updated.content_source is None else updated.content_source.revision,
                    str(course.id),
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise KeyError(course.id)
            db.execute(
                "INSERT INTO course_state(course_id, active) VALUES(?, ?) "
                "ON CONFLICT(course_id) DO UPDATE SET active=excluded.active",
                (str(updated.id), int(updated.active)),
            )
        return updated

    def list_courses(self, active_only: bool = False) -> tuple[Course, ...]:
        with connection(self.path) as db:
            where = (
                " WHERE COALESCE((SELECT active FROM course_state "
                "WHERE course_id = course.id), 1) = 1"
                if active_only
                else ""
            )
            ids = tuple(
                UUID(row["id"])
                for row in db.execute("SELECT id FROM course" + where + " ORDER BY name, id")
            )
        repo = CourseRepository(self.path)
        return tuple(item for item in (repo.get(item) for item in ids) if item is not None)

    def create_edition(
        self,
        course_id: UUID,
        label: str,
        *,
        external_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Edition:
        course = self.get_course(course_id)
        if course is None:
            raise ValueError("course does not exist")
        candidate = Edition(uuid4(), course, label, external_id, start_date, end_date)
        with connection(self.path) as db:
            rows = db.execute(
                "SELECT id FROM edition WHERE course_id = ? AND "
                "((external_id = ? AND ? IS NOT NULL) OR "
                "(external_id IS NULL AND ? IS NULL AND label = ?))",
                (str(course_id), external_id, external_id, external_id, label),
            ).fetchall()
            if len(rows) > 1:
                raise ValueError("ambiguous duplicate edition identity")
            if rows:
                return EditionRepository(self.path).get(UUID(rows[0]["id"]))  # type: ignore[return-value]
            db.execute(
                "INSERT INTO edition(id,course_id,label,external_id,start_date,end_date) "
                "VALUES(?,?,?,?,?,?)",
                (
                    str(candidate.id),
                    str(course_id),
                    label,
                    external_id,
                    start_date.isoformat() if start_date else None,
                    end_date.isoformat() if end_date else None,
                ),
            )
        return candidate

    def get_edition(self, edition_id: UUID) -> Edition | None:
        return EditionRepository(self.path).get(edition_id)

    def update_edition(self, edition: Edition, **changes: object) -> Edition:
        allowed = {"label", "external_id", "start_date", "end_date", "active"}
        if set(changes) - allowed:
            raise ValueError("unsupported edition metadata")
        updated = replace(edition, **changes)  # type: ignore[arg-type]
        with connection(self.path) as db:
            identity_column = "external_id" if updated.external_id is not None else "label"
            identity_value = (
                updated.external_id if updated.external_id is not None else updated.label
            )
            conflict = db.execute(
                f"SELECT 1 FROM edition WHERE course_id = ? AND {identity_column} = ? AND id <> ?",
                (str(edition.course.id), identity_value, str(edition.id)),
            ).fetchone()
            if conflict:
                raise ValueError(f"edition {identity_column} conflict: {identity_value}")
            db.execute(
                "UPDATE edition SET label=?, external_id=?, start_date=?, end_date=? WHERE id=?",
                (
                    updated.label,
                    updated.external_id,
                    updated.start_date.isoformat() if updated.start_date else None,
                    updated.end_date.isoformat() if updated.end_date else None,
                    str(edition.id),
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise KeyError(edition.id)
            db.execute(
                "INSERT INTO edition_state(edition_id, active) VALUES(?, ?) "
                "ON CONFLICT(edition_id) DO UPDATE SET active=excluded.active",
                (str(updated.id), int(updated.active)),
            )
        return updated

    def list_editions(
        self, course_id: UUID | None = None, active_only: bool = False
    ) -> tuple[Edition, ...]:
        with connection(self.path) as db:
            clauses, params = [], []
            if course_id:
                clauses.append("course_id = ?")
                params.append(str(course_id))
            if active_only:
                clauses.append(
                    "COALESCE((SELECT active FROM edition_state "
                    "WHERE edition_id = edition.id), 1) = 1"
                )
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            ids = tuple(
                UUID(row["id"])
                for row in db.execute(
                    "SELECT id FROM edition" + where + " ORDER BY label, id", params
                )
            )
        repo = EditionRepository(self.path)
        return tuple(item for item in (repo.get(item) for item in ids) if item is not None)

    def set_course_active(self, course_id: UUID, active: bool) -> None:
        with connection(self.path) as db:
            if (
                db.execute("SELECT 1 FROM course WHERE id = ?", (str(course_id),)).fetchone()
                is None
            ):
                raise KeyError(course_id)
            db.execute(
                "INSERT INTO course_state(course_id, active) VALUES(?, ?) "
                "ON CONFLICT(course_id) DO UPDATE SET active=excluded.active",
                (str(course_id), int(active)),
            )

    def set_edition_active(self, edition_id: UUID, active: bool) -> None:
        with connection(self.path) as db:
            if (
                db.execute("SELECT 1 FROM edition WHERE id = ?", (str(edition_id),)).fetchone()
                is None
            ):
                raise KeyError(edition_id)
            db.execute(
                "INSERT INTO edition_state(edition_id, active) VALUES(?, ?) "
                "ON CONFLICT(edition_id) DO UPDATE SET active=excluded.active",
                (str(edition_id), int(active)),
            )
