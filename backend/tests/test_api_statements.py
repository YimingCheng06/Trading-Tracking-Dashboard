from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "ibkr_flex_sample.csv"


def test_upload_statement_imports_and_lists_account(api_client):
    with FIXTURE.open("rb") as f:
        response = api_client.post(
            "/statements/upload", files={"file": ("statement.csv", f, "text/csv")}
        )
    assert response.status_code == 200
    body = response.json()
    accounts = {a["broker_account_id"]: a for a in body["accounts"]}
    assert "U0000000" in accounts
    # The synthetic fixture has 4 trades and 6 cash flows for U0000000.
    assert accounts["U0000000"]["trades"]["added"] == 4
    assert accounts["U0000000"]["cash_flows"]["added"] == 6

    # The imported account is now visible via GET /accounts.
    listed = api_client.get("/accounts").json()
    assert [a["broker_account_id"] for a in listed] == ["U0000000"]


def test_upload_statement_is_idempotent(api_client):
    with FIXTURE.open("rb") as f:
        api_client.post(
            "/statements/upload", files={"file": ("statement.csv", f, "text/csv")}
        )
    with FIXTURE.open("rb") as f:
        response = api_client.post(
            "/statements/upload", files={"file": ("statement.csv", f, "text/csv")}
        )
    body = response.json()
    accounts = {a["broker_account_id"]: a for a in body["accounts"]}
    assert accounts["U0000000"]["trades"]["added"] == 0  # all deduplicated


def test_upload_rejects_unparseable_file(api_client):
    response = api_client.post(
        "/statements/upload",
        files={"file": ("bad.csv", b"not,a,valid,flex,file\n", "text/csv")},
    )
    assert response.status_code == 400
