#!/usr/bin/env python3
"""Print Time Atlas events for a date or a range of dates, grouped by date."""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas
import timeatlas_pb2


# Event types we iterate through. Sleep is handled separately (summarized only).
EVENT_TYPES_TO_SHOW = [
    "placevisit",
    "movement",
    "workout",
    "eventgroup",
    "trip",
    "nodataperiod",
]


# Short activity codes (from MoveActivity.activity) mapped to display names.
ACTIVITY_NAMES = {
    "wlk": "Walk",
    "run": "Run",
    "cyc": "Bicycle",
    "stu": "Stairs Up",
    "std": "Stairs Down",
    "sta": "Stationary",
    "bus": "Bus",
    "car": "Car",
    "mtc": "Motorcycle",
    "ski": "Cross-country Ski",
    "mtr": "Metro",
    "sub": "Subway",
    "trm": "Tram",
    "trn": "Train",
    "boa": "Boating",
    "sct": "Scooting",
    "trp": "Transport",
    "non": "None",
    "mcy": "Maybe Cycling",
    "ndt": "Undetermined",
    "air": "Airplane",
    "dhs": "Downhill Skiing",
    "sbd": "Snowboarding",
    "rol": "Rollerskating",
    "hoo": "Hoops",
    "row": "Rowing",
    "slb": "Sailing",
    "pdl": "Paddling",
    "aeb": "Assisted E-Bike",
    "swm": "Swimming",
    "pub": "Public Transport",
}


def _activity_name(code: str) -> str:
    return ACTIVITY_NAMES.get(code, code)


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M") if dt else "--:--"


def _duration_str(start, end) -> str:
    if not start or not end:
        return ""
    secs = int((end - start).total_seconds())
    if secs < 0:
        return ""
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def _fmt_hm(total_secs: int) -> str:
    h, rem = divmod(int(total_secs), 3600)
    m = rem // 60
    return f"{h}h{m:02d}m"


def _fmt_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters/1000:.2f} km"
    return f"{int(meters)} m"


def _print_notes(event_id: str, indent: str = "    "):
    """Print journal entries (notes) for an event, if any."""
    for je in timeatlas.getJournalEntriesForEvent(event_id):
        if not je.text:
            continue
        first = True
        for line in je.text.splitlines() or [""]:
            prefix = f"{indent}> " if first else f"{indent}  "
            print(f"{prefix}{line}")
            first = False


def _describe_event(evt) -> str:
    if evt.type == timeatlas_pb2.PLACEVISIT:
        pv = evt.place_visit
        name = pv.name or pv.secondary_name or "(unnamed)"
        loc = pv.city_or_county or pv.region or pv.country_code or ""
        return f"PLACEVISIT  {name}" + (f"  ({loc})" if loc else "")
    if evt.type == timeatlas_pb2.MOVEMENT:
        mv = evt.movement
        return f"MOVEMENT    {mv.name}".rstrip()
    if evt.type == timeatlas_pb2.WORKOUT:
        w = evt.workout
        label = w.activity_name or "workout"
        extras = []
        if w.distance_meters:
            extras.append(_fmt_distance(w.distance_meters))
        if w.kcal:
            extras.append(f"{w.kcal} kcal")
        tail = f"  ({', '.join(extras)})" if extras else ""
        return f"WORKOUT     {label}{tail}"
    if evt.type == timeatlas_pb2.EVENT_GROUP:
        g = evt.event_group
        return f"GROUP       {g.name or timeatlas_pb2.EventGroupType.Name(g.group_type)}"
    if evt.type == timeatlas_pb2.TRIP:
        return f"TRIP        {evt.trip.name or '(unnamed)'}"
    if evt.type == timeatlas_pb2.NO_DATA_PERIOD:
        reason = evt.no_data_period.reason or ""
        return f"NO DATA     {reason}".rstrip()
    return timeatlas_pb2.EventType.Name(evt.type)


def _print_movement_details(evt, indent: str = "    "):
    """For movement events, show per-MoveActivity distances and non-zero steps."""
    mv = evt.movement
    for a in mv.move_activities:
        if not a.activity:
            continue
        parts = [_activity_name(a.activity)]
        if a.distance_meters:
            parts.append(_fmt_distance(a.distance_meters))
        if a.steps:
            parts.append(f"{a.steps} steps")
        if a.duration_secs:
            parts.append(_fmt_hm(a.duration_secs))
        print(f"{indent}- {'  '.join(parts)}")


def _print_date(date_str, start, end, show_notes: bool, show_summary: bool):
    header = f"=== {date_str}"
    if start and end:
        header += f"  ({_fmt_time(start)} - {_fmt_time(end)}, tz {start.utcoffset()})"
    print(header)

    if not start or not end:
        print("  (no start/end time for this date)")
        print()
        return

    # Notes attached to the date event itself.
    if show_notes:
        date_evt = timeatlas.getDateEvent(date_str)
        if date_evt is not None:
            _print_notes(date_evt.meta.ID, indent="  ")

    any_events = False
    daily_distance_by_activity: dict[str, float] = defaultdict(float)
    daily_duration_by_activity: dict[str, int] = defaultdict(int)
    daily_steps_by_activity: dict[str, int] = defaultdict(int)

    for type_name in EVENT_TYPES_TO_SHOW:
        events = timeatlas.getEvents(type_name, start, end)
        if not events:
            continue
        any_events = True
        for evt in events:
            ev_start = (
                timeatlas._tso_to_datetime(evt.start_at)
                if evt.HasField("start_at")
                else None
            )
            ev_end = (
                timeatlas._tso_to_datetime(evt.end_at)
                if evt.HasField("end_at")
                else None
            )
            duration = _duration_str(ev_start, ev_end)
            dur_str = f" [{duration}]" if duration else ""
            print(
                f"  {_fmt_time(ev_start)}-{_fmt_time(ev_end)}{dur_str}  "
                f"{_describe_event(evt)}"
            )

            if evt.type == timeatlas_pb2.MOVEMENT:
                _print_movement_details(evt)
                for a in evt.movement.move_activities:
                    if not a.activity:
                        continue
                    if a.distance_meters:
                        daily_distance_by_activity[a.activity] += a.distance_meters
                    if a.duration_secs:
                        daily_duration_by_activity[a.activity] += a.duration_secs
                    if a.steps:
                        daily_steps_by_activity[a.activity] += a.steps

            if show_notes and evt.type == timeatlas_pb2.PLACEVISIT:
                _print_notes(evt.meta.ID)

    # Sleeps are summarized, not printed.
    sleeps = timeatlas.getEvents("sleep", start, end)
    total_sleep_secs = sum(s.sleep.asleep_secs for s in sleeps)

    if not any_events and not sleeps:
        print("  (no events)")

    if show_summary:
        summary_lines = []
        if total_sleep_secs:
            summary_lines.append(f"Sleep total: {_fmt_hm(total_sleep_secs)}")

        activity_codes = (
            set(daily_distance_by_activity)
            | set(daily_duration_by_activity)
            | set(daily_steps_by_activity)
        )
        total_distance = sum(daily_distance_by_activity.values())
        if activity_codes:
            summary_lines.append(f"Total distance: {_fmt_distance(total_distance)}")
            for act in sorted(activity_codes):
                parts = []
                if daily_distance_by_activity.get(act):
                    parts.append(_fmt_distance(daily_distance_by_activity[act]))
                if daily_duration_by_activity.get(act):
                    parts.append(_fmt_hm(daily_duration_by_activity[act]))
                if daily_steps_by_activity.get(act):
                    parts.append(f"{daily_steps_by_activity[act]} steps")
                summary_lines.append(f"  {_activity_name(act)}: {', '.join(parts)}")

        if summary_lines:
            print("  --")
            for line in summary_lines:
                print(f"  {line}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Print events for a date or a range of dates (YYYY-mm-dd)."
    )
    parser.add_argument("from_date", help="Start date YYYY-mm-dd (or single date)")
    parser.add_argument(
        "to_date",
        nargs="?",
        help="End date YYYY-mm-dd (inclusive). Omit to print a single date.",
    )
    parser.add_argument(
        "--show-notes",
        action="store_true",
        help="Also print journal entries (notes) attached to date events and place visits.",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Hide the end-of-day totals (sleep, distance per activity).",
    )
    args = parser.parse_args()

    to_date = args.to_date or args.from_date

    dates = timeatlas.getDates(args.from_date, to_date)
    if not dates:
        print(f"No date events found between {args.from_date} and {to_date}.")
        return

    for date_str, start, end in dates:
        _print_date(
            date_str,
            start,
            end,
            show_notes=args.show_notes,
            show_summary=not args.no_summary,
        )


if __name__ == "__main__":
    main()
