"""Evidence tier scoring logic."""

from __future__ import annotations

from eds_researcher.memory.models import Evidence, EvidenceTier


# Source type to default tier mapping
SOURCE_TIER_MAP: dict[str, EvidenceTier] = {
    "pubmed": EvidenceTier.PEER_REVIEWED,
    "clinical_trials": EvidenceTier.CLINICAL_EMERGING,
    "scholar": EvidenceTier.PEER_REVIEWED,
    "pubchem": EvidenceTier.CLINICAL_EMERGING,
    "openfda": EvidenceTier.CLINICAL_EMERGING,
    "xai_search": EvidenceTier.ANECDOTAL_SINGLE,
    "reddit": EvidenceTier.ANECDOTAL_SINGLE,
}

# Keywords that suggest higher evidence quality
UPGRADE_KEYWORDS = {
    "randomized controlled trial": -1,
    "meta-analysis": -1,
    "systematic review": -1,
    "double-blind": -1,
    "placebo-controlled": -1,
    "clinical trial": -1,
    "case series": 0,
    "case report": 0,
    "case study": 0,
    "retrospective": 0,
    "pilot study": 0,
}

# Keywords suggesting anecdotal reports
ANECDOTAL_KEYWORDS = [
    "in my experience",
    "worked for me",
    "i've been taking",
    "my doctor recommended",
    "helped me",
    "i found that",
    "anecdotally",
]


def score_evidence_tier(source_type: str, content: str) -> EvidenceTier:
    """Determine evidence tier based on source type and content analysis."""
    base_tier = SOURCE_TIER_MAP.get(source_type, EvidenceTier.THEORETICAL_LEAD)
    content_lower = content.lower()

    # Check for upgrade keywords (stronger evidence)
    adjustment = 0
    for keyword, adj in UPGRADE_KEYWORDS.items():
        if keyword in content_lower:
            adjustment = min(adjustment, adj)
            break

    # For community sources, check if multiple reports are referenced
    if source_type in ("reddit", "xai_search"):
        multi_indicators = ["many people", "multiple users", "several people", "commonly reported",
                            "frequently mentioned", "lots of people", "many of us"]
        if any(ind in content_lower for ind in multi_indicators):
            # Upgrade from single anecdotal to multiple anecdotal
            base_tier = EvidenceTier.ANECDOTAL_MULTIPLE

        # Check for professional opinion indicators in community posts
        pro_indicators = ["my doctor says", "my rheumatologist", "per my specialist",
                          "according to dr", "physical therapist recommended"]
        if any(ind in content_lower for ind in pro_indicators):
            base_tier = min(base_tier, EvidenceTier.PROFESSIONAL_OPINION)

    # Apply adjustment (lower tier number = stronger evidence)
    final_tier = max(1, int(base_tier) + adjustment)
    return EvidenceTier(min(final_tier, 6))


def aggregate_treatment_tier(evidence_list: list[Evidence]) -> EvidenceTier:
    """Determine overall treatment tier from all its evidence.

    The treatment gets the tier of its strongest evidence.
    """
    if not evidence_list:
        return EvidenceTier.THEORETICAL_LEAD
    return min(e.evidence_tier for e in evidence_list)


def is_trending(evidence_list: list[Evidence], recent_days: int = 30) -> bool:
    """Determine if a treatment is trending based on recent evidence frequency."""
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=recent_days)
    recent_count = sum(1 for e in evidence_list if e.retrieval_date and e.retrieval_date >= cutoff)
    return recent_count >= 3
