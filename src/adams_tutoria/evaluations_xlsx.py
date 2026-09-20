# ruff: noqa: E501
"""Strict positional XLSX importer for the four evaluation items.

The workbook is deliberately treated as a contract, not as a discoverable
table.  No source rows are retained and the whole file is rejected when any
block or score is invalid.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from adams_tutoria.persistence.database import connection
from adams_tutoria.tabular_import import read_xlsx_values

CONTRACT_VERSION = "evaluations-positional-8-rows-v1"
_SCORE = re.compile(r"^([0-9]+(?:[.,][0-9]+)?)\s*\(([0-9]+(?:[.,][0-9]+)?)\)$")
_ITEMS = ("E1", "E2", "E3", "E4")
_LABELS = ("Evaluación Módulo 1", "Evaluación Módulo 2", "Evaluación Módulo 3", "Evaluación Final")


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    dni: str
    reference: str
    label: str
    raw_value: str | None
    score: Decimal | None
    threshold: Decimal | None
    result_status: str
    passed: bool | None
    block_row: int


@dataclass(frozen=True, slots=True)
class EvaluationDiagnostic:
    code: str
    row_number: int | None
    message: str


@dataclass(frozen=True, slots=True)
class EvaluationPreview:
    observations: tuple[EvaluationObservation, ...]
    diagnostics: tuple[EvaluationDiagnostic, ...]
    changes: tuple[str, ...]
    additions: int
    changes_count: int
    unchanged: int
    rejected: int
    ambiguities: int = 0

    @property
    def valid(self) -> bool:
        return not self.diagnostics

    @property
    def category_counts(self) -> dict[str, int]:
        """Return the complete, privacy-safe preview taxonomy."""
        return {
            "additions": self.additions,
            "changes": self.changes_count,
            "unchanged": self.unchanged,
            "rejected": self.rejected,
            "ambiguities": self.ambiguities,
        }

    def average(self, dni: str) -> Decimal:
        values = [o.score or Decimal("0") for o in self.observations if o.dni == dni]
        if len(values) != 4:
            raise ValueError("average requires all four evaluation positions")
        return sum(values, Decimal("0")) / Decimal("4")

    def global_passed(self, dni: str) -> bool:
        return self.average(dni) >= Decimal("50")


@dataclass(frozen=True, slots=True)
class EvaluationImportResult:
    applied: bool
    idempotent: bool
    preview: EvaluationPreview
    diagnostics: tuple[EvaluationDiagnostic, ...]


def _text(value: object) -> str:
    return "" if value is None else str(value).replace("\xa0", " ").strip()


def _score(
    value: object, row: int
) -> tuple[str | None, Decimal | None, Decimal | None, str, bool | None]:
    if value is None:
        return None, None, None, "not_attempted", None
    raw = str(value)
    text = raw.strip()
    if text in {"", "''"}:
        return raw, None, None, "not_attempted", None
    match = _SCORE.fullmatch(text)
    score_text, threshold_text = match.groups() if match else (text, None)
    try:
        score = Decimal(score_text.replace(",", "."))
        threshold = Decimal(threshold_text.replace(",", ".")) if threshold_text else None
    except InvalidOperation as error:
        raise ValueError("score is invalid") from error
    if not score.is_finite() or not Decimal("0") <= score <= Decimal("100"):
        raise ValueError("score must be between 0 and 100")
    if threshold is not None and threshold not in {Decimal("50"), Decimal("60"), Decimal("70")}:
        raise ValueError("threshold must be 50, 60 or 70")
    return raw, score, threshold, "attempted", score >= threshold if threshold is not None else None


def parse_evaluations_xlsx(
    source: str | Path | BinaryIO,
) -> tuple[tuple[EvaluationObservation, ...], tuple[EvaluationDiagnostic, ...]]:
    rows = [tuple(row) for row in read_xlsx_values(source)]
    while rows and all(value is None for value in rows[-1]):
        rows.pop()
    diagnostics: list[EvaluationDiagnostic] = []
    observations: list[EvaluationObservation] = []
    if not rows or len(rows) % 8:
        return (), (
            EvaluationDiagnostic(
                "invalid_block_length", None, "workbook must contain complete 8-row blocks"
            ),
        )
    for offset in range(0, len(rows), 8):
        start = offset + 1
        user = _text(rows[offset + 1][0] if len(rows[offset + 1]) else None)
        headers = tuple(
            _text(rows[offset + 6][column]) if len(rows[offset + 6]) > column else ""
            for column in range(2, 6)
        )
        if not user:
            diagnostics.append(
                EvaluationDiagnostic("missing_identity", start + 1, "DNI is missing")
            )
        if headers != _ITEMS:
            diagnostics.append(
                EvaluationDiagnostic(
                    "invalid_evaluation_headers",
                    start + 7,
                    "evaluation headers do not match contract",
                )
            )
        for index, reference in enumerate(_ITEMS):
            value = rows[offset + 7][index + 2] if len(rows[offset + 7]) > index + 2 else None
            try:
                raw, score, threshold, status, passed = _score(value, start + 8)
            except ValueError as error:
                diagnostics.append(EvaluationDiagnostic("invalid_score", start + 8, str(error)))
                continue
            observations.append(
                EvaluationObservation(
                    user, reference, _LABELS[index], raw, score, threshold, status, passed, start
                )
            )
    return tuple(observations), tuple(diagnostics)


def _resolve(db: sqlite3.Connection, dni: str, edition_id: UUID) -> tuple[str, str | None]:
    rows = db.execute(
        "SELECT enrollment_id FROM enrollment_external_identity WHERE source='dni' AND context='global' AND source_enrollment_id=? AND edition_id=?",
        (dni, str(edition_id)),
    ).fetchall()
    if not rows:
        return "not_resolved", None
    if len(rows) > 1:
        return "ambiguous", None
    return "resolved", rows[0][0]


def _values(
    observation: EvaluationObservation, enrollment_id: str, evaluation_id: str
) -> tuple[object, ...]:
    return (
        evaluation_id,
        enrollment_id,
        "evaluation_item",
        observation.reference,
        "completed",
        str(observation.score) if observation.score is not None else None,
        "100",
        observation.passed,
        None,
        observation.label,
        observation.reference,
        observation.result_status,
        observation.raw_value,
        str(observation.score) if observation.score is not None else None,
        "0-100",
        str(observation.threshold) if observation.threshold is not None else None,
    )


def import_evaluations_xlsx(
    path: str | Path,
    database_path: Path,
    edition_id: UUID,
    *,
    confirm: bool = False,
    contract_version: str = CONTRACT_VERSION,
) -> EvaluationImportResult:
    data = Path(path).read_bytes() if isinstance(path, (str, Path)) else path.read()
    observations, diagnostics = parse_evaluations_xlsx(BytesIO(data))
    digest = hashlib.sha256(data).hexdigest()
    with connection(database_path) as db:
        expanded = list(diagnostics)
        resolved: list[tuple[EvaluationObservation, str]] = []
        identity_codes: dict[int, str] = {}
        for observation in observations:
            resolution, enrollment_id = _resolve(db, observation.dni, edition_id)
            if enrollment_id is None:
                code = (
                    "identity_ambiguous" if resolution == "ambiguous" else "identity_not_resolved"
                )
                identity_codes[observation.block_row] = code
                if not any(
                    item.code == code and item.row_number == observation.block_row
                    for item in expanded
                ):
                    expanded.append(
                        EvaluationDiagnostic(
                            code,
                            observation.block_row,
                            (
                                "DNI matches more than one enrollment in the edition"
                                if code == "identity_ambiguous"
                                else "DNI does not match an enrollment in the edition"
                            ),
                        )
                    )
                continue
            resolved.append((observation, enrollment_id))
        changes: list[str] = []
        for observation, enrollment_id in resolved:
            row = db.execute(
                "SELECT * FROM evaluation e JOIN evaluation_external_identity x ON x.evaluation_id=e.id WHERE x.source=? AND x.context=? AND x.enrollment_id=? AND x.evaluation_reference=?",
                ("xlsx-evaluations", str(edition_id), enrollment_id, observation.reference),
            ).fetchone()
            candidate = _values(observation, enrollment_id, row["id"] if row else str(uuid4()))
            changes.append(
                "unchanged"
                if row is not None and tuple(row[:16]) == candidate
                else ("change" if row else "addition")
            )
        preview = EvaluationPreview(
            tuple(o for o, _ in resolved),
            tuple(expanded),
            tuple(changes),
            changes.count("addition"),
            changes.count("change"),
            changes.count("unchanged"),
            sum(code != "identity_ambiguous" for code in (item.code for item in expanded)),
            sum(code == "identity_ambiguous" for code in identity_codes.values()),
        )
        if not confirm or not preview.valid:
            return EvaluationImportResult(False, False, preview, preview.diagnostics)
        key = f"{digest}:{edition_id}:{contract_version}"
        existing = db.execute(
            "SELECT 1 FROM import_batch WHERE idempotency_key=?", (key,)
        ).fetchone()
        if existing:
            return EvaluationImportResult(True, True, preview, preview.diagnostics)
        batch_id = str(uuid4())
        db.execute(
            "INSERT INTO import_batch(id,source_type,source_name,started_at,finished_at,status,source_fingerprint,context,action,total_count,accepted_count,rejected_count,scope_type,scope_reference,idempotency_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                batch_id,
                "excel",
                "evaluations.xlsx",
                "now",
                "now",
                "applied",
                digest,
                str(edition_id),
                "upsert",
                len(resolved),
                sum(kind != "unchanged" for kind in changes),
                0,
                "full",
                str(edition_id),
                key,
            ),
        )
        for (observation, enrollment_id), kind in zip(resolved, changes, strict=True):
            if kind == "unchanged":
                continue
            row = db.execute(
                "SELECT e.id FROM evaluation e JOIN evaluation_external_identity x ON x.evaluation_id=e.id WHERE x.source=? AND x.context=? AND x.enrollment_id=? AND x.evaluation_reference=?",
                ("xlsx-evaluations", str(edition_id), enrollment_id, observation.reference),
            ).fetchone()
            evaluation_id = row[0] if row else str(uuid4())
            values = _values(observation, enrollment_id, evaluation_id)
            if row:
                db.execute(
                    "UPDATE evaluation SET enrollment_id=?,target_type=?,target_id=?,status=?,score=?,max_score=?,passed=?,completed_at=?,target_label=?,external_id=?,result_status=?,raw_value=?,numeric_value=?,scale=?,threshold=? WHERE id=?",
                    (*values[1:], evaluation_id),
                )
                change = "changed"
            else:
                db.execute(
                    "INSERT INTO evaluation(id,enrollment_id,target_type,target_id,status,score,max_score,passed,completed_at,target_label,external_id,result_status,raw_value,numeric_value,scale,threshold) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    values,
                )
                db.execute(
                    "INSERT INTO evaluation_external_identity VALUES(?,?,?,?,?)",
                    (
                        "xlsx-evaluations",
                        str(edition_id),
                        enrollment_id,
                        observation.reference,
                        evaluation_id,
                    ),
                )
                change = "created"
            db.execute(
                "INSERT INTO evaluation_history(id,evaluation_id,batch_id,status,score,max_score,passed,completed_at,result_status,raw_value,numeric_value,scale,threshold) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    evaluation_id,
                    batch_id,
                    values[4],
                    values[5],
                    values[6],
                    values[7],
                    values[8],
                    values[11],
                    values[12],
                    values[13],
                    values[14],
                    values[15],
                ),
            )
            db.execute(
                "INSERT INTO import_batch_change(id,batch_id,entity_type,change_type,entity_id,source_row_number) VALUES(?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    batch_id,
                    "evaluation",
                    change,
                    evaluation_id,
                    observation.block_row,
                ),
            )
        return EvaluationImportResult(True, False, preview, preview.diagnostics)
