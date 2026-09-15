"""Source-independent boundaries for the import pipeline.

Adapters own reading and source-specific adaptation.  Everything after
``ImportDataset`` is deliberately unaware of the source format; this makes a
small in-memory adapter useful for demos and tests without bypassing preview
or confirmation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from adams_tutoria.excel_contract import EvaluationRecord, ProgressRecord
from adams_tutoria.import_contract import ImportCandidate, ImportResult


@dataclass(frozen=True, slots=True)
class ImportDataset:
    """Normalized records handed from an adapter to the application pipeline."""

    candidates: tuple[ImportCandidate, ...] = ()
    progress: tuple[ProgressRecord, ...] = ()
    evaluations: tuple[EvaluationRecord, ...] = ()


class ImportDatasetAdapter(Protocol):
    """Adapt one source into normalized, source-independent records."""

    def load(self) -> ImportResult[ImportDataset]: ...


@dataclass(frozen=True, slots=True)
class InMemoryImportAdapter:
    """Synthetic adapter used by tests and documentation examples.

    It intentionally receives already normalized records.  It still returns
    an ``ImportResult`` so callers exercise the same rejection/preview path as
    file-backed adapters.
    """

    dataset: ImportDataset
    rejected: tuple = ()
    warnings: tuple = ()

    def load(self) -> ImportResult[ImportDataset]:
        return ImportResult(
            (self.dataset,),
            self.rejected,
            self.warnings,
        )


def dataset_from(
    *,
    candidates: Iterable[ImportCandidate] = (),
    progress: Iterable[ProgressRecord] = (),
    evaluations: Iterable[EvaluationRecord] = (),
) -> ImportDataset:
    """Build a dataset while keeping the adapter boundary explicit."""

    return ImportDataset(tuple(candidates), tuple(progress), tuple(evaluations))
