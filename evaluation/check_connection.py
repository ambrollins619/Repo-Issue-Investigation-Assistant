"""Check Gemini access without printing credentials or sending repository content."""
import argparse
import json

from google.genai import errors

from backend.app.config import Settings
from backend.app.llm import InvestigatorModel, ModelFailure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true", help="Also send a tiny planning prompt (consumes quota)")
    args = parser.parse_args()
    settings = Settings(llm_mode="gemini")
    model = InvestigatorModel(settings)
    try:
        available = [item.name.removeprefix("models/") for item in model.client.models.list()
                     if item.name and "gemini" in item.name.lower()]
        print(json.dumps({"configured_model": settings.gemini_model,
                          "configured_model_listed": settings.gemini_model in available,
                          "available_gemini_models": available}, indent=2))
        if args.generate:
            try:
                plan = model.plan("Page 1 skips the first two products", ["catalog.py", "main.py"])
                print(plan.model_dump_json())
            except ModelFailure as exc:
                cause = exc.__cause__
                message = str(getattr(cause, "message", str(exc))).replace(settings.gemini_api_key.get_secret_value(), "[REDACTED]")
                print(json.dumps({"error": str(exc), "diagnostic": message[:1000]}))
                return 1
        return 0
    except errors.APIError as exc:
        # Error bodies may contain submitted values; redact the key before displaying diagnostics.
        message = str(exc.message or "").replace(settings.gemini_api_key.get_secret_value(), "[REDACTED]")
        print(json.dumps({"http_status": exc.code, "message": message[:1000]}))
        return 1
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}))
        return 1
    finally:
        model.close()


if __name__ == "__main__":
    raise SystemExit(main())
