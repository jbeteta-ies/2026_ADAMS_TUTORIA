import sqlite3
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.persistence.catalog import Catalog


def test_catalog_lifecycle_and_idempotency(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    course = catalog.create_course("Curso sintético", "SYN")
    assert catalog.create_course("Otro nombre", "SYN").id == course.id
    edition = catalog.create_edition(
        course.id,
        "Edición 1",
        external_id="ext-1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 1),
    )
    assert catalog.create_edition(course.id, "Otra etiqueta", external_id="ext-1").id == edition.id
    catalog.set_edition_active(edition.id, False)
    assert catalog.list_editions(active_only=True) == ()
    catalog.set_edition_active(edition.id, True)
    assert catalog.list_editions(active_only=True)[0].id == edition.id


def test_catalog_rejects_missing_course_and_invalid_dates(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    with pytest.raises(ValueError, match="does not exist"):
        catalog.create_edition(uuid4(), "Edición")
    course = catalog.create_course("Curso")
    with pytest.raises(ValueError, match="end_date"):
        catalog.create_edition(
            course.id, "Edición", start_date=date(2026, 2, 1), end_date=date(2026, 1, 1)
        )


def test_catalog_updates_metadata_without_changing_identity(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    course = catalog.create_course("Curso sintético", "SYN")
    edition = catalog.create_edition(course.id, "Edición original")
    updated_course = catalog.update_course(course, name="Curso actualizado")
    updated_edition = catalog.update_edition(edition, label="Edición actualizada")
    assert updated_course.id == course.id
    assert updated_edition.id == edition.id
    assert updated_edition.course.id == course.id


def test_updates_reject_identity_conflicts_without_reassigning_records(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    first = catalog.create_course("Primero", "ONE")
    second = catalog.create_course("Segundo", "TWO")
    first_edition = catalog.create_edition(first.id, "Primera", external_id="ext-1")
    second_edition = catalog.create_edition(first.id, "Segunda", external_id="ext-2")

    with pytest.raises(ValueError, match="course code conflict"):
        catalog.update_course(second, code="ONE")
    with pytest.raises(ValueError, match="edition external_id conflict"):
        catalog.update_edition(second_edition, external_id="ext-1")

    assert catalog.get_course(first.id).id == first.id  # type: ignore[union-attr]
    assert catalog.get_course(second.id).code == "TWO"  # type: ignore[union-attr]
    assert catalog.get_edition(first_edition.id).id == first_edition.id  # type: ignore[union-attr]


def test_migration_rolls_back_all_ddl_and_checks_additional_tables(tmp_path: Path) -> None:
    from adams_tutoria.persistence.database import connection, initialize_database

    path = tmp_path / "legacy-with-extra.sqlite3"
    with connection(path) as db:
        db.execute("CREATE TABLE course (id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT)")
        db.execute(
            "CREATE TABLE edition (id TEXT PRIMARY KEY, course_id TEXT NOT NULL, "
            "label TEXT NOT NULL, external_id TEXT)"
        )
        db.execute("CREATE TABLE unrelated (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO course VALUES ('a', 'A', 'DUP')")
        db.execute("INSERT INTO course VALUES ('b', 'B', 'DUP')")

    with pytest.raises(ValueError, match="duplicate course code"):
        initialize_database(path)
    with sqlite3.connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"course", "edition", "unrelated"}


def test_catalog_migration_refuses_legacy_duplicates(tmp_path: Path) -> None:
    from adams_tutoria.persistence.database import connection, initialize_database

    path = tmp_path / "legacy.sqlite3"
    with connection(path) as db:
        db.execute("CREATE TABLE course (id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT)")
        db.execute(
            "CREATE TABLE edition (id TEXT PRIMARY KEY, course_id TEXT NOT NULL, "
            "label TEXT NOT NULL, external_id TEXT)"
        )
        db.execute("INSERT INTO course VALUES ('a', 'A', 'DUP')")
        db.execute("INSERT INTO course VALUES ('b', 'B', 'DUP')")
    with pytest.raises(ValueError, match="duplicate course code"):
        initialize_database(path)
