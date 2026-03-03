"""Data models for the EDS Researcher memory layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum, StrEnum


class EvidenceTier(IntEnum):
    """Evidence quality tiers — lower number = stronger evidence."""
    PEER_REVIEWED = 1
    CLINICAL_EMERGING = 2
    PROFESSIONAL_OPINION = 3
    ANECDOTAL_MULTIPLE = 4
    ANECDOTAL_SINGLE = 5
    THEORETICAL_LEAD = 6


class TreatmentCategory(StrEnum):
    MEDICATION = "medication"
    SUPPLEMENT = "supplement"
    EXERCISE = "exercise"
    THERAPY = "therapy"
    OTHER = "other"


class BodyRegion(StrEnum):
    JOINT = "joint"
    NEUROLOGICAL = "neurological"
    MUSCULAR = "muscular"
    COGNITIVE = "cognitive"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LeadStatus(StrEnum):
    PENDING = "pending"
    SEARCHED = "searched"
    EXHAUSTED = "exhausted"


class EvidenceSupport(StrEnum):
    SUPPORTS = "true"
    OPPOSES = "false"
    MIXED = "mixed"


@dataclass
class Treatment:
    name: str
    category: TreatmentCategory
    description: str = ""
    mechanism_of_action: str = ""
    legality: str = ""
    cost_estimate: str = ""
    evidence_tier: EvidenceTier = EvidenceTier.THEORETICAL_LEAD
    trending: bool = False
    first_seen: date = field(default_factory=date.today)
    last_updated: date = field(default_factory=date.today)
    id: int | None = None


@dataclass
class Symptom:
    name: str
    body_region: BodyRegion
    severity_relevance: Severity = Severity.MEDIUM
    id: int | None = None


@dataclass
class TreatmentSymptom:
    treatment_id: int
    symptom_id: int
    effectiveness_score: float = 0.0


@dataclass
class Evidence:
    treatment_id: int
    source_type: str  # pubmed, reddit, xai, clinical_trials, scholar
    source_url: str
    summary: str
    evidence_tier: EvidenceTier
    supports_treatment: EvidenceSupport = EvidenceSupport.SUPPORTS
    source_date: date | None = None
    retrieval_date: date = field(default_factory=date.today)
    raw_snippet: str = ""
    id: int | None = None


@dataclass
class Provider:
    name: str
    credentials: str = ""
    specialty: str = ""
    location: str = ""
    contact_info: str = ""
    source_url: str = ""
    notes: str = ""
    id: int | None = None


@dataclass
class SearchLead:
    query_text: str
    source_target: str  # which source to search
    priority: int = 5  # 1=highest, 10=lowest
    origin: str = ""  # what generated this lead
    status: LeadStatus = LeadStatus.PENDING
    created_date: date = field(default_factory=date.today)
    last_searched: date | None = None
    id: int | None = None


@dataclass
class SearchHistory:
    query_text: str
    source: str
    results_count: int = 0
    useful_results_count: int = 0
    date_run: datetime = field(default_factory=datetime.now)
    id: int | None = None


@dataclass
class RawFinding:
    """Intermediate result from a collector, before analysis."""
    source_type: str
    source_url: str
    title: str
    content: str
    date: date | None = None
    metadata: dict = field(default_factory=dict)
