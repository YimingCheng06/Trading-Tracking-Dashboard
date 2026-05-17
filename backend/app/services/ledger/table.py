"""Generic reader/appender for one CSV ledger file.

`read()` parses every row through the Pydantic row model. `append()` writes
only rows whose `dedup_key` is not already present — in the file or earlier
in the same batch — so re-importing a statement never duplicates rows.
`read()` raises `pydantic.ValidationError` if a row is missing a required
field (e.g. a blank `trade_id`) — corrupt rows are surfaced, not skipped.
`append()` is not safe under concurrent writers; this subsystem assumes a
single-user local app.
"""

import csv
from pathlib import Path

from pydantic import BaseModel


class AppendReport(BaseModel):
    added: int
    skipped: int


class LedgerTable[RowT: BaseModel]:
    def __init__(self, path: Path, row_model: type[RowT]) -> None:
        self.path = path
        self.row_model = row_model

    def read(self) -> list[RowT]:
        if not self.path.exists():
            return []
        with self.path.open(newline="") as f:
            # csv gives "" for blank cells; treat blank as missing so Pydantic
            # applies field defaults / None instead of seeing an empty string.
            return [
                self.row_model.model_validate(
                    {k: (v if v != "" else None) for k, v in raw.items()}
                )
                for raw in csv.DictReader(f)
            ]

    def append(self, rows: list[RowT]) -> AppendReport:
        seen = {r.dedup_key for r in self.read()}
        fresh: list[RowT] = []
        for row in rows:
            if row.dedup_key in seen:
                continue
            seen.add(row.dedup_key)
            fresh.append(row)

        write_header = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(self.row_model.model_fields)
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for row in fresh:
                writer.writerow(row.model_dump(mode="json"))

        return AppendReport(added=len(fresh), skipped=len(rows) - len(fresh))
