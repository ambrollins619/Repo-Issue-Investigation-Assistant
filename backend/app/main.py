from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .models import CreateInvestigation, ReviewDecision
from .repository import Repository
from .service import InvestigationService


def create_app(settings=None, model_factory=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        Repository(settings.repo_root)  # Fail clearly on invalid repository configuration.
        if settings.llm_mode == "gemini" and not settings.gemini_api_key:
            raise RuntimeError("Set GEMINI_API_KEY or select LLM_MODE=mock")
        kwargs = {"model_factory": model_factory} if model_factory else {}
        app.state.service = InvestigationService(settings, **kwargs)
        app.state.service.recover()
        yield
        app.state.service.close()

    app = FastAPI(title="Issue Investigation Assistant", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def service():
        return app.state.service

    def lookup(identifier):
        row = service().store.get(identifier)
        if row is None:
            raise HTTPException(404, "Investigation not found")
        row.pop("pending_review", None)
        row.pop("repo_root", None)
        return row

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": settings.llm_mode, "model": settings.gemini_model if settings.llm_mode == "gemini" else None,
                "repository": settings.repo_root.name}

    @app.post("/api/investigations", status_code=202)
    def create(request: CreateInvestigation):
        row = service().store.create(request.issue, settings)
        service().submit(row["id"])
        return lookup(row["id"])

    @app.get("/api/investigations")
    def history(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        return service().store.history(limit, offset)

    @app.get("/api/investigations/{identifier}")
    def get(identifier: str):
        return lookup(identifier)

    @app.post("/api/investigations/{identifier}/review", status_code=202)
    def review(identifier: str, request: ReviewDecision):
        lookup(identifier)
        if not service().store.claim_review(identifier, request):
            raise HTTPException(409, "This report is not awaiting review or its version changed. Refresh and try again.")
        service().submit(identifier)
        return lookup(identifier)

    return app


app = create_app()
