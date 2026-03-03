"""Full compendium report generator."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from eds_researcher.memory.database import Database
from eds_researcher.memory.models import EvidenceTier

logger = logging.getLogger(__name__)

TIER_LABELS = {
    1: "Peer-Reviewed",
    2: "Clinical/Emerging",
    3: "Professional Opinion",
    4: "Anecdotal — Multiple",
    5: "Anecdotal — Single",
    6: "Theoretical/Lead",
}

TIERS = [(i, TIER_LABELS[i]) for i in range(1, 7)]

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_full_report(db: Database, output_dir: str | Path) -> Path:
    """Generate a full treatment compendium report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("full_report.md.j2")

    treatments = db.get_all_treatments()
    symptoms = db.get_all_symptoms()

    # Build symptom -> treatments mapping
    symptom_treatments = {}
    for symptom in symptoms:
        symptom_treatments[symptom.name] = db.get_treatments_for_symptom(symptom.id)

    # Build treatment -> evidence mapping
    evidence_by_treatment = {}
    total_evidence = 0
    for t in treatments:
        evidence = db.get_evidence_for_treatment(t.id)
        evidence_by_treatment[t.id] = evidence
        total_evidence += len(evidence)

    # Build treatment -> providers mapping
    providers_by_treatment = {}
    for t in treatments:
        providers_by_treatment[t.id] = db.get_providers_for_treatment(t.id)

    pending_leads = db.get_pending_leads(limit=30)

    rendered = template.render(
        generated_date=date.today().isoformat(),
        treatments=treatments,
        symptoms=symptoms,
        symptom_treatments=symptom_treatments,
        evidence_by_treatment=evidence_by_treatment,
        providers_by_treatment=providers_by_treatment,
        total_evidence=total_evidence,
        pending_leads=pending_leads,
        tiers=TIERS,
        tier_labels=TIER_LABELS,
    )

    output_path = output_dir / f"full_report_{date.today().isoformat()}.md"
    output_path.write_text(rendered)
    logger.info(f"Full report written to {output_path}")
    return output_path
