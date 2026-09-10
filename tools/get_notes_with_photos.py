#!/usr/bin/env python3
# Requires: pip install osxphotos
"""Show journal notes for a date and open any attached photos in Preview."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas
import timeatlas_pb2
from photos import getPhotoForMedia


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M") if dt else "--:--"


def _event_label(evt: timeatlas_pb2.Event) -> str:
    if evt.type == timeatlas_pb2.PLACEVISIT:
        return evt.place_visit.name or evt.place_visit.secondary_name or "(place)"
    if evt.type == timeatlas_pb2.DATE:
        return "Day note"
    return timeatlas_pb2.EventType.Name(evt.type)


def main():
    date = input("Date (YYYY-MM-DD): ").strip()
    if not date:
        print("No date entered.")
        return

    date_range = timeatlas.getDateDateRange(date)
    if not date_range:
        print(f"No date event found for {date}.")
        return

    start, end = date_range

    # Collect all event IDs we want notes for: the date event + place visits
    event_entries: list[tuple[str, timeatlas_pb2.Event]] = []

    date_evt = timeatlas.getDateEvent(date)
    if date_evt is not None:
        event_entries.append(("day", date_evt))

    for evt in timeatlas.getEvents("placevisit", start, end):
        event_entries.append(("place", evt))

    if not event_entries:
        print("No events found for this date.")
        return

    photos_to_open: list[str] = []

    for _, evt in event_entries:
        notes = timeatlas.getJournalEntriesForEvent(evt.meta.ID)
        if not notes:
            continue

        ev_start = (
            timeatlas._tso_to_datetime(evt.start_at)
            if evt.HasField("start_at")
            else None
        )
        print(f"--- {_fmt_time(ev_start)}  {_event_label(evt)} ---")

        for je in notes:
            if je.text:
                print(je.text)
                print()

            media_list = timeatlas.getMediaForJournalEntry(je.meta.ID)
            for media in media_list:
                photo = getPhotoForMedia(media)
                if photo and photo.path:
                    photos_to_open.append(photo.path)
                    print(f"  [photo: {media.filename}]")
                elif media.HasField("filename"):
                    print(f"  [photo not found in library: {media.filename}]")

    if photos_to_open:
        print(f"\nOpening {len(photos_to_open)} photo(s) in Preview...")
        subprocess.run(["open", "-a", "Preview"] + photos_to_open)
    else:
        print("\nNo photos to open.")


if __name__ == "__main__":
    main()
