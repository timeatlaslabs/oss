#!/usr/bin/env python3
"""Export Time Atlas place visits and movement trajectories as GeoJSON.

Each place visit becomes a Point feature, and each movement activity becomes a
LineString feature. Output goes to stdout unless -o is given.
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import timeatlas
import timeatlas_pb2


_ACTIVITY_COLORS_PATH = os.path.join(_REPO_ROOT, "data", "activity_colors.json")
_FALLBACK_ACTIVITY_CODE = "trp"


def _load_activity_colors() -> dict[str, str]:
    with open(_ACTIVITY_COLORS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


ACTIVITY_COLORS = _load_activity_colors()

# Short activity codes mapped to full display names (mirrors date_query.py).
ACTIVITY_NAMES = {
    "wlk": "walk",
    "run": "run",
    "cyc": "bicycle",
    "stu": "stairs up",
    "std": "stairs down",
    "sta": "stationary",
    "bus": "bus",
    "car": "car",
    "mtc": "motorcycle",
    "ski": "cross-country ski",
    "mtr": "metro",
    "sub": "subway",
    "trm": "tram",
    "trn": "train",
    "boa": "boating",
    "sct": "scooting",
    "trp": "transport",
    "non": "none",
    "mcy": "maybe cycling",
    "ndt": "undetermined",
    "air": "airplane",
    "dhs": "downhill skiing",
    "sbd": "snowboarding",
    "rol": "rollerskating",
    "hoo": "hoops",
    "row": "rowing",
    "slb": "sailing",
    "pdl": "paddling",
    "aeb": "assisted e-bike",
    "swm": "swimming",
    "pub": "public transport",
}

# Reverse map: lowercase full name -> short code
_FULL_NAME_TO_CODE = {v: k for k, v in ACTIVITY_NAMES.items()}


def _resolve_activity_filter(value: str) -> str:
    """Return the short activity code for *value* (short code or full name)."""
    low = value.lower()
    # Direct short code match
    if low in ACTIVITY_NAMES:
        return low
    # Full name match
    if low in _FULL_NAME_TO_CODE:
        return _FULL_NAME_TO_CODE[low]
    # Substring / partial match (e.g. "cycling" matches "maybe cycling" / "bicycle")
    for full, code in _FULL_NAME_TO_CODE.items():
        if low in full or full in low:
            return code
    # Fall through – return as-is so filtering still works if the proto has it
    return low


def _stroke_for(activity_code: str) -> str | None:
    if activity_code and activity_code in ACTIVITY_COLORS:
        return ACTIVITY_COLORS[activity_code]
    return ACTIVITY_COLORS.get(_FALLBACK_ACTIVITY_CODE)


def _iso(tso) -> str | None:
    dt = timeatlas._tso_to_datetime(tso)
    return dt.isoformat() if dt else None


def _resolve_range(from_date: str, to_date: str):
    """Return (start_dt, end_dt) spanning the requested date range."""
    dates = timeatlas.getDates(from_date, to_date)
    if not dates:
        return None, None
    start = next((s for _, s, _ in dates if s is not None), None)
    end = next((e for _, _, e in reversed(dates) if e is not None), None)
    return start, end


def _place_visit_feature(evt) -> dict | None:
    pv = evt.place_visit
    if not pv.HasField("location"):
        return None
    loc = pv.location
    props = {
        "type": "placevisit",
        "name": pv.name or pv.secondary_name or None,
    }
    start_iso = _iso(evt.start_at) if evt.HasField("start_at") else None
    if start_iso:
        props["start"] = start_iso
    end_iso = _iso(evt.end_at) if evt.HasField("end_at") else None
    if end_iso:
        props["end"] = end_iso
    if evt.meta.ID:
        props["event_id"] = evt.meta.ID
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [loc.lon, loc.lat]},
        "properties": props,
    }


def _movement_features(evt, activity_code: str | None = None) -> list[dict]:
    features = []
    event_start = _iso(evt.start_at) if evt.HasField("start_at") else None
    for a in evt.movement.move_activities:
        if len(a.trajectory) < 2:
            continue
        if activity_code and a.activity != activity_code:
            continue
        coords = [[p.lon, p.lat] for p in a.trajectory]
        start_iso = _iso(a.start_at) if a.HasField("start_at") else event_start
        props = {
            "type": "movement",
            "activity": a.activity or None,
        }
        stroke = _stroke_for(a.activity)
        if stroke:
            props["stroke"] = stroke
        if start_iso:
            props["start"] = start_iso
        if a.distance_meters:
            props["distance_meters"] = a.distance_meters
        if a.duration_secs:
            props["duration_secs"] = a.duration_secs
        if evt.meta.ID:
            props["event_id"] = evt.meta.ID
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": props,
            }
        )
    return features


def build_geojson(from_date: str, to_date: str, activity_filter: str | None = None) -> dict:
    start, end = _resolve_range(from_date, to_date)
    if start is None or end is None:
        return {"type": "FeatureCollection", "features": []}

    activity_code = _resolve_activity_filter(activity_filter) if activity_filter else None

    features = []
    # When filtering by activity, do not include place visits.
    if not activity_code:
        for evt in timeatlas.getEvents("placevisit", start, end):
            f = _place_visit_feature(evt)
            if f is not None:
                features.append(f)
    for evt in timeatlas.getEvents("movement", start, end):
        features.extend(_movement_features(evt, activity_code))

    return {"type": "FeatureCollection", "features": features}


def main():
    parser = argparse.ArgumentParser(
        description="Export place visits and movement trajectories in GeoJSON."
    )
    parser.add_argument("from_date", help="Start date YYYY-mm-dd (or single date)")
    parser.add_argument(
        "to_date",
        nargs="?",
        help="End date YYYY-mm-dd (inclusive). Omit to export a single date.",
    )
    parser.add_argument(
        "-o", "--output", help="Write GeoJSON to this file instead of stdout."
    )
    parser.add_argument(
        "--activity",
        help="Filter movements by activity type (short code like 'ski' or full name like 'cycling'). Place visits are excluded when filtering.",
    )
    args = parser.parse_args()

    to_date = args.to_date or args.from_date
    geojson = build_geojson(args.from_date, to_date, activity_filter=args.activity)
    text = json.dumps(geojson, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(
            f"Wrote {len(geojson['features'])} feature(s) to {args.output}",
            file=sys.stderr,
        )
    else:
        print(text)


if __name__ == "__main__":
    main()
