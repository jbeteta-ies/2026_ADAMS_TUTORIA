"""Synthetic tests for the provisional ADAMS progress adapter."""

from pathlib import Path

from adams_tutoria.adapters.adams import AdamsProgressAdapter, AdamsProgressMapping
from adams_tutoria.import_contract import RejectionCode
from adams_tutoria.tabular_import import read_tabular


def _adapter() -> AdamsProgressAdapter:
    return AdamsProgressAdapter(
        AdamsProgressMapping(
            student_reference="student_key",
            edition_label="edition_key",
            progress_value="measure",
            recorded_at="when",
        )
    )


def test_progress_mapping_is_immutable_and_preserves_scalar_without_scale() -> None:
    mapping = AdamsProgressMapping(
        student_reference="student_key", edition_label="edition_key", progress_value="measure"
    )
    result = AdamsProgressAdapter(mapping).adapt(
        [{"student_key": "S-1", "edition_key": "Spring", "measure": "0.37"}]
    )
    candidate = result.accepted[0]
    assert candidate.values == (("progress_value", "0.37"),)
    assert candidate.enrollment is not None
    assert candidate.enrollment.student is not None
    assert candidate.enrollment.edition is not None
    assert candidate.enrollment.edition.edition_label == "Spring"

    try:
        mapping.progress_value = "other"  # type: ignore[misc]
    except Exception as error:
        assert isinstance(error, AttributeError)
    else:
        raise AssertionError("mapping unexpectedly mutable")


def test_progress_rows_are_rejected_conservatively_and_partial_success_is_retained() -> None:
    result = _adapter().adapt(
        [
            {"student_key": "S-1", "edition_key": "Spring", "measure": 42},
            {"edition_key": "Spring", "measure": 43},
            {"student_key": "S-3", "edition_key": "Spring", "measure": "not-a-number"},
        ]
    )
    assert len(result.accepted) == 1
    assert len(result.rejected) == 2
    assert result.partial_success
    assert all(rejection.code is RejectionCode.MISSING_EVIDENCE for rejection in result.rejected)
    assert all(rejection.fields == () for rejection in result.rejected)


def test_iso_timestamp_is_normalized_without_claiming_progress_semantics() -> None:
    result = _adapter().adapt(
        [
            {
                "student_key": "S-1",
                "edition_key": "Spring",
                "measure": -12.5,
                "when": "2026-01-02T03:04:05Z",
            }
        ]
    )
    assert result.accepted[0].values == (
        ("progress_value", "-12.5"),
        ("recorded_at", "2026-01-02T03:04:05+00:00"),
    )


def test_csv_reader_to_tabular_row_to_progress_adapter(tmp_path: Path) -> None:
    source = tmp_path / "synthetic-progress.csv"
    source.write_text("student_key,edition_key,measure\nStudent-001,Spring,7\n", encoding="utf-8")
    rows = read_tabular(source).accepted
    result = AdamsProgressAdapter(
        AdamsProgressMapping(
            student_reference="student_key", edition_label="edition_key", progress_value="measure"
        ),
        source_name=source.name,
        source_kind="csv",
    ).adapt(rows)

    assert len(result.accepted) == 1
    assert result.accepted[0].entity.value == "progress"
    assert result.accepted[0].provenance.source_name == "synthetic-progress.csv"
