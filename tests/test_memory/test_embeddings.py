"""Tests for the ChromaDB embeddings layer."""

import pytest

from eds_researcher.memory import EmbeddingStore


@pytest.fixture
def store(tmp_path):
    return EmbeddingStore(tmp_path / "chromadb")


class TestTreatmentEmbeddings:
    def test_add_and_search(self, store):
        store.add_treatment(1, "Low-dose naltrexone for chronic pain and inflammation in EDS")
        store.add_treatment(2, "Physical therapy strengthening exercises for hypermobile joints")
        store.add_treatment(3, "Magnesium glycinate supplement for muscle cramps and neuropathy")

        results = store.search_treatments("pain medication for EDS", n_results=2)
        assert len(results) == 2
        # LDN should be the top hit for pain medication
        assert "treatment_1" in results[0]["id"]

    def test_upsert_updates(self, store):
        store.add_treatment(1, "Old description")
        store.add_treatment(1, "New description about pain relief")
        results = store.search_treatments("pain relief")
        assert len(results) == 1
        assert "New description" in results[0]["document"]


class TestEvidenceEmbeddings:
    def test_add_and_search(self, store):
        store.add_evidence(1, "RCT showing naltrexone reduces pain by 30% in fibromyalgia patients")
        store.add_evidence(2, "Reddit user reports magnesium helps with leg cramps at night")

        results = store.search_evidence("clinical trial pain reduction", n_results=2)
        assert len(results) == 2

    def test_metadata_preserved(self, store):
        store.add_evidence(1, "Some evidence text", metadata={"tier": 1, "source": "pubmed"})
        results = store.search_evidence("evidence", n_results=1)
        assert results[0]["metadata"]["tier"] == 1
        assert results[0]["metadata"]["source"] == "pubmed"
