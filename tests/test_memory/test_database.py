"""Tests for the SQLite database layer."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from eds_researcher.memory import (
    BodyRegion,
    Database,
    Evidence,
    EvidenceSupport,
    EvidenceTier,
    LeadStatus,
    Provider,
    SearchHistory,
    SearchLead,
    Severity,
    Symptom,
    Treatment,
    TreatmentCategory,
    TreatmentSymptom,
)


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


class TestTreatments:
    def test_insert_and_get(self, db):
        t = Treatment(
            name="Low-dose naltrexone",
            category=TreatmentCategory.MEDICATION,
            description="Off-label use for pain modulation",
            evidence_tier=EvidenceTier.CLINICAL_EMERGING,
        )
        tid = db.upsert_treatment(t)
        assert tid is not None

        result = db.get_treatment(tid)
        assert result.name == "Low-dose naltrexone"
        assert result.category == TreatmentCategory.MEDICATION
        assert result.evidence_tier == EvidenceTier.CLINICAL_EMERGING

    def test_upsert_updates_existing(self, db):
        t = Treatment(name="Magnesium", category=TreatmentCategory.SUPPLEMENT)
        id1 = db.upsert_treatment(t)

        t2 = Treatment(
            name="Magnesium",
            category=TreatmentCategory.SUPPLEMENT,
            description="Updated description",
            evidence_tier=EvidenceTier.ANECDOTAL_MULTIPLE,
        )
        id2 = db.upsert_treatment(t2)
        assert id1 == id2

        result = db.get_treatment(id1)
        assert result.description == "Updated description"
        assert result.evidence_tier == EvidenceTier.ANECDOTAL_MULTIPLE

    def test_get_by_name(self, db):
        db.upsert_treatment(Treatment(name="CBD oil", category=TreatmentCategory.SUPPLEMENT))
        result = db.get_treatment_by_name("CBD oil")
        assert result is not None
        assert result.name == "CBD oil"

        assert db.get_treatment_by_name("nonexistent") is None

    def test_get_all(self, db):
        db.upsert_treatment(Treatment(name="A", category=TreatmentCategory.MEDICATION, evidence_tier=EvidenceTier.PEER_REVIEWED))
        db.upsert_treatment(Treatment(name="B", category=TreatmentCategory.SUPPLEMENT, evidence_tier=EvidenceTier.ANECDOTAL_SINGLE))
        treatments = db.get_all_treatments()
        assert len(treatments) == 2
        # Should be ordered by evidence tier
        assert treatments[0].name == "A"

    def test_get_treatments_since(self, db):
        db.upsert_treatment(Treatment(
            name="Old",
            category=TreatmentCategory.OTHER,
            first_seen=date(2024, 1, 1),
            last_updated=date(2024, 1, 1),
        ))
        db.upsert_treatment(Treatment(
            name="New",
            category=TreatmentCategory.OTHER,
            first_seen=date(2025, 6, 1),
            last_updated=date(2025, 6, 1),
        ))
        recent = db.get_treatments_since(date(2025, 1, 1))
        assert len(recent) == 1
        assert recent[0].name == "New"


class TestSymptoms:
    def test_insert_and_get(self, db):
        s = Symptom(name="knee_pain", body_region=BodyRegion.JOINT, severity_relevance=Severity.HIGH)
        sid = db.upsert_symptom(s)
        result = db.get_symptom_by_name("knee_pain")
        assert result is not None
        assert result.body_region == BodyRegion.JOINT

    def test_get_all(self, db):
        db.upsert_symptom(Symptom(name="brain_fog", body_region=BodyRegion.COGNITIVE))
        db.upsert_symptom(Symptom(name="hip_pain", body_region=BodyRegion.JOINT))
        symptoms = db.get_all_symptoms()
        assert len(symptoms) == 2


class TestTreatmentSymptomLinks:
    def test_link_and_query(self, db):
        tid = db.upsert_treatment(Treatment(name="PT exercises", category=TreatmentCategory.EXERCISE))
        sid = db.upsert_symptom(Symptom(name="knee_pain", body_region=BodyRegion.JOINT))
        db.link_treatment_symptom(TreatmentSymptom(treatment_id=tid, symptom_id=sid, effectiveness_score=0.75))

        results = db.get_treatments_for_symptom(sid)
        assert len(results) == 1
        treatment, score = results[0]
        assert treatment.name == "PT exercises"
        assert score == 0.75


class TestEvidence:
    def test_add_and_query(self, db):
        tid = db.upsert_treatment(Treatment(name="LDN", category=TreatmentCategory.MEDICATION))
        eid = db.add_evidence(Evidence(
            treatment_id=tid,
            source_type="pubmed",
            source_url="https://pubmed.ncbi.nlm.nih.gov/12345",
            summary="RCT showing 30% pain reduction",
            evidence_tier=EvidenceTier.PEER_REVIEWED,
            supports_treatment=EvidenceSupport.SUPPORTS,
        ))
        assert eid is not None
        evidence = db.get_evidence_for_treatment(tid)
        assert len(evidence) == 1
        assert evidence[0].summary == "RCT showing 30% pain reduction"

    def test_get_evidence_since(self, db):
        tid = db.upsert_treatment(Treatment(name="Test", category=TreatmentCategory.OTHER))
        db.add_evidence(Evidence(
            treatment_id=tid,
            source_type="reddit",
            source_url="https://reddit.com/r/eds/123",
            summary="Recent finding",
            evidence_tier=EvidenceTier.ANECDOTAL_SINGLE,
            retrieval_date=date.today(),
        ))
        results = db.get_evidence_since(date(2025, 1, 1))
        assert len(results) >= 1


class TestProviders:
    def test_upsert_and_query(self, db):
        pid = db.upsert_provider(Provider(
            name="Dr. Smith",
            credentials="MD, FACR",
            specialty="Rheumatology",
            location="NYC",
        ))
        providers = db.get_all_providers()
        assert len(providers) == 1
        assert providers[0].name == "Dr. Smith"

    def test_link_to_treatment(self, db):
        tid = db.upsert_treatment(Treatment(name="Prolotherapy", category=TreatmentCategory.THERAPY))
        pid = db.upsert_provider(Provider(name="Dr. Jones", specialty="Sports Medicine"))
        db.link_provider_treatment(pid, tid)

        providers = db.get_providers_for_treatment(tid)
        assert len(providers) == 1
        assert providers[0].name == "Dr. Jones"


class TestSearchLeads:
    def test_add_and_get_pending(self, db):
        db.add_lead(SearchLead(
            query_text="EDS prolotherapy outcomes",
            source_target="pubmed",
            priority=3,
            origin="grok_analysis",
        ))
        leads = db.get_pending_leads()
        assert len(leads) == 1
        assert leads[0].query_text == "EDS prolotherapy outcomes"

    def test_update_status(self, db):
        lid = db.add_lead(SearchLead(
            query_text="test query",
            source_target="reddit",
        ))
        db.update_lead_status(lid, LeadStatus.SEARCHED)
        leads = db.get_pending_leads()
        assert len(leads) == 0


class TestSearchHistory:
    def test_add_and_query(self, db):
        db.add_search_history(SearchHistory(
            query_text="EDS pain treatment",
            source="pubmed",
            results_count=15,
            useful_results_count=5,
        ))
        history = db.get_recent_searches(source="pubmed")
        assert len(history) == 1
        assert history[0].results_count == 15
