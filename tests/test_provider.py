import json

import httpx
import pytest
from google import genai
from google.genai import types

from backend.app.config import Settings
from backend.app.llm import InvestigatorModel, ModelFailure
from backend.app.models import Analysis


def response_body(content, finish="STOP"):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": content}]}, "finishReason": finish}]}


def fake_model(handler):
    model = InvestigatorModel(Settings(llm_mode="gemini", gemini_api_key="fake-test-key"))
    model.client.close()
    model.client = genai.Client(api_key="fake-test-key", http_options=types.HttpOptions(
        httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_options=types.HttpRetryOptions(attempts=1),
    ))
    return model


def test_real_sdk_structured_parse_with_fake_transport():
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response_body('{"terms":["products"],"files":["main.py"]}'))
    model = fake_model(handle)
    try:
        assert model.plan("Products fail", ["main.py"]).terms == ["products"]
        assert requests[0]["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseJsonSchema" in requests[0]["generationConfig"]
        assert "untrusted DATA" in requests[0]["systemInstruction"]["parts"][0]["text"]
        assert not requests[0].get("tools")
    finally:
        model.close()


def test_nested_analysis_schema_supported():
    body = {"report": {"likely_cause": "Unknown", "citations": [], "suggested_fix": "Provide reproduction",
                       "suggested_tests": ["Reproduce"], "uncertainties": ["Insufficient data"], "partial": True}, "next_search": None}
    model = fake_model(lambda request: httpx.Response(200, json=response_body(json.dumps(body))))
    try:
        result = model._parse(Analysis, "Analyze", {"issue": "Unknown failure"})
        assert result.report.partial and result.next_search is None
    finally:
        model.close()


def test_analysis_numbers_original_lines_without_mutating_evidence():
    sent = []
    body = {"report": {"likely_cause": "Unknown", "citations": [], "suggested_fix": "Reproduce",
                       "suggested_tests": ["Reproduce"], "uncertainties": ["Not executed"], "partial": True}, "next_search": None}
    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=response_body(json.dumps(body)))
    model = fake_model(handle)
    state = {"issue": "A failure", "snippets": [{"id": "E1", "path": "main.py", "start_line": 20,
                                               "end_line": 21, "content": "first\nsecond"}]}
    try:
        model.analyze(state)
        payload = json.loads(sent[0]["contents"][0]["parts"][0]["text"])
        assert payload["snippets"][0]["content"] == "20: first\n21: second"
        assert state["snippets"][0]["content"] == "first\nsecond"
    finally:
        model.close()


@pytest.mark.parametrize("content", ['{"terms":[],"files":[]}', 'not json'])
def test_invalid_structured_output_is_visible(content):
    model = fake_model(lambda request: httpx.Response(200, json=response_body(content)))
    try:
        with pytest.raises(ModelFailure, match="schema validation"):
            model.plan("Products fail", ["main.py"])
    finally:
        model.close()


@pytest.mark.parametrize("finish", ["SAFETY", "MAX_TOKENS"])
def test_blocked_or_truncated_output_is_visible(finish):
    model = fake_model(lambda request: httpx.Response(200, json=response_body('{}', finish)))
    try:
        with pytest.raises(ModelFailure, match="refusal or incomplete"):
            model.plan("Products fail", ["main.py"])
    finally:
        model.close()


@pytest.mark.parametrize("status, message", [(400, "rejected"), (403, "access denied"), (404, "unavailable"), (429, "quota")])
def test_provider_errors_redact_response_details(status, message):
    model = fake_model(lambda request: httpx.Response(status, json={"error": {
        "code": status, "message": "sensitive-provider-payload", "status": "FAILED_PRECONDITION"}}))
    try:
        with pytest.raises(ModelFailure, match=message) as caught:
            model.plan("Products fail", ["main.py"])
        assert "sensitive-provider-payload" not in str(caught.value)
        assert "fake-test-key" not in str(caught.value)
    finally:
        model.close()


def test_missing_key_and_legacy_mode_fail_explicitly():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        InvestigatorModel(Settings(llm_mode="gemini", gemini_api_key=""))
    legacy = Settings(llm_mode="mock").model_copy(update={"llm_mode": "openai"})
    with pytest.raises(ModelFailure, match="previous provider"):
        InvestigatorModel(legacy)
