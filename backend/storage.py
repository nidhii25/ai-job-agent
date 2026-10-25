"""SQLite, profile, and JSON export storage helpers."""

import json
import logging
import os
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "database.db"))
PROFILE_PATH = os.getenv("PROFILE_PATH", os.path.join(BASE_DIR, "profile.json"))
_EXPORT_ENV = os.getenv("APPLICATIONS_EXPORT_PATH", "applications.json")
EXPORT_PATH = (
    _EXPORT_ENV
    if os.path.isabs(_EXPORT_ENV)
    else os.path.join(BASE_DIR, _EXPORT_ENV)
)
_EXPORT_LOCK = threading.Lock()
logger = logging.getLogger("jobagent.storage")

DEFAULT_PROFILE = {
    "personal": {
        "full_name": "",
        "first_name": "",
        "last_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "country": "",
        "linkedin_url": "",
        "github_url": "",
        "website_url": "",
    },
    "education": [],
    "experience": [],
    "skills": [],
    "projects": [],
    "resume_path": "",
    "cover_letter": "",
    "cover_letter_path": "",
    "work_authorization": "",
    "saved_answers": {},
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_url TEXT NOT NULL,
            company TEXT,
            role TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            submitted_at TEXT,
            last_error TEXT,
            confirmation_details TEXT
        )
        """
    )

    # Older local databases predate submission outcome tracking. Add the
    # columns in place so existing application history is preserved.
    application_columns = {
        row["name"] for row in cursor.execute("PRAGMA table_info(applications)")
    }
    if "submission_attempted_at" not in application_columns:
        cursor.execute("ALTER TABLE applications ADD COLUMN submission_attempted_at TEXT")
    if "submission_outcome" not in application_columns:
        cursor.execute("ALTER TABLE applications ADD COLUMN submission_outcome TEXT")
    if "auto_submit" not in application_columns:
        cursor.execute("ALTER TABLE applications ADD COLUMN auto_submit INTEGER")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS review_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            reason TEXT,
            suggested_value TEXT,
            user_resolution TEXT,
            resolved_at TEXT,
            FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()
    conn.close()


def build_applications_export(conn=None):
    """Build the portable JSON export from the authoritative SQLite state."""
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, job_url, company, role, status, created_at, updated_at,
                   submitted_at, last_error, confirmation_details,
                   submission_attempted_at, submission_outcome
            FROM applications
            ORDER BY id ASC
            """
        )
        applications = []
        for row in cursor.fetchall():
            application = dict(row)
            cursor.execute(
                """
                SELECT id, field_name, reason, suggested_value, user_resolution,
                       resolved_at
                FROM review_items
                WHERE application_id = ?
                ORDER BY id ASC
                """,
                (application["id"],),
            )
            application["review_items"] = [dict(item) for item in cursor.fetchall()]
            cursor.execute(
                """
                SELECT id, event_type, message, created_at
                FROM application_events
                WHERE application_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (application["id"],),
            )
            application["events"] = [dict(event) for event in cursor.fetchall()]
            applications.append(application)

        return {
            "exported_at": utc_now(),
            "application_count": len(applications),
            "applications": applications,
        }
    finally:
        if owns_connection:
            conn.close()


def write_applications_export(conn=None):
    """Atomically write applications.json, using SQLite as the source of truth."""
    export_dir = os.path.dirname(EXPORT_PATH) or BASE_DIR
    os.makedirs(export_dir, exist_ok=True)

    with _EXPORT_LOCK:
        # Build inside the lock so a later writer cannot publish an older
        # snapshot after a newer one.
        payload = build_applications_export(conn)
        handle = None
        temp_path = None
        try:
            handle, temp_path = tempfile.mkstemp(
                prefix=".applications-",
                suffix=".tmp",
                dir=export_dir,
                text=True,
            )
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                handle = None
                json.dump(payload, output, indent=2, ensure_ascii=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_path, EXPORT_PATH)
            temp_path = None
        finally:
            if handle is not None:
                os.close(handle)
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    return EXPORT_PATH


def refresh_applications_export(conn=None):
    """Best-effort export refresh; automation must not fail because of disk I/O."""
    try:
        return write_applications_export(conn)
    except Exception as exc:
        logger.warning("Could not refresh applications JSON export: %s", exc)
        return None


def add_event(cursor, application_id, event_type, message):
    cursor.execute(
        """
        INSERT INTO application_events (application_id, event_type, message, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (application_id, event_type, message, utc_now()),
    )


def record_event(conn, application_id, event_type, message):
    """Insert an event and commit immediately so the UI can poll it live."""
    cursor = conn.cursor()
    add_event(cursor, application_id, event_type, message)
    cursor.execute(
        "UPDATE applications SET updated_at = ? WHERE id = ?",
        (utc_now(), application_id),
    )
    conn.commit()
    logger.info(
        "application=%s event=%s message=%s",
        application_id,
        event_type,
        (message or "").replace("\n", " ")[:1000],
    )
    refresh_applications_export(conn)


def update_application(conn, application_id, **fields):
    if not fields:
        return
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = list(fields.values()) + [application_id]
    conn.execute(
        f"UPDATE applications SET {assignments} WHERE id = ?",
        values,
    )
    conn.commit()
    logger.info(
        "application=%s updated_fields=%s",
        application_id,
        ",".join(sorted(fields)),
    )
    refresh_applications_export(conn)


def create_review_item(
    conn, application_id, field_name, reason, suggested_value=None
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO review_items
            (application_id, field_name, reason, suggested_value, user_resolution, resolved_at)
        VALUES (?, ?, ?, ?, NULL, NULL)
        """,
        (application_id, field_name, reason, suggested_value),
    )
    conn.commit()
    logger.info(
        "application=%s review_item_created field=%s",
        application_id,
        (field_name or "")[:300],
    )
    refresh_applications_export(conn)


def resolve_review_item(conn, application_id, item_id, resolution):
    """Store a user's answer for a review item and log the change."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, field_name, resolved_at FROM review_items
        WHERE id = ? AND application_id = ?
        """,
        (item_id, application_id),
    )
    item = cursor.fetchone()
    if not item:
        return None

    now = utc_now()
    cursor.execute(
        """
        UPDATE review_items
        SET user_resolution = ?, resolved_at = ?
        WHERE id = ? AND application_id = ?
        """,
        (resolution, now, item_id, application_id),
    )
    cursor.execute(
        "UPDATE applications SET updated_at = ? WHERE id = ?",
        (now, application_id),
    )
    add_event(
        cursor,
        application_id,
        "review_item_resolved",
        f"Resolved review item: {item['field_name']}",
    )
    conn.commit()
    logger.info(
        "application=%s review_item_resolved item=%s field=%s",
        application_id,
        item_id,
        (item["field_name"] or "")[:300],
    )
    refresh_applications_export(conn)
    return {
        "id": item_id,
        "field_name": item["field_name"],
        "user_resolution": resolution,
        "resolved_at": now,
    }


def load_resolved_answers(conn, application_id):
    """Return review answers keyed by field/question label for a rerun."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT field_name, user_resolution FROM review_items
        WHERE application_id = ?
          AND resolved_at IS NOT NULL
          AND user_resolution IS NOT NULL
          AND TRIM(user_resolution) <> ''
        ORDER BY id ASC
        """,
        (application_id,),
    )
    answers = {}
    for row in cursor.fetchall():
        answers[row["field_name"]] = row["user_resolution"]
    return answers


def load_profile():
    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
        except (OSError, json.JSONDecodeError):
            stored = {}
    else:
        stored = {}

    # Merge defaults so older profile files keep working after new fields are added.
    profile = json.loads(json.dumps(DEFAULT_PROFILE))
    profile.update(stored)
    profile["personal"] = {**DEFAULT_PROFILE["personal"], **stored.get("personal", {})}
    return profile


def save_profile(profile):
    with open(PROFILE_PATH, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2)
