"""Statement-upload endpoint."""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api import schemas
from app.api.deps import get_accounts_dir
from app.db.base import get_db
from app.services.ledger.account_ledger import AccountLedger
from app.services.parsers.ibkr_flex import import_statement
from app.services.projection.builder import rebuild_account

router = APIRouter(tags=["statements"])


def _counts(report) -> dict[str, schemas.AppendCountOut]:
    """An ImportReport's four AppendReports as AppendCountOut models."""
    return {
        name: schemas.AppendCountOut(added=ar.added, skipped=ar.skipped)
        for name, ar in (
            ("instruments", report.instruments),
            ("trades", report.trades),
            ("cash_flows", report.cash_flows),
            ("corporate_actions", report.corporate_actions),
        )
    }


@router.post("/statements/upload", response_model=schemas.UploadReportOut)
def upload_statement(
    file: UploadFile,
    db: Session = Depends(get_db),
    accounts_dir: Path = Depends(get_accounts_dir),
) -> schemas.UploadReportOut:
    """Parse an uploaded IBKR Flex CSV, append to the ledger, rebuild the DB.

    Local only — no market-data fetch. Parse failures become HTTP 400.
    """
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        reports = import_statement(tmp_path, accounts_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    accounts_out: list[schemas.AccountImportOut] = []
    for account_id, report in reports.items():
        rebuild_account(db, AccountLedger(accounts_dir / account_id))
        accounts_out.append(
            schemas.AccountImportOut(broker_account_id=account_id, **_counts(report))
        )
    return schemas.UploadReportOut(accounts=accounts_out)
