"""Generic structural readers for synthetic or operational tabular files.

This module deliberately stops at a header-keyed row mapping.  It does not
interpret source columns, create domain objects, or persist imported data.
"""

import csv
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook

from adams_tutoria.import_contract import ImportResult, Provenance, RejectedRow, RejectionCode

type TabularValue = object
type TabularRow = dict[str, TabularValue]


@dataclass(frozen=True, slots=True)
class TabularImportConfig:
    """Structural validation options for a CSV or XLSX source."""

    required_columns: tuple[str, ...] = ()
    required_non_empty_columns: tuple[str, ...] = ()
    delimiter: str = ","
    encoding: str = "utf-8-sig"

    def __post_init__(self) -> None:
        if len(self.delimiter) != 1:
            raise ValueError("delimiter must be exactly one character")
        if not self.encoding.strip():
            raise ValueError("encoding must not be blank")
        all_columns = (*self.required_columns, *self.required_non_empty_columns)
        if any(not column.strip() for column in all_columns):
            raise ValueError("required column names must not be blank")

    @property
    def all_required_columns(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.required_columns, *self.required_non_empty_columns)))


def read_tabular(
    path: str | Path | BinaryIO,
    *,
    config: TabularImportConfig | None = None,
) -> ImportResult[TabularRow]:
    """Read a ``.csv`` or ``.xlsx`` file and validate its tabular structure.

    Provenance row numbers are one-based data-record ordinals: the first data
    record is row 1, independent of physical file lines.  This avoids claiming
    a physical line number for CSV records that contain embedded newlines.
    """

    source = Path(path) if isinstance(path, (str, Path)) else None
    suffix = source.suffix.lower() if source else ".xlsx"
    options = config or TabularImportConfig()
    if suffix == ".csv":
        if source is None:
            raise ValueError("CSV input must be a filesystem path")
        rows = _read_csv(source, options)
        source_kind = "csv"
    elif suffix == ".xlsx":
        rows = _read_xlsx(path)
        source_kind = "xlsx"
    else:
        raise ValueError("only .csv and .xlsx files are supported")
    source_name = source.name if source else "uploaded.xlsx"
    return _validate_rows(source_name, source_kind, rows, options)


def read_xlsx_values(path: str | Path | BinaryIO) -> Iterator[Sequence[object]]:
    """Yield XLSX rows without assigning meaning to headers or values.

    This is the generic structural reader boundary.  Format-specific adapters
    may consume repeated headers and positional rows, but the reader itself
    must not resolve identities, interpret percentages, or persist data.
    """

    yield from _read_xlsx(path)


def import_tabular(
    path: str | Path,
    *,
    config: TabularImportConfig | None = None,
) -> ImportResult[TabularRow]:
    """Compatibility-oriented alias for :func:`read_tabular`."""

    return read_tabular(path, config=config)


def _read_csv(path: Path, config: TabularImportConfig) -> Iterator[Sequence[object]]:
    with path.open("r", encoding=config.encoding, newline="") as handle:
        yield from csv.reader(handle, delimiter=config.delimiter)


def _read_xlsx(path: str | Path | BinaryIO) -> Iterator[Sequence[object]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        yield from worksheet.iter_rows(values_only=True)
    finally:
        workbook.close()


def _validate_rows(
    source_name: str,
    source_kind: str,
    rows: Iterator[Sequence[object]],
    config: TabularImportConfig,
) -> ImportResult[TabularRow]:
    def provenance(row_number: int | None) -> Provenance:
        return Provenance(source_name, source_kind, row_number=row_number)

    try:
        header_values = next(rows)
    except StopIteration:
        return ImportResult(
            rejected=(RejectedRow(provenance(None), RejectionCode.INVALID, "input has no header"),)
        )

    headers = tuple(_header_text(value) for value in header_values)
    if any(not header for header in headers) or len(set(headers)) != len(headers):
        return ImportResult(
            rejected=(
                RejectedRow(
                    provenance(None), RejectionCode.INVALID, "header is blank or duplicated"
                ),
            )
        )
    missing = tuple(column for column in config.all_required_columns if column not in headers)
    if missing:
        return ImportResult(
            rejected=(
                RejectedRow(
                    provenance(None),
                    RejectionCode.INVALID,
                    "required columns are missing",
                    fields=missing,
                ),
            )
        )

    accepted: list[TabularRow] = []
    rejected: list[RejectedRow] = []
    for row_number, values in enumerate(rows, start=1):
        row_provenance = provenance(row_number)
        if len(values) != len(headers):
            rejected.append(
                RejectedRow(
                    row_provenance, RejectionCode.INVALID, "row does not match header width"
                )
            )
            continue
        row = dict(zip(headers, values, strict=True))
        empty_columns = tuple(
            column for column in config.required_non_empty_columns if _is_empty(row[column])
        )
        if empty_columns:
            rejected.append(
                RejectedRow(
                    row_provenance,
                    RejectionCode.MISSING_EVIDENCE,
                    "required values are empty",
                    fields=empty_columns,
                )
            )
            continue
        accepted.append(row)
    return ImportResult(accepted=tuple(accepted), rejected=tuple(rejected))


def _header_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else "" if value is None else str(value).strip()


def _is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
