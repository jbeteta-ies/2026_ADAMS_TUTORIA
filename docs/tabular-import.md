# Generic tabular import

`adams_tutoria.tabular_import.read_tabular` reads only `.csv` and `.xlsx`
files. CSV uses `utf-8-sig` and comma by default; callers can provide an
explicit one-character delimiter and encoding through `TabularImportConfig`.
XLSX is read with `openpyxl` in `read_only=True, data_only=True` mode.

The reader returns the existing `ImportResult`, with accepted rows represented
as header-keyed mappings. It performs structural checks only: required columns
must be present in the header, and required non-empty columns reject rows whose
value is `None` or blank. Missing/duplicate headers and inconsistent row widths
are rejected as invalid. It does not map ADAMS columns, construct domain
objects, match records, log raw rows, or write to SQLite.

Provenance row numbers are one-based data-record ordinals (the first record
after the header is 1), not physical CSV line numbers. This distinction is
important when a quoted CSV field contains a newline. Header-level rejections
have no row number.
