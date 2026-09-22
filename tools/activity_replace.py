#!/usr/bin/env python3
"""Interactively replace one activity type with another across a date range.

Loads all movement events in the range, finds MoveActivities matching the
source type, and (after confirmation) writes the changed events back as an
update file so the Time Atlas app picks up the changes.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import timeatlas
import timeatlas_pb2


def _parse_date(value: str) -> str:
    """Validate that value is a YYYY-mm-dd date string. Returns it or exits."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        print(f"Error: invalid date format '{value}', expected YYYY-mm-dd.", file=sys.stderr)
        sys.exit(1)
    return value


def _pick_activity(prompt: str) -> str:
    """Show a numbered list of activities and let the user pick one."""
    codes = sorted(timeatlas.ACTIVITY_NAMES.keys())
    print(prompt)
    for i, code in enumerate(codes, 1):
        print(f"  {i:2d}. {code} ({timeatlas.ACTIVITY_NAMES[code]})")
    while True:
        choice = input("Enter number: ").strip()
        try:
            idx = int(choice)
            if 1 <= idx <= len(codes):
                return codes[idx - 1]
        except ValueError:
            pass
        print("Invalid choice, try again.")


def main():
    # 1. Ask for date range
    print("Enter date range (YYYY-mm-dd).")
    from_date = _parse_date(input("From date: ").strip())
    to_date_input = input("  To date: ").strip()
    to_date = _parse_date(to_date_input) if to_date_input else from_date

    date_range = timeatlas.getDates(from_date, to_date)
    if not date_range:
        print(f"No date events found in range {from_date} .. {to_date}. "
              "Try running 'python sync.py' first.", file=sys.stderr)
        sys.exit(1)

    # 2. Pick source and target activity
    from_activity = _pick_activity("\nChange FROM activity:")
    to_activity = _pick_activity("\nChange TO activity:")

    if from_activity == to_activity:
        print("Source and target are the same. Nothing to do.")
        return

    print(f"\nReplacing '{from_activity}' ({timeatlas.ACTIVITY_NAMES[from_activity]}) "
          f"-> '{to_activity}' ({timeatlas.ACTIVITY_NAMES[to_activity]})")
    print(f"Date range: {from_date} .. {to_date}\n")

    # 3. Load movement events and find matches
    overall_start = date_range[0][1]
    overall_end = date_range[-1][2]
    if overall_start is None or overall_end is None:
        print("Error: date range has missing start/end times.", file=sys.stderr)
        sys.exit(1)

    movements = timeatlas.getEvents("movement", overall_start, overall_end)

    changed_events = []
    total_activities_changed = 0
    total_distance_changed = 0

    for evt in movements:
        if not evt.HasField("movement"):
            continue
        event_changed = False
        for ma in evt.movement.move_activities:
            if ma.activity == from_activity:
                ma.activity = to_activity
                total_activities_changed += 1
                total_distance_changed += ma.distance_meters
                event_changed = True
        if event_changed:
            changed_events.append(evt)

    if not changed_events:
        print(f"No '{from_activity}' activities found in the date range.")
        return

    # 4. Confirm
    dist_km = total_distance_changed / 1000
    print(f"Found {total_activities_changed} activit{'y' if total_activities_changed == 1 else 'ies'} "
          f"to change across {len(changed_events)} movement event(s).")
    print(f"Total distance affected: {dist_km:.1f} km")
    confirm = input("\nProceed? [y/N] ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return

    # 5. Write update
    filepath = timeatlas.updateObjects(changed_events)
    print(f"\nUpdate written to: {filepath}")
    print("Run 'python sync.py' to apply the changes to the local database.")


if __name__ == "__main__":
    main()
