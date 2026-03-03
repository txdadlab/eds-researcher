"""Weekly delta report generator — shows only changes since last run."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from eds_researcher.memory.database import Database

logger = logging.getLogger(__name__)

TIER_LABELS = {
    1: "Peer-Reviewed",
    2: "Clinical/Emerging",
    3: "Professional Opinion",
    4: "Anecdotal — Multiple",
    5: "Anecdotal — Single",
    6: "Theoretical/Lead",
}

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_delta_report(
    db: Database,
    output_dir: str | Path,
    since: date | None = None,
) -> Path:
    """Generate a delta report showing changes since the given date."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    since = since or (date.today() - timedelta(days=7))

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("delta_report.md.j2")

    # Get treatments that are new or updated since last run
    changed_treatments = db.get_treatments_since(since)
    new_treatments = [t for t in changed_treatments if t.first_seen >= since]
    updated_treatments = [t for t in changed_treatments if t.first_seen < since and t.last_updated >= since]

    # New evidence
    new_evidence = db.get_evidence_since(since)

    # Build treatment -> new evidence mapping
    new_evidence_by_treatment = {}
    for e in new_evidence:
        new_evidence_by_treatment.setdefault(e.treatment_id, []).append(e)

    # Treatment ID -> name mapping for the evidence table
    treatment_names = {}
    for t in changed_treatments:
        treatment_names[t.id] = t.name
    # Also look up names for any evidence whose treatment isn't in changed_treatments
    for e in new_evidence:
        if e.treatment_id not in treatment_names:
            t = db.get_treatment(e.treatment_id)
            if t:
                treatment_names[t.id] = t.name

    # New leads
    new_leads = db.get_pending_leads(limit=20)

    # Search effectiveness stats
    recent_searches = db.get_recent_searches(limit=200)
    search_stats = {}
    for sh in recent_searches:
        if sh.date_run and sh.date_run.date() >= since:
            if sh.source not in search_stats:
                search_stats[sh.source] = {"queries": 0, "total": 0, "useful": 0, "hit_rate": 0.0}
            stats = search_stats[sh.source]
            stats["queries"] += 1
            stats["total"] += sh.results_count
            stats["useful"] += sh.useful_results_count
    for stats in search_stats.values():
        stats["hit_rate"] = stats["useful"] / max(stats["total"], 1)

    rendered = template.render(
        generated_date=date.today().isoformat(),
        since_date=since.isoformat(),
        new_treatments=new_treatments,
        updated_treatments=updated_treatments,
        new_evidence=new_evidence,
        new_evidence_by_treatment=new_evidence_by_treatment,
        treatment_names=treatment_names,
        new_leads=new_leads,
        search_stats=search_stats,
        tier_labels=TIER_LABELS,
    )

    output_path = output_dir / f"delta_report_{date.today().isoformat()}.md"
    output_path.write_text(rendered)
    logger.info(f"Delta report written to {output_path}")
    return output_path
