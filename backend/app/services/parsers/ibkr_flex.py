"""Parse an IBKR Flex Query CSV into ledger row models.

A Flex export stacks three sections in one file — Trades, Corporate
Actions, Cash Transactions — each opening with its own header row whose
first cell is "ClientAccountID". `parse_flex_csv` splits the sections and
maps each to the M2 `Ledger*` row models; `import_statement` appends them
to an `AccountLedger`, deduplicated so re-importing a statement is a no-op.
No DB access — the M3 projection builder rebuilds the DB from the ledger.
"""


def _split_sections(
    rows: list[list[str]],
) -> list[tuple[list[str], list[list[str]]]]:
    """Split stacked CSV rows into (header, data_rows) groups.

    A header row is any row whose first cell is "ClientAccountID". Blank
    rows are dropped.
    """
    sections: list[tuple[list[str], list[list[str]]]] = []
    header: list[str] | None = None
    data: list[list[str]] = []
    for row in rows:
        if row and row[0] == "ClientAccountID":
            if header is not None:
                sections.append((header, data))
            header, data = row, []
        elif row:
            data.append(row)
    if header is not None:
        sections.append((header, data))
    return sections
