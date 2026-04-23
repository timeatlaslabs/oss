#!/usr/bin/env python3
"""
Time Atlas database setup and sync script.

Creates an SQLite database from Time Atlas iCloud protobuf files.
Each event type gets its own table (events_place_visits, events_movements, etc.)
with columns for all scalar sub-message fields.
"""

import os
import sqlite3
import zipfile
import io

import timeatlas
import timeatlas_pb2


ICLOUD_DIR = timeatlas.getIcloudDir()
DB_PATH = timeatlas.getDatabasePath()


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _tso_to_unix(tso) -> float | None:
    """Convert TimestampWithOffset to unix timestamp."""
    if tso is None or not tso.HasField("UTC_timestamp"):
        return None
    ts = tso.UTC_timestamp
    if ts.seconds == 0 and ts.nanos == 0:
        return None
    return ts.seconds + ts.nanos / 1e9


def _ts_to_unix(ts) -> float | None:
    """Convert google.protobuf.Timestamp to unix timestamp."""
    if ts is None:
        return None
    if ts.seconds == 0 and ts.nanos == 0:
        return None
    return ts.seconds + ts.nanos / 1e9


def _meta_info(msg):
    """Return (id, created_at, updated_at, is_deleted) from a message with .meta."""
    meta = msg.meta
    msg_id = meta.ID or None
    created = _tso_to_unix(meta.created_at)
    updated = _tso_to_unix(meta.updated_at)
    is_deleted = (
        meta.HasField("deleted_at")
        and meta.deleted_at.HasField("UTC_timestamp")
        and (meta.deleted_at.UTC_timestamp.seconds != 0
             or meta.deleted_at.UTC_timestamp.nanos != 0)
    )
    return msg_id, created, updated, is_deleted


# ---------------------------------------------------------------------------
# Field extraction helper
# ---------------------------------------------------------------------------

def _extract_scalar(msg, field_name: str, extract_type: str):
    """Extract a scalar field value from a protobuf message."""
    try:
        if not msg.HasField(field_name):
            return None
    except ValueError:
        pass  # Non-optional field, always present

    val = getattr(msg, field_name)

    if extract_type == "text":
        return val if val else None
    elif extract_type == "bool":
        return int(val)
    elif extract_type == "int":
        return val
    elif extract_type == "real":
        return val
    elif extract_type.startswith("enum:"):
        enum_name = extract_type.split(":")[1]
        enum_desc = getattr(timeatlas_pb2, enum_name).DESCRIPTOR
        return enum_desc.values_by_number[val].name
    return val


# ---------------------------------------------------------------------------
# Schema definitions — non-event tables
# ---------------------------------------------------------------------------
# Each entry: {table, field, ts_cols, ts_extractor, scalar_cols}
# scalar_cols: list of (sql_col_name, proto_field_name, sql_type, extract_type)
#   extract_type: "text", "bool", "int", "real", "enum:EnumName"

NON_EVENT_TABLE_DEFS = [
    {
        "table": "journal_entries",
        "field": "journal_entries",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("event_id", "eventID", "TEXT", "text"),
            ("source", "source", "TEXT", "text"),
            ("text", "text", "TEXT", "text"),
            ("reply_id", "replyID", "TEXT", "text"),
            ("is_dictated", "is_dictated", "INTEGER", "bool"),
            ("is_ai_rewritten", "is_ai_rewritten", "INTEGER", "bool"),
        ],
    },
    {
        "table": "known_places",
        "field": "known_places",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("name", "name", "TEXT", "text"),
            ("city_or_county", "city_or_county", "TEXT", "text"),
            ("country_code", "country_code", "TEXT", "text"),
            ("address", "address", "TEXT", "text"),
            ("region", "region", "TEXT", "text"),
            ("external_id", "externalID", "TEXT", "text"),
        ],
    },
    {
        "table": "media",
        "field": "media",
        "ts_cols": ["created_timestamp", "modified_timestamp"],
        "ts_extractor": lambda m: [
            _ts_to_unix(m.created_timestamp) if m.HasField("created_timestamp") else None,
            _ts_to_unix(m.modified_timestamp) if m.HasField("modified_timestamp") else None,
        ],
        "scalar_cols": [
            ("format", "format", "TEXT", "text"),
            ("path", "path", "TEXT", "text"),
            ("public_url", "public_url", "TEXT", "text"),
            ("apple_cloud_identifier", "apple_cloud_identifier", "TEXT", "text"),
            ("filename", "filename", "TEXT", "text"),
            ("imported", "imported", "INTEGER", "bool"),
            ("ai_summary", "ai_summary", "TEXT", "text"),
            ("app_asset_name", "app_asset_name", "TEXT", "text"),
            ("legacy_path", "legacy_path", "TEXT", "text"),
        ],
    },
    {
        "table": "pat_messages",
        "field": "pat_messages",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("recipient", "recipient", "TEXT", "enum:Recipient"),
            ("content_plain", "content_plain", "TEXT", "text"),
            ("transport", "transport", "TEXT", "enum:Transport"),
            ("in_reply_to", "in_reply_to", "TEXT", "text"),
            ("subject", "subject", "TEXT", "text"),
            ("external_id", "externalID", "TEXT", "text"),
        ],
    },
    {
        "table": "tallies",
        "field": "tallies",
        "ts_cols": ["time"],
        "ts_extractor": lambda m: [
            _tso_to_unix(m.time) if m.HasField("time") else None,
        ],
        "scalar_cols": [
            ("event_id", "eventID", "TEXT", "text"),
            ("journal_entry_id", "journalEntryID", "TEXT", "text"),
            ("source", "source", "TEXT", "text"),
            ("name", "name", "TEXT", "text"),
            ("unit", "unit", "TEXT", "text"),
            ("value", "value", "REAL", "real"),
            ("who", "who", "TEXT", "text"),
            ("category", "category", "TEXT", "text"),
            ("emoji", "emoji", "TEXT", "text"),
        ],
    },
    {
        "table": "ai_profiles",
        "field": "ai_profiles",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("purpose", "purpose", "TEXT", "enum:AIProfilePurpose"),
            ("version", "version", "INTEGER", "int"),
            ("prompt", "prompt", "TEXT", "text"),
            ("computed_input", "computed_input", "TEXT", "text"),
            ("model", "model", "TEXT", "text"),
            ("profile_text", "profile_text", "TEXT", "text"),
        ],
    },
    {
        "table": "embeddings",
        "field": "embeddings",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("version", "version", "TEXT", "text"),
            ("model", "model", "TEXT", "text"),
            ("embedding_type", "type", "TEXT", "enum:EmbeddingType"),
            ("source_id", "source_id", "TEXT", "text"),
        ],
    },
    {
        "table": "patterns",
        "field": "patterns",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("pattern_type", "type", "TEXT", "enum:PatternType"),
        ],
    },
    {
        "table": "chat_learnings",
        "field": "chat_learnings",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("learning", "learning", "TEXT", "text"),
        ],
    },
    {
        "table": "weather",
        "field": "weather",
        "ts_cols": ["observed_at"],
        "ts_extractor": lambda m: [
            _tso_to_unix(m.observed_at) if m.HasField("observed_at") else None,
        ],
        "scalar_cols": [
            ("condition_description", "condition_description", "TEXT", "text"),
            ("symbol_name", "symbol_name", "TEXT", "text"),
            ("temperature_celsius", "temperature_celsius", "REAL", "real"),
            ("apparent_temperature_celsius", "apparent_temperature_celsius", "REAL", "real"),
            ("humidity", "humidity", "REAL", "real"),
            ("pressure_millibars", "pressure_millibars", "REAL", "real"),
            ("dew_point_celsius", "dew_point_celsius", "REAL", "real"),
            ("cloud_cover", "cloud_cover", "REAL", "real"),
            ("visibility_meters", "visibility_meters", "REAL", "real"),
            ("wind_speed_meters_per_sec", "wind_speed_meters_per_sec", "REAL", "real"),
            ("wind_direction_degrees", "wind_direction_degrees", "REAL", "real"),
            ("uv_index", "uv_index", "INTEGER", "int"),
            ("is_daylight", "is_daylight", "INTEGER", "bool"),
        ],
    },
    {
        "table": "calendar_events",
        "field": "calendar_events",
        "ts_cols": ["start_at", "end_at", "created_at", "last_modified_at"],
        "ts_extractor": lambda m: [
            _ts_to_unix(m.start_at) if m.HasField("start_at") else None,
            _ts_to_unix(m.end_at) if m.HasField("end_at") else None,
            _ts_to_unix(m.created_at) if m.HasField("created_at") else None,
            _ts_to_unix(m.last_modified_at) if m.HasField("last_modified_at") else None,
        ],
        "scalar_cols": [
            ("uid", "uid", "TEXT", "text"),
            ("summary", "summary", "TEXT", "text"),
            ("is_all_day", "is_all_day", "INTEGER", "bool"),
            ("location", "location", "TEXT", "text"),
            ("description", "description", "TEXT", "text"),
            ("timezone", "timezone", "TEXT", "text"),
        ],
    },
    {
        "table": "settings_values",
        "field": "settings_values",
        "ts_cols": ["asked_for_review"],
        "ts_extractor": lambda m: [
            _ts_to_unix(m.asked_for_review) if m.HasField("asked_for_review") else None,
        ],
        "scalar_cols": [
            ("daily_email", "daily_email", "INTEGER", "bool"),
            ("disable_ai", "disableAI", "INTEGER", "bool"),
            ("timeline_most_recent_first", "timeline_most_recent_first", "INTEGER", "bool"),
            ("disable_scooting_detection", "disable_scooting_detection", "INTEGER", "bool"),
            ("hide_timeline_details", "hide_timeline_details", "INTEGER", "bool"),
            ("store_image_previews", "store_image_previews", "INTEGER", "bool"),
            ("enable_daily_notification", "enable_daily_notification", "INTEGER", "bool"),
            ("disable_pat_responses", "disable_pat_responses", "INTEGER", "bool"),
            ("disable_population_comparisons", "disable_population_comparisons", "INTEGER", "bool"),
            ("disable_automatic_log_inference", "disable_automatic_log_inference", "INTEGER", "bool"),
            ("use_tiles_for_trp", "use_tiles_for_trp", "INTEGER", "bool"),
            ("show_photos_on_timeline", "show_photos_on_timeline", "INTEGER", "bool"),
            ("show_media_metadata_overlay", "show_media_metadata_overlay", "INTEGER", "bool"),
            ("submit_to_apple_health", "submit_to_apple_health", "INTEGER", "bool"),
            ("deduplicate_week_photos", "deduplicate_week_photos", "INTEGER", "bool"),
            ("default_transport_method", "default_transport_method", "TEXT", "text"),
            ("day_end_offset_secs", "day_end_offset_secs", "INTEGER", "int"),
            ("disable_automatic_photo_days", "disable_automatic_photo_days", "INTEGER", "bool"),
            ("disable_automatic_photo_events", "disable_automatic_photo_events", "INTEGER", "bool"),
            ("personal_offer_code", "personal_offer_code", "TEXT", "text"),
            ("grandfathered_subscription", "grandfathered_subscription", "TEXT", "text"),
            ("disable_cycling_detection", "disable_cycling_detection", "INTEGER", "bool"),
        ],
    },
    {
        "table": "primary_devices",
        "field": "primary_devices",
        "ts_cols": [],
        "ts_extractor": None,
        "scalar_cols": [
            ("app_id", "app_id", "TEXT", "text"),
            ("user_action", "user_action", "INTEGER", "bool"),
        ],
    },
]


# ---------------------------------------------------------------------------
# Schema definitions — event tables
# ---------------------------------------------------------------------------

# Common columns shared by every events_* table
COMMON_EVENT_COLS = [
    ("id", "TEXT PRIMARY KEY"),
    ("data", "BLOB NOT NULL"),
    ("meta_created_at", "REAL"),
    ("meta_updated_at", "REAL"),
    ("start_at", "REAL"),
    ("end_at", "REAL"),
    ("event_type", "TEXT"),
    ("source", "TEXT"),
    ("app_id", "TEXT"),
    ("diagnostics_json", "TEXT"),
]

# Per-event-type definitions.
# Key = EventType enum int value.
# sub_field: attribute name on Event message for the sub-message (or None).
# cols: list of (sql_col_name, proto_field_name, sql_type, extract_type)
EVENT_TYPE_DEFS = {
    0: {  # ET_NOT_SPECIFIED
        "table": "events_unspecified",
        "sub_field": None,
        "cols": [],
    },
    1: {  # DATE
        "table": "events_dates",
        "sub_field": "date_event",
        "cols": [
            ("date", "date", "TEXT", "text"),
            ("favorite", "favorite", "INTEGER", "bool"),
            ("hide_summary", "hide_summary", "INTEGER", "bool"),
        ],
    },
    2: {  # PLACEVISIT
        "table": "events_place_visits",
        "sub_field": "place_visit",
        "cols": [
            ("name", "name", "TEXT", "text"),
            ("secondary_name", "secondary_name", "TEXT", "text"),
            ("requires_reverse_geo", "requires_reverse_geo", "INTEGER", "bool"),
            ("city_or_county", "city_or_county", "TEXT", "text"),
            ("country_code", "country_code", "TEXT", "text"),
            ("region", "region", "TEXT", "text"),
            ("known_place_id", "known_placeID", "TEXT", "text"),
            ("is_user_labeled", "is_user_labeled", "INTEGER", "bool"),
            ("is_user_corrected", "is_user_corrected", "INTEGER", "bool"),
        ],
    },
    3: {  # MOVEMENT
        "table": "events_movements",
        "sub_field": "movement",
        "cols": [
            ("name", "name", "TEXT", "text"),
            ("synthetic", "synthetic", "INTEGER", "bool"),
        ],
    },
    4: {  # NO_DATA_PERIOD
        "table": "events_no_data_periods",
        "sub_field": "no_data_period",
        "cols": [
            ("reason", "reason", "TEXT", "text"),
        ],
    },
    5: {  # WORKOUT
        "table": "events_workouts",
        "sub_field": "workout",
        "cols": [
            ("healthkit_activity_type", "healthkit_activity_type", "INTEGER", "int"),
            ("activity_name", "activity_name", "TEXT", "text"),
            ("duration_secs", "duration_secs", "INTEGER", "int"),
            ("workout_source", "source", "TEXT", "text"),
            ("moloc_activity", "moloc_activity", "TEXT", "text"),
            ("steps", "steps", "INTEGER", "int"),
            ("distance_meters", "distance_meters", "INTEGER", "int"),
            ("indoors", "indoors", "INTEGER", "bool"),
            ("kcal", "kcal", "INTEGER", "int"),
            ("healthkit_identifier", "healthkit_identifier", "TEXT", "text"),
            ("device_name", "device_name", "TEXT", "text"),
            ("device_manufacturer", "device_manufacturer", "TEXT", "text"),
            ("device_model", "device_model", "TEXT", "text"),
        ],
    },
    6: {  # SLEEP
        "table": "events_sleeps",
        "sub_field": "sleep",
        "cols": [
            ("asleep_secs", "asleep_secs", "INTEGER", "int"),
            ("sleep_type", "type", "TEXT", "enum:SleepType"),
            ("device_name", "device_name", "TEXT", "text"),
            ("device_manufacturer", "device_manufacturer", "TEXT", "text"),
            ("device_model", "device_model", "TEXT", "text"),
        ],
    },
    7: {  # EVENT_GROUP
        "table": "events_event_groups",
        "sub_field": "event_group",
        "cols": [
            ("name", "name", "TEXT", "text"),
            ("user_set_name", "user_set_name", "INTEGER", "bool"),
            ("group_type", "group_type", "TEXT", "enum:EventGroupType"),
        ],
    },
    8: {  # TRIP
        "table": "events_trips",
        "sub_field": "trip",
        "cols": [
            ("name", "name", "TEXT", "text"),
        ],
    },
}

ALL_EVENT_TABLES = [d["table"] for d in EVENT_TYPE_DEFS.values()]


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

def create_tables(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Non-event tables
    for tdef in NON_EVENT_TABLE_DEFS:
        col_defs = [
            "id TEXT PRIMARY KEY",
            "data BLOB NOT NULL",
            "meta_created_at REAL",
            "meta_updated_at REAL",
        ]
        for col in tdef["ts_cols"]:
            col_defs.append(f"{col} REAL")
        for col_name, _, sql_type, _ in tdef["scalar_cols"]:
            col_defs.append(f"{col_name} {sql_type}")
        cur.execute(f"CREATE TABLE IF NOT EXISTS {tdef['table']} ({', '.join(col_defs)})")

    # Event tables
    for evt_def in EVENT_TYPE_DEFS.values():
        table = evt_def["table"]
        col_defs = [f"{name} {typ}" for name, typ in COMMON_EVENT_COLS]
        for col_name, _, sql_type, _ in evt_def["cols"]:
            col_defs.append(f"{col_name} {sql_type}")
        cur.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(col_defs)})")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_start_at ON {table} (start_at)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_end_at ON {table} (end_at)")

    # Sync state
    cur.execute(
        "CREATE TABLE IF NOT EXISTS sync_state ("
        "  filename TEXT PRIMARY KEY,"
        "  synced_at REAL NOT NULL"
        ")"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Non-event entity processing
# ---------------------------------------------------------------------------

def _process_non_event_list(conn: sqlite3.Connection, tdef: dict,
                            directory: timeatlas_pb2.FullDirectory):
    messages = getattr(directory, tdef["field"])
    if not messages:
        return

    table_name = tdef["table"]
    ts_extractor = tdef["ts_extractor"]
    scalar_cols = tdef["scalar_cols"]
    cur = conn.cursor()

    for msg in messages:
        msg_id, created, updated, is_deleted = _meta_info(msg)
        if msg_id is None:
            continue

        if is_deleted:
            cur.execute(f"DELETE FROM {table_name} WHERE id = ?", (msg_id,))
            continue

        data = msg.SerializeToString()
        ts_vals = ts_extractor(msg) if ts_extractor else []
        scalar_vals = [_extract_scalar(msg, fn, et) for _, fn, _, et in scalar_cols]

        col_names = (
            ["id", "data", "meta_created_at", "meta_updated_at"]
            + tdef["ts_cols"]
            + [c[0] for c in scalar_cols]
        )
        all_vals = [msg_id, data, created, updated] + ts_vals + scalar_vals
        placeholders = ", ".join(["?"] * len(col_names))
        update_set = ", ".join(f"{c} = excluded.{c}" for c in col_names if c != "id")
        sql = (
            f"INSERT INTO {table_name} ({', '.join(col_names)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_set}"
        )
        cur.execute(sql, all_vals)


# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------

def _process_events(conn: sqlite3.Connection, directory: timeatlas_pb2.FullDirectory):
    if not directory.events:
        return

    cur = conn.cursor()

    for event in directory.events:
        msg_id, created, updated, is_deleted = _meta_info(event)
        if msg_id is None:
            continue

        evt_type_int = event.type
        evt_def = EVENT_TYPE_DEFS.get(evt_type_int, EVENT_TYPE_DEFS[0])
        table = evt_def["table"]

        # Delete from ALL event tables (handles type changes and deletions)
        for t in ALL_EVENT_TABLES:
            if t != table:
                cur.execute(f"DELETE FROM {t} WHERE id = ?", (msg_id,))

        if is_deleted:
            cur.execute(f"DELETE FROM {table} WHERE id = ?", (msg_id,))
            continue

        # Common values
        start = _tso_to_unix(event.start_at) if event.HasField("start_at") else None
        end = _tso_to_unix(event.end_at) if event.HasField("end_at") else None
        event_type_name = timeatlas_pb2.EventType.Name(evt_type_int)
        source = event.source or None
        app_id = event.appID if event.HasField("appID") else None
        diag = event.diagnostics_json if event.HasField("diagnostics_json") else None
        data = event.SerializeToString()

        common_col_names = ["id", "data", "meta_created_at", "meta_updated_at",
                            "start_at", "end_at", "event_type", "source", "app_id",
                            "diagnostics_json"]
        common_vals = [msg_id, data, created, updated, start, end,
                       event_type_name, source, app_id, diag]

        # Sub-message scalar values
        extra_col_names = []
        extra_vals = []
        if evt_def["sub_field"]:
            sub_msg = getattr(event, evt_def["sub_field"])
            for col_name, field_name, _, extract_type in evt_def["cols"]:
                extra_col_names.append(col_name)
                extra_vals.append(_extract_scalar(sub_msg, field_name, extract_type))

        all_col_names = common_col_names + extra_col_names
        all_vals = common_vals + extra_vals
        placeholders = ", ".join(["?"] * len(all_col_names))
        update_set = ", ".join(f"{c} = excluded.{c}" for c in all_col_names if c != "id")
        sql = (
            f"INSERT INTO {table} ({', '.join(all_col_names)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_set}"
        )
        cur.execute(sql, all_vals)


# ---------------------------------------------------------------------------
# Full directory processing
# ---------------------------------------------------------------------------

def process_full_directory(conn: sqlite3.Connection, directory: timeatlas_pb2.FullDirectory):
    _process_events(conn, directory)
    for tdef in NON_EVENT_TABLE_DEFS:
        _process_non_event_list(conn, tdef, directory)


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
                    directory = load_pb_data(zf.read(name))
                    process_full_directory(conn, directory)
    elif filepath.endswith(".pb"):
        with open(filepath, "rb") as f:
            directory = load_pb_data(f.read())
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
    for tdef in NON_EVENT_TABLE_DEFS:
        cur.execute(f"SELECT COUNT(*) FROM {tdef['table']}")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"  {tdef['table']}: {count}")

    print("  --- events ---")
    for evt_def in EVENT_TYPE_DEFS.values():
        table = evt_def["table"]
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"  {table}: {count}")

    cur.execute("SELECT COUNT(*) FROM sync_state")
    print(f"  sync_state: {cur.fetchone()[0]} files synced")
    conn.close()


if __name__ == "__main__":
    main()
