import time

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.llm import InvestigatorModel, ModelFailure
from backend.app.main import create_app


def wait_for(client, identifier, statuses):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = client.get(f"/api/investigations/{identifier}").json()
        if row["status"] in statuses:
            return row
        time.sleep(0.02)
    raise AssertionError(f"Did not reach {statuses}: {row}")


def test_api_restart_review_history_and_invalid_submissions(tmp_path):
    settings = Settings(data_dir=tmp_path, llm_mode="mock")
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/investigations", json={"issue": " "}).status_code == 422
        created = client.post("/api/investigations", json={"issue": "Page 1 skips the first two products"})
        assert created.status_code == 202
        identifier = created.json()["id"]
        row = wait_for(client, identifier, {"awaiting_review", "failed"})
        assert row["status"] == "awaiting_review", row
        assert row["mode"] == "mock"
        assert client.get("/api/investigations").json()[0]["id"] == identifier
    with TestClient(create_app(settings)) as client:
        url = f"/api/investigations/{identifier}/review"
        wait_for(client, identifier, {"awaiting_review"})
        assert client.post(url, json={"decision": "revise", "feedback": " ", "report_version": 1}).status_code == 422
        assert client.post(url, json={"decision": "accept", "report_version": 99}).status_code == 409
        assert client.post(url, json={"decision": "revise", "feedback": "Explain page zero", "report_version": 1}).status_code == 202
        row = wait_for(client, identifier, {"awaiting_review", "failed"})
        assert row["state"]["report_version"] == 2, row
        assert client.post(url, json={"decision": "accept", "report_version": 1}).status_code == 409
        assert client.post(url, json={"decision": "accept", "report_version": 2}).status_code == 202
        assert wait_for(client, identifier, {"accepted", "failed"})["status"] == "accepted"
        assert client.post(url, json={"decision": "accept", "report_version": 2}).status_code == 409
        assert client.get("/api/investigations/unknown").status_code == 404


class BrokenModel(InvestigatorModel):
    def plan(self, issue, files):
        raise ModelFailure("Simulated provider failure")


def test_provider_failure_is_visible(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, llm_mode="mock"), BrokenModel)) as client:
        identifier = client.post("/api/investigations", json={"issue": "Investigate a catalog failure"}).json()["id"]
        result = wait_for(client, identifier, {"failed"})
        assert result["error"] == "Simulated provider failure"

