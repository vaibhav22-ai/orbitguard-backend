"""Structured AI analyst with a deterministic, no-network fallback."""

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from orbitguard.backend.schemas.analyst import IncidentEvidence
from orbitguard.backend.schemas.events import Analysis, EnvironmentalEvent, Impact, Risk


class AnalystProviderError(RuntimeError):
    """Raised when an analyst provider cannot return trusted structured output."""


@runtime_checkable
class AnalystProvider(Protocol):
    def analyze(self, evidence: IncidentEvidence) -> Analysis:
        """Return analysis based only on the supplied evidence."""


@dataclass(frozen=True)
class AnalystResult:
    analysis: Analysis
    used_fallback: bool
    provider: str


def build_incident_evidence(
    event: EnvironmentalEvent, impact: Impact, risk: Risk
) -> IncidentEvidence:
    sources = [event.source, impact.data_source]
    if impact.infrastructure_data_source:
        sources.append(impact.infrastructure_data_source)
    return IncidentEvidence(
        event_type=event.event_type,
        affected_area_km2=event.affected_area_km2,
        model_confidence=event.confidence,
        population_exposed=impact.population_exposed,
        population_density_estimate=impact.population_density_estimate,
        roads_affected_km=impact.roads_affected_km,
        hospitals_nearby=impact.hospitals_nearby,
        buildings_affected=impact.buildings_affected,
        schools_nearby=impact.schools_nearby,
        risk_score=risk.score,
        risk_level=risk.level,
        data_quality=impact.data_quality,
        sources=sources,
    )


class DeterministicAnalyst:
    """Stable fallback that never invents numbers or external facts."""

    def analyze(self, evidence: IncidentEvidence) -> Analysis:
        label = "flood" if evidence.event_type == "flood" else "deforestation"
        if evidence.event_type == "flood":
            priority_areas = [
                "Validate the detected hazard footprint",
                "Review exposed roads, hospitals, buildings, and schools",
            ]
        else:
            priority_areas = [
                "Validate the detected forest-loss footprint",
                "Review nearby communities and infrastructure for disruption",
            ]

        uncertainty = [
            "This summary uses only the supplied structured evidence and creates no new measurements.",
            "The ORBITGUARD MVP Risk Score is a heuristic and is not scientifically validated.",
        ]
        if "demo" in evidence.data_quality.lower():
            uncertainty.insert(
                1, "Population and infrastructure values are demo estimates."
            )

        return Analysis(
            summary=(
                f"The supplied {label} evidence is assessed as {evidence.risk_level}. "
                "This is an operational summary, not a new measurement."
            ),
            severity=evidence.risk_level,
            priority_areas=priority_areas,
            recommended_actions=[
                "Confirm the detector footprint with an independent review",
                "Prioritize field verification around exposed people and infrastructure",
                "Use current authoritative data before operational decisions",
            ],
            uncertainty=uncertainty,
            analysis_source="deterministic_fallback",
        )


class OpenAIAnalystProvider:
    """OpenAI-compatible structured-output provider using an injected HTTP client."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1/chat/completions",
        timeout_seconds: float = 30,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key is required for the OpenAI analyst provider.")
        if not model:
            raise ValueError("model is required for the OpenAI analyst provider.")
        if not base_url:
            raise ValueError("base_url is required for the OpenAI analyst provider.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.client = client

    def analyze(self, evidence: IncidentEvidence) -> Analysis:
        request = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the ORBITGUARD AI Analyst. Treat the supplied "
                        "incident_evidence as authoritative. Return only JSON "
                        "matching the requested schema. Do not calculate, change, "
                        "or invent population, infrastructure, area, confidence, "
                        "risk, location, date, percentage, or count values. "
                        "Do not repeat numerical values in prose. Do not include "
                        "digits in any output text. Set severity exactly to the "
                        "supplied risk_level. State uncertainty explicitly."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"incident_evidence": evidence.model_dump(mode="json")},
                        sort_keys=True,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "orbitguard_incident_analysis",
                    "strict": True,
                    "schema": Analysis.model_json_schema(),
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self.client is None:
                with httpx.Client() as client:
                    response = client.post(
                        self.base_url,
                        headers=headers,
                        json=request,
                        timeout=self.timeout_seconds,
                    )
            else:
                response = self.client.post(
                    self.base_url,
                    headers=headers,
                    json=request,
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            decoded: Any = json.loads(content) if isinstance(content, str) else content
            return Analysis.model_validate(decoded)
        except Exception as exc:
            raise AnalystProviderError(
                "The analyst provider did not return valid structured output."
            ) from exc


class AnalystService:
    """Use a provider only when trusted output can be validated; otherwise fallback."""

    def __init__(
        self,
        provider: AnalystProvider | None = None,
        fallback: AnalystProvider | None = None,
    ) -> None:
        self.provider = provider
        self.fallback = fallback or DeterministicAnalyst()

    def analyze(self, evidence: IncidentEvidence) -> AnalystResult:
        if self.provider is None:
            return AnalystResult(
                analysis=self.fallback.analyze(evidence),
                used_fallback=True,
                provider="deterministic_fallback",
            )

        try:
            analysis = Analysis.model_validate(self.provider.analyze(evidence))
            if analysis.severity != evidence.risk_level:
                raise AnalystProviderError(
                    "Analyst severity does not match the risk engine level."
                )
            analysis = analysis.model_copy(update={"analysis_source": "llm"})
            return AnalystResult(
                analysis=analysis,
                used_fallback=False,
                provider="llm",
            )
        except Exception:
            return AnalystResult(
                analysis=self.fallback.analyze(evidence),
                used_fallback=True,
                provider="deterministic_fallback",
            )
