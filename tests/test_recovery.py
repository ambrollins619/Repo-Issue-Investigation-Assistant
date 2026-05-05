import sqlite3
from contextlib import closing

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from backend.app.config import Settings
from backend.app.llm import InvestigatorModel
from backend.app.models import ReviewDecision
from backend.app.repository import Repository
from backend.app.service import InvestigationService
from backend.app.workflow import build_graph


def test_durable_pending_review_recovers_without_double_revision(tmp_path):
    settings = Settings(data_dir=tmp_path, llm_mode="mock")
    service = InvestigationService(settings)
    row = service.store.create("Page 1 skips two products", settings)
    identifier = row["id"]
    service.run(identifier)
    decision = ReviewDecision(decision="revise", feedback="Clarify edge cases", report_version=1)
    assert service.store.claim_review(identifier, decision)
    service.close()
    # Simulate a process that persists Command consumption but dies before the UI projection update.
    with closing(sqlite3.connect(tmp_path / "checkpoints.db", check_same_thread=False)) as connection:
        graph = build_graph(Repository(settings.repo_root), InvestigatorModel(settings), SqliteSaver(connection))
        graph.invoke(Command(resume=decision.model_dump()), {"configurable": {"thread_id": identifier}})
    restarted = InvestigationService(settings)
    restarted.recover()
    restarted.close()
    recovered = restarted.store.get(identifier)
    assert recovered["status"] == "awaiting_review"
    assert recovered["state"]["report_version"] == 2
    assert recovered["pending_review"] is None


def test_pending_accept_survives_before_execution(tmp_path):
    settings = Settings(data_dir=tmp_path, llm_mode="mock")
    service = InvestigationService(settings)
    identifier = service.store.create("Page 1 skips two products", settings)["id"]
    service.run(identifier)
    decision = ReviewDecision(decision="accept", report_version=1)
    assert service.store.claim_review(identifier, decision)
    assert not service.store.claim_review(identifier, decision)
    service.close()
    restarted = InvestigationService(settings)
    restarted.recover()
    restarted.close()
    assert restarted.store.get(identifier)["status"] == "accepted"

