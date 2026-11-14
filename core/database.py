"""SQLite case storage with enforced human-review transitions."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from core.models import CATEGORIES, Intake, PRIORITIES, SOURCES, STATUSES, VERDICTS, observation_time, utc_now
from core.risk_rules import assess


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._transaction_connection: sqlite3.Connection | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    official_domain TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL CHECK(priority IN ('Low','Medium','High')),
                    indicators TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    url_analysis TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'New'
                        CHECK(status IN ('New','Reviewing','Validated','False Positive','Escalated')),
                    verdict TEXT NOT NULL DEFAULT 'Pending review',
                    observed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    validated_at TEXT,
                    is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0,1)),
                    demo_key TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    filename TEXT NOT NULL UNIQUE,
                    original_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    description TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
                CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence(case_id);
            """)

    @contextmanager
    def connection(self):
        if self._transaction_connection is not None:
            # The outer transaction owns commit, rollback and closing.
            yield self._transaction_connection
            return
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """Group public operations on this instance into one atomic write.

        Use a separate Database instance per caller, as the application does.
        Nested transactions are deliberately unsupported.
        """
        if self._transaction_connection is not None:
            raise RuntimeError("Nested database transactions are not supported.")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._transaction_connection = conn
            try:
                yield
            finally:
                self._transaction_connection = None

    @staticmethod
    def _case(row) -> dict | None:
        if row is None:
            return None
        result = dict(row)
        result["indicators"] = json.loads(result["indicators"])
        result["url_analysis"] = json.loads(result["url_analysis"])
        return result

    def create_case(self, intake: Intake, *, demo_key: str | None = None,
                    observed_at: str | None = None) -> str:
        observed = observation_time(observed_at) if observed_at is not None else None
        intake = intake.validated()
        assessment = assess(intake)
        now = utc_now()
        case_id = "DRT-" + uuid4().hex
        with self.connection() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            if demo_key:
                existing = conn.execute("SELECT case_id FROM cases WHERE demo_key = ?", (demo_key,)).fetchone()
                if existing:
                    return existing[0]
            conn.execute("""
                INSERT INTO cases (case_id,source_type,source_url,brand,official_domain,
                title,description,notes,category,priority,indicators,explanation,url_analysis,
                observed_at,created_at,updated_at,is_demo,demo_key)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (case_id, intake.source_type, intake.url, intake.brand, intake.official_domain,
                  intake.title, intake.description, intake.notes, assessment.category,
                  assessment.priority, json.dumps(assessment.indicators), assessment.explanation,
                  json.dumps(assessment.as_dict()["url_analysis"]), observed or now, now, now,
                  int(demo_key is not None), demo_key))
        return case_id

    def get_case(self, case_id: str) -> dict | None:
        with self.connection() as conn:
            return self._case(conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone())

    def list_cases(self, *, status: str | None = None, priority: str | None = None,
                   category: str | None = None, source_type: str | None = None) -> list[dict]:
        clauses, values = [], []
        for name, value, choices in (("status", status, STATUSES), ("priority", priority, PRIORITIES),
                                     ("category", category, CATEGORIES), ("source_type", source_type, SOURCES)):
            if value is not None:
                if value not in choices:
                    raise ValueError(f"Invalid {name} filter.")
                clauses.append(f"{name} = ?")
                values.append(value)
        query = "SELECT * FROM cases" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        with self.connection() as conn:
            return [self._case(row) for row in conn.execute(query + " ORDER BY created_at DESC, case_id", values)]

    def update_review(self, case_id: str, *, notes: str, status: str, verdict: str):
        if status not in STATUSES or verdict not in VERDICTS:
            raise ValueError("Choose a supported status and verdict.")
        notes = notes.strip()
        if len(notes) > 20000:
            raise ValueError("Notes exceed the 20,000-character limit.")
        if status in ("Validated", "Escalated") and (verdict != "Confirmed violation" or not notes):
            raise ValueError("Validation and escalation require a human 'Confirmed violation' verdict and supporting notes.")
        if status == "False Positive" and (verdict != "No violation found" or not notes):
            raise ValueError("False Positive requires a 'No violation found' verdict and supporting notes.")
        if status in ("New", "Reviewing") and verdict == "Confirmed violation":
            raise ValueError("Use Validated when recording a confirmed violation.")
        if status == "New" and verdict != "Pending review":
            raise ValueError("New cases require a 'Pending review' verdict.")
        if verdict == "No violation found" and not notes:
            raise ValueError("A 'No violation found' verdict requires supporting notes.")
        with self.connection() as conn:
            # Acquire the write lock before reading transition state.
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            if case is None:
                raise ValueError("Case not found.")
            if status == "Escalated" and (case["status"] not in ("Validated", "Escalated") or not case["validated_at"]):
                raise ValueError("Save this case as Validated before escalating it.")
            now = utc_now()
            validated_at = (case["validated_at"] or now) if status in ("Validated", "Escalated") else None
            conn.execute("UPDATE cases SET notes=?,status=?,verdict=?,updated_at=?,validated_at=? WHERE case_id=?",
                         (notes, status, verdict, now, validated_at, case_id))

    def list_evidence(self, case_id: str) -> list[dict]:
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM evidence WHERE case_id=? ORDER BY uploaded_at", (case_id,))]

    def add_evidence_metadata(self, metadata: dict):
        fields = ("evidence_id", "case_id", "filename", "original_name", "mime_type", "size_bytes",
                  "sha256", "source_url", "observed_at", "uploaded_at", "description")
        with self.connection() as conn:
            conn.execute(f"INSERT INTO evidence ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                         tuple(metadata[key] for key in fields))
