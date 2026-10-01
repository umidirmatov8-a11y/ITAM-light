import json

import httpx
import pytest
from pydantic import ValidationError

from app.ai.engine import AIAnalysisEngine, extract_json
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import AIProvider
from app.ai.providers.factory import create_provider
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.providers.openai_provider import GenericOpenAICompatibleProvider, OpenAIProvider
from app.ai.schemas import AIAnalysisResult
from app.core.config import AppConfig
from app.core.errors import ProviderResponseError, ProviderUnavailableError
from app.core.secrets import MemorySecretStore
from tests.unit.helpers import group, mitre

VALID = {
    "severity": "high", "confidence": 0.9, "summary": "Brute force from 203.0.113.5",
    "what_happened": "x", "why_it_matters": "y", "possible_attack": "z",
    "false_positive_probability": 0.1, "mitre": [{"technique_id": "T1110", "confidence": "medium", "evidence": "e"}],
    "iocs": ["203.0.113.5"], "cves": [], "immediate_actions": ["Block 203.0.113.5"],
    "investigation_steps": [], "remediation": [], "prevention": [],
}


def test_schema_accepts_valid_and_normalises():
    r = AIAnalysisResult.model_validate(dict(VALID, severity="High", confidence="90%",
                                             false_positive_probability=8, mitre=["T1078 Valid Accounts"]))
    assert r.severity == "high" and r.confidence == 0.9 and r.false_positive_probability == 0.08
    assert r.mitre[0].technique_id == "T1078"


@pytest.mark.parametrize("bad", [
    {"severity": "catastrophic"},
    {"confidence": 1.7},
    {"mitre": [{"technique_id": "X1234"}]},
    {"summary": None},
])
def test_schema_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        AIAnalysisResult.model_validate(dict(VALID, **bad))


def test_extract_json_variants():
    assert extract_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert extract_json("Sure! Here it is: {\"a\": {\"b\": \"}\"}} hope that helps") == {"a": {"b": "}"}}
    with pytest.raises(ValueError):
        extract_json("no json here")


class FakeProvider(AIProvider):
    name = "Fake"

    def __init__(self, answers, external=True):
        super().__init__(AppConfig().ai, AppConfig().network)
        self.answers = list(answers)
        self.prompts: list[str] = []
        self.is_external = external

    @property
    def model(self):
        return "fake-1"

    def complete(self, system, user):
        self.prompts.append(user)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def finding():
    g = group(id=7, count=147, peak_count=147, users=["j.doe", "admin"], user="j.doe", agent_name="web-01",
              agent_ip="10.20.1.10", src_ip="203.0.113.5", mitre=[mitre()], risk_score=70, severity="high",
              title="Repeated failed logins", evidence=["147 events"], sample_logs=["Invalid user j.doe from 203.0.113.5"])
    g.representative = {"agent": "web-01", "agent_ip": "10.20.1.10", "user": "j.doe", "source_ip": "203.0.113.5",
                        "full_log": "Invalid user j.doe from 203.0.113.5 on web-01 email j.doe@corp.example"}
    return g


def test_external_provider_receives_sanitized_context():
    provider = FakeProvider([json.dumps(VALID)])
    engine = AIAnalysisEngine(AppConfig(), MemorySecretStore(), provider=provider)
    result = engine.analyze([finding()])
    assert result.ok and result.anonymized and result.replacements > 0
    prompt = provider.prompts[0]
    for leaked in ("j.doe", "10.20.1.10", "web-01", "corp.example"):
        assert leaked not in prompt
    assert "203.0.113.5" in prompt  # the IOC under analysis stays visible


def test_local_provider_not_sanitized_by_default_but_configurable():
    provider = FakeProvider([json.dumps(VALID)], external=False)
    AIAnalysisEngine(AppConfig(), MemorySecretStore(), provider=provider).analyze([finding()])
    assert "j.doe" in provider.prompts[0]
    cfg = AppConfig.model_validate({"ai": {"anonymize_local": True}})
    provider2 = FakeProvider([json.dumps(VALID)], external=False)
    AIAnalysisEngine(cfg, MemorySecretStore(), provider=provider2).analyze([finding()])
    assert "j.doe" not in provider2.prompts[0]


def test_guardrails_remove_hallucinations_and_restore_placeholders():
    answer = dict(VALID, iocs=["203.0.113.5", "8.8.8.8", "evil.example.org"], cves=["CVE-2099-0001"],
                  mitre=[{"technique_id": "T1110", "confidence": "high", "evidence": "e"},
                         {"technique_id": "T9999", "confidence": "high", "evidence": "made up"},
                         {"technique_id": "T1059.001", "confidence": "high", "evidence": ""},
                         {"technique_id": "T1021.004", "confidence": "high", "evidence": "ssh"}],
                  summary="Account [USER_001] attacked")
    provider = FakeProvider([json.dumps(answer)])
    result = AIAnalysisEngine(AppConfig(), MemorySecretStore(), provider=provider).analyze([finding()])
    data = result.result
    assert data["iocs"] == ["203.0.113.5"]
    assert data["cves"] == []
    ids = {m["technique_id"]: m for m in data["mitre"]}
    assert "T9999" not in ids and "T1059.001" not in ids
    assert ids["T1021.004"]["confidence"] == "low"  # AI-only mapping is capped at low
    assert "j.doe" in data["summary"] or "admin" in data["summary"]
    assert len(result.removed) == 5


def test_invalid_answer_is_repaired_once():
    provider = FakeProvider(["not json at all", json.dumps(VALID)])
    result = AIAnalysisEngine(AppConfig(), MemorySecretStore(), provider=provider).analyze([finding()])
    assert result.ok and len(provider.prompts) == 2 and "not valid" in provider.prompts[1]


def test_invalid_answer_twice_is_discarded():
    provider = FakeProvider(["{}", "{\"severity\": \"nope\"}"])
    result = AIAnalysisEngine(AppConfig(), MemorySecretStore(), provider=provider).analyze([finding()])
    assert not result.ok and "discarded" in result.error


def test_ai_unavailable_is_graceful():
    provider = FakeProvider([ProviderUnavailableError("Fake: cannot connect")])
    result = AIAnalysisEngine(AppConfig(), MemorySecretStore(), provider=provider).analyze([finding()])
    assert not result.ok and "Local analysis results are shown" in result.error


def test_ai_disabled():
    engine = AIAnalysisEngine(AppConfig(), MemorySecretStore())
    assert not engine.available
    result = engine.analyze([finding()])
    assert not result.ok and "disabled" in result.error


# ----------------------------------------------------------------- providers over mocked HTTP
def transport(handler):
    return httpx.MockTransport(handler)


def test_openai_provider_request_and_parse():
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"ok\": 1}"}}]})

    cfg = AppConfig()
    p = OpenAIProvider(cfg.ai, cfg.network, "sk-test", transport(handler))
    assert p.complete("sys", "user") == "{\"ok\": 1}"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_anthropic_provider_request_and_parse():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        body = json.loads(request.content)
        assert body["system"] == "sys" and body["messages"][0]["role"] == "user"
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{\"a\": 1}"}]})

    cfg = AppConfig()
    p = AnthropicProvider(cfg.ai, cfg.network, "key", transport(handler))
    assert p.complete("sys", "u") == "{\"a\": 1}"
    assert seen["x-api-key"] == "key" and seen["anthropic-version"] == "2023-06-01"


def test_ollama_provider_and_models():
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3"}]})
        body = json.loads(request.content)
        assert body["format"] == "json" and body["stream"] is False
        return httpx.Response(200, json={"message": {"content": "{}"}})

    cfg = AppConfig()
    p = OllamaProvider(cfg.ai, cfg.network, None, transport(handler))
    assert not p.is_external
    assert p.complete("s", "u") == "{}"
    assert p.list_models() == ["llama3", "qwen2.5:7b"]
    assert p.test_connection().startswith("connected")


def test_remote_ollama_counts_as_external():
    cfg = AppConfig.model_validate({"ai": {"ollama_url": "https://llm.example.com"}})
    assert OllamaProvider(cfg.ai, cfg.network).is_external


def test_compatible_provider_locality():
    cfg = AppConfig()
    assert not GenericOpenAICompatibleProvider(cfg.ai, cfg.network).is_external
    remote = AppConfig.model_validate({"ai": {"compatible_base_url": "https://api.example.com/v1"}})
    assert GenericOpenAICompatibleProvider(remote.ai, remote.network).is_external


def test_provider_errors():
    cfg = AppConfig()
    p401 = OpenAIProvider(cfg.ai, cfg.network, "k", transport(lambda r: httpx.Response(401)))
    with pytest.raises(ProviderResponseError):
        p401.complete("s", "u")

    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderUnavailableError):
        OpenAIProvider(cfg.ai, cfg.network, "k", transport(timeout)).complete("s", "u")
    with pytest.raises(ProviderUnavailableError):
        OpenAIProvider(cfg.ai, cfg.network, None).complete("s", "u")  # no key configured


def test_factory():
    secrets = MemorySecretStore({"anthropic_api_key": "x"})
    assert create_provider(AppConfig(), secrets) is None
    cfg = AppConfig.model_validate({"ai": {"provider": "anthropic"}})
    p = create_provider(cfg, secrets)
    assert isinstance(p, AnthropicProvider) and p.api_key == "x"
