#!/usr/bin/env python3
"""Insert a tally (log entry) into Time Atlas.

Usage:
    python tools/insert_log.py <name> <value> <unit> [--who WHO] [--date YYYY-mm-dd]

Examples:
    python tools/insert_log.py coffee 2 cups
    python tools/insert_log.py coffee 1 cups --who self --date 2025-01-15
    python tools/insert_log.py pushups 30 reps
"""

import argparse
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas
import timeatlas_pb2


def main():
    parser = argparse.ArgumentParser(
        description="Insert a tally (log entry) into Time Atlas"
    )
    parser.add_argument("name", help="Tally name (must be lowercase)")
    parser.add_argument("value", type=float, help="Numeric value")
    parser.add_argument("unit", help="Unit of measurement (must be lowercase)")
    parser.add_argument("--category", "-c", default="", help="Category for the tally (optional)")
    parser.add_argument("--who", default="self", help="Who the tally is for (default: self)")
    parser.add_argument(
        "--date", "-d",
        default=None,
        help="Date in YYYY-mm-dd format (default: today)",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")

    # Look up the date event to get the event ID
    date_event = timeatlas.getDateEvent(date_str)
    if date_event is None:
        print(f"Error: no date event found for {date_str}. Try running 'python sync.py' first.", file=sys.stderr)
        sys.exit(1)

    event_id = date_event.meta.ID
    if not event_id:
        print(f"Error: date event for {date_str} has no ID", file=sys.stderr)
        sys.exit(1)

    # Build the tally
    tally = timeatlas_pb2.Tally()
    tally.eventID = event_id
    tally.name = args.name
    tally.unit = args.unit
    tally.value = args.value
    tally.who = args.who
    if args.category:
        tally.category = args.category

    # Set the time to now with local offset
    now = datetime.now(timezone.utc)
    local_now = datetime.now().astimezone()
    offset_secs = int(local_now.utcoffset().total_seconds())
    tally.time.UTC_timestamp.seconds = int(now.timestamp())
    tally.time.UTC_timestamp.nanos = int((now.timestamp() % 1) * 1e9)
    tally.time.UTC_offset_seconds = offset_secs

    try:
        filepath = timeatlas.insertTallies([tally])
    except timeatlas.TallyValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Tally inserted: {args.name} = {args.value} {args.unit} (who: {args.who})")
    print(f"  Date: {date_str} (event {event_id})")
    print(f"  Written to: {filepath}")


if __name__ == "__main__":
    main()
