"""Shared helpers for Time Atlas tools.

Loads and parses Time Atlas protobuf messages from the SQLite database
populated by setup.py.
"""

import os
import sqlite3
import sys
import time
import uuid
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


# Short activity codes (MoveActivity.activity) mapped to display names.
# Shared by the tools so they all speak the same activity vocabulary;
# the codes match the keys in data/activity_colors.json.
ACTIVITY_NAMES = {
    "aeb": "E-Biking",
    "air": "Airplane",
    "boa": "Boat",
    "bsw": "Beach walking",
    "bus": "Bus",
    "car": "Car",
    "cyc": "Cycling",
    "dhs": "Downhill skiing",
    "dsw": "Dog and stroller walk",
    "dwk": "Dog-walking",
    "hke": "Hiking",
    "ice": "Ice skating",
    "mtc": "Motorcycle",
    "pdl": "Paddling",
    "pub": "Public Transport",
    "rbd": "Rollerblading",
    "run": "Running",
    "sct": "Scooting",
    "ski": "Cross-country skiing",
    "slb": "Sailing",
    "sbd": "Snowboarding",
    "sub": "Subway",
    "swk": "Stroller walk",
    "swm": "Swimming",
    "tax": "Taxi",
    "trm": "Tram",
    "trn": "Train",
    "trp": "Transport",
    "tsw": "Twin-stroller walk",
    "wlk": "Walking",
}

# Reverse map: lowercased display name -> short code.
_ACTIVITY_NAME_TO_CODE = {name.lower(): code for code, name in ACTIVITY_NAMES.items()}


def getActivityName(code: str) -> str:
    """Return the display name for a short activity code (code itself if unknown)."""
    return ACTIVITY_NAMES.get(code, code)


def resolveActivityCode(value: str) -> str:
    """Return the short activity code for *value*, a short code or a display name.

    Matching is case-insensitive and falls back to a substring match (so
    "cycling" resolves to "cyc"). Unrecognised values are returned lowercased,
    so filtering still works for codes not listed in ACTIVITY_NAMES.
    """
    low = value.lower()
    if low in ACTIVITY_NAMES:
        return low
    if low in _ACTIVITY_NAME_TO_CODE:
        return _ACTIVITY_NAME_TO_CODE[low]
    for name, code in _ACTIVITY_NAME_TO_CODE.items():
        if low in name or name in low:
            return code
    return low


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


def getMediaForJournalEntry(entry_id: str) -> list[timeatlas_pb2.Media]:
    """Return all Media objects linked to the given journal entry."""
    if not entry_id:
        return []
    with _connect() as conn:
        cur = conn.execute(
            "SELECT media_id FROM journal_entry_media_ids WHERE journal_entry_id = ?",
            (entry_id,),
        )
        media_ids = [row[0] for row in cur.fetchall()]
    if not media_ids:
        return []
    placeholders = ",".join("?" * len(media_ids))
    with _connect() as conn:
        cur = conn.execute(
            f"SELECT data FROM media WHERE id IN ({placeholders})",
            media_ids,
        )
        rows = cur.fetchall()
    out = []
    for (data,) in rows:
        m = timeatlas_pb2.Media()
        m.ParseFromString(data)
        out.append(m)
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


def _to_date_str(value) -> str:
    """Accept a datetime/date or a 'YYYY-mm-dd' string and return 'YYYY-mm-dd'."""
    if isinstance(value, str):
        return value[:10]
    return value.strftime("%Y-%m-%d")


def getBooks(from_dt, to_dt) -> list[timeatlas_pb2.Book]:
    """Return Books whose read_date falls within [from, to].

    Books only carry a read_date ('YYYY-mm-dd' string), so the range is
    compared on calendar dates. Sorted by read_date ascending.
    """
    from_date = _to_date_str(from_dt)
    to_date = _to_date_str(to_dt)
    with _connect() as conn:
        cur = conn.execute(
            "SELECT data FROM books "
            "WHERE read_date IS NOT NULL AND read_date >= ? AND read_date <= ? "
            "ORDER BY read_date ASC, title ASC",
            (from_date, to_date),
        )
        rows = cur.fetchall()
    out = []
    for (data,) in rows:
        b = timeatlas_pb2.Book()
        b.ParseFromString(data)
        out.append(b)
    return out


def getMoviesAndTv(from_dt: datetime, to_dt: datetime) -> list[timeatlas_pb2.MovieAndTv]:
    """Return MovieAndTv entries watched within [from_dt, to_dt].

    Sorted by watched_at ascending.
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT data FROM movies_and_tv "
            "WHERE watched_at IS NOT NULL AND watched_at >= ? AND watched_at <= ? "
            "ORDER BY watched_at ASC",
            (from_dt.timestamp(), to_dt.timestamp()),
        )
        rows = cur.fetchall()
    out = []
    for (data,) in rows:
        m = timeatlas_pb2.MovieAndTv()
        m.ParseFromString(data)
        out.append(m)
    return out


def getLastFmTracks(from_dt: datetime, to_dt: datetime) -> list[timeatlas_pb2.LastFmTrack]:
    """Return Last.fm tracks played within [from_dt, to_dt].

    Sorted by played_at ascending.
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT data FROM lastfm_tracks "
            "WHERE played_at IS NOT NULL AND played_at >= ? AND played_at <= ? "
            "ORDER BY played_at ASC",
            (from_dt.timestamp(), to_dt.timestamp()),
        )
        rows = cur.fetchall()
    out = []
    for (data,) in rows:
        t = timeatlas_pb2.LastFmTrack()
        t.ParseFromString(data)
        out.append(t)
    return out


# ---------------------------------------------------------------------------
# Tally validation (port of data/tallyvalid.go)
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    pass


TallyValidationError = ValidationError


def validateTally(tally: timeatlas_pb2.Tally):
    """Validate a Tally message. Raises TallyValidationError on failure."""
    if not tally.eventID:
        raise TallyValidationError("tally-event-id-empty")

    if not tally.HasField("time") or not tally.time.HasField("UTC_timestamp"):
        raise TallyValidationError("tally-time-invalid")
    ts = tally.time.UTC_timestamp
    if ts.seconds == 0 and ts.nanos == 0:
        raise TallyValidationError("tally-time-invalid")

    if not tally.name:
        raise TallyValidationError("tally-name-empty")
    if tally.name != tally.name.lower():
        raise TallyValidationError("tally-name-not-lower-case")

    if not tally.who:
        raise TallyValidationError("tally-who-empty")

    if not tally.unit and not tally.category:
        raise TallyValidationError("tally-unit-and-category-empty")
    if tally.unit and tally.unit != tally.unit.lower():
        raise TallyValidationError("tally-unit-not-lower-case")

    if tally.value > 16777216:
        raise TallyValidationError("tally-too-large")
    if tally.value < 0:
        raise TallyValidationError("tally-negative")


def validateBook(book: timeatlas_pb2.Book):
    """Validate a Book message. Raises ValidationError on failure."""
    if not book.title:
        raise ValidationError("book-title-empty")
    if book.stars != 0 and not (1 <= book.stars <= 5):
        raise ValidationError("book-stars-out-of-range")


def validateMovieAndTv(movie: timeatlas_pb2.MovieAndTv):
    """Validate a MovieAndTv message. Raises ValidationError on failure."""
    if not movie.title:
        raise ValidationError("movie-title-empty")
    if movie.stars != 0 and not (1 <= movie.stars <= 5):
        raise ValidationError("movie-stars-out-of-range")


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------

def _populate_meta(msg):
    """Set meta.ID, created_at and updated_at on a protobuf message."""
    meta = msg.meta
    meta.ID = str(uuid.uuid4())
    now = time.time()
    secs = int(now)
    nanos = int((now - secs) * 1e9)
    meta.created_at.UTC_timestamp.seconds = secs
    meta.created_at.UTC_timestamp.nanos = nanos
    meta.updated_at.UTC_timestamp.seconds = secs
    meta.updated_at.UTC_timestamp.nanos = nanos


def _write_update_file(directory: timeatlas_pb2.FullDirectory):
    """Serialize a FullDirectory to a timestamped .pb file in iCloud."""
    icloud_dir = getIcloudDir()
    millis = int(time.time() * 1000)
    filename = f"{millis}_update.pb"
    filepath = os.path.join(icloud_dir, filename)
    with open(filepath, "wb") as f:
        f.write(directory.SerializeToString())
    return filepath


def insertTallies(tallies: list[timeatlas_pb2.Tally]) -> str:
    """Validate, assign meta, and write tallies to iCloud as a .pb file.

    Returns the path to the written file.
    """
    for t in tallies:
        _populate_meta(t)
        validateTally(t)

    directory = timeatlas_pb2.FullDirectory()
    directory.tallies.extend(tallies)
    return _write_update_file(directory)


def insertBooks(books: list[timeatlas_pb2.Book]) -> str:
    """Validate, assign meta, and write books to iCloud as a .pb file.

    Returns the path to the written file.
    """
    for b in books:
        _populate_meta(b)
        validateBook(b)

    directory = timeatlas_pb2.FullDirectory()
    directory.books.extend(books)
    return _write_update_file(directory)


def insertMoviesAndTvs(movies: list[timeatlas_pb2.MovieAndTv]) -> str:
    """Validate, assign meta, and write movies/TV entries to iCloud as a .pb file.

    Returns the path to the written file.
    """
    for m in movies:
        _populate_meta(m)
        validateMovieAndTv(m)

    directory = timeatlas_pb2.FullDirectory()
    directory.movies_and_tv.extend(movies)
    return _write_update_file(directory)


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------

# Maps protobuf message type -> FullDirectory field name.
_MSG_TYPE_TO_FIELD = {
    timeatlas_pb2.Event.DESCRIPTOR.full_name: "events",
    timeatlas_pb2.JournalEntry.DESCRIPTOR.full_name: "journal_entries",
    timeatlas_pb2.KnownPlace.DESCRIPTOR.full_name: "known_places",
    timeatlas_pb2.Media.DESCRIPTOR.full_name: "media",
    timeatlas_pb2.PatMessage.DESCRIPTOR.full_name: "pat_messages",
    timeatlas_pb2.Tally.DESCRIPTOR.full_name: "tallies",
    timeatlas_pb2.AIProfile.DESCRIPTOR.full_name: "ai_profiles",
    timeatlas_pb2.Embedding.DESCRIPTOR.full_name: "embeddings",
    timeatlas_pb2.Pattern.DESCRIPTOR.full_name: "patterns",
    timeatlas_pb2.ChatLearning.DESCRIPTOR.full_name: "chat_learnings",
    timeatlas_pb2.Weather.DESCRIPTOR.full_name: "weather",
    timeatlas_pb2.CalendarEvent.DESCRIPTOR.full_name: "calendar_events",
    timeatlas_pb2.SettingsValues.DESCRIPTOR.full_name: "settings_values",
    timeatlas_pb2.PrimaryDevice.DESCRIPTOR.full_name: "primary_devices",
    timeatlas_pb2.LastFmTrack.DESCRIPTOR.full_name: "lastfm_tracks",
    timeatlas_pb2.Book.DESCRIPTOR.full_name: "books",
    timeatlas_pb2.MovieAndTv.DESCRIPTOR.full_name: "movies_and_tv",
}


def updateObjects(objects: list) -> str:
    """Write updated objects to iCloud as a .pb file.

    All objects must have a populated meta.ID. Objects are grouped by type
    and placed into the appropriate FullDirectory field.

    Returns the path to the written file.
    """
    if not objects:
        raise ValueError("No objects to update")

    for obj in objects:
        if not obj.meta.ID:
            raise ValueError(f"Object missing meta.ID: {obj}")

        # Bump updated_at
        now = time.time()
        secs = int(now)
        nanos = int((now - secs) * 1e9)
        obj.meta.updated_at.UTC_timestamp.seconds = secs
        obj.meta.updated_at.UTC_timestamp.nanos = nanos

    directory = timeatlas_pb2.FullDirectory()
    for obj in objects:
        type_name = obj.DESCRIPTOR.full_name
        field = _MSG_TYPE_TO_FIELD.get(type_name)
        if field is None:
            raise ValueError(f"Unknown message type: {type_name}")
        getattr(directory, field).append(obj)

    return _write_update_file(directory)
