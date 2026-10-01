"""Local REST API over the analysis engine (optional; requires ``fastapi`` and ``uvicorn``).

Security: binds to 127.0.0.1 by default and requires a bearer token that is generated at
start-up (or taken from ``WSA_API_TOKEN``).  Paths given to ``/analyze`` are read with the
same safety limits as the GUI.
"""

from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path
from typing import Any

from app.core.config import ConfigManager
from app.core.logging_setup import setup_logging
from app.core.secrets import SecretStore
from app.database.state import StateStore
from app.database.store import GroupFilter
from app.services.pipeline import AnalysisPipeline
from app.services.session import AnalysisSession


def create_app(token: str, config_manager: ConfigManager | None = None, workspace: Path | None = None):
    from fastapi import Depends, FastAPI, Header, HTTPException, Query
    from pydantic import BaseModel, Field

    cm = config_manager or ConfigManager()
    state = StateStore(cm.config.storage.state_database_url or None)
    sessions: dict[str, AnalysisSession] = {}
    lock = threading.Lock()

    app = FastAPI(title="Wazuh Security Analyzer API", version="1.0.0")

    def auth(authorization: str = Header(default="")) -> None:
        expected = f"Bearer {token}"
        if not secrets.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    class AnalyzeRequest(BaseModel):
        paths: list[str] = Field(min_length=1, max_length=1000)
        online: bool = False

    def get_session(session_id: str) -> AnalysisSession:
        with lock:
            session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="unknown session")
        return session

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/analyze", dependencies=[Depends(auth)])
    def analyze(req: AnalyzeRequest) -> dict[str, Any]:
        for p in req.paths:
            if not Path(p).exists():
                raise HTTPException(status_code=400, detail=f"path not found: {p}")
        pipeline = AnalysisPipeline(cm.config, SecretStore(), state, online=req.online, workspace=workspace)
        session = pipeline.run(req.paths)
        sid = session.path.stem
        with lock:
            sessions[sid] = session
        return {"session_id": sid, "summary": session.summary.to_dict()}

    @app.get("/sessions/{session_id}/summary", dependencies=[Depends(auth)])
    def summary(session_id: str) -> dict[str, Any]:
        return get_session(session_id).summary.to_dict()

    @app.get("/sessions/{session_id}/incidents", dependencies=[Depends(auth)])
    def incidents(session_id: str) -> list[dict[str, Any]]:
        return [i.to_dict() for i in get_session(session_id).incidents()]

    @app.get("/sessions/{session_id}/findings", dependencies=[Depends(auth)])
    def findings(session_id: str, severity: str = "", offset: int = Query(0, ge=0),
                 limit: int = Query(100, ge=1, le=1000)) -> list[dict[str, Any]]:
        f = GroupFilter(severities=[severity] if severity else [])
        return get_session(session_id).store.group_rows(f, offset, limit)

    @app.get("/sessions/{session_id}/search", dependencies=[Depends(auth)])
    def search(session_id: str, q: str = Query(min_length=1, max_length=512)) -> dict[str, Any]:
        res = get_session(session_id).search(q)
        return {"term": res.term, "kind": res.kind, "alerts": res.alerts, "hosts": res.hosts, "users": res.users,
                "rules": res.rules, "incidents": res.incidents}

    return app


def serve(host: str = "127.0.0.1", port: int = 8765) -> int:
    try:
        import uvicorn
    except ImportError:
        print("The REST API requires: pip install fastapi uvicorn")
        return 1
    cm = ConfigManager()
    setup_logging(cm.config.logging.level, console=True)
    token = os.environ.get("WSA_API_TOKEN") or secrets.token_urlsafe(24)
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: the API is exposed beyond localhost.")
    print(f"API token (send as 'Authorization: Bearer <token>'): {token}")
    uvicorn.run(create_app(token, cm), host=host, port=port, log_level="info")
    return 0
