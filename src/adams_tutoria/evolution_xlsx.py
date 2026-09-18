"""Import the confirmed, local XLSX evolution report.

The parser is deliberately strict and retains no source rows.  The importer
stores current state in tables separate from ``ContentProgressSnapshot``.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4, uuid5

from adams_tutoria.persistence.database import connection
from adams_tutoria.tabular_import import read_xlsx_values

_NAMESPACE = UUID("6b7c65da-5ec6-4c1f-b6c6-4e3e6730e112")
_MODULE = re.compile(r"^Módulo ([1-4])$", re.IGNORECASE)
_SUBMODULE = re.compile(
    r"^([1-4])\.\s+.+\s+(M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class EvolutionRow:
    title: str
    pages_percentage: Decimal
    row_number: int


@dataclass(frozen=True, slots=True)
class EvolutionBlock:
    user: str
    global_g_percentage: Decimal
    rows: tuple[EvolutionRow, ...]
    start_row: int


@dataclass(frozen=True, slots=True)
class EvolutionDiagnostic:
    code: str
    row_number: int | None
    message: str


@dataclass(frozen=True, slots=True)
class EvolutionChange:
    kind: str
    entity: str
    row_number: int | None = None


@dataclass(frozen=True, slots=True)
class EvolutionPreview:
    blocks: tuple[EvolutionBlock, ...]
    diagnostics: tuple[EvolutionDiagnostic, ...]
    changes: tuple[EvolutionChange, ...]
    changed: int
    unchanged: int
    rejected: int
    excluded: int


@dataclass(frozen=True, slots=True)
class EvolutionImportResult:
    applied: bool
    idempotent: bool
    inserted_or_updated: int
    unchanged: int
    rejected: int
    diagnostics: tuple[EvolutionDiagnostic, ...]
    preview: EvolutionPreview | None = None
    excluded: int = 0


def _ordered_items(blocks: tuple[EvolutionBlock, ...]) -> tuple[EvolutionRow, ...]:
    """Return the single deterministic content plan shared by preview/apply."""
    modules = tuple(
        item for block in blocks for item in block.rows if _MODULE.fullmatch(item.title)
    )
    submodules = tuple(
        item for block in blocks for item in block.rows if _SUBMODULE.fullmatch(item.title)
    )
    return modules + submodules


def _percentage(value: object) -> Decimal:
    text = str(value).strip().replace("%", "")
    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("percentage is invalid") from error
    if not result.is_finite() or not Decimal("0") <= result <= Decimal("100"):
        raise ValueError("percentage must be between 0 and 100")
    return result


def _text(value: object) -> str:
    return "" if value is None else " ".join(str(value).replace("\xa0", " ").split())


def _read_rows(source: str | Path | BinaryIO) -> list[tuple[object, ...]]:
    return [tuple(row) for row in read_xlsx_values(source)]


def parse_evolution_xlsx(
    source: str | Path | BinaryIO,
) -> tuple[tuple[EvolutionBlock, ...], tuple[EvolutionDiagnostic, ...]]:
    """Parse ``Usuario`` blocks and only the confirmed progress rows."""
    rows = _read_rows(source)
    diagnostics: list[EvolutionDiagnostic] = []
    blocks: list[EvolutionBlock] = []
    current_user: str | None = None
    current_g: Decimal | None = None
    current_rows: list[EvolutionRow] = []
    start = 0

    def finish() -> None:
        if current_user is not None and current_g is not None:
            blocks.append(EvolutionBlock(current_user, current_g, tuple(current_rows), start))

    for number, row in enumerate(rows, 1):
        first = _text(row[0] if row else None)
        is_header = first == "Usuario" and _text(row[6] if len(row) > 6 else None) == "Evolución"
        if is_header:
            finish()
            current_user = None
            current_g = None
            current_rows = []
            continue
        if len(row) >= 7 and first and _text(row[1]) and _text(row[2]) and _text(row[6]):
            finish()
            try:
                current_g = _percentage(row[6])
            except ValueError as error:
                diagnostics.append(
                    EvolutionDiagnostic("invalid_global_progress", number, str(error))
                )
                current_g = None
            current_user = first
            start = number
            current_rows = []
            continue
        if (
            current_user is None
            or not first
            or first in {"Evolución por bloques de primer y segundo nivel", "Nombre"}
        ):
            continue
        if _MODULE.fullmatch(first) is None and _SUBMODULE.fullmatch(first) is None:
            # Explicitly ignored source categories are visible but are not
            # rejected data and never block confirmation.
            diagnostics.append(
                EvolutionDiagnostic("excluded", number, "content category is outside import scope")
            )
            continue
        try:
            value = _percentage(row[1] if len(row) > 1 else None)
        except ValueError:
            diagnostics.append(
                EvolutionDiagnostic("invalid_progress", number, "content percentage is invalid")
            )
            continue
        current_rows.append(EvolutionRow(first, value, number))
    finish()
    if not blocks:
        diagnostics.append(EvolutionDiagnostic("no_blocks", None, "no Usuario blocks were found"))
    return tuple(blocks), tuple(diagnostics)


def _node_id(edition_id: UUID, title: str) -> str:
    return str(uuid5(_NAMESPACE, f"{edition_id}:{title.casefold()}"))


def _resolve(db: sqlite3.Connection, user: str, edition_id: UUID) -> sqlite3.Row | None:
    # The Usuario value is an exact approved dni/global enrollment identity.
    return db.execute(
        "SELECT e.id FROM enrollment e JOIN enrollment_external_identity x "
        "ON x.enrollment_id=e.id WHERE e.edition_id=? AND x.source='dni' "
        "AND x.context='global' AND x.source_enrollment_id=? AND x.edition_id=?",
        (str(edition_id), user, str(edition_id)),
    ).fetchone()


def _preview(
    db: sqlite3.Connection,
    blocks: tuple[EvolutionBlock, ...],
    edition_id: UUID,
    diagnostics: tuple[EvolutionDiagnostic, ...],
) -> EvolutionPreview:
    result = list(diagnostics)
    changes: list[EvolutionChange] = []
    changed = unchanged = rejected = 0
    excluded = sum(1 for item in diagnostics if item.code == "excluded")
    rejected = len(diagnostics)
    rejected -= excluded
    planned_modules = {
        item.title for item in _ordered_items(blocks) if _MODULE.fullmatch(item.title)
    }
    seen_users: set[str] = set()
    for block in blocks:
        if block.user in seen_users:
            result.append(
                EvolutionDiagnostic(
                    "duplicate_identity", block.start_row, "duplicate enrollment identity"
                )
            )
            rejected += 1
            continue
        seen_users.add(block.user)
        enrollment = _resolve(db, block.user, edition_id)
        if enrollment is None:
            result.append(
                EvolutionDiagnostic(
                    "enrollment_not_found", block.start_row, "existing enrollment was not resolved"
                )
            )
            rejected += 1
            continue
        previous_global = db.execute(
            "SELECT global_g_percentage FROM enrollment_progress_current WHERE enrollment_id=?",
            (enrollment["id"],),
        ).fetchone()
        global_kind = (
            "unchanged"
            if previous_global is not None
            and previous_global["global_g_percentage"] == str(block.global_g_percentage)
            else "change"
        )
        changes.append(EvolutionChange(global_kind, "global_progress", block.start_row))
        if global_kind == "unchanged":
            unchanged += 1
        else:
            changed += 1
        ordered_items = tuple(item for item in _ordered_items(blocks) if item in block.rows)
        for item in ordered_items:
            match = _SUBMODULE.fullmatch(item.title)
            if match:
                parent_title = f"Módulo {match.group(1)}"
                parent = db.execute(
                    "SELECT id FROM content_node WHERE edition_id=? AND external_id=?",
                    (str(edition_id), _node_id(edition_id, parent_title)),
                ).fetchone()
                if parent is None and parent_title not in planned_modules:
                    result.append(
                        EvolutionDiagnostic(
                            "parent_not_found",
                            item.row_number,
                            "existing module parent was not resolved",
                        )
                    )
                    rejected += 1
                    continue
            node = db.execute(
                "SELECT pages_percentage FROM content_progress_current "
                "WHERE enrollment_id=? AND node_id=?",
                (enrollment["id"], _node_id(edition_id, item.title)),
            ).fetchone()
            kind = (
                "unchanged"
                if node is not None and node["pages_percentage"] == str(item.pages_percentage)
                else "change"
            )
            changes.append(EvolutionChange(kind, "content_progress", item.row_number))
            if kind == "unchanged":
                unchanged += 1
            else:
                changed += 1
    return EvolutionPreview(
        tuple(blocks), tuple(result), tuple(changes), changed, unchanged, rejected, excluded
    )


def import_evolution_xlsx(
    path: str | Path,
    database_path: Path,
    edition_id: UUID,
    imported_at: datetime,
    *,
    confirm: bool = False,
) -> EvolutionImportResult:
    """Return a safe preview, or apply it atomically after explicit confirmation."""
    if imported_at.tzinfo is None or imported_at.utcoffset() is None:
        raise ValueError("imported_at must be timezone-aware")
    blocks, parse_diagnostics = parse_evolution_xlsx(path)
    with connection(database_path) as db:
        preview = _preview(db, blocks, edition_id, parse_diagnostics)
        if not confirm:
            return EvolutionImportResult(
                False,
                False,
                preview.changed,
                preview.unchanged,
                preview.rejected,
                preview.diagnostics,
                preview,
                preview.excluded,
            )
        fingerprint = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        idempotency_key = f"evolution:{edition_id}:{fingerprint}"
        existing = db.execute(
            "SELECT status FROM import_batch WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if existing is not None:
            return EvolutionImportResult(
                True,
                True,
                0,
                len(preview.changes),
                preview.rejected,
                preview.diagnostics,
                preview,
                preview.excluded,
            )
        changed, unchanged = _apply(
            db, preview, edition_id, imported_at, fingerprint, idempotency_key
        )
        return EvolutionImportResult(
            True,
            changed == 0,
            changed,
            unchanged,
            preview.rejected,
            preview.diagnostics,
            preview,
            preview.excluded,
        )


def _apply(
    db: sqlite3.Connection,
    preview: EvolutionPreview,
    edition_id: UUID,
    imported_at: datetime,
    fingerprint: str,
    idempotency_key: str,
) -> tuple[int, int]:
    batch_id = str(uuid4())
    excluded = preview.excluded
    db.execute(
        "INSERT INTO import_batch("
        "id,source_type,source_name,started_at,status,source_fingerprint,"
        "context,action,total_count,accepted_count,rejected_count,excluded_count,finished_at,"
        "scope_type,scope_reference,idempotency_key) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            batch_id,
            "excel",
            "evolution.xlsx",
            imported_at.isoformat(),
            "applied",
            fingerprint,
            str(edition_id),
            "upsert",
            len(preview.changes) + preview.rejected + excluded,
            0,
            preview.rejected,
            excluded,
            imported_at.isoformat(),
            "partial",
            str(edition_id),
            idempotency_key,
        ),
    )
    changed = unchanged = 0
    seen_users: set[str] = set()
    for diagnostic in preview.diagnostics:
        db.execute(
            "INSERT INTO import_batch_change("
            "id,batch_id,entity_type,change_type,source_row_number,"
            "diagnostic_code,diagnostic_message) VALUES(?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                batch_id,
                "evolution",
                "EXCLUDED" if diagnostic.code == "excluded" else "REJECTED",
                diagnostic.row_number,
                diagnostic.code,
                diagnostic.message,
            ),
        )
    # Materialise every module first.  This is deliberately the same global
    # module-before-submodule plan used by preview, so a parent may be in a
    # different student block without being silently skipped during apply.
    for block in preview.blocks:
        if block.user in seen_users:
            continue
        enrollment = _resolve(db, block.user, edition_id)
        if enrollment is None:
            continue
        for item in block.rows:
            if not _MODULE.fullmatch(item.title):
                continue
            node_id = _node_id(edition_id, item.title)
            edition = db.execute(
                "SELECT course_id FROM edition WHERE id=?", (str(edition_id),)
            ).fetchone()
            if edition is None:
                raise RuntimeError("preview/apply edition resolution mismatch")
            db.execute(
                "INSERT INTO content_node"
                "(id,course_id,edition_id,node_type,title,parent_id,external_id) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (
                    node_id,
                    edition["course_id"],
                    str(edition_id),
                    "module",
                    item.title,
                    None,
                    node_id,
                ),
            )
    seen_users.clear()
    for block in preview.blocks:
        if block.user in seen_users:
            continue
        seen_users.add(block.user)
        enrollment = _resolve(db, block.user, edition_id)
        if enrollment is None:
            continue
        previous_global = db.execute(
            "SELECT global_g_percentage FROM enrollment_progress_current WHERE enrollment_id=?",
            (enrollment["id"],),
        ).fetchone()
        if previous_global is not None and previous_global["global_g_percentage"] == str(
            block.global_g_percentage
        ):
            unchanged += 1
            global_kind = "UNCHANGED"
        else:
            changed += 1
            global_kind = "CHANGE"
            db.execute(
                "INSERT INTO enrollment_progress_current VALUES(?,?,?) "
                "ON CONFLICT(enrollment_id) DO UPDATE SET "
                "global_g_percentage=excluded.global_g_percentage, "
                "imported_at=excluded.imported_at",
                (enrollment["id"], str(block.global_g_percentage), imported_at.isoformat()),
            )
        db.execute(
            "INSERT INTO import_batch_change("
            "id,batch_id,entity_type,change_type,entity_id,source_row_number) "
            "VALUES(?,?,?,?,?,?)",
            (
                str(uuid4()),
                batch_id,
                "global_progress",
                global_kind,
                enrollment["id"],
                block.start_row,
            ),
        )
        ordered_items = tuple(item for item in _ordered_items(preview.blocks) if item in block.rows)
        for item in ordered_items:
            match = _SUBMODULE.fullmatch(item.title)
            if match:
                parent_title = f"Módulo {match.group(1)}"
                parent = db.execute(
                    "SELECT id FROM content_node WHERE edition_id=? AND external_id=?",
                    (str(edition_id), _node_id(edition_id, parent_title)),
                ).fetchone()
                if parent is None:
                    # The preview contains the rejection diagnostic; do not
                    # create or update a node that was not accepted.
                    continue
                parent_id = parent["id"]
                node_type = "submodule"
            else:
                parent_id = None
                node_type = "module"
            node_id = _node_id(edition_id, item.title)
            db.execute(
                "INSERT INTO content_node("
                "id,course_id,edition_id,node_type,title,parent_id,external_id) "
                "SELECT ?,course_id,?, ?,?,?,? FROM edition WHERE id=? "
                "ON CONFLICT(id) DO NOTHING",
                (
                    node_id,
                    str(edition_id),
                    node_type,
                    item.title,
                    parent_id,
                    node_id,
                    str(edition_id),
                ),
            )
            existing = db.execute(
                "SELECT pages_percentage FROM content_progress_current "
                "WHERE enrollment_id=? AND node_id=?",
                (enrollment["id"], node_id),
            ).fetchone()
            is_unchanged = existing is not None and existing["pages_percentage"] == str(
                item.pages_percentage
            )
            if is_unchanged:
                unchanged += 1
                kind = "UNCHANGED"
            else:
                changed += 1
                kind = "CHANGE"
                db.execute(
                    "INSERT INTO content_progress_current VALUES(?,?,?,?) "
                    "ON CONFLICT(enrollment_id,node_id) DO UPDATE SET "
                    "pages_percentage=excluded.pages_percentage, "
                    "imported_at=excluded.imported_at",
                    (
                        enrollment["id"],
                        node_id,
                        str(item.pages_percentage),
                        imported_at.isoformat(),
                    ),
                )
            db.execute(
                "INSERT INTO import_batch_change("
                "id,batch_id,entity_type,change_type,entity_id,source_row_number) "
                "VALUES(?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    batch_id,
                    "content_progress",
                    kind,
                    enrollment["id"],
                    item.row_number,
                ),
            )
    db.execute(
        "UPDATE import_batch SET accepted_count=?, finished_at=? WHERE id=?",
        (changed, imported_at.isoformat(), batch_id),
    )
    return changed, unchanged
