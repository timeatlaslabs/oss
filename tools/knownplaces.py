#!/usr/bin/env python3
"""Print known places matching a name and list their place-visit events."""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas
import timeatlas_pb2


def _fmt_dt(tso) -> str:
    dt = timeatlas._tso_to_datetime(tso)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "---"


def _fetch_place_visits(known_place_id: str) -> list[timeatlas_pb2.Event]:
    with sqlite3.connect(timeatlas.getDatabasePath()) as conn:
        cur = conn.execute(
            "SELECT data FROM events_place_visits "
            "WHERE known_place_id = ? "
            "ORDER BY start_at ASC",
            (known_place_id,),
        )
        rows = cur.fetchall()
    out = []
    for (data,) in rows:
        evt = timeatlas_pb2.Event()
        evt.ParseFromString(data)
        out.append(evt)
    return out


def _print_notes(event_id: str, indent: str = "        "):
    for je in timeatlas.getJournalEntriesForEvent(event_id):
        if not je.text:
            continue
        first = True
        for line in je.text.splitlines() or [""]:
            prefix = f"{indent}> " if first else f"{indent}  "
            print(f"{prefix}{line}")
            first = False


def main():
    parser = argparse.ArgumentParser(
        description="Find known places by name and list their place-visit events."
    )
    parser.add_argument("name", help="Name of the known place")
    parser.add_argument(
        "--show-notes",
        action="store_true",
        help="Also print journal entries attached to each place-visit event.",
    )
    args = parser.parse_args()

    places = timeatlas.getKnownPlace(name=args.name)
    if not places:
        print(f"No known places with name '{args.name}'.")
        return

    for kp in places:
        print(f"=== {kp.name} (id: {kp.meta.ID})")
        if kp.address:
            print(f"    Address: {kp.address}")
        loc_line = " / ".join(
            filter(None, [kp.city_or_county, kp.region, kp.country_code])
        )
        if loc_line:
            print(f"    Location: {loc_line}")
        if kp.HasField("location"):
            print(f"    Coords: {kp.location.lat:.5f}, {kp.location.lon:.5f}")

        visits = _fetch_place_visits(kp.meta.ID)
        print(f"    {len(visits)} place visit(s):")
        for evt in visits:
            start = _fmt_dt(evt.start_at) if evt.HasField("start_at") else "---"
            end = _fmt_dt(evt.end_at) if evt.HasField("end_at") else "---"
            print(f"      {start}  →  {end}")
            if args.show_notes:
                _print_notes(evt.meta.ID)
        print()


if __name__ == "__main__":
    main()
