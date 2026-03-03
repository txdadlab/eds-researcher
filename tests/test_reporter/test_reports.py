"""Tests for full and delta report generation."""

from datetime import date, timedelta

import pytest

from eds_researcher.memory import (
    BodyRegion,
    Database,
    Evidence,
    EvidenceSupport,
    EvidenceTier,
    Provider,
    SearchLead,
    Severity,
    Symptom,
    Treatment,
    TreatmentCategory,
    TreatmentSymptom,
)
from eds_researcher.reporter import generate_delta_report, generate_full_report


@pytest.fixture
def populated_db(tmp_path):
    """Create a database with sample data for report testing."""
    db = Database(tmp_path / "test.db")

    # Add symptoms
    s1 = db.upsert_symptom(Symptom(name="knee_pain", body_region=BodyRegion.JOINT, severity_relevance=Severity.HIGH))
    s2 = db.upsert_symptom(Symptom(name="brain_fog", body_region=BodyRegion.COGNITIVE, severity_relevance=Severity.HIGH))

    # Add treatments
    t1 = db.upsert_treatment(Treatment(
        name="Low-dose naltrexone",
        category=TreatmentCategory.MEDICATION,
        description="Off-label opioid antagonist",
        mechanism_of_action="Upregulates endorphin production",
        evidence_tier=EvidenceTier.PEER_REVIEWED,
        trending=True,
    ))
    t2 = db.upsert_treatment(Treatment(
        name="Magnesium glycinate",
        category=TreatmentCategory.SUPPLEMENT,
        description="Bioavailable magnesium form",
        evidence_tier=EvidenceTier.ANECDOTAL_MULTIPLE,
    ))

    # Link treatments to symptoms
    db.link_treatment_symptom(TreatmentSymptom(treatment_id=t1, symptom_id=s1, effectiveness_score=0.75))
    db.link_treatment_symptom(TreatmentSymptom(treatment_id=t2, symptom_id=s2, effectiveness_score=0.6))

    # Add evidence
    db.add_evidence(Evidence(
        treatment_id=t1,
        source_type="pubmed",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345/",
        summary="RCT showing 30% pain reduction in fibromyalgia",
        evidence_tier=EvidenceTier.PEER_REVIEWED,
        supports_treatment=EvidenceSupport.SUPPORTS,
    ))
    db.add_evidence(Evidence(
        treatment_id=t2,
        source_type="reddit",
        source_url="https://reddit.com/r/ehlersdanlos/abc",
        summary="Multiple users report improved brain fog",
        evidence_tier=EvidenceTier.ANECDOTAL_MULTIPLE,
        supports_treatment=EvidenceSupport.SUPPORTS,
    ))

    # Add a provider
    pid = db.upsert_provider(Provider(
        name="Dr. Chopra",
        credentials="MD",
        specialty="Pain Management",
        location="Providence, RI",
    ))
    db.link_provider_treatment(pid, t1)

    # Add a lead
    db.add_lead(SearchLead(
        query_text="EDS prolotherapy outcomes",
        source_target="pubmed",
        priority=3,
        origin="grok_analysis",
    ))

    yield db
    db.close()


class TestFullReport:
    def test_generates_markdown(self, populated_db, tmp_path):
        report_dir = tmp_path / "reports"
        path = generate_full_report(populated_db, report_dir)

        assert path.exists()
        content = path.read_text()

        # Check key sections
        assert "EDS Pain Management Guide" in content
        assert "Low-dose naltrexone" in content
        assert "Magnesium glycinate" in content
        assert "Knee Pain" in content
        assert "Brain Fog" in content
        assert "Dr. Chopra" in content
        assert "Trending" in content

    def test_handles_empty_db(self, tmp_path):
        db = Database(tmp_path / "empty.db")
        report_dir = tmp_path / "reports"
        path = generate_full_report(db, report_dir)
        assert path.exists()
        content = path.read_text()
        assert "EDS Pain Management Guide" in content
        db.close()


class TestDeltaReport:
    def test_generates_markdown(self, populated_db, tmp_path):
        report_dir = tmp_path / "reports"
        # Everything should be "new" since it was all added today
        path = generate_delta_report(populated_db, report_dir, since=date.today() - timedelta(days=1))

        assert path.exists()
        content = path.read_text()

        assert "What's New" in content
        assert "Low-dose naltrexone" in content
        assert "Newly Discovered Treatments" in content

    def test_empty_delta(self, populated_db, tmp_path):
        report_dir = tmp_path / "reports"
        # Future date should produce empty delta
        path = generate_delta_report(populated_db, report_dir, since=date.today() + timedelta(days=1))
        assert path.exists()
        content = path.read_text()
        assert "No new treatments discovered this period" in content
