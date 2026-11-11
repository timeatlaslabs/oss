#!/usr/bin/env python3
"""Clear the bento selections of a date event.

Loads the date event for the given date, clears its bento_selections field
and writes the event back as an update file so the Time Atlas app picks up
the change.

Usage:
    python tools/clear_bento.py YYYY-mm-dd
"""

import argparse
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas


def main():
    parser = argparse.ArgumentParser(
        description="Clear the bento selections of a date event"
    )
    parser.add_argument("date", help="Date in YYYY-mm-dd format")
    args = parser.parse_args()

    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"Error: invalid date format '{args.date}', expected YYYY-mm-dd.", file=sys.stderr)
        sys.exit(1)

    event = timeatlas.getDateEvent(args.date)
    if event is None:
        print(f"Error: no date event found for {args.date}. "
              "Try running 'python sync.py' first.", file=sys.stderr)
        sys.exit(1)

    if not event.date_event.HasField("bento_selections"):
        print(f"Date event for {args.date} has no bento selections, nothing to do.")
        return

    event.appID = "oss"
    event.date_event.ClearField("bento_selections")

    print(event)

    path = timeatlas.updateObjects([event])
    print(f"Cleared bento selections for {args.date}. Update written to {path}")


if __name__ == "__main__":
    main()
