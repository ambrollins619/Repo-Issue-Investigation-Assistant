from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateInvestigation(StrictModel):
    issue: str = Field(min_length=10, max_length=6000)


class ReviewDecision(StrictModel):
    decision: Literal["accept", "revise"]
    feedback: str = Field(default="", max_length=3000)
    report_version: int = Field(ge=1)

    @model_validator(mode="after")
    def feedback_required(self):
        if self.decision == "revise" and not self.feedback:
            raise ValueError("Revision requires feedback")
        return self


class SearchPlan(StrictModel):
    terms: list[str] = Field(min_length=1, max_length=8)
    files: list[str] = Field(max_length=4)

    @model_validator(mode="after")
    def bounded_strings(self):
        if any(not t.strip() or len(t) > 80 for t in self.terms):
            raise ValueError("Search terms must contain 1–80 characters")
        if any(len(p) > 240 for p in self.files):
            raise ValueError("Filename too long")
        return self


class Citation(StrictModel):
    snippet_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    explanation: str = Field(min_length=1, max_length=1000)


class Report(StrictModel):
    likely_cause: str = Field(min_length=1, max_length=4000)
    citations: list[Citation] = Field(max_length=12)
    suggested_fix: str = Field(min_length=1, max_length=4000)
    suggested_tests: list[str] = Field(min_length=1, max_length=8)
    uncertainties: list[str] = Field(min_length=1, max_length=8)
    partial: bool


class Analysis(StrictModel):
    report: Report
    next_search: SearchPlan | None


def validate_citations(report: Report, evidence: list[dict]) -> Report:
    by_id = {snippet["id"]: snippet for snippet in evidence}
    if not report.partial and not report.citations:
        raise ValueError("A non-partial report needs supporting evidence")
    for citation in report.citations:
        snippet = by_id.get(citation.snippet_id)
        if not snippet or citation.path != snippet["path"] or not (
            snippet["start_line"] <= citation.start_line <= citation.end_line <= snippet["end_line"]
        ):
            raise ValueError("Report cites evidence that was not retrieved")
    return report

