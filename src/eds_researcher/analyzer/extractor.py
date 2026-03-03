"""Extract treatments, providers, and evidence from raw findings using Grok."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from eds_researcher.memory.models import EvidenceSupport, EvidenceTier, RawFinding

from .grok_client import GrokClient

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM = """You are a medical research assistant specializing in Ehlers-Danlos Syndrome (EDS).
You extract structured treatment information from research sources.
Always respond in valid JSON. Be precise and evidence-based.
For a 17-year-old patient with hEDS and autism experiencing joint pain, neuropathy, muscle pain, and brain fog."""

EXTRACTION_PROMPT = """Analyze the following research finding and extract any treatments, providers, or evidence mentioned.

Source type: {source_type}
Source URL: {source_url}
Title: {title}

Content:
{content}

Return a JSON object with:
{{
  "treatments": [
    {{
      "name": "treatment name (use the standard/generic name, e.g. 'Physical Therapy' not 'PT' or 'Physiotherapy')",
      "category": "medication|supplement|exercise|therapy|other",
      "description": "brief patient-friendly description of what this treatment is and how it helps",
      "mechanism_of_action": "how it works, explained simply",
      "dosage": "specific dosage, frequency, or protocol if mentioned (e.g. '300mg twice daily', '3x/week 30min sessions')",
      "side_effects": "any mentioned side effects, risks, or warnings",
      "legality": "legal status if mentioned (e.g. 'prescription required', 'OTC', 'legal supplement')",
      "cost_estimate": "cost info if mentioned (e.g. '$30/month', 'covered by most insurance')",
      "relevant_symptoms": ["which symptoms this targets: knee_pain, hip_pain, shoulder_pain, neuropathy, muscle_pain, brain_fog"],
      "effectiveness_notes": "what the source says about effectiveness in plain language"
    }}
  ],
  "providers": [
    {{
      "name": "provider name",
      "credentials": "degrees/certifications",
      "specialty": "medical specialty",
      "location": "location if mentioned",
      "contact_info": "contact details if available"
    }}
  ],
  "evidence_summary": "brief summary of the key evidence in this finding",
  "supports_treatment": "true|false|mixed",
  "relevance_score": 0.0-1.0
}}

IMPORTANT:
- Only extract actual medical treatments, medications, supplements, therapies, or exercises.
- Do NOT extract general life activities (food, water, travel tips, etc.) as treatments.
- Use standard treatment names consistently (e.g. always "Physical Therapy" not variants like "PT", "Physiotherapy").
- Include dosage information whenever the source mentions specific amounts, frequencies, or protocols.
If no treatments are found, return empty arrays. Always include evidence_summary."""


@dataclass
class ExtractionResult:
    """Result of extracting structured data from a raw finding."""
    treatments: list[dict] = field(default_factory=list)
    providers: list[dict] = field(default_factory=list)
    evidence_summary: str = ""
    supports_treatment: EvidenceSupport = EvidenceSupport.SUPPORTS
    relevance_score: float = 0.0
    source_finding: RawFinding | None = None


class Extractor:
    """Extracts treatments, providers, and evidence from raw findings via Grok."""

    def __init__(self, grok: GrokClient):
        self.grok = grok

    def extract(self, finding: RawFinding) -> ExtractionResult:
        """Extract structured data from a single raw finding."""
        prompt = EXTRACTION_PROMPT.format(
            source_type=finding.source_type,
            source_url=finding.source_url,
            title=finding.title,
            content=finding.content[:3000],  # Cap to avoid token limits
        )

        try:
            data = self.grok.complete_json(prompt, system=EXTRACTION_SYSTEM)
        except Exception:
            logger.warning(f"Extraction failed for {finding.source_url}", exc_info=True)
            return ExtractionResult(source_finding=finding)

        if not isinstance(data, dict):
            return ExtractionResult(source_finding=finding)

        supports = data.get("supports_treatment", "true")
        try:
            support_enum = EvidenceSupport(supports)
        except ValueError:
            support_enum = EvidenceSupport.MIXED

        return ExtractionResult(
            treatments=data.get("treatments", []),
            providers=data.get("providers", []),
            evidence_summary=data.get("evidence_summary", ""),
            supports_treatment=support_enum,
            relevance_score=float(data.get("relevance_score", 0.0)),
            source_finding=finding,
        )

    def extract_batch(self, findings: list[RawFinding]) -> list[ExtractionResult]:
        """Extract from multiple findings."""
        results = []
        for finding in findings:
            result = self.extract(finding)
            if result.relevance_score > 0.1 or result.treatments:
                results.append(result)
        return results
