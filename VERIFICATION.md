# Verification record

Validated locally on 6 October 2026 (Asia/Kolkata), Windows, Python 3.13.5,
Node 22.17.0, npm 10.9.2.

## Gemini integration

The single live provider is now Google Gemini, using `google-genai==2.28.0` and
`gemini-3.1-flash-lite`. The supplied key is stored only in the ignored backend
`.env`. No credentials are included in application records, frontend bundles,
example configuration, or this document. Rotate the key shared in chat.

Model discovery succeeded. Gemini 3.8 Flash generation returned HTTP 503 (high
demand); Gemini 2.5 Flash generation returned model-unavailable. Gemini 3.1
Flash-Lite successfully generated structured plans, reports, and a revision, so
it is the configured and documented default. There is no automatic model or
provider fallback, and no billing configuration was changed.

## Checks performed

- **27 passed, 1 skipped** via `python -m pytest -q`. The Windows account lacks
  symlink creation permission; the real junction escape check passed.
- Tests cover repository access/exclusions, evidence bounds, citation validation,
  three-round search limit, durable review and revision, consumed-command crash
  recovery, stale/duplicate reviews, and visible failures.
- The real Google SDK was exercised with fake HTTP responses for nested structured
  output, invalid JSON/schema, blocked/truncated generations, permission/model/
  quota errors, and credential redaction. Provider-bound snippets carry explicit
  source-line numbers without modifying their stored content.
- All five deterministic mock scenarios passed in the original baseline. Mock
  tests continue to pass after replacing the provider.
- `npm run build` passed with Gemini labels. `pip check` found no broken
  requirements. The OpenAI SDK was removed from the environment and pins.
- Browser test used real Gemini: submit pagination issue, receive a cited report,
  restart backend while paused, reload the same investigation, and request a
  substantive revision. Version 2 added last-partial-page, empty-page, and HTTP
  page-zero validation tests. It retained 1 search round and 3 evidence snippets.
  The revised report is left awaiting the user's review.
- Screenshot: `evaluation/browser-gemini-live.jpg`. The earlier
  `evaluation/browser-demo.jpg` is explicitly a mock demonstration.

## Live diagnosis evaluation

`python -m evaluation.run --live --output evaluation/results-gemini-live-final.json`
completed five scenarios. **4 of 5 passed the coarse rubric**:

| Scenario | Result |
| --- | --- |
| Pagination | Correct offset hypothesis and suggested fix; source references validated |
| Missing product | Correct missing-null-check ordering hypothesis and suggested fix |
| Filtering | Correct OR-versus-AND hypothesis and suggested fix |
| Missing payment code | Correctly returned a partial report identifying absent implementation |
| Vague catalog issue | Needs improvement: identifies real defects but claims a complete diagnosis without enough reproduction detail |

The vague-case failure persisted after strengthening uncertainty instructions.
It is not counted as a pass. The model also mentioned a possible KeyError in the
missing-product report, while indexing None specifically raises TypeError; the
root-cause diagnosis was correct but explanatory precision still needs review.
Explicit source-line numbering improved the observed citation accuracy.

The rubric uses paths, keywords, partial-report status, and search counts, not
semantic proof. Reports were also read manually; results from this small sample
are not a general accuracy estimate. Generated code and target-repository code
were never executed. Prompt-injection robustness, larger repositories, other
operating systems, adversarial filesystem mutation, and multiple backend workers
remain unverified.

Key pins: FastAPI 0.142.2, LangGraph 1.2.13, langgraph-checkpoint-sqlite 3.1.1,
Google Gen AI 2.28.0, Pydantic 2.13.5, React/React DOM 19.3.0, Vite 7.3.6.
