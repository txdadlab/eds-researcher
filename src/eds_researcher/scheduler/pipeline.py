"""Main pipeline orchestration: PLAN → SEARCH → ANALYZE → LEARN."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from eds_researcher.analyzer.extractor import Extractor
from eds_researcher.analyzer.grok_client import GrokClient
from eds_researcher.analyzer.lead_generator import LeadGenerator
from eds_researcher.analyzer.scorer import (
    aggregate_treatment_tier,
    is_trending,
    score_evidence_tier,
)
from eds_researcher.collectors.base import Collector
from eds_researcher.collectors.clinical_trials import ClinicalTrialsCollector
from eds_researcher.collectors.openfda import OpenFDACollector
from eds_researcher.collectors.pubchem import PubChemCollector
from eds_researcher.collectors.pubmed import PubMedCollector
from eds_researcher.collectors.reddit import RedditCollector
from eds_researcher.collectors.scholar import ScholarCollector
from eds_researcher.collectors.xai_search import XAISearchCollector
from eds_researcher.memory.database import Database
from eds_researcher.memory.embeddings import EmbeddingStore
from eds_researcher.memory.models import (
    BodyRegion,
    Evidence,
    EvidenceTier,
    LeadStatus,
    RawFinding,
    SearchHistory,
    SearchLead,
    Severity,
    Symptom,
    Treatment,
    TreatmentCategory,
    TreatmentSymptom,
)
from eds_researcher.reporter.delta_report import generate_delta_report
from eds_researcher.reporter.full_report import generate_full_report

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the 4-stage research pipeline."""

    def __init__(self, config_path: str | Path = "config.yaml"):
        self.config = self._load_config(config_path)
        self.db = Database(self.config["database"]["path"])
        self.embeddings = EmbeddingStore(self.config["database"]["chromadb_path"])

        grok_cfg = self.config["grok"]
        self.grok = GrokClient(
            base_url=grok_cfg["base_url"],
            screening_model=grok_cfg["screening_model"],
            analysis_model=grok_cfg["analysis_model"],
            max_tokens=grok_cfg.get("max_tokens", 4096),
            temperature=grok_cfg.get("temperature", 0.3),
        )

        self.extractor = Extractor(self.grok)
        self.lead_generator = LeadGenerator(self.grok)
        self.collectors = self._init_collectors()

    def _load_config(self, path: str | Path) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def _init_collectors(self) -> dict[str, Collector]:
        """Initialize enabled collectors."""
        sources = self.config.get("sources", {})
        collectors = {}

        if sources.get("pubmed", {}).get("enabled", True):
            pubmed_cfg = sources["pubmed"]
            collectors["pubmed"] = PubMedCollector(
                email=pubmed_cfg.get("email", ""),
                databases=pubmed_cfg.get("databases", ["pubmed", "pmc"]),
            )

        if sources.get("reddit", {}).get("enabled", True):
            reddit_cfg = sources["reddit"]
            collectors["reddit"] = RedditCollector(
                subreddits=reddit_cfg.get("subreddits"),
                time_filter=reddit_cfg.get("time_filter", "month"),
            )

        if sources.get("xai_search", {}).get("enabled", True):
            collectors["xai_search"] = XAISearchCollector(
                base_url=self.config["grok"]["base_url"],
            )

        if sources.get("clinical_trials", {}).get("enabled", True):
            collectors["clinical_trials"] = ClinicalTrialsCollector()

        if sources.get("scholar", {}).get("enabled", True):
            collectors["scholar"] = ScholarCollector(
                use_proxy=sources.get("scholar", {}).get("use_proxy", False),
            )

        if sources.get("pubchem", {}).get("enabled", True):
            collectors["pubchem"] = PubChemCollector()

        if sources.get("openfda", {}).get("enabled", True):
            collectors["openfda"] = OpenFDACollector()

        return collectors

    def run(self) -> dict:
        """Execute the full 4-stage pipeline. Returns run statistics."""
        logger.info("=== Pipeline run starting ===")
        stats = {"queries": 0, "findings": 0, "treatments": 0, "evidence": 0}

        # Ensure symptoms are seeded
        self._seed_symptoms()

        # Stage 1: PLAN
        logger.info("Stage 1: PLAN — Generating search queries")
        queries = self._plan()
        stats["queries"] = len(queries)

        # Stage 2: SEARCH
        logger.info(f"Stage 2: SEARCH — Executing {len(queries)} queries across {len(self.collectors)} sources")
        all_findings = self._search(queries)
        stats["findings"] = len(all_findings)

        # Stage 3: ANALYZE
        logger.info(f"Stage 3: ANALYZE — Processing {len(all_findings)} findings")
        extraction_results = self._analyze(all_findings)

        # Stage 4: LEARN
        logger.info("Stage 4: LEARN — Persisting results to database")
        learn_stats = self._learn(extraction_results, all_findings)
        stats.update(learn_stats)

        logger.info(f"=== Pipeline complete: {stats} ===")
        return stats

    # ── Stage 1: PLAN ──────────────────────────────────────

    def _plan(self) -> list[tuple[str, str]]:
        """Generate search queries based on current knowledge state.

        Returns list of (query_text, source_target) tuples.
        """
        queries = []

        # Get pending leads from DB
        pending_leads = self.db.get_pending_leads(limit=30)
        for lead in pending_leads:
            queries.append((lead.query_text, lead.source_target))

        # If not enough leads, generate new ones via Grok
        if len(queries) < 10:
            known = [t.name for t in self.db.get_all_treatments()]
            low_yield = [
                sh.query_text for sh in self.db.get_recent_searches()
                if sh.useful_results_count == 0
            ][:10]

            new_leads = self.lead_generator.generate(
                known_treatments=known,
                recent_summary=self._build_recent_summary(),
                low_yield_queries=low_yield,
                num_leads=15,
            )
            for lead in new_leads:
                lead_id = self.db.add_lead(lead)
                queries.append((lead.query_text, lead.source_target))

        return queries

    def _build_recent_summary(self) -> str:
        """Build a summary of recent findings for Grok context."""
        recent = self.db.get_treatments_since(date.today() - timedelta(days=30))
        if not recent:
            return "No recent findings."
        parts = []
        for t in recent[:20]:
            evidence = self.db.get_evidence_for_treatment(t.id)
            parts.append(f"- {t.name} (T{t.evidence_tier}): {len(evidence)} evidence records")
        return "\n".join(parts)

    # ── Stage 2: SEARCH ────────────────────────────────────

    def _search(self, queries: list[tuple[str, str]]) -> list[RawFinding]:
        """Execute queries against appropriate collectors."""
        all_findings = []
        max_results = self.config.get("search", {}).get("max_results_per_source", 20)

        for query_text, source_target in queries:
            collector = self.collectors.get(source_target)
            if not collector:
                logger.warning(f"No collector for source '{source_target}', skipping")
                continue

            findings = collector.search_safe(query_text, max_results=max_results)

            # Record search history
            self.db.add_search_history(SearchHistory(
                query_text=query_text,
                source=source_target,
                results_count=len(findings),
                useful_results_count=0,  # Updated after analysis
            ))

            # Update lead status
            leads = self.db.get_pending_leads(limit=100)
            for lead in leads:
                if lead.query_text == query_text and lead.source_target == source_target:
                    self.db.update_lead_status(lead.id, LeadStatus.SEARCHED)

            all_findings.extend(findings)

        return all_findings

    # ── Stage 3: ANALYZE ───────────────────────────────────

    def _analyze(self, findings: list[RawFinding]):
        """Extract structured data from raw findings via Grok."""
        return self.extractor.extract_batch(findings)

    # ── Stage 4: LEARN ─────────────────────────────────────

    def _learn(self, extraction_results, all_findings: list[RawFinding]) -> dict:
        """Persist extracted data to the database and embeddings."""
        stats = {"treatments": 0, "evidence": 0, "providers": 0}

        for result in extraction_results:
            finding = result.source_finding
            if not finding:
                continue

            for t_data in result.treatments:
                # Upsert treatment
                try:
                    category = TreatmentCategory(t_data.get("category", "other"))
                except ValueError:
                    category = TreatmentCategory.OTHER

                treatment = Treatment(
                    name=t_data["name"],
                    category=category,
                    description=t_data.get("description", ""),
                    mechanism_of_action=t_data.get("mechanism_of_action", ""),
                    legality=t_data.get("legality", ""),
                    cost_estimate=t_data.get("cost_estimate", ""),
                )

                tid = self.db.upsert_treatment(treatment)
                stats["treatments"] += 1

                # Score and add evidence
                tier = score_evidence_tier(finding.source_type, finding.content)
                eid = self.db.add_evidence(Evidence(
                    treatment_id=tid,
                    source_type=finding.source_type,
                    source_url=finding.source_url,
                    source_date=finding.date,
                    summary=result.evidence_summary,
                    evidence_tier=tier,
                    raw_snippet=finding.content[:1000],
                    supports_treatment=result.supports_treatment,
                ))
                stats["evidence"] += 1

                # Update treatment tier based on all evidence
                all_evidence = self.db.get_evidence_for_treatment(tid)
                agg_tier = aggregate_treatment_tier(all_evidence)
                trending = is_trending(all_evidence)
                updated = Treatment(
                    name=t_data["name"],
                    category=category,
                    description=t_data.get("description", ""),
                    mechanism_of_action=t_data.get("mechanism_of_action", ""),
                    legality=t_data.get("legality", ""),
                    cost_estimate=t_data.get("cost_estimate", ""),
                    evidence_tier=agg_tier,
                    trending=trending,
                )
                self.db.upsert_treatment(updated)

                # Link to symptoms
                for symptom_name in t_data.get("relevant_symptoms", []):
                    symptom = self.db.get_symptom_by_name(symptom_name)
                    if symptom:
                        self.db.link_treatment_symptom(TreatmentSymptom(
                            treatment_id=tid,
                            symptom_id=symptom.id,
                            effectiveness_score=result.relevance_score,
                        ))

                # Update embeddings
                embed_text = f"{t_data['name']}: {t_data.get('description', '')} {t_data.get('mechanism_of_action', '')}"
                self.embeddings.add_treatment(tid, embed_text, metadata={
                    "category": category,
                    "tier": int(agg_tier),
                })
                self.embeddings.add_evidence(eid, result.evidence_summary, metadata={
                    "treatment_id": tid,
                    "source_type": finding.source_type,
                    "tier": int(tier),
                })

            # Upsert providers
            for p_data in result.providers:
                if not p_data.get("name"):
                    continue
                from eds_researcher.memory.models import Provider
                pid = self.db.upsert_provider(Provider(
                    name=p_data["name"],
                    credentials=p_data.get("credentials", ""),
                    specialty=p_data.get("specialty", ""),
                    location=p_data.get("location", ""),
                    contact_info=p_data.get("contact_info", ""),
                    source_url=finding.source_url,
                ))
                stats["providers"] += 1

                # Link provider to all treatments in this finding
                for t_data in result.treatments:
                    t = self.db.get_treatment_by_name(t_data["name"])
                    if t:
                        self.db.link_provider_treatment(pid, t.id)

        return stats

    # ── Helpers ─────────────────────────────────────────────

    def _seed_symptoms(self) -> None:
        """Seed default symptoms from config if not already present."""
        existing = {s.name for s in self.db.get_all_symptoms()}
        for sym_cfg in self.config.get("symptoms", []):
            if sym_cfg["name"] not in existing:
                self.db.upsert_symptom(Symptom(
                    name=sym_cfg["name"],
                    body_region=BodyRegion(sym_cfg["body_region"]),
                    severity_relevance=Severity(sym_cfg["severity"]),
                ))
                logger.info(f"Seeded symptom: {sym_cfg['name']}")

    def generate_reports(self, since: date | None = None) -> tuple[Path, Path]:
        """Generate both full and delta reports."""
        output_dir = self.config.get("reports", {}).get("output_dir", "data/reports")
        full = generate_full_report(self.db, output_dir)
        delta = generate_delta_report(self.db, output_dir, since=since)
        return full, delta

    def close(self) -> None:
        self.db.close()
