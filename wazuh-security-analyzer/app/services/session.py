"""Access to a completed analysis (thin facade over :class:`AnalysisStore`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.store import AnalysisStore, GroupFilter, SearchResult
from app.models.analysis import AlertGroup, AnalysisSummary, Incident, IncidentStatus


class AnalysisSession:
    def __init__(self, store: AnalysisStore, summary: AnalysisSummary | None = None):
        self.store = store
        self.summary = summary or store.summary()
        self._incidents: list[Incident] | None = None

    @classmethod
    def open(cls, path: Path | str) -> "AnalysisSession":
        return cls(AnalysisStore(path, create=False))

    @property
    def path(self) -> Path:
        return self.store.path

    def close(self) -> None:
        self.store.close()

    # convenience accessors
    def incidents(self) -> list[Incident]:
        if self._incidents is None:
            self._incidents = self.store.incidents()
        return self._incidents

    def incident(self, incident_id: str) -> Incident | None:
        return next((i for i in self.incidents() if i.id == incident_id), None)

    def groups(self, f: GroupFilter | None = None, offset: int = 0, limit: int = 500) -> list[AlertGroup]:
        return self.store.query_groups(f, offset, limit)

    def group(self, group_id: int) -> AlertGroup | None:
        return self.store.get_group(group_id)

    def dashboard(self) -> dict[str, Any]:
        return self.store.get_meta("dashboard", {}) or {}

    def mitre_stats(self) -> list[dict[str, Any]]:
        return self.store.get_meta("mitre", []) or []

    def search(self, term: str) -> SearchResult:
        return self.store.search(term)

    def set_incident_status(self, incident_id: str, status: str, state=None, note: str = "") -> Incident | None:
        incident = self.incident(incident_id)
        if incident is None:
            return None
        incident.status = IncidentStatus.parse(status).value
        if note:
            incident.note = note
        self.store.update_incident(incident)
        if state is not None:
            state.set_status(incident.fingerprint, incident.status, note)
        return incident

    def save_incident_ai(self, incident: Incident) -> None:
        self.store.update_incident(incident)
