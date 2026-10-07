import json

import httpx
import pytest
from pydantic import ValidationError

from orbitguard.backend.mock.data import DEMO_FLOOD_EVENT
from orbitguard.backend.schemas.analyst import IncidentEvidence
from orbitguard.backend.schemas.events import Analysis, EnvironmentalEvent, Impact, Risk
from orbitguard.backend.services.analyst import (
    AnalystService,
    DeterministicAnalyst,
    OpenAIAnalystProvider,
    build_incident_evidence,
)


def _evidence() -> IncidentEvidence:
    event = EnvironmentalEvent(**DEMO_FLOOD_EVENT)
    impact = Impact(
        population_exposed=12_400,
        population_density_estimate=331,
        data_source="demo population data",
        infrastructure_data_source="demo infrastructure data",
        data_quality="demo",
        roads_affected_km=18.3,
        hospitals_nearby=2,
        buildings_affected=1_840,
        schools_nearby=7,
    )
    risk = Risk(score=79, level="HIGH")
    return build_incident_evidence(event, impact, risk)


def _valid_analysis() -> dict:
    return {
        "summary": "The supplied flood evidence requires operational review.",
        "severity": "HIGH",
        "priority_areas": ["Validate the hazard footprint"],
        "recommended_actions": ["Coordinate field verification"],
        "uncertainty": ["The source evidence may include demo estimates."],
    }


def test_incident_evidence_preserves_authoritative_numeric_facts():
    evidence = _evidence()

    assert evidence.affected_area_km2 == 37.4
    assert evidence.model_confidence == 0.91
    assert evidence.population_exposed == 12_400
    assert evidence.risk_score == 79
    assert evidence.risk_level == "HIGH"


def test_deterministic_fallback_is_stable_and_numeric_claim_free():
    evidence = _evidence()
    first = DeterministicAnalyst().analyze(evidence).model_dump()
    second = DeterministicAnalyst().analyze(evidence).model_dump()

    assert first == second
    assert first["analysis_source"] == "deterministic_fallback"
    prose = [
        first["summary"],
        *first["priority_areas"],
        *first["recommended_actions"],
        *first["uncertainty"],
    ]
    assert not any(character.isdigit() for text in prose for character in text)


def test_service_uses_fallback_without_provider():
    result = AnalystService().analyze(_evidence())

    assert result.used_fallback is True
    assert result.provider == "deterministic_fallback"
    assert result.analysis.severity == "HIGH"


def test_service_accepts_valid_provider_output_and_overrides_source():
    class GoodProvider:
        def analyze(self, evidence):
            return Analysis.model_validate(_valid_analysis())

    result = AnalystService(provider=GoodProvider()).analyze(_evidence())

    assert result.used_fallback is False
    assert result.provider == "llm"
    assert result.analysis.analysis_source == "llm"


def test_service_rejects_numeric_or_mismatched_provider_output():
    class UnsafeProvider:
        def analyze(self, evidence):
            return {
                **_valid_analysis(),
                "summary": "This affects 12400 people.",
            }

    class MismatchedProvider:
        def analyze(self, evidence):
            return {**_valid_analysis(), "severity": "CRITICAL"}

    unsafe = AnalystService(provider=UnsafeProvider()).analyze(_evidence())
    mismatched = AnalystService(provider=MismatchedProvider()).analyze(_evidence())

    assert unsafe.used_fallback is True
    assert mismatched.used_fallback is True


def test_openai_provider_sends_structured_evidence_and_schema():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(_valid_analysis())}}]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIAnalystProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/chat/completions",
            client=client,
        )
        result = provider.analyze(_evidence())

    assert result.severity == "HIGH"
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert requests[0]["response_format"]["json_schema"]["strict"] is True
    assert requests[0]["model"] == "test-model"
    assert "incident_evidence" in json.loads(
        requests[0]["messages"][1]["content"]
    )


def test_openai_provider_invalid_output_falls_back_through_service():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {**_valid_analysis(), "severity": "CRITICAL"}
                            )
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIAnalystProvider(api_key="test-key", client=client)
        result = AnalystService(provider=provider).analyze(_evidence())

    assert result.used_fallback is True
    assert result.analysis.analysis_source == "deterministic_fallback"


def test_provider_requires_api_key_and_analysis_rejects_numeric_prose():
    with pytest.raises(ValueError):
        OpenAIAnalystProvider(api_key="")

    with pytest.raises(ValidationError):
        Analysis.model_validate({**_valid_analysis(), "summary": "Area is 37 km2."})
