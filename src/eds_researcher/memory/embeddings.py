"""ChromaDB embeddings for semantic search over treatments and evidence."""

from __future__ import annotations

from pathlib import Path

import chromadb


class EmbeddingStore:
    """Manages ChromaDB collections for semantic search."""

    def __init__(self, persist_dir: str | Path):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.treatments = self.client.get_or_create_collection(
            name="treatments",
            metadata={"hnsw:space": "cosine"},
        )
        self.evidence = self.client.get_or_create_collection(
            name="evidence",
            metadata={"hnsw:space": "cosine"},
        )

    def add_treatment(self, treatment_id: int, text: str, metadata: dict | None = None) -> None:
        """Add or update a treatment embedding."""
        doc_id = f"treatment_{treatment_id}"
        self.treatments.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata] if metadata else None,
        )

    def add_evidence(self, evidence_id: int, text: str, metadata: dict | None = None) -> None:
        """Add or update an evidence embedding."""
        doc_id = f"evidence_{evidence_id}"
        self.evidence.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata] if metadata else None,
        )

    def search_treatments(self, query: str, n_results: int = 10) -> list[dict]:
        """Semantic search over treatments. Returns list of {id, document, metadata, distance}."""
        results = self.treatments.query(query_texts=[query], n_results=n_results)
        return self._unpack_results(results)

    def search_evidence(self, query: str, n_results: int = 10) -> list[dict]:
        """Semantic search over evidence. Returns list of {id, document, metadata, distance}."""
        results = self.evidence.query(query_texts=[query], n_results=n_results)
        return self._unpack_results(results)

    def _unpack_results(self, results: dict) -> list[dict]:
        if not results["ids"] or not results["ids"][0]:
            return []
        items = []
        for i, doc_id in enumerate(results["ids"][0]):
            items.append({
                "id": doc_id,
                "document": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return items
