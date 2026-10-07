import json
import threading

import pytest

from app.config import Settings, load_settings, save_settings
from app.pipeline import (STAGE_DONE, STAGE_EXECUTE, STAGE_PROMPT, STAGE_VERIFY, AgentPipeline, Cancelled,
                          parse_verdict)
from app.providers import ProviderError
from app.report import render_report


class ScriptedProvider:
    """Answers by agent role; verdicts are consumed in order."""

    name = "fake"

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.calls = []

    def complete(self, system, user, schema=None):
        self.calls.append((system, user, schema))
        if "Промпт-инженер" in system:
            return f"PROMPT#{sum('Промпт-инженер' in c[0] for c in self.calls)}"
        if "Исполнитель" in system:
            return f"RESULT for {user}"
        return json.dumps(self.verdicts.pop(0), ensure_ascii=False)


def verdict(approved, score=5, feedback="fix it"):
    return {"approved": approved, "score": score, "issues": [] if approved else ["bug"], "feedback": feedback}


def test_approved_on_first_round():
    provider = ScriptedProvider([verdict(True, 9)])
    events = []
    run = AgentPipeline(provider, 3).run("напиши хокку", events.append)
    assert run.approved and len(run.attempts) == 1
    assert run.best.result == "RESULT for PROMPT#1"
    assert [e.stage for e in events if not e.started] == [STAGE_PROMPT, STAGE_EXECUTE, STAGE_VERIFY, STAGE_DONE]
    assert provider.calls[2][2] is not None  # verifier asks for structured JSON


def test_rejection_loops_back_to_prompt_engineer_with_feedback():
    provider = ScriptedProvider([verdict(False, 4, "добавь заголовок"), verdict(True, 8)])
    run = AgentPipeline(provider, 3).run("задача")
    assert run.approved and len(run.attempts) == 2
    second_engineer_input = provider.calls[3][1]
    assert "PROMPT#1" in second_engineer_input and "добавь заголовок" in second_engineer_input
    assert run.best.prompt == "PROMPT#2"


def test_returns_best_attempt_when_never_approved():
    provider = ScriptedProvider([verdict(False, 3), verdict(False, 7), verdict(False, 5)])
    run = AgentPipeline(provider, 3).run("задача")
    assert not run.approved and len(run.attempts) == 3
    assert run.best.iteration == 2
    assert "НЕ принят" in render_report(run)


def test_cancel_stops_the_run():
    cancel = threading.Event()
    provider = ScriptedProvider([verdict(False)] * 3)

    def on_event(event):
        if event.stage == STAGE_EXECUTE and event.started:
            cancel.set()

    with pytest.raises(Cancelled):
        AgentPipeline(provider, 3).run("задача", on_event, cancel)
    assert len(provider.calls) == 2


def test_empty_task_rejected():
    with pytest.raises(ValueError):
        AgentPipeline(ScriptedProvider([]), 1).run("   ")


@pytest.mark.parametrize("raw", [
    '{"approved": true, "score": 9, "issues": [], "feedback": ""}',
    'Вот ответ:\n```json\n{"approved": "true", "score": "9", "issues": [], "feedback": ""}\n```',
])
def test_parse_verdict_tolerant(raw):
    v = parse_verdict(raw)
    assert v.approved and v.score == 9


def test_parse_verdict_clamps_and_rejects_garbage():
    assert parse_verdict('{"approved": false, "score": 42, "issues": "x"}').score == 10
    with pytest.raises(ProviderError):
        parse_verdict("не JSON")


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    save_settings(Settings(provider="ollama", max_iterations=5), path)
    loaded = load_settings(path)
    assert loaded.provider == "ollama" and loaded.max_iterations == 5
    path.write_text("{broken", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_anthropic_provider_request_shape(monkeypatch):
    from types import SimpleNamespace

    from app.providers import AnthropicProvider

    provider = AnthropicProvider(Settings(anthropic_api_key="sk-test", effort="high"))
    sent = {}

    def fake_create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=" ok ")])

    monkeypatch.setattr(provider._client.beta.messages, "create", fake_create)
    assert provider.complete("sys", "user", schema={"type": "object"}) == "ok"
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"] == {"effort": "high", "format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert sent["fallbacks"] == "default"

    def refused(**_kwargs):
        return SimpleNamespace(stop_reason="refusal", content=[])

    monkeypatch.setattr(provider._client.beta.messages, "create", refused)
    with pytest.raises(ProviderError):
        provider.complete("sys", "user")
