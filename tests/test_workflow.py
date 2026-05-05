import json
import sqlite3
from contextlib import closing

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from backend.app.config import PROJECT_ROOT, Settings
from backend.app.llm import InvestigatorModel
from backend.app.models import Analysis, Report, SearchPlan, validate_citations
from backend.app.repository import Repository
from backend.app.workflow import build_graph


def graph_at(path, model):
    connection = sqlite3.connect(path, check_same_thread=False)
    return connection, build_graph(Repository(PROJECT_ROOT / "sample_repo"), model, SqliteSaver(connection))


def test_review_survives_closed_connection_and_revision(tmp_path):
    model = InvestigatorModel(Settings(llm_mode="mock"))
    config = {"configurable": {"thread_id": "stable-id"}}
    connection, graph = graph_at(tmp_path / "checkpoints.db", model)
    with closing(connection):
        first = graph.invoke({"issue": "Page 1 skips the first products", "snippets": [], "search_rounds": 0}, config)
        assert first["search_rounds"] == 1
        assert graph.get_state(config).interrupts
        original_evidence = first["snippets"]
    connection, graph = graph_at(tmp_path / "checkpoints.db", model)
    with closing(connection):
        revised = graph.invoke(Command(resume={"decision": "revise", "feedback": "Explain the empty page boundary", "report_version": 1}), config)
        assert revised["report_version"] == 2
        assert revised["snippets"] == original_evidence
        assert revised["search_rounds"] == 1
        assert "empty page" in " ".join(revised["report"]["uncertainties"])
        assert graph.get_state(config).interrupts
    connection, graph = graph_at(tmp_path / "checkpoints.db", model)
    with closing(connection):
        accepted = graph.invoke(Command(resume={"decision": "accept", "feedback": "", "report_version": 2}), config)
        assert accepted["status"] == "accepted"
        assert not graph.get_state(config).next


class AlwaysSearch(InvestigatorModel):
    def analyze(self, state, revision=False):
        return Analysis(report=Report(likely_cause="Insufficient evidence", citations=[], suggested_fix="Provide missing code",
                                      suggested_tests=["Reproduce"], uncertainties=["Missing implementation"], partial=True),
                        next_search=SearchPlan(terms=["missing"], files=[]))


def test_retry_budget(tmp_path):
    connection, graph = graph_at(tmp_path / "checkpoints.db", AlwaysSearch(Settings(llm_mode="mock")))
    with closing(connection):
        result = graph.invoke({"issue": "Something unexplained happened", "snippets": [], "search_rounds": 0}, {"configurable": {"thread_id": "limit"}})
        assert result["search_rounds"] == 3
        assert len(result["snippets"]) <= 16
        assert result["report"]["partial"]
        assert "budget exhausted" in " ".join(result["report"]["uncertainties"])


def test_invented_citations_rejected():
    report = Report(likely_cause="Hypothesis", citations=[dict(snippet_id="E1", path="x.py", start_line=1, end_line=100, explanation="why")],
                    suggested_fix="Fix", suggested_tests=["Test"], uncertainties=["Not executed"], partial=False)
    with pytest.raises(ValueError, match="not retrieved"):
        validate_citations(report, [{"id": "E1", "path": "x.py", "start_line": 1, "end_line": 5}])


@pytest.mark.parametrize("case", json.loads((PROJECT_ROOT / "evaluation/issues.json").read_text()), ids=lambda case: case["id"])
def test_mock_sample_scenarios(tmp_path, case):
    connection, graph = graph_at(tmp_path / "checkpoints.db", InvestigatorModel(Settings(llm_mode="mock")))
    with closing(connection):
        result = graph.invoke({"issue": case["issue"], "snippets": [], "search_rounds": 0}, {"configurable": {"thread_id": case["id"]}})
        report = result["report"]
        assert report["partial"] == case["partial"]
        if case["expected_path"]:
            assert any(c["path"] == case["expected_path"] for c in report["citations"])
        assert all(word in (report["likely_cause"] + report["suggested_fix"]).lower() for word in case["expected_terms"])

