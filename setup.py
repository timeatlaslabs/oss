#!/usr/bin/env python3
"""
Time Atlas database setup and sync script.

Creates an SQLite database from Time Atlas iCloud protobuf files.
"""

import os
import sqlite3
import zipfile
import io
import glob

import timeatlas_pb2

ICLOUD_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~com~timeatlaslabs~Pat/Documents"
)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timeatlas.db")

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Each entry: (table_name, field_name_in_FullDirectory, extra_timestamp_columns)
# Every table gets: id TEXT PK, data BLOB, meta_created_at REAL, meta_updated_at REAL
TABLE_DEFS = [
    ("events", "events", ["start_at", "end_at"]),
    ("journal_entries", "journal_entries", []),
    ("known_places", "known_places", []),
    ("media", "media", ["created_timestamp", "modified_timestamp"]),
    ("pat_messages", "pat_messages", []),
    ("tallies", "tallies", ["time"]),
    ("ai_profiles", "ai_profiles", []),
    ("embeddings", "embeddings", []),
    ("patterns", "patterns", []),
    ("chat_learnings", "chat_learnings", []),
    ("weather", "weather", ["observed_at"]),
    ("calendar_events", "calendar_events", ["start_at", "end_at", "created_at", "last_modified_at"]),
    ("settings_values", "settings_values", ["asked_for_review"]),
    ("primary_devices", "primary_devices", []),
]


def create_tables(conn: sqlite3.Connection):
    cur = conn.cursor()
    for table_name, _, extra_ts_cols in TABLE_DEFS:
        cols = [
            "id TEXT PRIMARY KEY",
            "data BLOB NOT NULL",
            "meta_created_at REAL",
            "meta_updated_at REAL",
        ]
        for col in extra_ts_cols:
            cols.append(f"{col} REAL")
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(cols)})"
        cur.execute(sql)

    cur.execute(
        "CREATE TABLE IF NOT EXISTS sync_state ("
        "  filename TEXT PRIMARY KEY,"
        "  synced_at REAL NOT NULL"
        ")"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _ts_with_offset_to_unix(tso) -> float | None:
    """Convert a TimestampWithOffset to a unix timestamp float."""
    if tso is None or not tso.HasField("UTC_timestamp"):
        return None
    ts = tso.UTC_timestamp
    if ts.seconds == 0 and ts.nanos == 0:
        return None
    return ts.seconds + ts.nanos / 1e9


def _ts_to_unix(ts) -> float | None:
    """Convert a google.protobuf.Timestamp to a unix timestamp float."""
    if ts is None:
        return None
    if ts.seconds == 0 and ts.nanos == 0:
        return None
    return ts.seconds + ts.nanos / 1e9


def _meta_timestamps(msg) -> tuple[str | None, float | None, float | None, bool]:
    """Return (id, created_at, updated_at, is_deleted) from a message with .meta."""
    meta = msg.meta
    msg_id = meta.ID if meta.ID else None
    created = _ts_with_offset_to_unix(meta.created_at)
    updated = _ts_with_offset_to_unix(meta.updated_at)
    is_deleted = meta.HasField("deleted_at") and (
        meta.deleted_at.HasField("UTC_timestamp")
        and (meta.deleted_at.UTC_timestamp.seconds != 0 or meta.deleted_at.UTC_timestamp.nanos != 0)
    )
    return msg_id, created, updated, is_deleted


# ---------------------------------------------------------------------------
# Per-entity extra timestamp extractors
# ---------------------------------------------------------------------------

def _event_extra(msg) -> list[float | None]:
    start = _ts_with_offset_to_unix(msg.start_at) if msg.HasField("start_at") else None
    end = _ts_with_offset_to_unix(msg.end_at) if msg.HasField("end_at") else None
    return [start, end]


def _media_extra(msg) -> list[float | None]:
    created = _ts_to_unix(msg.created_timestamp) if msg.HasField("created_timestamp") else None
    modified = _ts_to_unix(msg.modified_timestamp) if msg.HasField("modified_timestamp") else None
    return [created, modified]


def _tally_extra(msg) -> list[float | None]:
    return [_ts_with_offset_to_unix(msg.time) if msg.HasField("time") else None]


def _weather_extra(msg) -> list[float | None]:
    return [_ts_with_offset_to_unix(msg.observed_at) if msg.HasField("observed_at") else None]


def _calendar_event_extra(msg) -> list[float | None]:
    start = _ts_to_unix(msg.start_at) if msg.HasField("start_at") else None
    end = _ts_to_unix(msg.end_at) if msg.HasField("end_at") else None
    created = _ts_to_unix(msg.created_at) if msg.HasField("created_at") else None
    last_mod = _ts_to_unix(msg.last_modified_at) if msg.HasField("last_modified_at") else None
    return [start, end, created, last_mod]


def _settings_extra(msg) -> list[float | None]:
    return [_ts_to_unix(msg.asked_for_review) if msg.HasField("asked_for_review") else None]


EXTRA_EXTRACTORS = {
    "events": _event_extra,
    "media": _media_extra,
    "tallies": _tally_extra,
    "weather": _weather_extra,
    "calendar_events": _calendar_event_extra,
    "settings_values": _settings_extra,
}


# ---------------------------------------------------------------------------
# Upsert / delete logic
# ---------------------------------------------------------------------------

def _process_entity_list(conn: sqlite3.Connection, table_name: str, field_name: str,
                         extra_ts_cols: list[str], directory: timeatlas_pb2.FullDirectory):
    messages = getattr(directory, field_name)
    if not messages:
        return

    extractor = EXTRA_EXTRACTORS.get(table_name)
    cur = conn.cursor()

    for msg in messages:
        msg_id, created, updated, is_deleted = _meta_timestamps(msg)
        if msg_id is None:
            continue

        if is_deleted:
            cur.execute(f"DELETE FROM {table_name} WHERE id = ?", (msg_id,))
            continue

        data = msg.SerializeToString()
        extra_vals = extractor(msg) if extractor else []

        # Build UPSERT
        col_names = ["id", "data", "meta_created_at", "meta_updated_at"] + extra_ts_cols
        placeholders = ", ".join(["?"] * len(col_names))
        update_set = ", ".join(f"{c} = excluded.{c}" for c in col_names if c != "id")
        sql = (
            f"INSERT INTO {table_name} ({', '.join(col_names)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_set}"
        )
        cur.execute(sql, [msg_id, data, created, updated] + extra_vals)


def process_full_directory(conn: sqlite3.Connection, directory: timeatlas_pb2.FullDirectory):
    for table_name, field_name, extra_ts_cols in TABLE_DEFS:
        _process_entity_list(conn, table_name, field_name, extra_ts_cols, directory)


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_pb_data(raw_bytes: bytes) -> timeatlas_pb2.FullDirectory:
    directory = timeatlas_pb2.FullDirectory()
    directory.ParseFromString(raw_bytes)
    return directory


def process_file(conn: sqlite3.Connection, filepath: str):
    """Process a single .pb or .zip file."""
    if filepath.endswith(".zip"):
        with open(filepath, "rb") as f:
            zip_data = io.BytesIO(f.read())
        with zipfile.ZipFile(zip_data) as zf:
            for name in sorted(zf.namelist()):
                if name.endswith(".pb"):
                    pb_bytes = zf.read(name)
                    directory = load_pb_data(pb_bytes)
                    process_full_directory(conn, directory)
    elif filepath.endswith(".pb"):
        with open(filepath, "rb") as f:
            pb_bytes = f.read()
        directory = load_pb_data(pb_bytes)
        process_full_directory(conn, directory)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def get_synced_filenames(conn: sqlite3.Connection) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT filename FROM sync_state")
    return {row[0] for row in cur.fetchall()}


def get_data_files(icloud_dir: str) -> list[str]:
    """Return data files sorted by name (timestamp order), excluding 'ip' prefixed files."""
    files = []
    for entry in os.listdir(icloud_dir):
        # Skip non-data files
        if entry.startswith("ip"):
            continue
        if not (entry.endswith(".pb") or entry.endswith(".zip")):
            continue
        files.append(entry)
    return sorted(files)


def sync(conn: sqlite3.Connection, icloud_dir: str = ICLOUD_DIR):
    """Sync new files from iCloud into the database."""
    synced = get_synced_filenames(conn)
    data_files = get_data_files(icloud_dir)
    new_files = [f for f in data_files if f not in synced]

    if not new_files:
        print("Already up to date.")
        return

    print(f"Syncing {len(new_files)} new file(s)...")
    for filename in new_files:
        filepath = os.path.join(icloud_dir, filename)
        print(f"  Processing {filename}...")
        try:
            process_file(conn, filepath)
            conn.execute(
                "INSERT INTO sync_state (filename, synced_at) VALUES (?, ?)",
                (filename, os.path.getmtime(filepath)),
            )
            conn.commit()
        except Exception as e:
            print(f"  ERROR processing {filename}: {e}")
            conn.rollback()
            raise

    print("Sync complete.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    sync(conn)

    # Print summary
    cur = conn.cursor()
    print("\n--- Database summary ---")
    for table_name, _, _ in TABLE_DEFS:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"  {table_name}: {count} rows")

    cur.execute("SELECT COUNT(*) FROM sync_state")
    print(f"  sync_state: {cur.fetchone()[0]} files synced")
    conn.close()


if __name__ == "__main__":
    main()
