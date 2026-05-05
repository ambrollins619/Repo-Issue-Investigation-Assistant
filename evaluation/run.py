"""Explicit evaluation runner; expected answers are never sent to the graph/model."""
import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from backend.app.config import PROJECT_ROOT, Settings
from backend.app.llm import InvestigatorModel, ModelFailure
from backend.app.repository import Repository
from backend.app.workflow import build_graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call Gemini using your backend API key (consumes provider quota)")
    parser.add_argument("--case", choices=["pagination", "null", "filter", "vague", "unavailable"], help="Run one scenario")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation/results.json")
    args = parser.parse_args()
    settings = Settings(llm_mode="gemini" if args.live else "mock", repo_root=PROJECT_ROOT / "sample_repo")
    model = InvestigatorModel(settings)
    cases = json.loads((PROJECT_ROOT / "evaluation/issues.json").read_text())
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
    results = []
    try:
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(Path(directory) / "checkpoints.db", check_same_thread=False)) as connection:
                graph = build_graph(Repository(settings.repo_root), model, SqliteSaver(connection))
                for case in cases:
                    try:
                        state = graph.invoke({"issue": case["issue"], "snippets": [], "search_rounds": 0},
                                             {"configurable": {"thread_id": case["id"]}})
                        report = state["report"]
                        text = (report["likely_cause"] + " " + report["suggested_fix"]).lower()
                        checks = {"partial_matches": report["partial"] == case["partial"],
                                  "expected_file_cited": not case["expected_path"] or any(c["path"] == case["expected_path"] for c in report["citations"]),
                                  "expected_terms_present": all(t in text for t in case["expected_terms"]),
                                  "bounded_search": 1 <= state["search_rounds"] <= 3}
                        results.append({"id": case["id"], "checks": checks, "report": report, "search_rounds": state["search_rounds"]})
                    except Exception as exc:
                        failure = {"id": case["id"], "error": type(exc).__name__}
                        if isinstance(exc, ModelFailure):
                            failure["message"] = str(exc)  # Deliberately sanitized provider diagnostic.
                        results.append(failure)
    finally:
        model.close()
    result = {"mode": settings.llm_mode, "model": settings.gemini_model if args.live else None,
              "note": "Keyword/path checks are a coarse rubric, not proof of diagnosis correctness. Mock results validate demo plumbing only.", "results": results}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for case in results:
        passed = "error" not in case and all(case["checks"].values())
        print(f"{settings.llm_mode.upper()} {case['id']}: {'PASS' if passed else 'REVIEW'}")
    print(f"Reports saved to {args.output}")
    return 0 if all("error" not in case and all(case["checks"].values()) for case in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
