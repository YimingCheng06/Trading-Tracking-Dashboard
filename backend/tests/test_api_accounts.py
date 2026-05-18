def test_list_accounts_empty(api_client):
    response = api_client.get("/accounts")
    assert response.status_code == 200
    assert response.json() == []
