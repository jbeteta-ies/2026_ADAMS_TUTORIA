"""Synthetic tests for generic CSV/XLSX structural import."""

from pathlib import Path

from openpyxl import Workbook

from adams_tutoria.import_contract import RejectionCode
from adams_tutoria.tabular_import import TabularImportConfig, read_tabular


def test_csv_accepts_rows_and_rejects_empty_required_values(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.csv"
    source.write_text("code;label\nA1;First\nA2; \n", encoding="utf-8")

    result = read_tabular(
        source,
        config=TabularImportConfig(
            required_columns=("code",),
            required_non_empty_columns=("label",),
            delimiter=";",
        ),
    )

    assert result.accepted == ({"code": "A1", "label": "First"},)
    assert len(result.rejected) == 1
    assert result.rejected[0].code is RejectionCode.MISSING_EVIDENCE
    assert result.rejected[0].provenance.row_number == 2


def test_csv_utf8_sig_and_multiline_record_use_record_ordinal(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.csv"
    source.write_bytes(b'code,description\nA1,"line one\nline two"\n')

    result = read_tabular(source)

    assert result.accepted[0]["description"] == "line one\nline two"
    assert result.accepted[0]["code"] == "A1"
    assert result.accepted[0] == {"code": "A1", "description": "line one\nline two"}


def test_xlsx_reads_values_without_domain_interpretation(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["code", "amount"])
    worksheet.append(["A1", 3.5])
    workbook.save(source)

    result = read_tabular(source, config=TabularImportConfig(required_columns=("code",)))

    assert result.accepted == ({"code": "A1", "amount": 3.5},)


def test_missing_required_header_is_rejected_without_reading_rows(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.csv"
    source.write_text("code\nA1\n", encoding="utf-8")

    result = read_tabular(source, config=TabularImportConfig(required_columns=("missing",)))

    assert not result.accepted
    assert result.rejected[0].code is RejectionCode.INVALID
    assert result.rejected[0].fields == ("missing",)
