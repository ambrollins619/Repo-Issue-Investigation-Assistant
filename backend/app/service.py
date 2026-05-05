import sqlite3
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import ValidationError

from .llm import InvestigatorModel, ModelFailure
from .repository import Repository
from .storage import Store
from .workflow import build_graph


class InvestigationService:
    def __init__(self, settings, model_factory=InvestigatorModel):
        self.settings = settings
        self.model_factory = model_factory
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(settings.data_dir / "investigations.db")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="investigation")

    def recover(self):
        for identifier in self.store.unfinished():
            self.submit(identifier)

    def submit(self, identifier):
        self.pool.submit(self.run, identifier)

    def close(self):
        self.pool.shutdown(wait=True)

    def run(self, identifier):
        row = self.store.get(identifier)
        if row is None:
            return
        state = row["state"]
        model = None
        try:
            settings = self.settings.model_copy(update={"llm_mode": row["mode"], "gemini_model": row["model"]})
            model = self.model_factory(settings)
            repository = Repository(Path(row["repo_root"]))
            with closing(sqlite3.connect(self.settings.data_dir / "checkpoints.db", check_same_thread=False)) as connection:
                saver = SqliteSaver(connection)
                graph = build_graph(repository, model, saver)
                config = {"configurable": {"thread_id": identifier}, "recursion_limit": 30}
                snapshot = graph.get_state(config)
                payload = None
                if not snapshot.values:
                    payload = {**state, "status": "planning"}
                else:
                    state = snapshot.values
                    pending = row["pending_review"]
                    # A persisted action may already have been consumed before a crash.
                    # Resume only the matching interrupt/version; otherwise continue from checkpoint.
                    if snapshot.interrupts:
                        if pending and pending["report_version"] == state["report_version"]:
                            payload = Command(resume=pending)
                        else:
                            self.store.publish(identifier, state, "awaiting_review", finished=True)
                            return
                    elif not snapshot.next:
                        self.store.publish(identifier, state, state["status"], finished=True)
                        return
                self.store.publish(identifier, state, "running")
                for update in graph.stream(payload, config, stream_mode="values"):
                    # Stream metadata contains Interrupt objects; only graph state belongs in JSON records.
                    state = {key: value for key, value in update.items() if key != "__interrupt__"}
                    status = state.get("status", "running")
                    if status in {"awaiting_review", "accepted"}:
                        status = "preparing_review" if status == "awaiting_review" else "finishing"
                    self.store.publish(identifier, state, status)
                snapshot = graph.get_state(config)
                state = snapshot.values
                status = "awaiting_review" if snapshot.interrupts else state["status"]
                self.store.publish(identifier, state, status, finished=True)
        except ModelFailure as exc:
            self.store.publish(identifier, state, "failed", str(exc), finished=True)
        except (ValueError, ValidationError):
            self.store.publish(identifier, state, "failed", "Invalid workflow output or evidence references. Start a new investigation after checking the model and repository configuration.", finished=True)
        except Exception as exc:
            self.store.publish(identifier, state, "failed", f"Investigation failed ({type(exc).__name__}). Check backend configuration and restart with a new investigation.", finished=True)
        finally:
            if model:
                model.close()
