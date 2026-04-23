"""Shared helpers for Time Atlas tools.

Loads and parses Time Atlas protobuf messages from the SQLite database
populated by setup.py.
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import timeatlas_pb2


_DB_FILENAME = "timeatlas.db"


def getIcloudDir() -> str:
    """Return the Time Atlas iCloud directory path for the current platform."""
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE", "")
        return os.path.join(
            base, "iCloudDrive", "iCloud~com~timeatlaslabs~Pat", "Documents"
        )
    return os.path.expanduser(
        "~/Library/Mobile Documents/iCloud~com~timeatlaslabs~Pat/Documents"
    )

# Maps the short "type" names used in getEvents() to table names in the DB.
_EVENT_TYPE_TABLES = {
    "date": "events_dates",
    "placevisit": "events_place_visits",
    "movement": "events_movements",
    "nodataperiod": "events_no_data_periods",
    "no_data_period": "events_no_data_periods",
    "workout": "events_workouts",
    "sleep": "events_sleeps",
    "eventgroup": "events_event_groups",
    "event_group": "events_event_groups",
    "trip": "events_trips",
}


def getDatabasePath() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _DB_FILENAME)


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(getDatabasePath())


def _tso_to_datetime(tso) -> datetime | None:
    """TimestampWithOffset -> timezone-aware datetime using UTC_offset_seconds."""
    if not tso.HasField("UTC_timestamp"):
        return None
    ts = tso.UTC_timestamp
    if ts.seconds == 0 and ts.nanos == 0:
        return None
    offset_secs = tso.UTC_offset_seconds if tso.HasField("UTC_offset_seconds") else 0
    tz = timezone(timedelta(seconds=offset_secs))
    return datetime.fromtimestamp(ts.seconds + ts.nanos / 1e9, tz=tz)


def _parse_event(data: bytes) -> timeatlas_pb2.Event:
    evt = timeatlas_pb2.Event()
    evt.ParseFromString(data)
    return evt


def getDateDateRange(date: str) -> tuple[datetime, datetime] | None:
    """Return (start_dt, end_dt) for the date event with the given YYYY-mm-dd date.

    Datetimes carry the timezone from the event's UTC_offset_seconds so they
    represent local wall-clock time.
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT data FROM events_dates WHERE date = ? LIMIT 1", (date,)
        )
        row = cur.fetchone()
    if not row:
        return None
    evt = _parse_event(row[0])
    start = _tso_to_datetime(evt.start_at) if evt.HasField("start_at") else None
    end = _tso_to_datetime(evt.end_at) if evt.HasField("end_at") else None
    return (start, end)


def getDates(from_date: str, to_date: str) -> list[tuple[str, datetime, datetime]]:
    """Return list of (date-string, start-dt, end-dt) for dates in [from, to]."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT date, data FROM events_dates "
            "WHERE date >= ? AND date <= ? "
            "ORDER BY date ASC",
            (from_date, to_date),
        )
        rows = cur.fetchall()

    out = []
    for date_str, data in rows:
        evt = _parse_event(data)
        start = _tso_to_datetime(evt.start_at) if evt.HasField("start_at") else None
        end = _tso_to_datetime(evt.end_at) if evt.HasField("end_at") else None
        out.append((date_str, start, end))
    return out


def getEvents(
    type: str, from_dt: datetime, to_dt: datetime
) -> list[timeatlas_pb2.Event]:
    """Return Events of the given type whose [start_at, end_at] overlaps [from, to].

    Sorted by start_at ascending.
    """
    table = _EVENT_TYPE_TABLES.get(type.lower())
    if table is None:
        raise ValueError(
            f"Unknown event type: {type!r}. "
            f"Known: {sorted(set(_EVENT_TYPE_TABLES))}"
        )
    from_ts = from_dt.timestamp()
    to_ts = to_dt.timestamp()
    with _connect() as conn:
        cur = conn.execute(
            f"SELECT data FROM {table} "
            f"WHERE start_at <= ? AND (end_at IS NULL OR end_at >= ?) "
            f"ORDER BY start_at ASC",
            (to_ts, from_ts),
        )
        rows = cur.fetchall()
    return [_parse_event(data) for (data,) in rows]


def getDateEvent(date: str) -> timeatlas_pb2.Event | None:
    """Return the full Event message for the given YYYY-mm-dd date, or None."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT data FROM events_dates WHERE date = ? LIMIT 1", (date,)
        )
        row = cur.fetchone()
    if not row:
        return None
    return _parse_event(row[0])


def getJournalEntriesForEvent(event_id: str) -> list[timeatlas_pb2.JournalEntry]:
    """Return all JournalEntry messages whose eventID matches."""
    if not event_id:
        return []
    with _connect() as conn:
        cur = conn.execute(
            "SELECT data FROM journal_entries WHERE event_id = ? "
            "ORDER BY meta_created_at ASC",
            (event_id,),
        )
        rows = cur.fetchall()
    out = []
    for (data,) in rows:
        je = timeatlas_pb2.JournalEntry()
        je.ParseFromString(data)
        out.append(je)
    return out


def getKnownPlace(
    id: str | None = None, name: str | None = None
):
    """Look up known places.

    - If `id` is given: returns the single KnownPlace message, or None.
    - If `name` is given: returns a list of KnownPlace messages with that name.
    """
    if (id is None) == (name is None):
        raise ValueError("Provide exactly one of `id` or `name`.")

    with _connect() as conn:
        if id is not None:
            cur = conn.execute(
                "SELECT data FROM known_places WHERE id = ? LIMIT 1", (id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            kp = timeatlas_pb2.KnownPlace()
            kp.ParseFromString(row[0])
            return kp
        else:
            cur = conn.execute(
                "SELECT data FROM known_places WHERE name = ?", (name,)
            )
            out = []
            for (data,) in cur.fetchall():
                kp = timeatlas_pb2.KnownPlace()
                kp.ParseFromString(data)
                out.append(kp)
            return out
