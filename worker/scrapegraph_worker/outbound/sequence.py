"""Tracks which step of a generated follow-up sequence (see
`OutboundMessageSet.follow_up_sequence`) is next due for a given person.

Same "minimal SQLite-backed store, one job, no ORM" shape as
`progress.py::JobStore` -- this table has one job too: given a person and
their drafted sequence, know which relative-day step is due today, and
record that it fired so it isn't sent twice.

Scheduling here is intentionally decoupled from *sending*: `schedule()`
just registers the sequence's absolute due dates; `outbound_scheduler_
main.py`'s daily sweep is what actually calls a send adapter for whatever
comes back from `due_steps()`.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from .models import OutboundMessageSet, SequenceStep

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbound_sequences (
    person_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    started_on TEXT NOT NULL,
    steps TEXT NOT NULL,        -- JSON array of SequenceStep
    sent_step_numbers TEXT NOT NULL DEFAULT '[]',
    recipient_email TEXT,
    updated_at TEXT NOT NULL
);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SequenceStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        parent = Path(db_path).parent
        if str(parent) != ".":
            parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def schedule(
        self,
        *,
        person_id: str,
        company_id: str,
        steps: list[SequenceStep],
        recipient_email: Optional[str] = None,
        start_date: Optional[date] = None,
    ) -> None:
        """Registers a sequence for a person. Re-scheduling (e.g. a
        re-drafted outreach set) replaces the prior schedule entirely --
        this is idempotent by person_id, not append-only, since only one
        active sequence per person makes sense at a time.
        """
        started_on = (start_date or datetime.now(timezone.utc).date()).isoformat()
        payload = json.dumps([s.model_dump(mode="json") for s in steps])
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO outbound_sequences "
                "(person_id, company_id, started_on, steps, sent_step_numbers, recipient_email, updated_at) "
                "VALUES (?, ?, ?, ?, '[]', ?, ?) "
                "ON CONFLICT(person_id) DO UPDATE SET "
                "company_id=excluded.company_id, started_on=excluded.started_on, steps=excluded.steps, "
                "sent_step_numbers='[]', recipient_email=excluded.recipient_email, updated_at=excluded.updated_at",
                (person_id, company_id, started_on, payload, recipient_email, _utcnow_iso()),
            )

    def schedule_from_message_set(self, message_set: OutboundMessageSet, *, recipient_email: Optional[str] = None) -> None:
        if not message_set.person_id or not message_set.follow_up_sequence:
            return
        self.schedule(
            person_id=message_set.person_id,
            company_id=message_set.company_id,
            steps=message_set.follow_up_sequence,
            recipient_email=recipient_email,
        )

    def due_steps(self, *, as_of: Optional[date] = None, limit: int = 200) -> list[dict]:
        """Every step, across every scheduled person, whose due date has
        arrived and hasn't been marked sent yet. Returns plain dicts (not
        SequenceStep) alongside the person/company/recipient context a
        sender needs, since that context lives in this table, not on the
        step itself.
        """
        today = as_of or datetime.now(timezone.utc).date()
        due: list[dict] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT person_id, company_id, started_on, steps, sent_step_numbers, recipient_email FROM outbound_sequences").fetchall()

        for person_id, company_id, started_on, steps_json, sent_json, recipient_email in rows:
            start = date.fromisoformat(started_on)
            sent = set(json.loads(sent_json))
            for raw_step in json.loads(steps_json):
                step = SequenceStep(**raw_step)
                if step.step_number in sent:
                    continue
                due_date = start + timedelta(days=step.day_offset)
                if due_date <= today:
                    due.append(
                        {
                            "person_id": person_id,
                            "company_id": company_id,
                            "recipient_email": recipient_email,
                            "step": step,
                            "due_date": due_date.isoformat(),
                        }
                    )
                if len(due) >= limit:
                    return due
        return due

    def mark_step_sent(self, *, person_id: str, step_number: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sent_step_numbers FROM outbound_sequences WHERE person_id = ?", (person_id,)
            ).fetchone()
            if row is None:
                return
            sent = set(json.loads(row[0]))
            sent.add(step_number)
            conn.execute(
                "UPDATE outbound_sequences SET sent_step_numbers = ?, updated_at = ? WHERE person_id = ?",
                (json.dumps(sorted(sent)), _utcnow_iso(), person_id),
            )
