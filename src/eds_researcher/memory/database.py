"""SQLite database operations for the EDS Researcher memory layer."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import (
    Evidence,
    EvidenceSupport,
    EvidenceTier,
    LeadStatus,
    Provider,
    SearchHistory,
    SearchLead,
    Symptom,
    Treatment,
    TreatmentCategory,
    TreatmentSymptom,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS treatments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT DEFAULT '',
    mechanism_of_action TEXT DEFAULT '',
    dosage TEXT DEFAULT '',
    side_effects TEXT DEFAULT '',
    legality TEXT DEFAULT '',
    cost_estimate TEXT DEFAULT '',
    evidence_tier INTEGER DEFAULT 6,
    trending INTEGER DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS symptoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    body_region TEXT NOT NULL,
    severity_relevance TEXT DEFAULT 'medium'
);

CREATE TABLE IF NOT EXISTS treatment_symptoms (
    treatment_id INTEGER NOT NULL,
    symptom_id INTEGER NOT NULL,
    effectiveness_score REAL DEFAULT 0.0,
    PRIMARY KEY (treatment_id, symptom_id),
    FOREIGN KEY (treatment_id) REFERENCES treatments(id),
    FOREIGN KEY (symptom_id) REFERENCES symptoms(id)
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    treatment_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_date TEXT,
    retrieval_date TEXT NOT NULL,
    evidence_tier INTEGER NOT NULL,
    summary TEXT NOT NULL,
    raw_snippet TEXT DEFAULT '',
    supports_treatment TEXT DEFAULT 'true',
    FOREIGN KEY (treatment_id) REFERENCES treatments(id)
);

CREATE TABLE IF NOT EXISTS providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    credentials TEXT DEFAULT '',
    specialty TEXT DEFAULT '',
    location TEXT DEFAULT '',
    contact_info TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS provider_treatments (
    provider_id INTEGER NOT NULL,
    treatment_id INTEGER NOT NULL,
    PRIMARY KEY (provider_id, treatment_id),
    FOREIGN KEY (provider_id) REFERENCES providers(id),
    FOREIGN KEY (treatment_id) REFERENCES treatments(id)
);

CREATE TABLE IF NOT EXISTS search_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    source_target TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    origin TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    created_date TEXT NOT NULL,
    last_searched TEXT
);

CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    source TEXT NOT NULL,
    date_run TEXT NOT NULL,
    results_count INTEGER DEFAULT 0,
    useful_results_count INTEGER DEFAULT 0
);
"""


def _date_to_str(d: date | None) -> str | None:
    if d is None:
        return None
    return d.isoformat()


def _str_to_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def _str_to_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


class Database:
    """SQLite database for storing treatments, evidence, and search state."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns that may be missing from older databases."""
        cursor = self.conn.execute("PRAGMA table_info(treatments)")
        existing = {row["name"] for row in cursor.fetchall()}
        for col in ("dosage", "side_effects"):
            if col not in existing:
                self.conn.execute(f"ALTER TABLE treatments ADD COLUMN {col} TEXT DEFAULT ''")


    def close(self) -> None:
        self.conn.close()

    # ── Treatments ──────────────────────────────────────────

    def upsert_treatment(self, t: Treatment) -> int:
        """Insert or update a treatment. Returns the treatment id."""
        existing = self.conn.execute(
            "SELECT id FROM treatments WHERE name = ?", (t.name,)
        ).fetchone()
        if existing:
            self.conn.execute(
                """UPDATE treatments SET category=?, description=?, mechanism_of_action=?,
                   dosage=?, side_effects=?, legality=?, cost_estimate=?,
                   evidence_tier=?, trending=?, last_updated=?
                   WHERE id=?""",
                (
                    t.category, t.description, t.mechanism_of_action,
                    t.dosage, t.side_effects,
                    t.legality, t.cost_estimate, int(t.evidence_tier),
                    int(t.trending), _date_to_str(t.last_updated),
                    existing["id"],
                ),
            )
            self.conn.commit()
            return existing["id"]
        cursor = self.conn.execute(
            """INSERT INTO treatments (name, category, description, mechanism_of_action,
               dosage, side_effects, legality, cost_estimate, evidence_tier, trending,
               first_seen, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t.name, t.category, t.description, t.mechanism_of_action,
                t.dosage, t.side_effects,
                t.legality, t.cost_estimate, int(t.evidence_tier),
                int(t.trending), _date_to_str(t.first_seen),
                _date_to_str(t.last_updated),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_treatment(self, treatment_id: int) -> Treatment | None:
        row = self.conn.execute(
            "SELECT * FROM treatments WHERE id = ?", (treatment_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_treatment(row)

    def get_treatment_by_name(self, name: str) -> Treatment | None:
        row = self.conn.execute(
            "SELECT * FROM treatments WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_treatment(row)

    def get_all_treatments(self) -> list[Treatment]:
        rows = self.conn.execute(
            "SELECT * FROM treatments ORDER BY evidence_tier, name"
        ).fetchall()
        return [self._row_to_treatment(r) for r in rows]

    def get_treatments_for_symptom(self, symptom_id: int) -> list[tuple[Treatment, float]]:
        """Returns (treatment, effectiveness_score) pairs for a symptom."""
        rows = self.conn.execute(
            """SELECT t.*, ts.effectiveness_score FROM treatments t
               JOIN treatment_symptoms ts ON t.id = ts.treatment_id
               WHERE ts.symptom_id = ?
               ORDER BY t.evidence_tier, ts.effectiveness_score DESC""",
            (symptom_id,),
        ).fetchall()
        return [(self._row_to_treatment(r), r["effectiveness_score"]) for r in rows]

    def get_treatments_since(self, since: date) -> list[Treatment]:
        """Get treatments first seen or updated since a given date."""
        rows = self.conn.execute(
            """SELECT * FROM treatments
               WHERE first_seen >= ? OR last_updated >= ?
               ORDER BY evidence_tier, name""",
            (_date_to_str(since), _date_to_str(since)),
        ).fetchall()
        return [self._row_to_treatment(r) for r in rows]

    def _row_to_treatment(self, row: sqlite3.Row) -> Treatment:
        return Treatment(
            id=row["id"],
            name=row["name"],
            category=TreatmentCategory(row["category"]),
            description=row["description"],
            mechanism_of_action=row["mechanism_of_action"],
            dosage=row["dosage"] or "",
            side_effects=row["side_effects"] or "",
            legality=row["legality"],
            cost_estimate=row["cost_estimate"],
            evidence_tier=EvidenceTier(row["evidence_tier"]),
            trending=bool(row["trending"]),
            first_seen=_str_to_date(row["first_seen"]),
            last_updated=_str_to_date(row["last_updated"]),
        )

    # ── Symptoms ────────────────────────────────────────────

    def upsert_symptom(self, s: Symptom) -> int:
        existing = self.conn.execute(
            "SELECT id FROM symptoms WHERE name = ?", (s.name,)
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE symptoms SET body_region=?, severity_relevance=? WHERE id=?",
                (s.body_region, s.severity_relevance, existing["id"]),
            )
            self.conn.commit()
            return existing["id"]
        cursor = self.conn.execute(
            "INSERT INTO symptoms (name, body_region, severity_relevance) VALUES (?, ?, ?)",
            (s.name, s.body_region, s.severity_relevance),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_all_symptoms(self) -> list[Symptom]:
        rows = self.conn.execute("SELECT * FROM symptoms ORDER BY name").fetchall()
        return [self._row_to_symptom(r) for r in rows]

    def get_symptom_by_name(self, name: str) -> Symptom | None:
        row = self.conn.execute(
            "SELECT * FROM symptoms WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_symptom(row)

    def _row_to_symptom(self, row: sqlite3.Row) -> Symptom:
        return Symptom(
            id=row["id"],
            name=row["name"],
            body_region=row["body_region"],
            severity_relevance=row["severity_relevance"],
        )

    # ── Treatment-Symptom Links ─────────────────────────────

    def link_treatment_symptom(self, ts: TreatmentSymptom) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO treatment_symptoms
               (treatment_id, symptom_id, effectiveness_score)
               VALUES (?, ?, ?)""",
            (ts.treatment_id, ts.symptom_id, ts.effectiveness_score),
        )
        self.conn.commit()

    # ── Evidence ────────────────────────────────────────────

    def add_evidence(self, e: Evidence) -> int:
        cursor = self.conn.execute(
            """INSERT INTO evidence (treatment_id, source_type, source_url, source_date,
               retrieval_date, evidence_tier, summary, raw_snippet, supports_treatment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.treatment_id, e.source_type, e.source_url,
                _date_to_str(e.source_date), _date_to_str(e.retrieval_date),
                int(e.evidence_tier), e.summary, e.raw_snippet,
                e.supports_treatment,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_evidence_for_treatment(self, treatment_id: int) -> list[Evidence]:
        rows = self.conn.execute(
            "SELECT * FROM evidence WHERE treatment_id = ? ORDER BY evidence_tier, retrieval_date DESC",
            (treatment_id,),
        ).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def get_evidence_since(self, since: date) -> list[Evidence]:
        rows = self.conn.execute(
            "SELECT * FROM evidence WHERE retrieval_date >= ? ORDER BY evidence_tier",
            (_date_to_str(since),),
        ).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def _row_to_evidence(self, row: sqlite3.Row) -> Evidence:
        return Evidence(
            id=row["id"],
            treatment_id=row["treatment_id"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            source_date=_str_to_date(row["source_date"]),
            retrieval_date=_str_to_date(row["retrieval_date"]),
            evidence_tier=EvidenceTier(row["evidence_tier"]),
            summary=row["summary"],
            raw_snippet=row["raw_snippet"],
            supports_treatment=EvidenceSupport(row["supports_treatment"]),
        )

    # ── Providers ───────────────────────────────────────────

    def upsert_provider(self, p: Provider) -> int:
        existing = self.conn.execute(
            "SELECT id FROM providers WHERE name = ? AND specialty = ?",
            (p.name, p.specialty),
        ).fetchone()
        if existing:
            self.conn.execute(
                """UPDATE providers SET credentials=?, location=?, contact_info=?,
                   source_url=?, notes=? WHERE id=?""",
                (p.credentials, p.location, p.contact_info, p.source_url, p.notes, existing["id"]),
            )
            self.conn.commit()
            return existing["id"]
        cursor = self.conn.execute(
            """INSERT INTO providers (name, credentials, specialty, location,
               contact_info, source_url, notes) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (p.name, p.credentials, p.specialty, p.location, p.contact_info, p.source_url, p.notes),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_all_providers(self) -> list[Provider]:
        rows = self.conn.execute("SELECT * FROM providers ORDER BY name").fetchall()
        return [self._row_to_provider(r) for r in rows]

    def link_provider_treatment(self, provider_id: int, treatment_id: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO provider_treatments (provider_id, treatment_id) VALUES (?, ?)",
            (provider_id, treatment_id),
        )
        self.conn.commit()

    def get_providers_for_treatment(self, treatment_id: int) -> list[Provider]:
        rows = self.conn.execute(
            """SELECT p.* FROM providers p
               JOIN provider_treatments pt ON p.id = pt.provider_id
               WHERE pt.treatment_id = ?""",
            (treatment_id,),
        ).fetchall()
        return [self._row_to_provider(r) for r in rows]

    def _row_to_provider(self, row: sqlite3.Row) -> Provider:
        return Provider(
            id=row["id"],
            name=row["name"],
            credentials=row["credentials"],
            specialty=row["specialty"],
            location=row["location"],
            contact_info=row["contact_info"],
            source_url=row["source_url"],
            notes=row["notes"],
        )

    # ── Search Leads ────────────────────────────────────────

    def add_lead(self, lead: SearchLead) -> int:
        cursor = self.conn.execute(
            """INSERT INTO search_leads (query_text, source_target, priority, origin,
               status, created_date, last_searched) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                lead.query_text, lead.source_target, lead.priority,
                lead.origin, lead.status,
                _date_to_str(lead.created_date), _date_to_str(lead.last_searched),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_pending_leads(self, limit: int = 20) -> list[SearchLead]:
        rows = self.conn.execute(
            "SELECT * FROM search_leads WHERE status = 'pending' ORDER BY priority, created_date LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_lead(r) for r in rows]

    def update_lead_status(self, lead_id: int, status: LeadStatus) -> None:
        self.conn.execute(
            "UPDATE search_leads SET status=?, last_searched=? WHERE id=?",
            (status, _date_to_str(date.today()), lead_id),
        )
        self.conn.commit()

    def _row_to_lead(self, row: sqlite3.Row) -> SearchLead:
        return SearchLead(
            id=row["id"],
            query_text=row["query_text"],
            source_target=row["source_target"],
            priority=row["priority"],
            origin=row["origin"],
            status=LeadStatus(row["status"]),
            created_date=_str_to_date(row["created_date"]),
            last_searched=_str_to_date(row["last_searched"]),
        )

    # ── Search History ──────────────────────────────────────

    def add_search_history(self, sh: SearchHistory) -> int:
        cursor = self.conn.execute(
            """INSERT INTO search_history (query_text, source, date_run,
               results_count, useful_results_count) VALUES (?, ?, ?, ?, ?)""",
            (sh.query_text, sh.source, sh.date_run.isoformat(), sh.results_count, sh.useful_results_count),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_recent_searches(self, source: str | None = None, limit: int = 50) -> list[SearchHistory]:
        if source:
            rows = self.conn.execute(
                "SELECT * FROM search_history WHERE source = ? ORDER BY date_run DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM search_history ORDER BY date_run DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_search_history(r) for r in rows]

    def _row_to_search_history(self, row: sqlite3.Row) -> SearchHistory:
        return SearchHistory(
            id=row["id"],
            query_text=row["query_text"],
            source=row["source"],
            date_run=_str_to_datetime(row["date_run"]),
            results_count=row["results_count"],
            useful_results_count=row["useful_results_count"],
        )
