"""Tests for evidence tier scoring logic."""

from datetime import date, timedelta

from eds_researcher.analyzer.scorer import (
    aggregate_treatment_tier,
    is_trending,
    score_evidence_tier,
)
from eds_researcher.memory.models import Evidence, EvidenceTier


def test_pubmed_default_tier():
    tier = score_evidence_tier("pubmed", "A study about EDS pain treatment.")
    assert tier == EvidenceTier.PEER_REVIEWED


def test_pubmed_rct_stays_t1():
    tier = score_evidence_tier("pubmed", "A randomized controlled trial of LDN in EDS patients.")
    assert tier == EvidenceTier.PEER_REVIEWED


def test_reddit_default_is_anecdotal_single():
    tier = score_evidence_tier("reddit", "LDN helped me with my pain.")
    assert tier == EvidenceTier.ANECDOTAL_SINGLE


def test_reddit_multiple_reports():
    tier = score_evidence_tier("reddit", "Many people in this sub report that LDN helps significantly.")
    assert tier == EvidenceTier.ANECDOTAL_MULTIPLE


def test_reddit_professional_opinion():
    tier = score_evidence_tier("reddit", "My rheumatologist recommended magnesium glycinate for muscle cramps.")
    assert tier == EvidenceTier.PROFESSIONAL_OPINION


def test_clinical_trials_default():
    tier = score_evidence_tier("clinical_trials", "Phase 2 study of LDN in EDS.")
    assert tier == EvidenceTier.CLINICAL_EMERGING


def test_unknown_source():
    tier = score_evidence_tier("unknown_source", "Some content")
    assert tier == EvidenceTier.THEORETICAL_LEAD


def test_aggregate_takes_strongest():
    evidence = [
        Evidence(treatment_id=1, source_type="reddit", source_url="", summary="", evidence_tier=EvidenceTier.ANECDOTAL_SINGLE),
        Evidence(treatment_id=1, source_type="pubmed", source_url="", summary="", evidence_tier=EvidenceTier.PEER_REVIEWED),
        Evidence(treatment_id=1, source_type="xai_search", source_url="", summary="", evidence_tier=EvidenceTier.ANECDOTAL_MULTIPLE),
    ]
    assert aggregate_treatment_tier(evidence) == EvidenceTier.PEER_REVIEWED


def test_aggregate_empty():
    assert aggregate_treatment_tier([]) == EvidenceTier.THEORETICAL_LEAD


def test_trending_detection():
    today = date.today()
    evidence = [
        Evidence(treatment_id=1, source_type="reddit", source_url="", summary="", evidence_tier=EvidenceTier.ANECDOTAL_SINGLE, retrieval_date=today),
        Evidence(treatment_id=1, source_type="reddit", source_url="", summary="", evidence_tier=EvidenceTier.ANECDOTAL_SINGLE, retrieval_date=today - timedelta(days=5)),
        Evidence(treatment_id=1, source_type="pubmed", source_url="", summary="", evidence_tier=EvidenceTier.PEER_REVIEWED, retrieval_date=today - timedelta(days=10)),
    ]
    assert is_trending(evidence) is True


def test_not_trending():
    old = date.today() - timedelta(days=60)
    evidence = [
        Evidence(treatment_id=1, source_type="pubmed", source_url="", summary="", evidence_tier=EvidenceTier.PEER_REVIEWED, retrieval_date=old),
    ]
    assert is_trending(evidence) is False
