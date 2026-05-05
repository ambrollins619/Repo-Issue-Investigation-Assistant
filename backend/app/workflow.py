from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .models import Report, ReviewDecision, SearchPlan, validate_citations

MAX_ROUNDS = 3
MAX_SNIPPETS = 16


class State(TypedDict, total=False):
    issue: str
    plan: dict
    search_rounds: int
    snippets: list[dict]
    report: dict
    feedback: str
    status: str
    report_version: int
    needs_search: bool
    retrieval_notes: list[str]


def build_graph(repository, model, checkpointer):
    def plan(state):
        return {"plan": model.plan(state["issue"], repository.list_files()).model_dump(), "status": "collecting"}

    def collect(state):
        search = SearchPlan.model_validate(state["plan"])
        snippets = list(state.get("snippets", []))
        notes = list(state.get("retrieval_notes", []))
        retrieved = []
        for path in search.files:
            try:
                retrieved.append(repository.read_file(path))
            except (OSError, ValueError):
                notes.append("A planned file could not be read under repository access rules.")
        retrieved.extend(repository.search_code(search.terms))
        seen = {(s["path"], s["start_line"], s["end_line"]) for s in snippets}
        for snippet in retrieved:
            key = (snippet["path"], snippet["start_line"], snippet["end_line"])
            covered = any(s["path"] == snippet["path"] and s["start_line"] <= snippet["start_line"]
                          and snippet["end_line"] <= s["end_line"] for s in snippets)
            if key not in seen and not covered and len(snippets) < MAX_SNIPPETS:
                snippets.append({"id": f"E{len(snippets) + 1}", **snippet})
                seen.add(key)
        return {"snippets": snippets, "search_rounds": state.get("search_rounds", 0) + 1,
                "retrieval_notes": notes[-12:], "status": "analyzing"}

    def analyze(state):
        result = model.analyze(state)
        report = validate_citations(result.report, state["snippets"])
        more = result.next_search is not None and state["search_rounds"] < MAX_ROUNDS
        if result.next_search is not None and not more:
            report.partial = True
            report.uncertainties = (report.uncertainties[:7] + ["Search budget exhausted after the initial search and two additional rounds; requested evidence remains missing."])
        return {"report": report.model_dump(), "needs_search": more,
                "plan": result.next_search.model_dump() if more else state["plan"],
                "report_version": 1, "status": "collecting" if more else "awaiting_review"}

    def review(state):
        # LangGraph replays this node on resume. Keep everything before interrupt pure.
        decision = ReviewDecision.model_validate(interrupt({"report_version": state["report_version"], "report": state["report"]}))
        if decision.report_version != state["report_version"]:
            raise ValueError("Stale review version")
        return {"feedback": decision.feedback, "status": "accepted" if decision.decision == "accept" else "revising"}

    def revise(state):
        result = model.analyze(state, revision=True)
        report = validate_citations(result.report, state["snippets"])
        return {"report": report.model_dump(), "report_version": state["report_version"] + 1, "status": "awaiting_review"}

    graph = StateGraph(State)
    for name, node in [("plan", plan), ("collect", collect), ("analyze", analyze), ("review", review), ("revise", revise)]:
        graph.add_node(name, node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "collect")
    graph.add_edge("collect", "analyze")
    graph.add_conditional_edges("analyze", lambda s: "collect" if s["needs_search"] else "review")
    graph.add_conditional_edges("review", lambda s: END if s["status"] == "accepted" else "revise")
    graph.add_edge("revise", "review")
    return graph.compile(checkpointer=checkpointer)
