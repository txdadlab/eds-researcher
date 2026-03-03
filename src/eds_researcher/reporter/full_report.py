"""Full compendium report generator — patient-friendly treatment guide."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from eds_researcher.memory.database import Database
from eds_researcher.memory.models import EvidenceTier

logger = logging.getLogger(__name__)

# Patient-friendly evidence labels (lower number = stronger evidence)
TIER_LABELS = {
    1: "Strong Research Evidence",
    2: "Emerging Clinical Evidence",
    3: "Professional Recommendation",
    4: "Community Reported (Multiple People)",
    5: "Community Reported (Individual)",
    6: "Under Investigation",
}

TIER_DESCRIPTIONS = {
    1: "Supported by published clinical studies and peer-reviewed research",
    2: "Currently being studied in clinical trials or emerging research",
    3: "Recommended by medical professionals based on clinical experience",
    4: "Reported helpful by multiple people in the EDS community",
    5: "Reported by an individual in the EDS community",
    6: "Mentioned in research but not yet directly studied for EDS",
}

# Treatments that are clearly not medical and should be excluded
_NOISE_NAMES = frozenset({
    "gelato", "water", "food", "seat upgrades", "shelf-stable meals",
    "floor time", "jelliebend", "increased water intake",
    "portable lumbar support cushions",
})

# Canonical names for deduplication — maps lowercase variant to preferred name
_CANONICAL_NAMES = {
    "physical therapy": "Physical Therapy",
    "physical therapy (pt)": "Physical Therapy",
    "physiotherapy": "Physical Therapy",
    "pt": "Physical Therapy",
    "multidisciplinary pain management": "Multidisciplinary Pain Management",
    "multidisciplinary pain management with pt": "Multidisciplinary Pain Management",
    "multidisciplinary approach": "Multidisciplinary Pain Management",
    "multidisciplinary management program": "Multidisciplinary Pain Management",
    "multidisciplinary rehabilitation treatment": "Multidisciplinary Rehabilitation",
    "pain management programme": "Pain Management Program",
    "pain management recommendations": "Pain Management Program",
    "exercise therapy": "Exercise Therapy",
    "exercise intervention program": "Exercise Therapy",
    "exercises": "Exercise Therapy",
    "rehabilitation therapy": "Rehabilitation Therapy",
    "interdisciplinary pain management": "Interdisciplinary Pain Management",
}

CATEGORY_LABELS = {
    "medication": "Medication",
    "supplement": "Supplement",
    "exercise": "Exercise / Movement",
    "therapy": "Therapy / Rehabilitation",
    "other": "Other",
}

CATEGORY_ICONS = {
    "medication": "💊",
    "supplement": "🌿",
    "exercise": "🏃",
    "therapy": "🩺",
    "other": "📋",
}

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _is_noise(name: str) -> bool:
    """Check if a treatment name is noise (non-medical)."""
    lower = name.lower().strip()
    if lower in _NOISE_NAMES:
        return True
    # Strip parenthetical suffixes and re-check
    base = re.sub(r"\s*\(.*\)\s*$", "", lower).strip()
    if base in _NOISE_NAMES:
        return True
    # Also filter out very generic/unspecified entries
    if "unspecified" in lower:
        return True
    return False


def _canonical_name(name: str) -> str:
    """Return the canonical (deduplicated) name for a treatment."""
    lower = name.lower().strip()
    return _CANONICAL_NAMES.get(lower, name)


def _has_info(value: str) -> bool:
    """Check if a field actually contains useful info (not just 'Not specified' etc.)."""
    if not value or not value.strip():
        return False
    lower = value.strip().lower().rstrip(".")
    empty_phrases = (
        "not mentioned", "not specified", "n/a", "none", "none mentioned",
        "not applicable", "unknown", "not available", "no information",
        "not provided", "not stated", "not reported",
    )
    # Exact match
    if lower in empty_phrases:
        return False
    # "Not specified in the source", "Not mentioned in source", etc.
    for phrase in empty_phrases:
        if lower.startswith(phrase) and ("in the source" in lower or "in source" in lower):
            return False
    return True


def _effectiveness_label(score: float) -> str:
    """Convert a 0-1 effectiveness score to a patient-friendly label."""
    if score >= 0.8:
        return "Highly Effective"
    elif score >= 0.6:
        return "Moderately Effective"
    elif score >= 0.4:
        return "Somewhat Effective"
    elif score >= 0.2:
        return "Limited Effectiveness"
    else:
        return "Effectiveness Unknown"


def _support_label(support: str) -> str:
    """Convert evidence support value to patient-friendly text."""
    if support == "true":
        return "Supportive"
    elif support == "false":
        return "Not supportive"
    return "Mixed results"


def _symptom_display(name: str) -> str:
    """Convert symptom DB name to readable display name."""
    return name.replace("_", " ").title()


def _deduplicate_treatments(treatments, evidence_by_treatment, providers_by_treatment):
    """Merge duplicate treatments under canonical names.

    Returns (merged_treatments, merged_evidence, merged_providers) where
    each merged treatment combines the best data from all variants.
    """
    # Group by canonical name
    groups = defaultdict(list)
    for t in treatments:
        if _is_noise(t.name):
            continue
        canon = _canonical_name(t.name)
        groups[canon].append(t)

    merged_treatments = []
    merged_evidence = {}
    merged_providers = {}

    for canon_name, variants in groups.items():
        # Pick the variant with the best (lowest) evidence tier as the primary
        primary = min(variants, key=lambda t: (t.evidence_tier, -len(t.description)))

        # Combine descriptions — use the longest non-empty one
        best_desc = max(
            (v.description for v in variants if v.description),
            key=len, default=""
        )
        best_moa = max(
            (v.mechanism_of_action for v in variants if v.mechanism_of_action),
            key=len, default=""
        )
        best_dosage = max(
            (v.dosage for v in variants if v.dosage),
            key=len, default=""
        )
        best_side_effects = max(
            (v.side_effects for v in variants if v.side_effects),
            key=len, default=""
        )
        best_legality = max(
            (v.legality for v in variants if v.legality),
            key=len, default=""
        )
        best_cost = max(
            (v.cost_estimate for v in variants if v.cost_estimate),
            key=len, default=""
        )

        # Create merged treatment with canonical name
        from eds_researcher.memory.models import Treatment
        merged = Treatment(
            id=primary.id,
            name=canon_name,
            category=primary.category,
            description=best_desc,
            mechanism_of_action=best_moa,
            dosage=best_dosage,
            side_effects=best_side_effects,
            legality=best_legality,
            cost_estimate=best_cost,
            evidence_tier=primary.evidence_tier,
            trending=any(v.trending for v in variants),
            first_seen=min(v.first_seen for v in variants),
            last_updated=max(v.last_updated for v in variants),
        )
        merged_treatments.append(merged)

        # Merge evidence from all variants
        all_ev = []
        for v in variants:
            all_ev.extend(evidence_by_treatment.get(v.id, []))
        merged_evidence[primary.id] = all_ev

        # Merge providers from all variants
        all_prov = []
        seen_prov = set()
        for v in variants:
            for p in providers_by_treatment.get(v.id, []):
                if p.name not in seen_prov:
                    all_prov.append(p)
                    seen_prov.add(p.name)
        merged_providers[primary.id] = all_prov

    # Sort by evidence tier (strongest first), then name
    merged_treatments.sort(key=lambda t: (t.evidence_tier, t.name))
    return merged_treatments, merged_evidence, merged_providers


def generate_full_report(db: Database, output_dir: str | Path) -> Path:
    """Generate a patient-friendly treatment guide report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("full_report.md.j2")

    treatments = db.get_all_treatments()
    symptoms = db.get_all_symptoms()

    # Build symptom -> treatments mapping
    symptom_treatments = {}
    for symptom in symptoms:
        raw_pairs = db.get_treatments_for_symptom(symptom.id)
        # Deduplicate and filter within each symptom
        deduped = {}
        for t, score in raw_pairs:
            if _is_noise(t.name):
                continue
            canon = _canonical_name(t.name)
            if canon not in deduped or score > deduped[canon][1]:
                deduped[canon] = (t, score)
        # Replace treatment names with canonical names
        result = []
        for canon, (t, score) in deduped.items():
            result.append((t, score, canon))
        # Sort: best evidence first, then highest effectiveness
        result.sort(key=lambda x: (x[0].evidence_tier, -x[1]))
        symptom_treatments[symptom.name] = result

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

    # Deduplicate and clean treatments for the detailed profiles section
    clean_treatments, clean_evidence, clean_providers = _deduplicate_treatments(
        treatments, evidence_by_treatment, providers_by_treatment
    )

    # Sort symptoms by severity (high first)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_symptoms = sorted(
        symptoms,
        key=lambda s: (severity_order.get(s.severity_relevance, 9), s.name),
    )

    rendered = template.render(
        generated_date=date.today().isoformat(),
        treatments=clean_treatments,
        symptoms=sorted_symptoms,
        symptom_treatments=symptom_treatments,
        evidence_by_treatment=clean_evidence,
        providers_by_treatment=clean_providers,
        total_evidence=total_evidence,
        total_treatments=len(clean_treatments),
        tier_labels=TIER_LABELS,
        tier_descriptions=TIER_DESCRIPTIONS,
        category_labels=CATEGORY_LABELS,
        category_icons=CATEGORY_ICONS,
        effectiveness_label=_effectiveness_label,
        support_label=_support_label,
        symptom_display=_symptom_display,
        canonical_name=_canonical_name,
        is_noise=_is_noise,
        has_info=_has_info,
    )

    output_path = output_dir / f"full_report_{date.today().isoformat()}.md"
    output_path.write_text(rendered)
    logger.info(f"Full report written to {output_path}")

    # Generate PDF alongside markdown
    from eds_researcher.reporter.pdf_export import markdown_to_pdf
    try:
        markdown_to_pdf(output_path)
    except Exception:
        logger.warning("PDF generation failed — markdown report still available", exc_info=True)

    return output_path
