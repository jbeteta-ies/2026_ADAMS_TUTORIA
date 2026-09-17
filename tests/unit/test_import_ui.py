from datetime import UTC, datetime
from uuid import uuid4

from adams_tutoria.domain import ImportChangeType
from adams_tutoria.import_review import ImportPreview, PreviewChange
from adams_tutoria.import_ui import _count_name_changes, _count_operations


def _preview(*changes: PreviewChange) -> ImportPreview:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return ImportPreview(uuid4(), "digest", "state", now, changes)


def test_snapshot_rename_counter_accepts_enrollment_entity() -> None:
    preview = _preview(
        PreviewChange("enrollment", ImportChangeType.CHANGE, operation="modified"),
        PreviewChange("student", ImportChangeType.CHANGE, operation="modified"),
        PreviewChange("enrollment", ImportChangeType.CHANGE, operation="created"),
    )

    assert _count_name_changes(preview) == 2


def test_preview_operation_counts_keep_categories_separate() -> None:
    preview = _preview(
        PreviewChange("enrollment", ImportChangeType.CHANGE, operation="created"),
        PreviewChange("enrollment", ImportChangeType.CHANGE, operation="absent"),
        PreviewChange("enrollment", ImportChangeType.CHANGE, operation="reactivated"),
        PreviewChange("enrollment", ImportChangeType.UNCHANGED, operation="unchanged"),
        PreviewChange("enrollment", ImportChangeType.CONFLICT, operation="conflict"),
    )

    assert _count_operations(preview, "created") == 1
    assert _count_operations(preview, "absent") == 1
    assert _count_operations(preview, "reactivated") == 1
    assert _count_operations(preview, "unchanged") == 1
