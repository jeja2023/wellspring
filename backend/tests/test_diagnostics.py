import logging
from test_workflow import context, auth


def test_request_diagnostics_do_not_record_query_or_credentials(context, caplog):
    client, _ = context
    actor = auth(client, "alice")
    with caplog.at_level(logging.INFO, logger="wellspring.requests"):
        response = client.get("/api/cases?q=synthetic-private-query", headers=actor)
    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records if record.name == "wellspring.requests"]
    assert any(response.headers["X-Request-ID"] in message and "duration_ms=" in message for message in messages)
    assert all("synthetic-private-query" not in message and "Bearer" not in message for message in messages)
